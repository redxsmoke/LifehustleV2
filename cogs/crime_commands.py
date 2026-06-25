import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta

from db.connection import get_pool
from cogs.minigames.breakjob.command import start_vault_game

# Import GoFreeMe + Bribe DA
from cogs.gofreeme import GoFreeMeCreateModal, BribeDAButton

# ⭐ NEW: universal jail helper
from utils.jail_check import check_if_in_jail

# ============================================================
# ⭐ NEW: Per‑Guild Cooldown Storage
# ============================================================
rob_cooldowns = {}
COOLDOWN_DURATION = timedelta(minutes=30)


class CrimeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crime", description="Commit a crime to earn rewards or penalties.")
    async def crime(self, interaction: discord.Interaction):

        # ⭐ UNIVERSAL JAIL CHECK
        if await check_if_in_jail(interaction):
            return

        # ============================
        # 🟢 USER IS FREE → NORMAL CRIME MENU
        # ============================
        from cogs.crime_views import CrimeSelectionView  # avoid circular import

        view = CrimeSelectionView(interaction.user, self.bot)
        embed = discord.Embed(
            title="Choose a Crime",
            description="Select a crime to commit:",
            color=0x7289DA
        )

        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            print(f"[ERROR] Failed to send initial crime selection message: {e}")

    # ============================
    # ROB JOB LOGIC
    # ============================
    async def handle_rob_job(self, interaction: discord.Interaction):
        from cogs.crime_views import ConfirmRobberyView

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        # ============================================================
        # ⭐ PER-GUILD COOLDOWN CHECK
        # ============================================================
        if guild_id not in rob_cooldowns:
            rob_cooldowns[guild_id] = {}

        now = datetime.utcnow()
        next_allowed = rob_cooldowns[guild_id].get(user_id)

        if next_allowed and now < next_allowed:
            remaining = next_allowed - now
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)

            embed = discord.Embed(
                title="⏳ Cooldown Active",
                description=(
                    f"**Are you trying to get fired?**\n\n"
                    f"Try again in **{minutes}m {seconds}s**."
                ),
                color=0xF04747
            )

            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Set new cooldown
        rob_cooldowns[guild_id][user_id] = now + COOLDOWN_DURATION

        # ============================================================
        # CONFIRM ROBBERY
        # ============================================================
        confirm_view = ConfirmRobberyView(user_id=interaction.user.id)

        try:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔐🔓 Breaking In...",
                    description=(
                        "You're breaking into your workplace safe... If you get caught you will "
                        "certainly be fired and arrested. Other consequences may also occur. "
                        "Do you wish to continue?"
                    ),
                    color=0xFAA61A,
                ),
                view=confirm_view,
                ephemeral=True,
            )
        except Exception as e:
            print(f"[ERROR] Failed to send robbery confirmation message: {e}")
            return

        await confirm_view.wait()

        if confirm_view.value is None:
            try:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="⌛ Timeout",
                        description="You took too long to decide. Robbery cancelled.",
                        color=0x747F8D,
                    ),
                    ephemeral=True,
                )
            except Exception as e:
                print(f"[ERROR] Failed to send timeout followup message: {e}")
            return

        if not confirm_view.value:
            return

        # ============================================================
        # EMPLOYMENT CHECK
        # ============================================================
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                employed = await conn.fetchval("""
                    SELECT 1
                    FROM user_occupations
                    WHERE discord_id = $1
                      AND guild_id = $2
                      AND employment_end_date IS NULL
                """, interaction.user.id, interaction.guild.id)

            if not employed:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        title="🚫 You Are Not Employed",
                        description="You can't rob a workplace safe if you don't even work there.",
                        color=0xFF0000
                    ),
                    ephemeral=True
                )

            # ============================================================
            # ⭐ START NEW BREAKJOB VAULT GAME
            # ============================================================
            await start_vault_game(interaction, self.bot)
            return

        except Exception as e:
            print(f"❌ Exception in handle_rob_job: {e}")
            try:
                await interaction.channel.send(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Something went wrong during the robbery.",
                        color=0xF04747,
                    )
                )
            except Exception as inner_e:
                print(f"❌ Could not send error message: {inner_e}")


async def setup(bot):
    await bot.add_cog(CrimeCommands(bot))
