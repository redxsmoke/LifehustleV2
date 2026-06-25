import discord
from discord.ext import commands
from discord import app_commands
from db.connection import get_pool


# =========================
# PRICE MULTIPLIERS
# =========================
CONDITION_MULTIPLIERS = {
    "New": 0.80,
    "Used": 0.65,
    "Worn": 0.50,
    "Rusty": 0.35,
    "Poor": 0.20,
    "Broken Down": 0.10
}


# =========================
# CONFIRM SELL VIEW
# =========================
class ConfirmSellView(discord.ui.View):
    def __init__(self, vehicle, resale_value):
        super().__init__(timeout=30)
        self.vehicle = vehicle
        self.resale_value = resale_value

    @discord.ui.button(label="Sell Vehicle", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):

        pool = get_pool()

        async with pool.acquire() as conn:

            # =========================
            # DELETE VEHICLE (GUILD SAFE)
            # =========================
            await conn.execute("""
                DELETE FROM user_vehicles
                WHERE user_vehicle_id = $1
                  AND discord_id = $2
                  AND guild_id = $3
            """,
            self.vehicle["user_vehicle_id"],
            interaction.user.id,
            interaction.guild.id)

            # =========================
            # REFUND MONEY (GUILD SAFE)
            # =========================
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance + $1
                WHERE discord_id = $2
                  AND guild_id = $3
            """,
            self.resale_value,
            interaction.user.id,
            interaction.guild.id)

            # =========================
            # AUTO-SELECT NEW ACTIVE VEHICLE (SAFE FALLBACK)
            # =========================
            remaining = await conn.fetchrow("""
                SELECT user_vehicle_id
                FROM user_vehicles
                WHERE discord_id = $1
                  AND guild_id = $2
                LIMIT 1
            """, interaction.user.id, interaction.guild.id)

            if remaining:
                await conn.execute("""
                    UPDATE user_vehicles
                    SET is_active = true
                    WHERE user_vehicle_id = (
                        SELECT user_vehicle_id
                        FROM user_vehicles
                        WHERE discord_id = $1
                          AND guild_id = $2
                        ORDER BY user_vehicle_id ASC
                        LIMIT 1
                    )
                """, interaction.user.id, interaction.guild.id)

        # =========================
        # GET UPDATED BALANCE
        # =========================
        async with pool.acquire() as conn:
            updated = await conn.fetchrow("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1
                  AND guild_id = $2
            """,
            interaction.user.id,
            interaction.guild.id)

        embed = discord.Embed(
            title="🚗 Vehicle Sold",
            description="The dealer counts the cash slowly… then nods.",
            color=discord.Color.green()
        )

        embed.add_field(
            name="💰 You received",
            value=f"${self.resale_value/100:,.2f}",
            inline=True
        )

        embed.add_field(
            name="🏦 New Balance",
            value=f"${updated['checking_account_balance']/100:,.2f}",
            inline=True
        )

        await interaction.response.edit_message(embed=embed, view=None)

        # =========================
        # OPTIONAL UX NOTIFICATION
        # =========================
        if remaining:
            await interaction.followup.send(
                "🚗 Your previous vehicle was sold. We've selected a new default vehicle for you.",
                ephemeral=True
            )


# =========================
# SELL BUTTON
# =========================
class SellVehicleButton(discord.ui.Button):
    def __init__(self, vehicle):
        self.vehicle = vehicle

        super().__init__(
            label=vehicle["vehicle_type"],
            style=discord.ButtonStyle.danger
        )

    async def callback(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            # =========================
            # GET CONDITION
            # =========================
            condition = await conn.fetchrow("""
                SELECT condition_name
                FROM cd_vehicle_conditions
                WHERE cd_vehicle_condition_id = $1
            """, self.vehicle["vehicle_condition_id"])

            condition_name = condition["condition_name"]

            multiplier = CONDITION_MULTIPLIERS.get(condition_name, 0.5)

            resale_value = int(self.vehicle["purchase_price"] * multiplier)

        # =========================
        # OFFER PREVIEW EMBED
        # =========================
        embed = discord.Embed(
            title="🚗 Dealer Offer",
            description="The dealer walks around your vehicle… silently judging it.",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="🚙 Vehicle",
            value=self.vehicle["vehicle_type"],
            inline=True
        )

        embed.add_field(
            name="🎨 Color",
            value=self.vehicle.get("color", "Unknown"),
            inline=True
        )

        embed.add_field(
            name="🪪 Plate",
            value=self.vehicle.get("license_plate", "Unknown"),
            inline=True
        )

        embed.add_field(
            name="⚠ Condition",
            value=condition_name,
            inline=True
        )

        embed.add_field(
            name="💰 Offer",
            value=f"${resale_value/100:,.2f}",
            inline=True
        )

        view = ConfirmSellView(self.vehicle, resale_value)

        await interaction.response.edit_message(embed=embed, view=view)


# =========================
# SELL VIEW
# =========================
class SellVehicleView(discord.ui.View):
    def __init__(self, vehicles):
        super().__init__(timeout=60)

        for v in vehicles:
            self.add_item(SellVehicleButton(v))


# =========================
# COG
# =========================
class SellVehicle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="sellvehicle",
        description="Sell one of your vehicles to the dealer"
    )
    async def sellvehicle(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            vehicles = await conn.fetch("""
                SELECT uv.user_vehicle_id,
                       uv.purchase_price,
                       uv.vehicle_condition_id,
                       uv.color,
                       uv.license_plate,
                       cv.vehicle_type
                FROM user_vehicles uv
                JOIN cd_vehicles cv ON cv.cd_vehicle_id = uv.cd_vehicle_id
                WHERE uv.discord_id = $1
                  AND uv.guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        if not vehicles:
            return await interaction.response.send_message(
                "You don’t own any vehicles.",
                ephemeral=True
            )

        view = SellVehicleView(vehicles)

        embed = discord.Embed(
            title="🚗 Sell Vehicle",
            description="Select a vehicle to get a dealer offer.",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(SellVehicle(bot))