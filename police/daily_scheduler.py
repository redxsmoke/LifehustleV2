import asyncio
import datetime
from discord.ext import commands, tasks

from police.daily_report import select_daily_crimes


class DailyCrimeScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_crimes = {}  # guild_id → list of crime rows
        # IMPORTANT: loop is NOT started here anymore


    # ------------------------------------------------------------
    # WAIT UNTIL MIDNIGHT (DISABLED FOR TESTING)
    # ------------------------------------------------------------
    async def wait_until_midnight(self):
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        midnight = datetime.datetime.combine(tomorrow.date(), datetime.time.min)

        seconds = (midnight - now).total_seconds()
        await asyncio.sleep(seconds)

    # ------------------------------------------------------------
    # DAILY TASK (RUNS EVERY 24 HOURS)
    # ------------------------------------------------------------
    @tasks.loop(hours=24)
    async def run_daily_report(self):
        await self.bot.wait_until_ready()

        # (Midnight wait disabled for testing)
        # await self.wait_until_midnight()

        for guild in self.bot.guilds:
            guild_id = guild.id

            # 1. Select crimes
            crimes = await select_daily_crimes(guild_id)

            # 2. Store them for the UI to use later
            self.daily_crimes[guild_id] = crimes

            print(f"[Daily Report] Selected {len(crimes)} crimes for guild {guild_id}")

    @run_daily_report.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    scheduler = DailyCrimeScheduler(bot)
    await bot.add_cog(scheduler)

    # START LOOP HERE — AFTER BOT IS LOADED
    scheduler.run_daily_report.start()
