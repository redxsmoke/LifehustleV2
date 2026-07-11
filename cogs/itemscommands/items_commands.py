import discord
from discord import app_commands
from discord.ext import commands
import logging

log = logging.getLogger("items")

RARITY_COLORS = {
    "Common": "⬜",
    "Uncommon": "🟩",
    "Rare": "🟦",
    "Epic": "🟪",
    "Legendary": "🟨"
}

def is_valid_url(url: str):
    if not url or not isinstance(url, str):
        return False
    return url.startswith("http://") or url.startswith("https://")


class Items(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ============================================================
    # AUTOCOMPLETE
    # ============================================================
    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            async with self.bot.db.acquire(timeout=2) as conn:
                rows = await conn.fetch("""
                    SELECT item_id, name
                    FROM cd_items
                    WHERE is_active = TRUE
                    AND LOWER(name) LIKE LOWER($1)
                    ORDER BY name ASC
                    LIMIT 25
                """, f"%{current}%")
        except Exception as e:
            log.error(f"[AUTOCOMPLETE] DB error for '{current}': {e}")
            return []

        return [
            app_commands.Choice(name=row["name"], value=str(row["item_id"]))
            for row in rows
        ]

    # ============================================================
    # NEW UI SELECT — ITEM TYPE FILTER
    # ============================================================
    class ItemTypeSelect(discord.ui.Select):
        def __init__(self, current_filter: str):
            options = [
                discord.SelectOption(label="All", value="all"),
                discord.SelectOption(label="Consumable", value="consumable"),
                discord.SelectOption(label="Reward", value="reward"),
                discord.SelectOption(label="Tool", value="tool"),
                discord.SelectOption(label="Badge", value="badge"),
            ]

            super().__init__(
                placeholder="Filter items by type",
                min_values=1,
                max_values=1,
                options=options,
            )

            for opt in self.options:
                if opt.value == current_filter:
                    opt.default = True

        async def callback(self, interaction: discord.Interaction):
            view: "ItemsView" = self.view  # type: ignore

            if interaction.user.id != view.user.id:
                return await interaction.response.send_message(
                    "⛔ This menu is not for you.",
                    ephemeral=True
                )

            view.type_filter = self.values[0]
            view.page = 0
            await view.refresh(interaction)

    # ============================================================
    # NEW UI VIEW — LOTTERY STYLE
    # ============================================================
    class ItemsView(discord.ui.View):
        def __init__(self, bot, user, guild_id, sort):
            super().__init__(timeout=300)
            self.bot = bot
            self.user = user
            self.guild_id = guild_id
            self.sort = sort
            self.type_filter = "all"
            self.page = 0
            self.per_page = 10
            self.rows = []

            # Dropdown ABOVE pagination (Option 1)
            self.add_item(Items.ItemTypeSelect(self.type_filter))

        async def fetch_items(self):
            try:
                async with self.bot.db.acquire(timeout=2) as conn:
                    base_sql = """
                        SELECT ui.item_id, ui.quantity, ci.*
                        FROM user_items ui
                        JOIN cd_items ci ON ci.item_id = ui.item_id
                        WHERE ui.discord_id = $1
                        AND ui.guild_id = $2
                        AND ci.is_active = TRUE
                    """

                    params = [self.user.id, self.guild_id]

                    if self.type_filter != "all":
                        base_sql += " AND LOWER(ci.type) = LOWER($3)"
                        params.append(self.type_filter)

                    rows = await conn.fetch(base_sql, *params)
                    self.rows = rows

            except Exception as e:
                log.error(f"[ItemsView.fetch_items] {e}")
                self.rows = []

        def sort_items(self):
            try:
                if self.sort == "name":
                    self.rows = sorted(self.rows, key=lambda r: r["name"])
                elif self.sort == "type":
                    self.rows = sorted(self.rows, key=lambda r: r["type"])
                else:
                    rarity_order = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 5}
                    self.rows = sorted(self.rows, key=lambda r: rarity_order.get(r["rarity"], 0), reverse=True)
            except Exception as e:
                log.error(f"[ItemsView.sort_items] {e}")

        def get_page_items(self):
            start = self.page * self.per_page
            end = start + self.per_page
            return self.rows[start:end]

        def build_embed(self):
            embed = discord.Embed(
                title="🎒 Your Active Items",
                description=f"Sorted by **{self.sort.capitalize()}** | Filter: **{self.type_filter.capitalize()}**",
                color=discord.Color.blurple()
            )

            page_items = self.get_page_items()

            if not page_items:
                embed.description = "📭 You have no items in this category."
                return embed

            text = ""

            for item in page_items:
                icon = item["icon_path"]
                if is_valid_url(icon):
                    icon_prefix = f"[⠀]({icon})"
                else:
                    icon_prefix = RARITY_COLORS.get(item["rarity"], "⬜")

                text += f"{icon_prefix} **{item['name']} ×{item['quantity']}**\n"
                text += f"{item['description']}\n\n"

            embed.description = text.strip()
            return embed

        async def refresh(self, interaction: discord.Interaction):
            await self.fetch_items()
            self.sort_items()

            # Remove old dropdown and re-add fresh one
            for item in list(self.children):
                if isinstance(item, Items.ItemTypeSelect):
                    self.remove_item(item)

            self.add_item(Items.ItemTypeSelect(self.type_filter))

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
            )

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
        async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message("⛔ Not allowed.", ephemeral=True)

            if self.page > 0:
                self.page -= 1

            await self.refresh(interaction)

        @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message("⛔ Not allowed.", ephemeral=True)

            max_page = max(0, (len(self.rows) - 1) // self.per_page)
            if self.page < max_page:
                self.page += 1

            await self.refresh(interaction)

    # ============================================================
    # /items COMMAND
    # ============================================================
    @app_commands.command(name="items", description="View your items, item info, or search items.")
    @app_commands.describe(
        action="Choose what you want to do",
        query="Item name or ID",
        sort="Sort your inventory"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="My Items", value="my"),
        app_commands.Choice(name="About Item", value="about"),
        app_commands.Choice(name="Search Item", value="search")
    ])
    @app_commands.choices(sort=[
        app_commands.Choice(name="Name (A→Z)", value="name"),
        app_commands.Choice(name="Rarity (High→Low)", value="rarity"),
        app_commands.Choice(name="Type (A→Z)", value="type")
    ])
    @app_commands.autocomplete(query=item_autocomplete)
    async def items(self, interaction: discord.Interaction, action: app_commands.Choice[str], query: str = None, sort: app_commands.Choice[str] = None):
        await interaction.response.defer()

        try:
            if action.value == "my":
                sort_value = sort.value if sort else "rarity"
                view = Items.ItemsView(self.bot, interaction.user, interaction.guild_id, sort_value)
                await view.fetch_items()
                view.sort_items()

                await interaction.followup.send(
                    embed=view.build_embed(),
                    view=view
                )
                return

            elif action.value == "about":
                if not query:
                    return await interaction.followup.send("❌ You must provide an item name or ID.", ephemeral=True)
                await self.show_item_about(interaction, query)

            elif action.value == "search":
                if not query:
                    return await interaction.followup.send("❌ You must provide an item name or ID.", ephemeral=True)
                await self.search_item(interaction, query)

        except Exception as e:
            log.error(f"[ITEMS ROOT] Unexpected error: {e}")
            await interaction.followup.send("❌ Something went wrong running this command.", ephemeral=True)

    # ============================================================
    # /items about (UNCHANGED)
    # ============================================================
    async def show_item_about(self, interaction, query):
        try:
            async with self.bot.db.acquire(timeout=2) as conn:
                row = await conn.fetchrow("""
                    SELECT *
                    FROM cd_items
                    WHERE is_active = TRUE
                    AND (item_id::text = $1 OR LOWER(name) = LOWER($1))
                """, query)
        except Exception as e:
            log.error(f"[ABOUT] DB error for '{query}': {e}")
            return await interaction.followup.send("❌ Failed to fetch item info.", ephemeral=True)

        if not row:
            return await interaction.followup.send("❌ Item not found or inactive.", ephemeral=True)

        color = discord.Color.green()

        try:
            embed = discord.Embed(
                title=f"📘 {row['name']}",
                description=row["description"],
                color=color
            )
            embed.add_field(name="💰 Cost", value=f"${row['price']:,}")
            embed.add_field(name="🎚️ Rarity", value=row["rarity"])
            embed.add_field(name="📦 Type", value=row["type"])

            icon = row["icon_path"]
            if is_valid_url(icon):
                embed.set_thumbnail(url=icon)

        except Exception as e:
            log.error(f"[ABOUT] Embed creation failed for '{query}': {e}")
            return await interaction.followup.send("❌ Failed to build item info.", ephemeral=True)

        await interaction.followup.send(embed=embed)

    # ============================================================
    # /items search (UNCHANGED)
    # ============================================================
    async def search_item(self, interaction, query):
        try:
            async with self.bot.db.acquire(timeout=2) as conn:

                if query.isdigit():
                    row = await conn.fetchrow("""
                        SELECT *
                        FROM cd_items
                        WHERE is_active = TRUE
                        AND item_id = $1
                    """, int(query))
                else:
                    row = await conn.fetchrow("""
                        SELECT *
                        FROM cd_items
                        WHERE is_active = TRUE
                        AND LOWER(name) LIKE LOWER($1)
                    """, f"%{query}%")

                if not row:
                    return await interaction.followup.send("❌ No active item found.", ephemeral=True)

                perk_type = None
                if row["grants_perk_id"]:
                    perk_row = await conn.fetchrow("""
                        SELECT perk_type
                        FROM cd_perks
                        WHERE perk_id = $1
                    """, row["grants_perk_id"])

                    if perk_row:
                        perk_type = perk_row["perk_type"]

        except Exception as e:
            log.error(f"[SEARCH] DB error for '{query}': {e}")
            return await interaction.followup.send("❌ Search failed.", ephemeral=True)

        color = discord.Color.gold()

        try:
            embed = discord.Embed(
                title=f"🔍 {row['name']}",
                description=row["description"],
                color=color
            )

            icon = row["icon_path"]
            if is_valid_url(icon):
                embed.set_thumbnail(url=icon)

            embed.add_field(name="💰 Cost", value=f"${row['price']:,}")
            embed.add_field(name="🎚️ Rarity", value=row["rarity"])
            embed.add_field(name="📦 Type", value=row["type"])
            embed.add_field(name="🔁 Tradable", value="Yes" if row["tradable"] else "No")
            embed.add_field(name="🛒 Purchasable", value="Yes" if row["purchasable"] else "No")

            if perk_type:
                embed.add_field(name="🎁 Perk Granted", value=perk_type)
            else:
                embed.add_field(name="🎁 Perk Granted", value="None")

            embed.add_field(name="📉 Purchase Limit", value=str(row["purchase_limit"]))
            embed.add_field(name="🆔 Item ID", value=str(row["item_id"]))

        except Exception as e:
            log.error(f"[SEARCH] Embed creation failed for '{query}': {e}")
            return await interaction.followup.send("❌ Failed to build item profile.", ephemeral=True)

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Items(bot))
