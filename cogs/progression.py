import time
import discord
from discord.ext import commands

from db.connection import get_pool
from db.users import upsert_user


BASE_XP = 500
BASE_MONEY = 10000
COOLDOWN = 86400  # 24 hours


class Progression(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="level", description="Check your XP and level")
    async def level(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:
            await upsert_user(conn, interaction.user.id, str(interaction.user))

            user = await conn.fetchrow(
                """
                SELECT xp, level
                FROM users
                WHERE discord_id = $1
                """,
                interaction.user.id
            )

        if not user:
            return await interaction.response.send_message("User not found.")

        roast = [
            "You’re basically a tutorial NPC at this point.",
            "Not bad… but also not impressive.",
            "I’ve seen bots with more XP than you.",
            "Grinding… or just existing? Hard to tell.",
            "Respectable. For a human."
        ]

        embed = discord.Embed(
            title=f"📊 {interaction.user.name}'s Stats",
            description=roast[hash(interaction.user.id) % len(roast)],
            color=discord.Color.blurple()
        )

        embed.add_field(name="⭐ XP", value=str(user["xp"]), inline=True)
        embed.add_field(name="📈 Level", value=str(user["level"]), inline=True)

        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="daily", description="Claim your daily XP and money reward")
    async def daily(self, interaction: discord.Interaction):
        pool = get_pool()
        now = int(time.time())

        async with pool.acquire() as conn:
            await upsert_user(conn, interaction.user.id, str(interaction.user))

            user = await conn.fetchrow(
                """
                SELECT xp, checking_account_balance, daily_last_claim, daily_streak
                FROM users
                WHERE discord_id = $1
                """,
                interaction.user.id
            )

            if not user:
                return await interaction.response.send_message("User not found.")

            xp = user["xp"] or 0
            balance = user["checking_account_balance"] or 0
            last_claim = user["daily_last_claim"] or 0
            streak = user["daily_streak"] or 0

            # cooldown check
            if now - last_claim < COOLDOWN:
                remaining = COOLDOWN - (now - last_claim)
                hours = remaining // 3600
                minutes = (remaining % 3600) // 60

                embed = discord.Embed(
                    title="⏳ Daily Already Claimed",
                    description=f"Come back in **{hours}h {minutes}m**",
                    color=discord.Color.red()
                )

                return await interaction.response.send_message(embed=embed, ephemeral=True)

            # streak logic
            if last_claim and now - last_claim <= COOLDOWN * 2:
                streak += 1
            else:
                streak = 1

            multiplier = 1 + (streak * 0.1)

            reward_xp = int(BASE_XP * multiplier)
            reward_money = int(BASE_MONEY * multiplier)

            new_xp = xp + reward_xp
            new_balance = balance + reward_money

            await conn.execute(
                """
                UPDATE users
                SET xp = $1,
                    checking_account_balance = $2,
                    daily_last_claim = $3,
                    daily_streak = $4
                WHERE discord_id = $5
                """,
                new_xp,
                new_balance,
                now,
                streak,
                interaction.user.id
            )

        embed = discord.Embed(
            title="🎉 Daily Claimed",
            description="You showed up. That’s suspiciously consistent.",
            color=discord.Color.green()
        )

        embed.add_field(name="🔥 Streak", value=str(streak), inline=True)
        embed.add_field(name="⭐ XP", value=f"+{reward_xp}", inline=True)
        embed.add_field(name="💰 Money", value=f"+${reward_money:,}", inline=False)

        if streak >= 5:
            embed.add_field(
                name="⚠️ Warning",
                value="You are dangerously close to becoming consistent.",
                inline=False
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Progression(bot))