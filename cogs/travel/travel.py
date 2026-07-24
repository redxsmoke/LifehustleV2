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


class FilePoliceReportButton(discord.ui.Button):
    def __init__(self, stolen_vehicle_id: int, vehicle_info: dict):
        super().__init__(label="📢 File Police Report", style=discord.ButtonStyle.danger)
        self.stolen_vehicle_id = stolen_vehicle_id
        self.vehicle_info = vehicle_info  # vehicle_type, color, plate, last_stolen_at, thief_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:

            # ⭐ Update stolen_vehicles to mark report filed
            await conn.execute(
                """
                UPDATE stolen_vehicles
                SET reported_to_police = TRUE,
                    reported_date = NOW(),
                    case_status = 'open'
                WHERE stolen_vehicle_id = $1
                """,
                self.stolen_vehicle_id
            )

            # ⭐ Insert into police_crimes
            await conn.execute(
                """
                INSERT INTO police_crimes (
                    guild_id,
                    perpetrator_id,
                    crime_type,
                    crime_description,
                    clue_description,
                    timestamp,
                    status,
                    solver_id,
                    reward_given,
                    evidence_list,
                    tip_count,
                    location
                )
                VALUES (
                    $1, $2, 'Grand Theft Auto',
                    $3, NULL, NOW(), 'unsolved',
                    NULL, FALSE, '[]', 0, NULL
                )
                """,
                interaction.guild.id,
                self.vehicle_info["thief_id"],  # perpetrator
                f"Vehicle stolen: {self.vehicle_info['vehicle_type']} | "
                f"Color: {self.vehicle_info['color']} | "
                f"Plate: {self.vehicle_info['license_plate']} | "
                f"Stolen At: {self.vehicle_info['last_stolen_at']}"
            )

        embed = discord.Embed(
            title="📢 Police Report Filed",
            description="Your stolen vehicle has been reported to the authorities.\nThey will begin investigating the case.",
            color=discord.Color.blue()
        )

        await interaction.response.edit_message(embed=embed, view=None)


class Travel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="travel", description="Travel between locations")
    async def travel(self, interaction: discord.Interaction):

        # ⭐ UNIVERSAL JAIL CHECK
        if await check_if_in_jail(interaction):
            return

        pool = get_pool()

        # ⭐ CHECK FOR UNREPORTED STOLEN VEHICLES (victim-based)
        async with pool.acquire() as conn:
            stolen = await conn.fetchrow(
                """
                SELECT 
                    sv.stolen_vehicle_id,
                    sv.discord_id AS thief_id,
                    cv.vehicle_type,
                    uv.color,
                    uv.license_plate,
                    uv.last_stolen_at
                FROM stolen_vehicles sv
                JOIN user_vehicles uv ON sv.user_vehicle_id = uv.user_vehicle_id
                JOIN cd_vehicles cv ON cv.cd_vehicle_id = uv.cd_vehicle_id
                WHERE sv.guild_id = $1
                  AND uv.stolen_from_discord_id = $2   -- victim
                  AND sv.reported_to_police = FALSE
                ORDER BY uv.last_stolen_at DESC
                LIMIT 1
                """,
                interaction.guild.id,
                interaction.user.id
            )

        # ⭐ If the user is the victim → block travel
        if stolen:
            stolen_embed = discord.Embed(
                title="🚨 Your Vehicle Was Stolen!",
                description=(
                    "You cannot travel until you report the theft.\n\n"
                    f"**Vehicle:** {stolen['vehicle_type']}\n"
                    f"**Color:** {stolen['color']}\n"
                    f"**Plate:** {stolen['license_plate']}\n"
                    f"**Stolen At:** {stolen['last_stolen_at']}\n\n"
                    "Please file a police report to proceed."
                ),
                color=discord.Color.red()
            )

            vehicle_info = {
                "vehicle_type": stolen["vehicle_type"],
                "color": stolen["color"],
                "license_plate": stolen["license_plate"],
                "last_stolen_at": stolen["last_stolen_at"],
                "thief_id": stolen["thief_id"]
            }

            view = discord.ui.View()
            view.add_item(FilePoliceReportButton(stolen["stolen_vehicle_id"], vehicle_info))

            return await interaction.response.send_message(
                embed=stolen_embed,
                view=view,
                ephemeral=True
            )

        # ⭐ USER IS NOT IN JAIL AND HAS NO UNREPORTED STOLEN VEHICLES → continue with normal travel logic
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
