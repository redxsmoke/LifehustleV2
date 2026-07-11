import sys
print("RUNNING PYTHON FROM:", sys.executable)
import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import logging
from datetime import datetime

from db.connection import init_db, get_pool
from db.users import upsert_user

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.all()


# =========================================================
# LOTTERY PLACEHOLDER INITIALIZER (using lottery_results_id only)
# =========================================================
async def ensure_lottery_placeholder(pool):
    async with pool.acquire() as conn:

        # 1. Check for any open draw
        open_row = await conn.fetchrow(
            """
            SELECT lottery_results_id, draw_date, ran_status
            FROM lottery_results
            WHERE ran_status = 'not ran'
            LIMIT 1
            """
        )

        # 2. Check if today's draw already exists
        today_row = await conn.fetchrow(
            """
            SELECT lottery_results_id, draw_date, ran_status
            FROM lottery_results
            WHERE draw_date = CURRENT_DATE
            LIMIT 1
            """
        )

        # VALID CASES
        if open_row:
            print("[LOTTERY] Open 'not ran' draw already exists.")
            return

        if today_row:
            print("[LOTTERY] Today's draw already exists.")
            return

        # INSERT NEW PLACEHOLDER (PK lottery_results_id will be generated automatically)
        print("[LOTTERY] No valid draw found. Creating new placeholder...")

        await conn.execute(
            """
            INSERT INTO lottery_results (
                draw_date,
                ran_status
            )
            VALUES (CURRENT_DATE, 'not ran')
            """
        )

        print("[LOTTERY] Inserted new placeholder draw.")


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.last_channel = None

    async def setup_hook(self):
        await init_db()
        self.db = get_pool()

        # PLACEHOLDER FIRST
        await ensure_lottery_placeholder(self.db)

        # LOTTERY COGS
        await self.load_extension("cogs.lottery.lottery_draw")
        await self.load_extension("cogs.lottery.mylotterytickets")

        # OTHER COGS
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.economy")
        await self.load_extension("cogs.progression")
        await self.load_extension("cogs.gambling")
        await self.load_extension("cogs.travel.travel")
        await self.load_extension("cogs.buyvehicle")
        await self.load_extension("cogs.sellvehicle")
        await self.load_extension("cogs.switchvehicle")
        await self.load_extension("cogs.user_stats.mystats")
        await self.load_extension("cogs.lifecheck")
        await self.load_extension("cogs.myvehicles")
        await self.load_extension("cogs.occupations")
        await self.load_extension("cogs.crime_commands")
        await self.load_extension("cogs.shop.shop")
        await self.load_extension("cogs.deletemessages")
        await self.load_extension("users.views_civinfo")
        await self.load_extension("cogs.itemscommands.items_commands")

        # POLICE
        await self.load_extension("police.daily_scheduler")
        await self.load_extension("police.commands_daily_report")
        await self.load_extension("police.clue_scheduler")

        guild = discord.Object(id=GUILD_ID)
        self.tree.clear_commands(guild=guild)
        await self.tree.sync(guild=guild)
        await self.tree.sync()

        print("Commands currently loaded:")
        for cmd in self.tree.get_commands():
            print(f"- {cmd.name}")

    async def on_interaction(self, interaction: discord.Interaction):
        async def track_response_send(*args, **kwargs):
            msg = await original_send(*args, **kwargs)
            self.last_channel = msg.channel
            print(f"[BOT] last_channel updated (interaction): {msg.channel.id}")
            return msg

        if interaction.response.is_done() is False:
            original_send = interaction.response.send_message
            interaction.response.send_message = track_response_send

        original_followup = interaction.followup.send

        async def track_followup_send(*args, **kwargs):
            msg = await original_followup(*args, **kwargs)
            self.last_channel = msg.channel
            print(f"[BOT] last_channel updated (followup): {msg.channel.id}")
            return msg

        interaction.followup.send = track_followup_send

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

    async def on_message(self, message):
        if message.author.id == self.user.id:
            self.last_channel = message.channel
            print(f"[BOT] last_channel updated (message): {message.channel.id}")

        await self.process_commands(message)


bot = MyBot()


@bot.event
async def on_ready():
    try:
        print(f" bot.user = {bot.user}")

        for guild in bot.guilds:
            for channel in guild.text_channels:
                bot.last_channel = channel
                print(f"[BOT] last_channel initialized to: {channel.id}")
                break
            if bot.last_channel:
                break

        if bot.last_channel is None:
            print("[BOT][WARN] No text channels found in any guild!")

    except Exception as e:
        print("❌ ERROR INSIDE on_ready:", e)


async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing from environment variables")

    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
