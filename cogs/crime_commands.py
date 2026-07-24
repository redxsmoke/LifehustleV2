import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import logging

from db.connection import get_pool

from cogs.gofreeme import GoFreeMeCreateModal, BribeDAButton
from utils.jail_check import check_if_in_jail

gta_logger = logging.getLogger("crime.gtaerrors")
gta_logger.setLevel(logging.ERROR)

rob_logger = logging.getLogger("crime.robjob")
rob_logger.setLevel(logging.ERROR)

rob_cooldowns = {}
COOLDOWN_DURATION = timedelta(minutes=30)

# GTA cooldowns
gta_cooldowns = {}
GTA_COOLDOWN_DURATION = timedelta(minutes=30)

# Import GTA Stage 1
from cogs.minigames.grandtheftauto.stage1 import start_gta_stage1


class CrimeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crime", description="Commit a crime to earn rewards or penalties.")
    async def crime(self, interaction: discord.Interaction):

        if await check_if_in_jail(interaction):
            return

        from cogs.crime_views import CrimeSelectionView

        view = CrimeSelectionView(interaction.user, self.bot)
        embed = discord.Embed(
            title="Choose a Crime",
            description="Select a crime to commit:",
            color=0x7289DA
        )

        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            rob_logger.exception("Failed to send initial crime selection message: %s", e)

    async def handle_rob_job(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        try:
            await interaction.response.defer()
        except discord.errors.InteractionResponded:
            pass

        from cogs.minigames.breakjob.command import start_vault_game

        try:
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

                return await interaction.followup.send(embed=embed, ephemeral=True)

            rob_cooldowns[guild_id][user_id] = now + COOLDOWN_DURATION

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
                embed = discord.Embed(
                    title="🚫 You Are Not Employed",
                    description="You can't rob a workplace safe if you don't even work there.",
                    color=0xFF0000
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)

            class DummyResponse:
                def __init__(self, channel: discord.TextChannel):
                    self.channel = channel

                @property
                def is_done(self) -> bool:
                    return True

                async def send_message(self, content=None, **kwargs):
                    await self.channel.send(content=content, **kwargs)

            class DummyFollowup:
                def __init__(self, channel: discord.TextChannel):
                    self.channel = channel

                async def send(self, content=None, **kwargs):
                    await self.channel.send(content=content, **kwargs)

            class DummyInteraction:
                def __init__(self, real: discord.Interaction):
                    self.user = real.user
                    self.guild = real.guild
                    self.channel = real.channel
                    self.response = DummyResponse(real.channel)
                    self.followup = DummyFollowup(real.channel)

            dummy = DummyInteraction(interaction)

            rob_logger.info(
                "Starting vault game for user %s in guild %s via DummyInteraction",
                user_id,
                guild_id,
            )

            await start_vault_game(dummy, self.bot)
            return

        except Exception as e:
            rob_logger.exception("Exception in handle_rob_job: %s", e)
            try:
                await interaction.channel.send(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Something went wrong during the robbery.",
                        color=0xF04747,
                    )
                )
            except Exception as inner_e:
                rob_logger.exception("Could not send robbery error message: %s", inner_e)

    async def handle_grand_theft_auto(self, interaction: discord.Interaction, victim: discord.Member):
        try:
            if await check_if_in_jail(interaction):
                return

            guild_id = interaction.guild.id
            thief_id = interaction.user.id

            # ============================
            # 🚗 GTA COOLDOWN (funny)
            # ============================
            if guild_id not in gta_cooldowns:
                gta_cooldowns[guild_id] = {}

            now = datetime.utcnow()
            next_allowed = gta_cooldowns[guild_id].get(thief_id)

            if next_allowed and now < next_allowed:
                remaining = next_allowed - now
                minutes = int(remaining.total_seconds() // 60)
                seconds = int(remaining.total_seconds() % 60)

                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⏳ Whoa there, *Speed Racer!*",
                        description=(
                            "Your criminal engine is overheating.\n\n"
                            f"Try stealing another car in **{minutes}m {seconds}s**.\n"
                            "Let the cops finish their paperwork first."
                        ),
                        color=discord.Color.orange()
                    ),
                    ephemeral=True
                )

            gta_cooldowns[guild_id][thief_id] = now + GTA_COOLDOWN_DURATION

            # ============================
            # 🚫 Prevent repeated thefts (funny victim block)
            # ============================
            pool = get_pool()
            async with pool.acquire() as conn:
                stolen_recently = await conn.fetchrow("""
                    SELECT last_stolen_at,
                           (last_stolen_at + INTERVAL '12 hours') - NOW() AS remaining
                    FROM user_vehicles
                    WHERE guild_id = $1
                      AND stolen_from_discord_id = $2
                      AND is_stolen = TRUE
                      AND last_stolen_at >= NOW() - INTERVAL '12 hours'
                    ORDER BY last_stolen_at DESC
                    LIMIT 1
                """, interaction.guild.id, victim.id)

            if stolen_recently:
                remaining = stolen_recently["remaining"]
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)

                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚗 Slow down there, *Dominic Toretto!*",
                        description=(
                            f"**{victim.display_name}** is already filing enough insurance claims.\n\n"
                            f"You can't steal from them again for **{hours}h {minutes}m**.\n"
                            "Let their poor deductible breathe."
                        ),
                        color=discord.Color.orange()
                    ),
                    ephemeral=True
                )

            # ============================
            # Continue to GTA Stage 1
            # ============================
            await start_gta_stage1(interaction, self.bot, victim)

        except Exception as e:
            gta_logger.exception("Error in handle_grand_theft_auto: %s", e)
            try:
                await interaction.response.send_message(
                    "❌ Something went wrong starting Grand Theft Auto.",
                    ephemeral=True
                )
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(CrimeCommands(bot))
