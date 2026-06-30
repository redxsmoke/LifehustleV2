import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import logging

from db.connection import get_pool
from db.users import upsert_user
from cogs.xp_engine import add_xp

logger = logging.getLogger("LifeHustle.Progression")

BASE_XP = 500
BASE_MONEY = 10000
COOLDOWN = 86400  # 24 hours


class Progression(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =====================================================
    # 📊 LEVEL COMMAND
    # =====================================================
    @app_commands.command(name="level", description="Check your XP and level")
    async def level(self, interaction: discord.Interaction):
        try:
            pool = get_pool()
            guild_id = interaction.guild.id if interaction.guild else 0

            async with pool.acquire() as conn:
                await upsert_user(
                    conn,
                    interaction.user.id,
                    guild_id,
                    interaction.user.name
                )

                user = await conn.fetchrow(
                    """
                    SELECT xp, level
                    FROM users
                    WHERE discord_id = $1
                      AND guild_id = $2
                    """,
                    interaction.user.id,
                    guild_id
                )

                logger.debug(f"/level user row: {user}")

                if not user:
                    return await interaction.response.send_message(
                        "User not found.",
                        ephemeral=True
                    )

                xp = user["xp"] or 0
                level = user["level"] or 1

                current_row = await conn.fetchrow(
                    "SELECT xp_required FROM cd_levels WHERE level = $1",
                    level
                )

                next_row = await conn.fetchrow(
                    "SELECT xp_required FROM cd_levels WHERE level = $1",
                    level + 1
                )

            current_level_xp = current_row["xp_required"] if current_row else 0
            next_level_xp = next_row["xp_required"] if next_row else current_level_xp

            span = next_level_xp - current_level_xp
            gained = xp - current_level_xp

            progress = max(0, min(gained / span, 1))
            filled = int(progress * 20)
            bar = "█" * filled + "░" * (20 - filled)

            roast = [
                "You’re basically a tutorial NPC at this point.",
                "Not bad… but also not impressive.",
                "I’ve seen bots with more XP than you.",
                "Grinding… or just existing? Hard to tell.",
                "Respectable. For a human."
            ]

            color = (
                discord.Color.green() if level >= 50 else
                discord.Color.gold() if level >= 25 else
                discord.Color.blurple()
            )

            embed = discord.Embed(
                title=f"🏅 {interaction.user.name}",
                description=f"**Level {level}** • {roast[hash(interaction.user.id) % len(roast)]}",
                color=color
            )

            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(name="🔥 Current XP", value=f"**{xp:,}**", inline=True)
            embed.add_field(name="⬆️ Next Level", value=f"**{next_level_xp:,} XP**", inline=True)
            embed.add_field(name="📈 Progress", value=f"`{bar}`\n**{int(progress * 100)}%** complete", inline=False)
            embed.set_footer(text="Keep grinding. Or don’t. I’m not your boss.")

            await interaction.response.send_message(embed=embed)

        except Exception:
            logger.exception("Error in /level")
            await interaction.response.send_message(
                "An error occurred while processing /level.",
                ephemeral=True
            )

    # =====================================================
    # 🎁 DAILY COMMAND
    # =====================================================
    @app_commands.command(name="daily", description="Claim your daily XP and money reward")
    async def daily(self, interaction: discord.Interaction):
        try:
            pool = get_pool()

            # Make NOW naive (Postgres timestamp requires naive)
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            guild_id = interaction.guild.id if interaction.guild else 0

            async with pool.acquire() as conn:
                await upsert_user(
                    conn,
                    interaction.user.id,
                    guild_id,
                    interaction.user.name
                )

                user = await conn.fetchrow(
                    """
                    SELECT xp,
                           checking_account_balance,
                           daily_last_claim,
                           daily_streak
                    FROM users
                    WHERE discord_id = $1
                      AND guild_id = $2
                    """,
                    interaction.user.id,
                    guild_id
                )

                logger.debug(f"/daily user row: {user}")

                if not user:
                    return await interaction.response.send_message(
                        "User not found.",
                        ephemeral=True
                    )

                xp = user["xp"] or 0
                balance = user["checking_account_balance"] or 0
                last_claim = user["daily_last_claim"]
                streak = user["daily_streak"] or 0

                logger.debug(f"Raw last_claim type={type(last_claim)} value={last_claim}")

                # Convert string → datetime
                if isinstance(last_claim, str):
                    try:
                        last_claim = datetime.fromisoformat(last_claim)
                        logger.debug(f"Converted string → datetime: {last_claim}")
                    except Exception:
                        logger.exception("Failed to parse last_claim string")
                        last_claim = None

                # Convert aware → naive
                if isinstance(last_claim, datetime) and last_claim.tzinfo is not None:
                    last_claim = last_claim.replace(tzinfo=None)
                    logger.debug(f"Converted aware → naive: {last_claim}")

                # Cooldown math
                if last_claim is None:
                    elapsed = COOLDOWN + 1
                else:
                    try:
                        elapsed = (now - last_claim).total_seconds()
                    except Exception:
                        logger.exception("Cooldown math failed")
                        last_claim = None
                        elapsed = COOLDOWN + 1

                logger.debug(f"Cooldown elapsed={elapsed}")

                if elapsed < COOLDOWN:
                    remaining = COOLDOWN - elapsed
                    hours = int(remaining // 3600)
                    minutes = int((remaining % 3600) // 60)

                    embed = discord.Embed(
                        title="⏳ Daily Already Claimed",
                        description=f"Come back in **{hours}h {minutes}m**",
                        color=discord.Color.red()
                    )

                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                # Streak logic
                if last_claim and elapsed <= COOLDOWN * 2:
                    streak += 1
                else:
                    streak = 1

                logger.debug(f"New streak={streak}")

                multiplier = 1 + (streak * 0.1)
                reward_xp = int(BASE_XP * multiplier)
                reward_money = int(BASE_MONEY * multiplier)
                new_balance = balance + reward_money

                # XP Engine
                result = await add_xp(
                    conn,
                    interaction.user.id,
                    guild_id,
                    reward_xp,
                    xp
                )

                logger.debug(f"XP Engine result: {result}")

                # Update DB
                await conn.execute(
                    """
                    UPDATE users
                    SET checking_account_balance = $1,
                        daily_last_claim = $2,
                        daily_streak = $3
                    WHERE discord_id = $4
                      AND guild_id = $5
                    """,
                    new_balance,
                    now,
                    streak,
                    interaction.user.id,
                    guild_id
                )

            # Daily reward embed
            embed = discord.Embed(
                title="🎉 Daily Claimed",
                description="You showed up. That’s suspiciously consistent.",
                color=discord.Color.green()
            )

            embed.add_field(name="🔥 Streak", value=str(streak), inline=True)
            embed.add_field(name="⭐ XP", value=f"+{reward_xp}", inline=True)
            embed.add_field(name="💰 Money", value=f"+${reward_money:,}", inline=False)

            await interaction.response.send_message(embed=embed)

            # Level up embed
            if result.get("leveled_up") and result.get("levelup_embed"):
                await interaction.followup.send(embed=result["levelup_embed"], ephemeral=False)

        except Exception:
            logger.exception("Error in /daily")
            await interaction.response.send_message(
                "An error occurred while processing /daily.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Progression(bot))
