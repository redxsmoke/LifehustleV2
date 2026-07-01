import discord
import asyncio
import random
from db.connection import get_pool

# Item IDs
SMOKE_BOMB_ID = 12
CORRUPT_COP_ID = 13


class PoliceItemView(discord.ui.View):
    """
    Universal police item selection UI.
    Used by ALL crime games:
    - Vault Robbery
    - GTA
    - Future crimes
    """

    def __init__(self, controller, user_items):
        super().__init__(timeout=20)  # ⏳ 20-second timeout
        self.controller = controller
        self.user_items = user_items

        self.choice_made = asyncio.Event()
        self.selected_option = "chance"  # default if timeout

        # Add buttons based on inventory
        if self.user_items.get(SMOKE_BOMB_ID, 0) > 0:
            self.add_item(UseSmokeBombButton())

        if self.user_items.get(CORRUPT_COP_ID, 0) > 0:
            self.add_item(UseCorruptCopButton())

        self.add_item(TakeChancesButton())

    async def on_timeout(self):
        """
        If user does not choose within 20 seconds,
        auto-select "Take My Chances".
        """
        if not self.choice_made.is_set():
            self.selected_option = "chance"
            self.choice_made.set()

    async def wait_for_choice(self):
        """
        Wait for the user to choose OR timeout.
        """
        try:
            await asyncio.wait_for(self.choice_made.wait(), timeout=20)
        except asyncio.TimeoutError:
            self.selected_option = "chance"
            self.choice_made.set()

    async def finalize_choice(self, interaction):
        """
        Executes the police response based on selected option.
        """
        controller = self.controller

        # ============================================================
        # SMOKE BOMB → vanish → police search → guaranteed escape
        # ============================================================
        if self.selected_option == "smoke":
            controller.outcome = "success"
            controller.robbery_complete.set()

            await controller.channel.send(
                embed=discord.Embed(
                    title="💨 Vanished!",
                    description="The suspect disappears into the smoke like a magician who owes child support.",
                    color=0x95A5A6
                )
            )
            await asyncio.sleep(5)

            await controller.channel.send(
                embed=discord.Embed(
                    title="🚨 Police Arriving!",
                    description="The police rush in, coughing like they just tried vaping for the first time.",
                    color=0xE74C3C
                )
            )
            await asyncio.sleep(5)

            FUNNY_SEARCH_LINES = [
                "They squint into the smoke like boomers trying to read a tiny phone screen.",
                "One officer waves his flashlight around like he's directing airplane traffic.",
                "They cough dramatically, hoping someone will offer them workers’ comp."
            ]
            random.shuffle(FUNNY_SEARCH_LINES)

            vault_spots = [
                ("📦", "Behind the storage crates"),
                ("🗄️", "Inside the filing cabinet"),
                ("🚪", "Behind the maintenance door"),
                ("🧯", "Next to the fire extinguisher"),
                ("🪜", "Up on the ladder platform")
            ]
            searched = random.sample(vault_spots, 3)

            for idx, (emoji, desc) in enumerate(searched):
                await controller.channel.send(
                    embed=discord.Embed(
                        title=f"🔍 Police Search: {emoji} {desc}",
                        description=FUNNY_SEARCH_LINES[idx],
                        color=0x3498DB
                    )
                )
                await asyncio.sleep(5)

            await controller.channel.send(
                embed=discord.Embed(
                    title="💨 The thief Escaped!",
                    description="The police forgot to bring their gas masks and left the scene punching air.",
                    color=0x2ECC71
                )
            )

            await controller.log_escape()
            controller.stop()
            return

        # ============================================================
        # CORRUPT COP → instant escape
        # ============================================================
        if self.selected_option == "corrupt":
            controller.outcome = "success"
            controller.robbery_complete.set()

            await controller.channel.send(
                embed=discord.Embed(
                    title="🍩 The thief Escaped!",
                    description="The thief's cop buddy brought donuts for everyone just as the police were about to respond.",
                    color=0x2ECC71
                )
            )
            await controller.log_escape()
            controller.stop()
            return

        # ============================================================
        # TAKE MY CHANCES → continue hide sequence
        # ============================================================
        from police.police_reported_logic.hide_engine import start_hide_sequence
        await start_hide_sequence(controller, interaction)


# ============================================================
# BUTTONS
# ============================================================

class UseSmokeBombButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Use Smoke Bomb", emoji="💨", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction):
        view: PoliceItemView = self.view

        if interaction.user.id != view.controller.user_id:
            return await interaction.response.send_message("This isn't your robbery.", ephemeral=True)

        await consume_item(view.controller.user_id, view.controller.guild_id, SMOKE_BOMB_ID)

        view.selected_option = "smoke"
        view.choice_made.set()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="💨 Smoke Bomb Deployed",
                description="You yeet a smoke bomb so hard it looks like the building is vaping.",
                color=0x95A5A6
            ),
            view=None
        )


class UseCorruptCopButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Use Corrupt Cop", emoji="🍩", style=discord.ButtonStyle.green)

    async def callback(self, interaction):
        view: PoliceItemView = self.view

        if interaction.user.id != view.controller.user_id:
            return await interaction.response.send_message("This isn't your robbery.", ephemeral=True)

        await consume_item(view.controller.user_id, view.controller.guild_id, CORRUPT_COP_ID)

        view.selected_option = "corrupt"
        view.choice_made.set()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🍩 Corrupt Cop Activated",
                description="Your cop contact is handling things...",
                color=0x2ECC71
            ),
            view=None
        )


class TakeChancesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Take My Chances", emoji="🎲", style=discord.ButtonStyle.red)

    async def callback(self, interaction):
        view: PoliceItemView = self.view

        if interaction.user.id != view.controller.user_id:
            return await interaction.response.send_message("This isn't your robbery.", ephemeral=True)

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


# ============================================================
# DB HELPER
# ============================================================

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
