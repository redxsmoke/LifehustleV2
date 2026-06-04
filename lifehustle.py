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

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    if getattr(bot, "synced_once", False):
        return

    bot.synced_once = True

    print(f"Logged in as {bot.user}")

    try:
        guild = discord.Object(id=GUILD_ID)

        # FORCE TREE DISCOVERY AFTER COG LOAD
        await bot.tree.sync(guild=guild)

        print("Synced commands to guild")

    except Exception as e:
        print(f"Sync error: {e}")

async def load_cogs():
    try:
        await bot.load_extension("cogs.general")
        await bot.load_extension("cogs.economy")
        await bot.load_extension("cogs.progression")
        await bot.load_extension("cogs.gambling")

        print("All cogs loaded successfully")

    except Exception as e:
        print(f"Cog loading error: {e}")


async def main():
    async with bot:
        await init_db()
        await load_cogs()
        await bot.start(TOKEN)


asyncio.run(main())