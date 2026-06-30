import asyncio
import json
import logging
import discord
from discord.ext import commands, tasks
from zoneinfo import ZoneInfo

from db.connection import get_pool
from police.daily_report import select_daily_crimes
from police.views_daily_report import DailyCrimeReportView

logger = logging.getLogger("ClueScheduler")
logger.setLevel(logging.DEBUG)


class ClueScheduler(commands.Cog):
    def __init__(self, bot, *, test_mode: bool = False):
        logger.warning("🔥 [ClueScheduler] __init__ CALLED")
        self.bot = bot
        self.test_mode = test_mode

        # Test mode rotates stages every tick
        self._test_index = 0
        self._test_stages = ["midnight", "clue1", "clue2", "clue3"]

        # Real mode flags
        self.ran_midnight = False
        self.ran_clue1 = False
        self.ran_clue2 = False
        self.ran_clue3 = False
        # ❗ loop is NOT started here anymore

    async def _run_real_stage(self, stage: str):
        await self.run_stage(stage)

    # ------------------------------------------------------------
    # START LOOP AFTER READY
    # ------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.clue_loop.is_running():
            self.clue_loop.start()

    async def get_main_channel(self, guild: discord.Guild) -> int | None:
        """
        Returns the channel where the bot should broadcast.
        Priority:
        1. The last channel the bot successfully sent a message in (cached)
        2. The first text channel the bot has permission to send in
        """

        # Create cache if missing
        if not hasattr(self.bot, "police_channels"):
            self.bot.police_channels = {}

        # If we already know the channel, return it
        if guild.id in self.bot.police_channels:
            return self.bot.police_channels[guild.id]

        # Otherwise: find the first channel the bot can speak in
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if perms.send_messages:
                self.bot.police_channels[guild.id] = channel.id
                return channel.id

        return None


    # ------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------
    @tasks.loop(seconds=30)
    async def clue_loop(self):
        now_utc = discord.utils.utcnow().replace(tzinfo=ZoneInfo("UTC"))
        est = now_utc.astimezone(ZoneInfo("America/New_York"))
        logger.warning(f"🔥 [ClueScheduler] now_utc={now_utc}, est={est}")

        # ------------------------------------------------------------
        # TEST MODE
        # ------------------------------------------------------------
        if self.test_mode:
            try:
                stage = self._test_stages[self._test_index % len(self._test_stages)]
                self._test_index += 1

                for guild in self.bot.guilds:
                    await self.update_stage_number(guild.id, stage)

                await self.run_stage(stage)
            except Exception as e:
                logger.exception(f"❌ [ClueScheduler] EXCEPTION IN TEST MODE BLOCK: {e}")
            return


        # ------------------------------------------------------------
        # REAL MODE
        # ------------------------------------------------------------
        if now_utc.second != 0:
            logger.debug(f"[ClueScheduler] Skipping real mode, now_utc.second={now_utc.second}")
            return

        current_minute = est.strftime("%H:%M")
        logger.warning(f"🔥 [ClueScheduler] REAL MODE current_minute={current_minute}")

        times = {
            "midnight": "00:00",
            "clue1": "10:00",
            "clue2": "15:00",
            "clue3": "19:00",
            "reset": "00:01",
        }

        logger.warning(
            f"midnight={self.ran_midnight}, "
            f"clue1={self.ran_clue1}, "
            f"clue2={self.ran_clue2}, "
            f"clue3={self.ran_clue3}"
        )

        if current_minute == times["midnight"] and not self.ran_midnight:
            await self._run_real_stage("midnight")
            self.ran_midnight = True

        elif current_minute == times["clue1"] and not self.ran_clue1:
            await self._run_real_stage("clue1")
            self.ran_clue1 = True

        elif current_minute == times["clue2"] and not self.ran_clue2:
            await self._run_real_stage("clue2")
            self.ran_clue2 = True

        elif current_minute == times["clue3"] and not self.ran_clue3:
            await self._run_real_stage("clue3")
            self.ran_clue3 = True

        if current_minute == times["reset"]:
            self.ran_midnight = False
            self.ran_clue1 = False
            self.ran_clue2 = False
            self.ran_clue3 = False


    # ------------------------------------------------------------
    # UPDATE STAGE NUMBER
    # ------------------------------------------------------------
    async def update_stage_number(self, guild_id: int, stage: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE police_broadcast_stage
                SET stage_number = $2
                WHERE guild_id = $1
                """,
                guild_id,
                stage,
            )

    # ------------------------------------------------------------
    # RUN STAGE
    # ------------------------------------------------------------
    async def run_stage(self, stage: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            guilds = list(self.bot.guilds)
            scheduler = self.bot.get_cog("DailyCrimeScheduler")
            if not scheduler:
                logger.warning("❌ [ClueScheduler] DailyCrimeScheduler NOT FOUND")
                return

            for guild in guilds:
                try:
                    if stage == "midnight":
                        crimes = await select_daily_crimes(guild.id)
                        scheduler.daily_crimes[guild.id] = crimes
                    else:
                        crimes = scheduler.daily_crimes.get(guild.id, [])

                    if not crimes:
                        logger.warning(f"⚠️ [ClueScheduler] No crimes for guild {guild.id}")
                        continue

                    for crime in crimes:
                        crime_id = crime.get("crime_id")
                        perp_id = crime.get("perpetrator_id")
                        crime_guild_id = crime.get("guild_id") or guild.id

                        username = "Unknown"
                        location_desc = crime.get("location", "an unknown location")
                        networth = 0

                        if perp_id:
                            perp = await conn.fetchrow("""
                                SELECT 
                                    u.username,
                                    (COALESCE(u.checking_account_balance,0) + COALESCE(u.savings_account_balance,0)) AS networth,
                                    c.description AS location_description
                                FROM users u
                                LEFT JOIN cd_location c ON c.cd_location_id = u.cd_location_id
                                WHERE u.discord_id = $1
                                  AND u.guild_id = $2
                            """, perp_id, crime_guild_id)

                            if perp:
                                username = perp.get("username") or username
                                networth = perp.get("networth") or 0
                                location_desc = perp.get("location_description") or location_desc

                        next_clue = self.generate_clue(stage, username, location_desc, networth)
                        if not next_clue:
                            continue

                        existing = await conn.fetchval("""
                            SELECT COUNT(*)
                            FROM police_crime_tips
                            WHERE crime_id = $1
                              AND guild_id = $2
                              AND tip_type = 'auto_clue'
                        """, crime_id, crime_guild_id)

                        if existing >= 3:
                            continue

                        await conn.execute("""
                            INSERT INTO police_crime_tips (crime_id, guild_id, tip_type, tip_data)
                            VALUES ($1, $2, 'auto_clue', $3::jsonb)
                        """, crime_id, crime_guild_id, json.dumps({"clue": next_clue}))

                    scheduler.daily_crimes[guild.id] = await select_daily_crimes(guild.id)

                    view = DailyCrimeReportView(scheduler.daily_crimes[guild.id], guild.id, stage)
                    embed = await view.build_page()

                    await self.broadcast_report(guild, embed, view, stage)

                except Exception as e:
                    logger.exception(f"❌ [ClueScheduler] ERROR in run_stage for guild {guild.id}: {e}")

    # ------------------------------------------------------------
    # CLUE GENERATOR (YOUR ORIGINAL RANGES)
    # ------------------------------------------------------------
    def generate_clue(self, stage, username, location, networth):
        username = username or "Unknown"
        location = location or "an unknown location"
        nw = networth or 0

        if stage == "clue1":
            return f"A reputable source said the perp’s username contains **{len(username)} characters**."

        if stage == "clue2":
            return f"A reputable source said they last saw the perp at **{location}**."

        if stage == "clue3":
            def fmt(amount):
                return f"${amount:,.0f}"

            ranges = [
                (0, 10_000, 0, 1_000_000),
                (10_000, 50_000, 1_000_000, 5_000_000),
                (50_000, 100_000, 5_000_000, 10_000_000),
                (100_000, 500_000, 10_000_000, 50_000_000),
                (500_000, 750_000, 50_000_000, 75_000_000),
                (750_000, 1_000_000, 75_000_000, 100_000_000),
                (1_000_000, 5_000_000, 100_000_000, 500_000_000),
                (5_000_000, 15_000_000, 500_000_000, 1_500_000_000),
                (15_000_000, 30_000_000, 1_500_000_000, 3_000_000_000),
                (30_000_000, 50_000_000, 3_000_000_000, 5_000_000_000),
                (50_000_000, 100_000_000, 5_000_000_000, 10_000_000_000),
                (100_000_000, 500_000_000, 10_000_000_000, 50_000_000_000),
                (500_000_000, 1_000_000_000, 50_000_000_000, 100_000_000_000),
            ]

            for low_d, high_d, low_p, high_p in ranges:
                if low_p <= nw < high_p:
                    return f"💰 A police informant said the perp’s net worth is between **{fmt(low_d)} and {fmt(high_d)}**."

            return "💰 A police informant said the perp’s net worth exceeds **$1,000,000,000**."

        return None

    # ------------------------------------------------------------
    # BROADCAST REPORT
    # ------------------------------------------------------------
    async def broadcast_report(self, guild: discord.Guild, embed: discord.Embed, view: DailyCrimeReportView, stage: str):
        try:
            channel_id = await self.get_main_channel(guild)
            if not channel_id:
                logger.warning(f"⚠️ [ClueScheduler] No main channel for guild {guild.id}")
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"⚠️ [ClueScheduler] Channel {channel_id} not found for guild {guild.id}")
                return

            labels = {
                "midnight": "🕛 **Daily Crime Report (Initial)**",
                "clue1": "🕙 **Clue #1 Added**",
                "clue2": "🕒 **Clue #2 Added**",
                "clue3": "🕖 **Clue #3 Added**"
            }

            await channel.send(
                content=f"🚨 {labels.get(stage, 'Crime Update')} 🚨",
                embed=embed,
                view=view
            )

        except Exception as e:
            logger.exception(f"❌ [ClueScheduler] ERROR in broadcast_report: {e}")


async def setup(bot):
    cog = ClueScheduler(bot, test_mode=False)
    await bot.add_cog(cog)
