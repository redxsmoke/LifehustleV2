import random
import discord
from discord.ext import commands, tasks
from db.connection import get_pool
import asyncio


class LotteryDraw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("[POWERBALLZ][OK] lottery_draw cog loaded")

        try:
            self.test_draw.start()
            print("[POWERBALLZ][OK] test_draw loop started")
        except Exception as e:
            print(f"[POWERBALLZ][ERROR] Failed to start loop: {e}")

    @tasks.loop(minutes=2)
    async def test_draw(self):
        print("[POWERBALLZ][OK] Loop tick — running draw...")
        await self.run_lottery_draw()

    @test_draw.before_loop
    async def before_test_draw(self):
        print("[POWERBALLZ][OK] Waiting for bot to be ready...")
        await self.bot.wait_until_ready()

    async def run_lottery_draw(self):
        print("[POWERBALLZ][OK] Generating numbers...")

        try:
            draw_order = random.sample(range(1, 70), 5)
            powerball = random.randint(1, 69)
            winning_sorted = sorted(draw_order)
        except Exception as e:
            print(f"[POWERBALLZ][ERROR] Number generation failed: {e}")
            return

        print(f"[POWERBALLZ][OK] Draw order: {draw_order} + PB {powerball}")
        print(f"[POWERBALLZ][OK] Winning sorted: {winning_sorted}")

        # Insert into DB
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO lottery_results (
                        draw_date, num1, num2, num3, num4, num5, powerball
                    )
                    VALUES (CURRENT_DATE, $1, $2, $3, $4, $5, $6)
                    """,
                    winning_sorted[0], winning_sorted[1], winning_sorted[2],
                    winning_sorted[3], winning_sorted[4], powerball
                )
            print("[POWERBALLZ][OK] DB insert successful")
        except Exception as e:
            print(f"[POWERBALLZ][ERROR] DB insert failed: {e}")

        # Determine channel — NO DEFAULT, NO FALLBACK
        channel = getattr(self.bot, "last_channel", None)

        if channel is None:
            print("[POWERBALLZ][ERROR] last_channel is None — cannot send draw message.")
            return

        # Initial embed
        try:
            embed = discord.Embed(
                title="🎱 **PowerBallz Draw Time!** 🎱",
                description="Tonight's numbers are being drawn...",
                color=discord.Color.gold()
            )
            embed.add_field(name="Drawn Numbers", value="(drawing...)", inline=False)
            embed.add_field(name="Winning Numbers", value="(waiting...)", inline=False)

            message = await channel.send(embed=embed)
            print("[POWERBALLZ][OK] Initial message sent")
        except Exception as e:
            print(f"[POWERBALLZ][ERROR] Failed to send initial message: {e}")
            return

        # Reveal numbers one by one
        revealed = []

        for num in draw_order:
            try:
                print(f"[POWERBALLZ][REVEAL] Showing number: {num}")
                revealed.append(num)

                embed = discord.Embed(
                    title="🎱 **PowerBallz Draw Time!** 🎱",
                    description="Tonight's numbers are being drawn...",
                    color=discord.Color.gold()
                )

                draw_display = ""
                for n in revealed:
                    draw_display += f"⚪ **{n}**   "
                draw_display += "\n\n🔴 **PowerBallz:** (drawing...)"

                embed.add_field(name="Drawn Numbers", value=draw_display, inline=False)
                embed.add_field(name="Winning Numbers", value="(waiting...)", inline=False)

                await message.edit(embed=embed)
                print("[POWERBALLZ][OK] Message updated")
            except Exception as e:
                print(f"[POWERBALLZ][ERROR] Failed to update message: {e}")

            await asyncio.sleep(3)

        # Final reveal
        try:
            embed = discord.Embed(
                title="🎱 **PowerBallz Draw Time!** 🎱",
                description="Tonight's numbers are being drawn...",
                color=discord.Color.gold()
            )

            draw_display = ""
            for n in revealed:
                draw_display += f"⚪ **{n}**   "
            draw_display += f"\n\n🔴 **PowerBallz:** {powerball}"

            winning_display = ""
            for n in winning_sorted:
                winning_display += f"⚪ **{n}**   "
            winning_display += f"\n\n🔴 **PowerBallz:** {powerball}"

            embed.add_field(name="Drawn Numbers", value=draw_display, inline=False)
            embed.add_field(name="Winning Numbers", value=winning_display, inline=False)

            await message.edit(embed=embed)
            print("[POWERBALLZ][OK] Final message updated")
        except Exception as e:
            print(f"[POWERBALLZ][ERROR] Final update failed: {e}")

    async def cog_unload(self):
        print("[POWERBALLZ][OK] Unloading cog — stopping loop")
        self.test_draw.cancel()


async def setup(bot):
    print("[POWERBALLZ][OK] Setting up lottery_draw cog...")
    await bot.add_cog(LotteryDraw(bot))
    print("[POWERBALLZ][OK] Setup complete")
