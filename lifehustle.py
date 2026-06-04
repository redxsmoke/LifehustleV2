import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio

from db.connection import init_db

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.message_content = True


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()

        await self.load_extension("cogs.general")
        await self.load_extension("cogs.economy")
        await self.load_extension("cogs.progression")
        await self.load_extension("cogs.gambling")

        guild = discord.Object(id=GUILD_ID)

        # Keep your cleanup (safe)
        self.tree.clear_commands(guild=guild)

        # Sync commands
        await self.tree.sync()

        # REAL DEBUG OUTPUT (what actually exists)
        print("Commands currently loaded:")
        for cmd in self.tree.get_commands():
            print(f"- {cmd.name}")


bot = MyBot()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


async def main():
    await bot.start(TOKEN)


asyncio.run(main())