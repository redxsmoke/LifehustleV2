import discord
from discord.ext import commands
from discord import app_commands
from db.connection import get_pool


# =========================
# STATUS MAP
# =========================
STATUS_MAP = {
    6: ("Operational", "🟢"),
    7: ("Impounded", "🚓"),
    8: ("Broken Down", "🔧"),
    9: ("Flat Tire", "🛞"),
    10: ("Stolen", "🚨")
}


# =========================
# CONDITION MAP
# =========================
async def get_condition_name(conn, condition_id: int):
    row = await conn.fetchrow("""
        SELECT condition_name
        FROM cd_vehicle_conditions
        WHERE cd_vehicle_condition_id = $1
    """, condition_id)

    return row["condition_name"] if row else "Unknown"


# =========================
# VEHICLE BUTTON
# =========================
class MyVehicleButton(discord.ui.Button):
    def __init__(self, vehicle):
        self.vehicle = vehicle

        super().__init__(
            label=vehicle["vehicle_type"],
            style=discord.ButtonStyle.primary,
            emoji="🚗"
        )

    async def callback(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            condition_name = await get_condition_name(
                conn,
                self.vehicle["vehicle_condition_id"]
            )

        status_text, status_emoji = STATUS_MAP.get(
            self.vehicle["vehicle_status_id"],
            ("Unknown", "❓")
        )

        embed = discord.Embed(
            title=f"{status_emoji} Vehicle Details",
            description=(
                f"> 🚗 **Vehicle Type:** {self.vehicle['vehicle_type']}\n"
                f"> 🎨 **Color:** {self.vehicle.get('color', 'Unknown')}\n"
                f"> 🪪 **License Plate:** {self.vehicle.get('license_plate', 'Unknown')}\n"
                f"> 🚦 **Vehicle Status:** {status_text}\n"
                f"> 🔧 **Vehicle Condition:** {condition_name}\n"
                f"> 🛣️ **Commute Count:** {self.vehicle['commute_count']:,}"
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# =========================
# VIEW
# =========================
class MyVehiclesView(discord.ui.View):
    def __init__(self, vehicles):
        super().__init__(timeout=60)

        for v in vehicles:
            self.add_item(MyVehicleButton(v))


# =========================
# COG
# =========================
class MyVehicles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="myvehicles",
        description="View your owned vehicles"
    )
    async def myvehicles(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            vehicles = await conn.fetch("""
                SELECT uv.user_vehicle_id,
                       cv.vehicle_type,
                       uv.vehicle_status_id,
                       uv.vehicle_condition_id,
                       uv.commute_count,
                       uv.color,
                       uv.license_plate
                FROM user_vehicles uv
                JOIN cd_vehicles cv
                    ON cv.cd_vehicle_id = uv.cd_vehicle_id
                WHERE uv.discord_id = $1
                  AND uv.guild_id = $2
                ORDER BY cv.vehicle_type
            """, interaction.user.id, interaction.guild.id)

        if not vehicles:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚗 No Vehicles",
                    description="You don't own any vehicles yet.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        embed = discord.Embed(
            title="🚗 Your Vehicles",
            description="Click a vehicle below to view details.",
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            view=MyVehiclesView(vehicles),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(MyVehicles(bot))