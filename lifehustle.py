import sys
print("🔥 RUNNING PYTHON FROM:", sys.executable)
import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio

from db.connection import init_db, get_pool
from db.users import upsert_user

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.all()


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # =========================
        # DB INIT
        # =========================
        await init_db()
        self.db = get_pool()

        # =========================
        # LOAD COGS
        # =========================
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.economy")
        await self.load_extension("cogs.progression")
        await self.load_extension("cogs.gambling")
        await self.load_extension("cogs.travel.travel")
        await self.load_extension("cogs.buyvehicle")
        await self.load_extension("cogs.sellvehicle")
        await self.load_extension("cogs.switchvehicle")
        await self.load_extension("cogs.lifecheck")
        await self.load_extension("cogs.myvehicles")
        await self.load_extension("cogs.occupations")
        await self.load_extension("cogs.crime_commands")
        await self.load_extension("cogs.shop.shop")
        


        # POLICE SYSTEM
        await self.load_extension("police.daily_scheduler")
        await self.load_extension("police.commands_daily_report")
        await bot.load_extension("police.clue_scheduler")

        # =========================
        # COMMAND SYNC
        # =========================
        guild = discord.Object(id=GUILD_ID)

        self.tree.clear_commands(guild=guild)
        await self.tree.sync(guild=guild)
        await self.tree.sync()

        print("Commands currently loaded:")
        for cmd in self.tree.get_commands():
            print(f"- {cmd.name}")

    # =========================================================
    # USER BOOTSTRAP (FIXED + RELIABLE)
    # =========================================================
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.user or interaction.user.bot:
            return

        pool = get_pool()

        async with pool.acquire() as conn:
            created = await upsert_user(
                conn,
                interaction.user.id,
                interaction.guild.id if interaction.guild else None,
                str(interaction.user)
            )

        interaction._user_created = created
        await self.process_application_commands(interaction)


bot = MyBot()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Sync slash commands
    await bot.tree.sync()
    print("Slash commands synced.")

    # Force scheduler to run immediately
    scheduler = bot.get_cog("DailyCrimeScheduler")
    if scheduler:
        print("Scheduler found, forcing first run...")
        await scheduler.run_daily_report()


async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing from environment variables")

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
