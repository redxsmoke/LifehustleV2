import discord
import asyncio
from db.connection import get_pool

SMOKE_BOMB_ID = 12
CORRUPT_COP_ID = 13


class PoliceItemView(discord.ui.View):
    """
    UI shown AFTER police are alerted but BEFORE hide sequence.
    Allows the robber to use Smoke Bomb, Corrupt Cop, or Take My Chances.
    """

    def __init__(self, vault_view, user_items):
        super().__init__(timeout=10)

        self.vault_view = vault_view
        self.user_items = user_items  # dict: {item_id: quantity}
        self.choice_made = asyncio.Event()
        self.selected_option = "chance"  # default if timeout

        # Add buttons based on inventory
        if self.user_items.get(SMOKE_BOMB_ID, 0) > 0:
            self.add_item(UseSmokeBombButton())

        if self.user_items.get(CORRUPT_COP_ID, 0) > 0:
            self.add_item(UseCorruptCopButton())

        # Always add "Take My Chances"
        self.add_item(TakeChancesButton())

    async def on_timeout(self):
        # Auto-select "Take My Chances"
        if not self.choice_made.is_set():
            self.selected_option = "chance"
            self.choice_made.set()


# ------------------------------------------------------------
# BUTTONS
# ------------------------------------------------------------

class UseSmokeBombButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Use Smoke Bomb",
            style=discord.ButtonStyle.blurple
        )

    async def callback(self, interaction: discord.Interaction):
        view: PoliceItemView = self.view

        if interaction.user.id != view.vault_view.user_id:
            return await interaction.response.send_message(
                "This isn't your robbery.", ephemeral=True
            )

        # Deduct item
        await consume_item(view.vault_view.user_id, view.vault_view.guild_id, SMOKE_BOMB_ID)

        view.vault_view.smoke_bomb_used = True
        view.selected_option = "smoke"
        view.choice_made.set()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="💨 Used Smoke Bomb",
                description="You deployed a smoke bomb!",
                color=0x95A5A6
            ),
            view=None
        )


class UseCorruptCopButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Use Corrupt Cop",
            style=discord.ButtonStyle.green
        )

    async def callback(self, interaction: discord.Interaction):
        view: PoliceItemView = self.view

        if interaction.user.id != view.vault_view.user_id:
            return await interaction.response.send_message(
                "This isn't your robbery.", ephemeral=True
            )

        # Deduct item
        await consume_item(view.vault_view.user_id, view.vault_view.guild_id, CORRUPT_COP_ID)

        view.vault_view.corrupt_cop_used = True
        view.selected_option = "corrupt"
        view.choice_made.set()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🍩 Used Corrupt Cop",
                description="Your cop contact is handling things...",
                color=0x2ECC71
            ),
            view=None
        )


class TakeChancesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Take My Chances",
            style=discord.ButtonStyle.red
        )

    async def callback(self, interaction: discord.Interaction):
        view: PoliceItemView = self.view

        if interaction.user.id != view.vault_view.user_id:
            return await interaction.response.send_message(
                "This isn't your robbery.", ephemeral=True
            )

        view.selected_option = "chance"
        view.choice_made.set()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🎲 Taking Your Chances",
                description="You're facing the police head-on.",
                color=0xE67E22
            ),
            view=None
        )


# ------------------------------------------------------------
# DB HELPER
# ------------------------------------------------------------

async def consume_item(user_id: int, guild_id: int, item_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE user_items
            SET quantity = quantity - 1
            WHERE discord_id = $1
              AND guild_id = $2
              AND item_id = $3
              AND quantity > 0
        """, user_id, guild_id, item_id)
