import discord
from discord.ext import commands
from discord import app_commands
from db.connection import get_pool
import random


# =========================
# VEHICLE HELPERS
# =========================

VEHICLE_COLORS = [
    "Black",
    "White",
    "Silver",
    "Gray",
    "Red",
    "Blue",
    "Green",
    "Yellow",
    "Orange",
    "Purple",
    "Brown",
    "Tan"
]


def generate_plate():
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=2))
    numbers = random.randint(1000, 9999)
    return f"{letters}-{numbers}"


# =========================
# VEHICLE BUTTON
# =========================
class VehicleButton(discord.ui.Button):
    def __init__(self, vehicle):
        self.vehicle = vehicle

        emoji_map = {
            "Bicycle": "🚲",
            "Beater Car": "🚗",
            "Sedan": "🚙",
            "SUV": "🚙",
            "Sports Car": "🏎️",
            "Super Car": "🏁"
        }

        emoji = emoji_map.get(vehicle["vehicle_type"], "🚗")

        super().__init__(
            label=f"{vehicle['vehicle_type']} - ${vehicle['cost']/100:,.2f}",
            emoji=emoji,
            style=discord.ButtonStyle.success
        )

    async def callback(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:

            # =========================
            # USER (SERVER SCOPED)
            # =========================
            user = await conn.fetchrow("""
                SELECT cd_location_id, checking_account_balance
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

            car_dealer = await conn.fetchrow("""
                SELECT cd_location_id
                FROM cd_location
                WHERE description = 'Car Dealer'
            """)

            if user["cd_location_id"] != car_dealer["cd_location_id"]:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚫 Not Allowed",
                        description="You must be at the **Car Dealer** to buy vehicles. Use /travel to take a trip to the car dealer",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            owned_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM user_vehicles
                WHERE discord_id = $1
                  AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

            if owned_count >= 3:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚫 Garage Full",
                        description="You already own **3 vehicles**.",
                        color=discord.Color.orange()
                    ),
                    ephemeral=True
                )

            cost = self.vehicle["cost"]

            if user["checking_account_balance"] < cost:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="💸 Not Enough Money",
                        description="Your wallet is crying in the corner.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            # =========================
            # CHARGE USER
            # =========================
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance - $1
                WHERE discord_id = $2
                  AND guild_id = $3
            """, cost, interaction.user.id, interaction.guild.id)

            # =========================
            # DEACTIVATE OTHER VEHICLES (NON BIKES)
            # =========================
            await conn.execute("""
                UPDATE user_vehicles
                SET is_active = false,
                    cd_location_id = 1
                WHERE discord_id = $1
                  AND guild_id = $2
                  AND cd_vehicle_id IN (
                      SELECT cd_vehicle_id
                      FROM cd_vehicles
                      WHERE vehicle_type != 'Bicycle'
                  )
            """, interaction.user.id, interaction.guild.id)

            new_condition = await conn.fetchrow("""
                SELECT cd_vehicle_condition_id
                FROM cd_vehicle_conditions
                WHERE condition_name = 'New'
            """)

            poor_condition = await conn.fetchrow("""
                SELECT cd_vehicle_condition_id
                FROM cd_vehicle_conditions
                WHERE condition_name = 'Poor'
            """)

            condition_id = (
                poor_condition["cd_vehicle_condition_id"]
                if self.vehicle["vehicle_type"] == "Beater Car"
                else new_condition["cd_vehicle_condition_id"]
            )

            commute_count = (
                random.randint(400, 500)
                if self.vehicle["cd_vehicle_id"] == 2
                else 0
            )

            status_id = 6  # Operational

            # =========================
            # COLOR + PLATE
            # =========================
            color = random.choice(VEHICLE_COLORS)

            if self.vehicle["vehicle_type"] == "Bicycle":
                plate = "BIKE"
            else:
                while True:
                    plate = generate_plate()

                    exists = await conn.fetchval("""
                        SELECT 1
                        FROM user_vehicles
                        WHERE guild_id = $1
                          AND license_plate = $2
                        LIMIT 1
                    """, interaction.guild.id, plate)

                    if not exists:
                        break

            # =========================
            # INSERT VEHICLE
            # =========================
            await conn.execute("""
                INSERT INTO user_vehicles (
                    guild_id,
                    discord_id,
                    cd_vehicle_id,
                    is_active,
                    purchase_price,
                    purchased_timestamp,
                    vehicle_status_id,
                    vehicle_condition_id,
                    cd_location_id,
                    commute_count,
                    color,
                    license_plate
                )
                VALUES (
                    $1,$2,$3,
                    true,
                    $4,
                    NOW(),
                    $5,$6,$7,$8,
                    $9,$10
                )
            """,
                interaction.guild.id,
                interaction.user.id,
                self.vehicle["cd_vehicle_id"],
                cost,
                status_id,
                condition_id,
                car_dealer["cd_location_id"],
                commute_count,
                color,
                plate
            )

            updated = await conn.fetchrow("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1
                  AND guild_id = $2
            """, interaction.user.id, interaction.guild.id)

        embed = discord.Embed(
            title="🚗 Purchase Successful",
            description=f"You bought a **{self.vehicle['vehicle_type']}**!",
            color=discord.Color.green()
        )

        embed.add_field(name="💰 Cost", value=f"${cost/100:,.2f}", inline=True)
        embed.add_field(name="🏦 New Balance", value=f"${updated['checking_account_balance']/100:,.2f}", inline=True)
        embed.add_field(name="🎨 Color", value=color, inline=True)
        embed.add_field(name="🪪 Plate", value=plate, inline=True)

        await interaction.response.edit_message(embed=embed, view=None)


# =========================
# SHOP VIEW
# =========================
class VehicleShopView(discord.ui.View):
    def __init__(self, vehicles):
        super().__init__(timeout=60)

        for v in vehicles:
            self.add_item(VehicleButton(v))


class BuyVehicle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="buyvehicle", description="Buy a vehicle")
    async def buyvehicle(self, interaction: discord.Interaction):

        pool = get_pool()

        async with pool.acquire() as conn:
            vehicles = await conn.fetch("""
                SELECT cd_vehicle_id, vehicle_type, cost
                FROM cd_vehicles
                WHERE is_active = true
                  AND travel_class_id = 1   -- ONLY player-owned vehicles
                ORDER BY cost
            """)

        embed = discord.Embed(
            title="🚗 Vehicle Shop",
            description="Click a vehicle below to purchase it.",
            color=discord.Color.blurple()
        )

        view = VehicleShopView(vehicles)

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(BuyVehicle(bot))
