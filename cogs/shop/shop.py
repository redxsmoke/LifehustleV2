import discord
from discord.ext import commands
from discord import app_commands
import traceback

from cogs.economy import money   # <-- USE YOUR EXISTING MONEY FORMATTER


GRID_IMAGE = "police_items_shop_grid.png"


class QuantityModal(discord.ui.Modal, title="Purchase Item"):
    quantity = discord.ui.TextInput(
        label="How many would you like to buy?",
        placeholder="Enter a number",
        required=True
    )

    def __init__(self, item, owned, limit, price, bot, user_id, guild_id):
        super().__init__()
        self.item = item
        self.owned = owned
        self.limit = limit
        self.price = price
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value)
            if qty <= 0:
                return await interaction.response.send_message(
                    "Quantity must be greater than zero.",
                    ephemeral=True
                )

            if self.owned + qty > self.limit:
                return await interaction.response.send_message(
                    f"You can only own **{self.limit}** of this item.",
                    ephemeral=True
                )

            total_cost = self.price * qty

            user_balance = await self.bot.db.fetchval("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, self.user_id, self.guild_id)

            if user_balance < total_cost:
                return await interaction.response.send_message(
                    f"You don't have enough money.\n"
                    f"**Cost:** {money(total_cost)}\n"
                    f"**Your Balance:** {money(user_balance)}",
                    ephemeral=True
                )

            # Deduct money
            await self.bot.db.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance - $1
                WHERE discord_id = $2 AND guild_id = $3
            """, total_cost, self.user_id, self.guild_id)

            # Add item(s)
            await self.bot.db.execute("""
                INSERT INTO user_items (discord_id, guild_id, item_id, quantity)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (discord_id, guild_id, item_id)
                DO UPDATE SET quantity = user_items.quantity + EXCLUDED.quantity
            """, self.user_id, self.guild_id, self.item["item_id"], qty)

            new_balance = user_balance - total_cost

            embed = discord.Embed(
                title=f"Purchased {self.item['name']}",
                description=(
                    f"**Quantity:** {qty}\n"
                    f"**Total Cost:** {money(total_cost)}\n"
                    f"**New Balance:** {money(new_balance)}"
                ),
                color=discord.Color.green()
            )

            await interaction.response.send_message(embed=embed)

        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number.",
                ephemeral=True
            )
        except Exception as e:
            print(f"[ERROR][QuantityModal] {e}")
            await interaction.response.send_message(
                "An error occurred while processing your purchase.",
                ephemeral=True
            )


class BuyButton(discord.ui.Button):
    def __init__(self, item):
        super().__init__(
            label=item["name"],
            style=discord.ButtonStyle.green,
            custom_id=f"buy_{item['item_id']}"
        )
        self.item = item

    async def callback(self, interaction: discord.Interaction):
        try:
            bot = interaction.client
            user_id = interaction.user.id
            guild_id = interaction.guild.id

            user = await bot.db.fetchrow("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, user_id, guild_id)

            if not user:
                return await interaction.response.send_message(
                    "You do not have an account.",
                    ephemeral=True
                )

            owned = await bot.db.fetchval("""
                SELECT quantity
                FROM user_items
                WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
            """, user_id, guild_id, self.item["item_id"]) or 0

            limit = self.item["purchase_limit"]
            price = self.item["price"]

            modal = QuantityModal(
                item=self.item,
                owned=owned,
                limit=limit,
                price=price,
                bot=bot,
                user_id=user_id,
                guild_id=guild_id
            )

            await interaction.response.send_modal(modal)

        except Exception:
            traceback.print_exc()
            try:
                await interaction.response.send_message(
                    "An error occurred while opening the purchase dialog.",
                    ephemeral=True
                )
            except discord.InteractionResponded:
                await interaction.followup.send(
                    "An error occurred while opening the purchase dialog.",
                    ephemeral=True
                )


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_all_items(self):
        return await self.bot.db.fetch("""
            SELECT item_id, name, description, rarity, type, price,
                   purchase_limit, grants_perk_id
            FROM cd_items
            WHERE purchasable = TRUE
            ORDER BY rarity, price
        """)

    @app_commands.command(name="shop", description="Browse the item shop.")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer()

        items = await self.fetch_all_items()

        embed = discord.Embed(
            title="Police Encounter Shop",
            description="Select an item below to purchase.",
            color=discord.Color.blue()
        )

        file_path = f"./assets/items/{GRID_IMAGE}"
        file = discord.File(file_path, filename=GRID_IMAGE)
        embed.set_image(url=f"attachment://{GRID_IMAGE}")

        view = discord.ui.View(timeout=180)

        for item in items:
            view.add_item(BuyButton(item))

        await interaction.followup.send(embed=embed, file=file, view=view)


async def setup(bot):
    await bot.add_cog(Shop(bot))
