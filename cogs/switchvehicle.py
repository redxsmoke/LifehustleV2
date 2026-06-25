import discord
from discord.ext import commands
from discord import app_commands
from db.connection import get_pool


# =========================
# VEHICLE SWITCH BUTTON
# =========================
class SwitchVehicleButton(discord.ui.Button):
    def __init__(self, vehicle):
        self.vehicle = vehicle

        super().__init__(
            label=vehicle["vehicle_type"],
            emoji="🚗",
            style=discord.ButtonStyle.primary
        )

    async def callback(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            # =========================
            # DEACTIVATE ALL VEHICLES (GUILD SAFE)
            # =========================
            await conn.execute("""
                UPDATE user_vehicles
                SET is_active = false
                WHERE discord_id = $1
                  AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            # =========================
            # ACTIVATE SELECTED VEHICLE (GUILD SAFE)
            # =========================
            await conn.execute("""
                UPDATE user_vehicles
                SET is_active = true
                WHERE user_vehicle_id = $1
                  AND discord_id = $2
                  AND guild_id = $3
            """,
            self.vehicle["user_vehicle_id"],
            interaction.user.id,
            interaction.guild.id)

            # =========================
            # FETCH UPDATED VEHICLE NAME
            # =========================
            updated = await conn.fetchrow("""
                SELECT cv.vehicle_type
                FROM user_vehicles uv
                JOIN cd_vehicles cv ON cv.cd_vehicle_id = uv.cd_vehicle_id
                WHERE uv.user_vehicle_id = $1
                  AND uv.discord_id = $2
                  AND uv.guild_id = $3
            """,
            self.vehicle["user_vehicle_id"],
            interaction.user.id,
            interaction.guild.id)

        embed = discord.Embed(
            title="🚗 Vehicle Switched",
            description=f"You are now using **{updated['vehicle_type']}**",
            color=discord.Color.green()
        )

        await interaction.response.edit_message(embed=embed, view=None)


# =========================
# VIEW
# =========================
class SwitchVehicleView(discord.ui.View):
    def __init__(self, vehicles):
        super().__init__(timeout=60)

        for v in vehicles:
            self.add_item(SwitchVehicleButton(v))


# =========================
# COG
# =========================
class SwitchVehicle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="switchvehicle",
        description="Switch your active vehicle"
    )
    async def switchvehicle(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            # =========================
            # MUST BE AT HOME (GUILD SAFE USER)
            # =========================
            user = await conn.fetchrow("""
                SELECT cd_location_id
                FROM users
                WHERE discord_id = $1
                  AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            if not user:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="User not found in this server.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            if user["cd_location_id"] != 1:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🏠 Must Be Home",
                        description="You must be at **Home** to switch vehicles.",
                        color=discord.Color.orange()
                    ),
                    ephemeral=True
                )

            # =========================
            # GET USER VEHICLES (GUILD SAFE)
            # =========================
            vehicles = await conn.fetch("""
                SELECT uv.user_vehicle_id,
                       cv.vehicle_type
                FROM user_vehicles uv
                JOIN cd_vehicles cv ON cv.cd_vehicle_id = uv.cd_vehicle_id
                WHERE uv.discord_id = $1
                  AND uv.guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        if not vehicles:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚗 No Vehicles",
                    description="You don't own any vehicles.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        view = SwitchVehicleView(vehicles)

        embed = discord.Embed(
            title="🚗 Switch Vehicle",
            description="Select which vehicle you want to use:",
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )


# =========================
# SETUP
# =========================
async def setup(bot):
    await bot.add_cog(SwitchVehicle(bot))