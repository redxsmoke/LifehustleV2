import random
import discord
from discord.ext import commands, tasks
from db.connection import get_pool
import asyncio
from datetime import datetime, timedelta
import pytz
import traceback

WHITE = "⚪"
RED = "🔴"
MONEY = "💸"

TEST_MODE = True

BASE_JACKPOT = 100_000_000 * 100
LOTTO_COST = 25000 * 100
FOUR_MATCH_PRIZE = 25_000_000 * 100
FIVE_MATCH_PRIZE = 50_000_000 * 100

EST = pytz.timezone("America/New_York")

def log(msg):
    print(f"[POWERBALLZ][ERROR] {msg}")

def fmt(n: int) -> str:
    return f"{n:02d}"

def fmt_m_short(pennies: int) -> str:
    dollars = pennies / 100
    millions = dollars / 1_000_000
    if millions.is_integer():
        return f"{int(millions)}m"
    return f"{millions:.1f}m"

class LotteryDraw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        try:
            if TEST_MODE:
                self.test_draw.change_interval(minutes=3)
            else:
                self.test_draw.change_interval(minutes=10)

            self.test_draw.start()
        except Exception as e:
            log(f"Failed to start loop: {e}")
            traceback.print_exc()

    @tasks.loop(minutes=10)
    async def test_draw(self):
        asyncio.create_task(self.run_lottery_draw())

    @test_draw.before_loop
    async def before_test_draw(self):
        await self.bot.wait_until_ready()

    async def run_lottery_draw(self):
        try:
            now_est = datetime.now(EST).replace(tzinfo=None)

            # Determine next draw date
            if TEST_MODE:
                next_draw_date = now_est.date() + timedelta(days=1)
            else:
                weekday = now_est.weekday()
                days_until_tuesday = (1 - weekday) % 7
                next_draw_date = (now_est + timedelta(days=days_until_tuesday)).date()

            pool = get_pool()

            # Skip draw unless correct time
            if not TEST_MODE:
                if not (now_est.weekday() == 1 and now_est.hour == 20 and now_est.minute == 0):
                    return

            # ⭐ RUN STORED PROCEDURE ⭐
            try:
                async with pool.acquire() as conn:
                    await conn.execute("CALL run_lottery_draw();")
            except Exception as e:
                log(f"Stored procedure failed: {e}")
                traceback.print_exc()
                return

            # ⭐ FETCH CURRENT DRAW RESULTS ⭐
            try:
                async with pool.acquire() as conn:
                    current_row = await conn.fetchrow(
                        """
                        SELECT draw_id, draw_date,
                               num1, num2, num3, num4, num5, powerball,
                               jackpot,
                               four_match_winners,
                               five_match_winners,
                               jackpot_winners,
                               next_jackpot
                        FROM lottery_results
                        WHERE ran_status = 'ran'
                        ORDER BY draw_date DESC
                        LIMIT 1
                        """
                    )

                    if not current_row:
                        log("ERROR: No current draw row found after procedure.")
                        return

                    winning_nums = [
                        current_row["num1"],
                        current_row["num2"],
                        current_row["num3"],
                        current_row["num4"],
                        current_row["num5"],
                    ]
                    powerball = current_row["powerball"]

                    jackpot_for_this_draw = current_row["jackpot"]

                    four_match_winners = current_row["four_match_winners"] or 0
                    five_match_winners = current_row["five_match_winners"] or 0
                    jackpot_winners = current_row["jackpot_winners"] or 0

                    next_jackpot = current_row["next_jackpot"]

            except Exception as e:
                log(f"Failed to fetch current draw results: {e}")
                traceback.print_exc()
                return

            # ⭐ PREPARE VALUES FOR EMBED ⭐
            winning_sorted = sorted(winning_nums)
            revealed = winning_sorted

            # ⭐ SEND INITIAL DRAW MESSAGE ⭐
            channel = getattr(self.bot, "last_channel", None)
            if channel is None:
                log("ERROR: last_channel is None")
                return

            try:
                embed = discord.Embed(
                    title=f"{MONEY} PowerBallz Weekly Draw {MONEY}",
                    description="The numbers are being drawn...",
                    color=discord.Color.gold()
                )

                embed.add_field(name="Drawn Numbers", value="`Drawing now...`", inline=False)
                embed.add_field(name="Winning Numbers", value="`Waiting...`", inline=False)
                embed.add_field(
                    name="Jackpot (This Draw)",
                    value=f"**{fmt_m_short(jackpot_for_this_draw)}**",
                    inline=False
                )

                message = await channel.send(embed=embed)

            except Exception as e:
                log(f"Failed to send initial message: {e}")
                traceback.print_exc()
                return

            # ⭐ ANIMATE NUMBER REVEAL ⭐
            revealed = []
            for num in winning_sorted:
                try:
                    revealed.append(num)

                    embed = discord.Embed(
                        title=f"{MONEY} PowerBallz Weekly Draw {MONEY}",
                        description="Numbers are being revealed...",
                        color=discord.Color.gold()
                    )

                    draw_display = "   ".join([f"{WHITE} `{fmt(n)}`" for n in revealed])
                    draw_display += f"   {RED} `??`"

                    embed.add_field(name="Drawn Numbers", value=draw_display, inline=False)
                    embed.add_field(name="Winning Numbers", value="`Waiting...`", inline=False)
                    embed.add_field(
                        name="Jackpot (This Draw)",
                        value=f"**{fmt_m_short(jackpot_for_this_draw)}**",
                        inline=False
                    )

                    await message.edit(embed=embed)

                except Exception as e:
                    log(f"Failed to update message: {e}")
                    traceback.print_exc()

                await asyncio.sleep(3)

            # ⭐ FINAL RESULTS EMBED ⭐
            try:
                embed = discord.Embed(
                    title=f"{MONEY} PowerBallz Weekly Draw Results {MONEY}",
                    description="Here are tonight's winning numbers!\n\u200b",
                    color=discord.Color.green()
                )

                # Drawn numbers (animated)
                draw_display = " ".join([f"{WHITE} `{fmt(n)}`" for n in revealed])
                draw_display += f" {RED} `{fmt(powerball)}`"

                # Winning numbers (sorted)
                winning_display = " ".join([f"{WHITE} `{fmt(n)}`" for n in winning_sorted])
                winning_display += f" {RED} `{fmt(powerball)}`"

                embed.add_field(
                    name="Drawn Numbers",
                    value=draw_display,
                    inline=False
                )

                embed.add_field(
                    name="Winning Numbers",
                    value=winning_display + "\n\u200b",
                    inline=False
                )

                embed.add_field(
                    name="4 Number Match Winners",
                    value=f"{four_match_winners:,}",
                    inline=False
                )

                embed.add_field(
                    name="5 Number Match Winners",
                    value=f"{five_match_winners:,}",
                    inline=False
                )

                embed.add_field(
                    name="Jackpot Winners",
                    value=f"{jackpot_winners:,}",
                    inline=False
                )

                embed.add_field(
                    name="Jackpot (This Draw)",
                    value=f"**{fmt_m_short(jackpot_for_this_draw)}**",
                    inline=False
                )

                if next_jackpot is not None:
                    embed.add_field(
                        name="New Jackpot (Next Draw)",
                        value=f"**{fmt_m_short(next_jackpot)}**",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="New Jackpot (Next Draw)",
                        value="`Unavailable`",
                        inline=False
                    )

                await message.edit(embed=embed)

            except Exception as e:
                log(f"Final update failed: {e}")
                traceback.print_exc()

        except Exception as e:
            log(f"Lottery draw FAILED: {e}")
            traceback.print_exc()

            pool = get_pool()
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE lottery_results
                        SET ran_status = 'failed'
                        WHERE draw_date = CURRENT_DATE
                        """
                    )
            except Exception as e2:
                log(f"Failed to mark draw as failed: {e2}")
                traceback.print_exc()

    async def cog_unload(self):
        self.test_draw.cancel()


async def setup(bot):
    await bot.add_cog(LotteryDraw(bot))
