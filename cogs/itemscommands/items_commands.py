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
                await self.show_my_items(interaction, interaction.user.id, interaction.guild_id, sort.value if sort else "rarity")

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
    # PAGINATION VIEW
    # ============================================================
    class InventoryView(discord.ui.View):
        def __init__(self, pages, user):
            super().__init__(timeout=60)
            self.pages = pages
            self.index = 0
            self.user = user

        async def interaction_check(self, interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                log.warning(f"[PAGINATION] Unauthorized user {interaction.user.id} attempted to use buttons.")
                return False
            return True

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
        async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                self.index = (self.index - 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.pages[self.index], view=self)
            except Exception as e:
                log.error(f"[PAGINATION] Previous button failed: {e}")

        @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                self.index = (self.index + 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.pages[self.index], view=self)
            except Exception as e:
                log.error(f"[PAGINATION] Next button failed: {e}")

    # ============================================================
    # /items my — HYBRID LAYOUT (10 PER PAGE) + ACTIVE FILTER
    # ============================================================
    async def show_my_items(self, interaction, user_id, guild_id, sort):
        try:
            async with self.bot.db.acquire(timeout=2) as conn:
                rows = await conn.fetch("""
                    SELECT ui.item_id, ui.quantity, ci.*
                    FROM user_items ui
                    JOIN cd_items ci ON ci.item_id = ui.item_id
                    WHERE ui.discord_id = $1
                    AND ui.guild_id = $2
                    AND ci.is_active = TRUE
                """, user_id, guild_id)
        except Exception as e:
            log.error(f"[MY ITEMS] DB fetch failed for user {user_id}: {e}")
            return await interaction.followup.send("❌ Failed to load your inventory.", ephemeral=True)

        if not rows:
            return await interaction.followup.send("📭 You don't own any active items.", ephemeral=True)

        # Sorting
        try:
            if sort == "name":
                rows = sorted(rows, key=lambda r: r["name"])
            elif sort == "type":
                rows = sorted(rows, key=lambda r: r["type"])
            else:
                rarity_order = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 5}
                rows = sorted(rows, key=lambda r: rarity_order.get(r["rarity"], 0), reverse=True)
        except Exception as e:
            log.error(f"[MY ITEMS] Sorting failed: {e}")

        # Pagination (10 per page)
        pages = []
        chunk = 10

        try:
            for i in range(0, len(rows), chunk):
                embed = discord.Embed(
                    title="🎒 Your Active Items",
                    description=f"Sorted by **{sort.capitalize()}**",
                    color=discord.Color.blurple()
                )

                text = ""

                for item in rows[i:i+chunk]:
                    rarity_square = RARITY_COLORS.get(item["rarity"], "⬜")
                    text += f"{rarity_square} **{item['name']} ×{item['quantity']}**\n"
                    text += f"{item['description']}\n\n"

                embed.description = text.strip()
                pages.append(embed)

        except Exception as e:
            log.error(f"[MY ITEMS] Pagination embed creation failed: {e}")
            return await interaction.followup.send("❌ Failed to build inventory pages.", ephemeral=True)

        # Hide pagination if only 1 page
        if len(pages) > 1:
            view = self.InventoryView(pages, interaction.user)
            await interaction.followup.send(embed=pages[0], view=view)
        else:
            await interaction.followup.send(embed=pages[0])

    # ============================================================
    # /items about
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
    # /items search — FIXED + PERK TYPE LOOKUP + ACTIVE FILTER
    # ============================================================
    async def search_item(self, interaction, query):
        try:
            async with self.bot.db.acquire(timeout=2) as conn:

                # If autocomplete was used → query is an item_id
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

                # Fetch perk type
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
