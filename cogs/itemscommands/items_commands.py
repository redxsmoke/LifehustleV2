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
    # ITEM TYPE FILTER
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
            view: "Items.ItemsView" = self.view  # type: ignore
            if interaction.user.id != view.user.id:
                return await interaction.response.send_message("⛔ This menu is not for you.", ephemeral=True)
            view.type_filter = self.values[0]
            view.page = 0
            await view.refresh(interaction)

    # ============================================================
    # INVENTORY VIEW — DANK MEMER STYLE (ONE EMBED, EMOJIS)
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
            self.add_item(Items.ItemTypeSelect(self.type_filter))

        async def fetch_items(self):
            try:
                async with self.bot.db.acquire(timeout=2) as conn:
                    base_sql = """
                        SELECT ui.item_id, ui.quantity, ci.name, ci.type, ci.rarity,
                               ci.description, ci.emoji_name, ci.emoji_id
                        FROM user_items ui
                        JOIN cd_items ci ON ci.item_id = ui.item_id
                        WHERE ui.discord_id = $1
                        AND ui.guild_id = $2
                        AND ci.is_active = TRUE
                        AND ui.quantity >='1'
                    """
                    params = [self.user.id, self.guild_id]
                    if self.type_filter != "all":
                        base_sql += " AND LOWER(ci.type) = LOWER($3)"
                        params.append(self.type_filter)

                    self.rows = await conn.fetch(base_sql, *params)

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

        # ============================================================
        # ONE EMBED, MULTIPLE EMOJI ICONS
        # ============================================================
        async def build_embeds(self):
            page_items = self.get_page_items()

            embed = discord.Embed(
                title=f"{self.user.display_name}'s Inventory",
                color=discord.Color.blurple()
            )

            if not page_items:
                embed.description = "📭 You have no items in this category."
                return [embed]

            lines = []

            for item in page_items:
                emoji = (
                    f"<:{item['emoji_name']}:{item['emoji_id']}>"
                    if item["emoji_id"] else "⬜"
                )

                lines.append(
                    f"{emoji} **{item['name']} ─ {item['quantity']}**\n"
                    f"{item['type']}"
                )

            embed.description = "\n\n".join(lines)
            return [embed]

        async def refresh(self, interaction: discord.Interaction):
            await self.fetch_items()
            self.sort_items()

            for child in list(self.children):
                if isinstance(child, Items.ItemTypeSelect):
                    self.remove_item(child)

            self.add_item(Items.ItemTypeSelect(self.type_filter))

            embeds = await self.build_embeds()

            await interaction.response.edit_message(
                embeds=embeds,
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
                embeds = await view.build_embeds()
                await interaction.followup.send(embeds=embeds, view=view)
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
    # /items about (UPDATED)
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

        emoji = (
            f"<:{row['emoji_name']}:{row['emoji_id']}>"
            if row["emoji_id"] else "⬜"
        )

        cost = (
            "Not Purchasable"
            if row["price"] == 0
            else f"${row['price']:,}"
        )

        embed = discord.Embed(
            title=f"{emoji} {row['name']}",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📥 How Obtained",
            value=row["description"],
            inline=False
        )

        embed.add_field(name="💰 Cost", value=cost)
        embed.add_field(name="🎚️ Rarity", value=row["rarity"])
        embed.add_field(name="📦 Type", value=row["type"])

        await interaction.followup.send(embed=embed)

    # ============================================================
    # /items search (UPDATED)
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

        emoji = (
            f"<:{row['emoji_name']}:{row['emoji_id']}>"
            if row["emoji_id"] else "⬜"
        )

        cost = (
            "Not Purchasable"
            if row["price"] == 0
            else f"${row['price']:,}"
        )

        purchase_limit = (
            "N/A"
            if not row["purchase_limit"] or row["purchase_limit"] == 0
            else str(row["purchase_limit"])
        )

        embed = discord.Embed(
            title=f"{emoji} {row['name']}",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="📥 How Obtained",
            value=row["description"],
            inline=False
        )

        embed.add_field(name="💰 Cost", value=cost)
        embed.add_field(name="🎚️ Rarity", value=row["rarity"])
        embed.add_field(name="📦 Type", value=row["type"])
        embed.add_field(name="🔁 Tradable", value="Yes" if row["tradable"] else "No")
        embed.add_field(name="🛒 Purchasable", value="Yes" if row["purchasable"] else "No")
        embed.add_field(name="🎁 Perk Granted", value=perk_type or "None")
        embed.add_field(name="💸 Purchase Limit", value=purchase_limit)


        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Items(bot))
