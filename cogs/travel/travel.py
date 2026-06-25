import discord
from discord import app_commands
from discord.ext import commands

from db.connection import get_pool

# These imports are still needed for GoFreeMe UI inside jail_check
from cogs.gofreeme import GoFreeMeCreateModal, BribeDAButton

from cogs.travel.travel_ui import TravelView, travel_error
from cogs.travel.travel_events import generate_travel_event

# ⭐ UNIVERSAL JAIL CHECK (now includes Bail Coupon logic)
from utils.jail_check import check_if_in_jail


class Travel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="travel", description="Travel between locations")
    async def travel(self, interaction: discord.Interaction):

        # ⭐ UNIVERSAL JAIL CHECK
        # If user is incarcerated, the helper sends the jail UI and returns True.
        if await check_if_in_jail(interaction):
            return

        pool = get_pool()

        # ⭐ USER IS NOT IN JAIL → continue with normal travel logic
        try:
            async with pool.acquire() as conn:
                vehicles = await conn.fetch("""
                    SELECT uv.user_vehicle_id,
                           uv.purchase_price,
                           uv.vehicle_condition_id,
                           uv.color,
                           uv.license_plate,
                           uv.vehicle_status_id,
                           uv.commute_count,
                           cv.vehicle_type,
                           cv.fuel_cost,
                           cv.travel_class_id
                    FROM user_vehicles uv
                    JOIN cd_vehicles cv ON cv.cd_vehicle_id = uv.cd_vehicle_id
                    WHERE uv.discord_id = $1
                      AND uv.guild_id = $2
                      AND uv.is_active = true
                """, interaction.user.id, interaction.guild.id)
        except Exception as e:
            travel_error(f"Failed to load vehicles: {e}")
            return await interaction.response.send_message("Error loading vehicles.", ephemeral=True)

        try:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚦 Choose Transport Method",
                    description="Select how you want to travel:",
                    color=discord.Color.blurple()
                ),
                view=TravelView(vehicles),
                ephemeral=True
            )
        except Exception as e:
            travel_error(f"Failed to send transport selection UI: {e}")


async def setup(bot):
    await bot.add_cog(Travel(bot))
