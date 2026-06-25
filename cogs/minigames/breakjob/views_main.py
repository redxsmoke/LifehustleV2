import asyncio
import discord

from .engine import VaultGame
from .views_hide import HideOnlyView
from .views_snitch import handle_snitch
from .police import handle_police_outcome
from .rewards import apply_success_rewards
from .views_police_items import PoliceItemView
from db.connection import get_pool

from utils.crime_system import (
    log_crime,
    get_user_company
)

COLOR_PRIMARY = 0x2ECC71


class VaultGuessModal(discord.ui.Modal, title="🔢 Enter Vault Code"):
    guess = discord.ui.TextInput(
        label="Enter a 3-digit code",
        max_length=3,
        required=True
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        result = self.view.game.check_guess(self.guess.value)

        await interaction.response.defer(ephemeral=True)

        # SUCCESS
        if result == "unlocked":
            self.view.outcome = "success"
            cash, xp = await apply_success_rewards(interaction, self.view.user_id)

            await self.view.channel.send(
                embed=discord.Embed(
                    title="🔓 Vault Cracked",
                    description=(
                        f"💰You made off with **${cash/100:,.2f}**.\n"
                        f"📈XP Bonus: {xp}"
                    ),
                    color=discord.Color.green()
                )
            )

            # --- CRIME LOGGING: SUCCESSFUL ROBBERY ---
            pool = get_pool()
            company_name, occupation_name = await get_user_company(self.view.guild_id, self.view.user_id)

            await log_crime(
                guild_id=self.view.guild_id,
                perpetrator_id=self.view.user_id,
                crime_type="vault robbery",
                crime_description=f"Successful vault robbery at {company_name}",
                clue_description=None,      # UPDATED
                evidence_list=[],           # UPDATED
                status="unsolved",
                location=company_name
            )

            self.view.robbery_complete.set()
            self.view.stop()
            return

        # LOCKED OUT → POLICE ITEM CHOICE FIRST
        if result == "locked_out":
            self.view.outcome = "failure"
            await self.view.start_police_item_choice(interaction)
            return

        # FEEDBACK
        await self.view.channel.send(result)


class VaultGameView(discord.ui.View):
    """
    Main controller for the BreakJob robbery minigame.
    """

    def __init__(self, user_id: int, bot, channel: discord.TextChannel):
        super().__init__(timeout=120)

        self.user_id = user_id
        self.bot = bot
        self.channel = channel
        self.guild_id = channel.guild.id

        self.game = VaultGame()

        self.snitched = False
        self.snitcher_id = None

        self.hide_spot_chosen = False
        self.chosen_spot = None

        self.outcome = None
        self.robbery_complete = asyncio.Event()

        # NEW FLAGS
        self.smoke_bomb_used = False
        self.corrupt_cop_used = False

        # 12 hiding spots
        self.hide_spots = [
            ("🗄️", "behind the storage shelves"),
            ("🧺", "inside the supply closet"),
            ("🪑", "under the desk"),
            ("🛠️", "in the maintenance room"),
            ("📦", "behind the delivery crates"),
            ("🚪", "inside the loading dock"),
            ("📦", "under a pile of boxes"),
            ("🧥", "behind the office curtains"),
            ("🗑️", "inside the trash bin"),
            ("🔥", "in the boiler room"),
            ("🧣", "behind the coat rack"),
            ("🌬️", "inside the ventilation duct"),
        ]

    # ------------------------------------------------------------
    # BUTTONS
    # ------------------------------------------------------------

    @discord.ui.button(label="Enter Code", style=discord.ButtonStyle.green)
    async def enter_code(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your robbery.", ephemeral=True
            )

        await interaction.response.send_modal(VaultGuessModal(self))

    @discord.ui.button(label="Snitch", style=discord.ButtonStyle.red)
    async def snitch(self, interaction: discord.Interaction, button):
        await handle_snitch(self, interaction)

    # ------------------------------------------------------------
    # POLICE ITEM CHOICE
    # ------------------------------------------------------------

    async def start_police_item_choice(self, interaction):
        """
        Called when:
        - vault fails (locked_out)
        - snitch confirmed (no intimidation)
        BEFORE hide sequence.
        """

        # 1. Police Alert Message
        if not self.snitched:
            await self.channel.send(
                embed=discord.Embed(
                    title="🚨 Police Alerted!",
                    description="The police are on their way!",
                    color=0xF04747
                )
            )

        # 2. Fetch user items
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT item_id, quantity
                FROM user_items
                WHERE discord_id = $1 AND guild_id = $2
            """, self.user_id, self.guild_id)

        user_items = {row["item_id"]: row["quantity"] for row in rows}

        # 3. Show item choice UI
        view = PoliceItemView(self, user_items)
        msg = await self.channel.send(
            embed=discord.Embed(
                title="⚠️ Choose Your Move",
                description="The police are closing in. Make your choice.",
                color=0xE67E22
            ),
            view=view
        )

        # 4. Wait for choice or timeout
        await view.choice_made.wait()

        # 5. Branch based on choice
        if view.selected_option == "corrupt":
            self.outcome = "success"
            self.robbery_complete.set()

            await asyncio.sleep(5)

            await self.channel.send(
                embed=discord.Embed(
                    title="🍩 You Escaped!",
                    description="Your cop contact brought in donuts just as the police were about to leave. This crime will not be reported.\nYou escaped safely.",
                    color=0x2ECC71
                )
            )

            self.stop()
            return

        # Smoke Bomb or Take My Chances → continue to hide UI
        await self.start_hide_sequence(interaction)

    # ------------------------------------------------------------
    # HIDE SEQUENCE
    # ------------------------------------------------------------

    async def start_hide_sequence(self, interaction):
        await self.channel.send(
            "Choose a hiding spot before the police arrive!",
            view=HideOnlyView(self)
        )

        asyncio.create_task(self.handle_hide_timeout())

    async def handle_hide_timeout(self):
        await asyncio.sleep(10)

        if self.hide_spot_chosen or self.robbery_complete.is_set():
            return

        # No hide chosen → automatic arrest
        self.chosen_spot = None

        # --- CRIME LOGGING: TIMEOUT ARREST ---
        company_name, occupation_name = await get_user_company(self.guild_id, self.user_id)

        await log_crime(
            guild_id=self.guild_id,
            perpetrator_id=self.user_id,
            crime_type="vault robbery",
            crime_description=f"Vault robbery attempt at {company_name}",
            clue_description=None,      # UPDATED
            evidence_list=[],           # UPDATED
            status="solved",
            location=company_name
        )

        await handle_police_outcome(self, None, None)

    # ------------------------------------------------------------
    # POLICE SEARCH
    # ------------------------------------------------------------

    async def trigger_police_search(self, interaction, spot):
        if self.robbery_complete.is_set():
            return

        await asyncio.sleep(5)

        # Smoke Bomb guarantees escape
        if self.smoke_bomb_used:
            self.outcome = "success"
            self.robbery_complete.set()

            await self.channel.send(
                embed=discord.Embed(
                    title="💨 Criminal Escaped!",
                    description="The police didn’t bring their gas masks and left. The thief escaped.",
                    color=0x2ECC71
                )
            )

            # --- CRIME LOGGING: SMOKE BOMB ESCAPE ---
            company_name, occupation_name = await get_user_company(self.guild_id, self.user_id)

            await log_crime(
                guild_id=self.guild_id,
                perpetrator_id=self.user_id,
                crime_type="vault robbery",
                crime_description=f"Smoke bomb escape from {company_name}",
                clue_description=None,      # UPDATED
                evidence_list=[],           # UPDATED
                status="unsolved",
                location=company_name
            )

            return

        # Otherwise normal police search
        await handle_police_outcome(self, interaction, spot)

    # ------------------------------------------------------------
    # TIMEOUT
    # ------------------------------------------------------------

    async def on_timeout(self):
        if not self.robbery_complete.is_set():
            await self.channel.send("⏳ The robbery timed out.")
        self.stop()
