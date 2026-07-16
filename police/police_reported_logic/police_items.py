import discord
import asyncio
import random
from db.connection import get_pool

# Item IDs
SMOKE_BOMB_ID = 12
CORRUPT_COP_ID = 13

# ============================================================
# POLICE ITEM VIEW FIRST
# ============================================================

class PoliceItemView(discord.ui.View):
    def __init__(self, controller, user_items):
        super().__init__(timeout=20)
        self.controller = controller
        self.user_items = user_items

        self.choice_made = asyncio.Event()
        self.selected_option = "chance"
        self.choice_finalized = False

        try:
            if self.user_items.get(SMOKE_BOMB_ID, 0) > 0:
                self.add_item(UseSmokeBombButton())

            if self.user_items.get(CORRUPT_COP_ID, 0) > 0:
                self.add_item(UseCorruptCopButton())

            self.add_item(TakeChancesButton())
        except Exception as e:
            asyncio.create_task(
                self.controller.channel.send(f"ERROR: PoliceItemView init → {e}")
            )

    async def on_timeout(self):
        if not self.choice_made.is_set():
            self.selected_option = "chance"
            self.choice_made.set()

    async def wait_for_choice(self):
        try:
            await asyncio.wait_for(self.choice_made.wait(), timeout=20)
        except asyncio.TimeoutError:
            self.selected_option = "chance"
            self.choice_made.set()

    async def finalize_choice(self, interaction):
        controller = self.controller

        if self.choice_finalized:
            return
        self.choice_finalized = True

        # SMOKE BOMB
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

            from police.police_reported_logic.hide_locations import HIDE_SPOTS
            FUNNY_SEARCH_LINES = [
                "They squint into the smoke like boomers trying to read a tiny phone screen.",
                "One officer waves his flashlight around like he's directing airplane traffic.",
                "They cough dramatically, hoping someone will offer them workers’ comp."
            ]
            random.shuffle(FUNNY_SEARCH_LINES)

            crime_type = controller.crime_type
            spots = HIDE_SPOTS.get(crime_type, HIDE_SPOTS.get("vault"))
            searched = random.sample(spots, 3)

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

            await controller.log_unsolved_crime()
            self.stop()
            return

        # CORRUPT COP
        if self.selected_option == "corrupt":
            controller.outcome = "success"
            controller.robbery_complete.set()

            await asyncio.sleep(5)
            await controller.channel.send(
                embed=discord.Embed(
                    title="🍩 The thief Escaped!",
                    description="The thief's cop buddy brought donuts for everyone just as the police were about to respond.",
                    color=0x2ECC71
                )
            )

            self.stop()
            return

        # TAKE CHANCES → hide engine
        from police.police_reported_logic.hide_engine import start_hide_sequence
        await start_hide_sequence(controller, interaction)

        self.stop()


# ============================================================
# BUTTONS SECOND
# ============================================================

class UseSmokeBombButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Use Smoke Bomb", emoji="💨", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction):
        view = self.view

        await interaction.response.defer()

        if interaction.user.id != view.controller.user_id:
            return await interaction.followup.send("This isn't your robbery.")

        await consume_item(view.controller.user_id, view.controller.guild_id, SMOKE_BOMB_ID)

        view.selected_option = "smoke"
        view.choice_made.set()

        await interaction.followup.edit_message(
            embed=discord.Embed(
                title="💨 Smoke Bomb Deployed",
                description="The suspect yeeted a smoke bomb so hard it looks like the building is vaping.",
                color=0x95A5A6
            ),
            view=None
        )


class UseCorruptCopButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Use Corrupt Cop", emoji="🍩", style=discord.ButtonStyle.green)

    async def callback(self, interaction):
        view = self.view

        await interaction.response.defer()

        if interaction.user.id != view.controller.user_id:
            return await interaction.followup.send("This isn't your robbery.")

        await consume_item(view.controller.user_id, view.controller.guild_id, CORRUPT_COP_ID)

        view.selected_option = "corrupt"
        view.choice_made.set()

        # 🔹 CHANGE: send a new message instead of editing the old one
        await interaction.followup.send(
            embed=discord.Embed(
                title="🍩 Corrupt Cop Activated",
                description="Your cop contact is handling things...",
                color=0x2ECC71
            )
        )

        # Escape message still sent via finalize_choice


class TakeChancesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Take My Chances", emoji="🎲", style=discord.ButtonStyle.red)

    async def callback(self, interaction):
        view = self.view

        await interaction.response.defer()

        if interaction.user.id != view.controller.user_id:
            return await interaction.followup.send("This isn't your robbery.")

        view.selected_option = "chance"
        view.choice_made.set()

        await interaction.followup.edit_message(
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
