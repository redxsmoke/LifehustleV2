import asyncio
import json
import discord
from discord.ext import commands, tasks

from db.connection import get_pool
from police.daily_report import select_daily_crimes
from police.views_daily_report import DailyCrimeReportView


class ClueScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.test_cycle_index = 0
        print("[ClueScheduler] Initializing clue scheduler...")
        self.clue_loop.start()

    # ------------------------------------------------------------
    # FIND MAIN CHANNEL
    # ------------------------------------------------------------
    async def get_main_channel(self, guild):
        if not hasattr(self.bot, "police_channels"):
            self.bot.police_channels = {}

        if guild.id in self.bot.police_channels:
            return self.bot.police_channels[guild.id]

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                self.bot.police_channels[guild.id] = channel.id
                return channel.id

        return None

    # ------------------------------------------------------------
    # TEST LOOP
    # ------------------------------------------------------------
    @tasks.loop(seconds=45)
    async def clue_loop(self):
        stages = ["midnight", "clue1", "clue2", "clue3"]
        stage = stages[self.test_cycle_index]

        print(f"[ClueScheduler] Running stage: {stage}")
        await self.run_stage(stage)

        self.test_cycle_index = (self.test_cycle_index + 1) % 4

    @clue_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(1)

    # ------------------------------------------------------------
    # RUN STAGE
    # ------------------------------------------------------------
    async def run_stage(self, stage):
        pool = get_pool()

        async with pool.acquire() as conn:
            for guild in self.bot.guilds:
                scheduler = self.bot.get_cog("DailyCrimeScheduler")
                if not scheduler:
                    continue

                # Midnight → select new crimes
                if stage == "midnight":
                    crimes = await select_daily_crimes(guild.id)
                    scheduler.daily_crimes[guild.id] = crimes
                    print(f"[ClueScheduler] Midnight crimes: {crimes}")
                else:
                    crimes = scheduler.daily_crimes.get(guild.id, [])
                    print(f"[ClueScheduler] Loaded {len(crimes)} crimes from memory")

                for crime in crimes:
                    crime_id = crime["crime_id"]
                    perp_id = crime.get("perpetrator_id")
                    crime_guild_id = crime["guild_id"]

                    # ------------------------------------------------------------
                    # FETCH PERP INFO
                    # ------------------------------------------------------------
                    username = "Unknown"
                    location_desc = crime.get("location", "an unknown location")
                    networth = 0

                    try:
                        perp = await conn.fetchrow("""
                            SELECT 
                                u.username,
                                (u.checking_account_balance + u.savings_account_balance) AS networth,
                                c.description AS location_description
                            FROM users u
                            LEFT JOIN cd_location c ON c.cd_location_id = u.cd_location_id
                            WHERE u.discord_id = $1
                        """, perp_id)

                        if perp:
                            username = perp["username"]
                            networth = perp["networth"] or 0
                            location_desc = perp["location_description"] or location_desc

                    except Exception as e:
                        print(f"[ClueScheduler] ERROR fetching perp info: {e}")

                    # ------------------------------------------------------------
                    # GENERATE CLUE
                    # ------------------------------------------------------------
                    next_clue = self.generate_clue(stage, username, location_desc, networth)
                    print(f"[ClueScheduler] Next clue for crime {crime_id}: {next_clue}")

                    if next_clue:

                        # ------------------------------------------------------------
                        # LIMIT TO 3 CLUES MAX
                        # ------------------------------------------------------------
                        existing = await conn.fetchval("""
                            SELECT COUNT(*)
                            FROM police_crime_tips
                            WHERE crime_id = $1
                              AND guild_id = $2
                              AND tip_type = 'auto_clue'
                        """, crime_id, crime_guild_id)

                        if existing >= 3:
                            print(f"[ClueScheduler] Crime {crime_id} already has 3 clues. Skipping.")
                            continue

                        # ------------------------------------------------------------
                        # INSERT CLUE
                        # ------------------------------------------------------------
                        try:
                            await conn.execute("""
                                INSERT INTO police_crime_tips (crime_id, guild_id, tip_type, tip_data)
                                VALUES ($1, $2, 'auto_clue', $3::jsonb)
                            """, crime_id, crime_guild_id, json.dumps({"clue": next_clue}))
                            print(f"[ClueScheduler] Inserted clue for crime {crime_id}")
                        except Exception as e:
                            print(f"[ClueScheduler] ERROR inserting clue: {e}")
                            continue

                # ------------------------------------------------------------
                # RELOAD CRIMES AFTER INSERTING CLUES
                # ------------------------------------------------------------
                crimes = await select_daily_crimes(guild.id)
                scheduler.daily_crimes[guild.id] = crimes  # IMPORTANT

                view = DailyCrimeReportView(crimes, guild.id)
                embed = await view.build_page()

                await self.broadcast_report(guild, embed, view, stage)

    # ------------------------------------------------------------
    # REAL CLUE GENERATOR
    # ------------------------------------------------------------
    def generate_clue(self, stage, username, location, networth):

        if stage == "clue1":
            return (
                f"A reputable source said the perp’s username contains "
                f"**{len(username)} characters**."
            )

        if stage == "clue2":
            return (
                f"A reputable source said they last saw the perp at "
                f"**{location}**."
            )

        if stage == "clue3":
            if networth < 500_000:
                return "A police informant said the perp’s net worth is between **$0 and $500,000**."
            elif networth < 2_000_000:
                return "A police informant said the perp’s net worth is between **$500,000 and $2,000,000**."
            elif networth < 10_000_000:
                return "A police informant said the perp’s net worth is between **$2,000,000 and $10,000,000**."
            else:
                return "A police informant said the perp’s net worth exceeds **$10,000,000**."

        return None

    # ------------------------------------------------------------
    # BROADCAST
    # ------------------------------------------------------------
    async def broadcast_report(self, guild, embed, view, stage):
        channel_id = await self.get_main_channel(guild)
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        labels = {
            "midnight": "🕛 **Daily Crime Report (Initial)**",
            "clue1": "🕗 **Clue #1 Added**",
            "clue2": "🕑 **Clue #2 Added**",
            "clue3": "🕕 **Clue #3 Added**"
        }

        await channel.send(
            content=f"🚨 {labels.get(stage)} 🚨",
            embed=embed,
            view=view
        )


async def setup(bot):
    await bot.add_cog(ClueScheduler(bot))
