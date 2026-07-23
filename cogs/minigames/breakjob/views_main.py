import discord
import random
import asyncio
import logging
from datetime import timedelta, datetime

from db.connection import get_pool

from police.police_reported_logic.police_flow_controller import PoliceFlowController
from police.police_reported_logic.intimidation_engine import process_snitch as handle_universal_snitch
from police.police_reported_logic.police_items import PoliceItemView
from police.police_reported_logic.universal_snitch_system import UniversalSnitchView
from police.police_reported_logic.universal_snitch_system import CRIME_TEXT


from .engine import VaultGame   

COLOR_PRIMARY = 0x5865F2

logger = logging.getLogger("crime.breakjob")
logger.setLevel(logging.ERROR)


# ============================================================
# VAULT GUESS MODAL
# ============================================================

class VaultGuessModal(discord.ui.Modal):
    def __init__(self, view: "VaultGameView"):
        super().__init__(title="🔢 Enter Vault Code")
        self.view = view

        self.guess = discord.ui.TextInput(
            label="Enter a 3-digit code",
            max_length=3,
            required=True
        )
        self.add_item(self.guess)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.view.has_snitched or self.view.snitch_disabled:
                return await interaction.response.send_message(
                    "Someone snitched. The vault is locked down. You can't enter the code anymore.",
                    ephemeral=True
                )

            result = self.view.game.check_guess(self.guess.value)

            await interaction.response.defer(ephemeral=True)

            if result == "unlocked":
                self.view.outcome = "success"
                cash, xp = await self.view.apply_success_rewards(interaction)

                await self.view.channel.send(
                    embed=discord.Embed(
                        title="💰 Vault Cracked",
                        description=(
                            f"You made off with **${cash/100:,.2f}**.\n"
                            f"XP Bonus: {xp}"
                        ),
                        color=discord.Color.green()
                    )
                )

                self.view.controller.stolen_amount = cash
                self.view.stop()
                return

            elif result == "locked_out":
                self.view.outcome = "failure"

                await self.view.channel.send(
                    embed=discord.Embed(
                        title="🚨 Vault Locked Out",
                        description="You failed to crack the vault. The police may get involved.",
                        color=0xF04747,
                    )
                )

                user_items = await self.view.controller.get_user_items()
                police_view = PoliceItemView(self.view.controller, user_items)

                msg = await self.view.channel.send(
                    embed=discord.Embed(
                        title="🚨 The vault autolocked and alerted the Police!",
                        description="⚠️ Choose your move! You have 20 seconds before the police leave the station!",
                        color=0xE74C3C
                    ),
                    view=police_view
                )

                await police_view.wait_for_choice()

                if police_view.selected_option == "chance":
                    await self.view.channel.send(
                        embed=discord.Embed(
                            title="🚨 The police grab their donuts and head to their patrol cars!",
                            description="They stop for coffee on the way!",
                            color=0xE74C3C
                        )
                    )
                    await asyncio.sleep(3)

                await police_view.finalize_choice(interaction)
                self.view.stop()
                return

            else:
                await self.view.channel.send(result)

        except Exception:
            logger.exception("VaultGuessModal.on_submit crashed")
            try:
                await interaction.followup.send(
                    "❌ Error processing your vault guess.",
                    ephemeral=True
                )
            except Exception:
                pass


# ============================================================
# VAULT GAME VIEW (Universal Snitch System)
# ============================================================

class VaultGameView(discord.ui.View):
    def __init__(self, user_id, bot, channel, guild_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bot = bot
        self.channel = channel
        self.guild_id = guild_id

        self.game = VaultGame()
        self.outcome = None

        # Universal snitch controller
        self.controller = PoliceFlowController(
            user_id=self.user_id,
            guild_id=self.guild_id,
            channel=self.channel,
            crime_type="vault",
            stolen_amount=None,
            company_name=None,
        )

        # Vault still uses these flags
        self.snitch_disabled = False
        self.has_snitched = False

        # Track witness votes
        self.snitchers = set()
        self.no_snitchers = set()

        # Send universal snitch buttons
        asyncio.create_task(self.send_snitch_buttons())

    async def send_snitch_buttons(self):
        view = UniversalSnitchView(
            controller=self.controller,
            channel=self.channel,
            crime_owner_id=self.user_id,
            lockout_target=self
        )

        msg = await self.channel.send(
            embed=discord.Embed(
                title=CRIME_TEXT["vault"]["witness_title"],
                description=CRIME_TEXT["vault"]["witness_description"],
                color=discord.Color.orange()
            ),
            view=view
        )

        view.message = msg

    async def apply_success_rewards(self, interaction):
        try:
            pool = get_pool()

            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT o.wage_per_shift, o.xp_per_shift
                    FROM user_occupations uo
                    JOIN cd_occupations o ON o.cd_occupation_id = uo.cd_occupation_id
                    WHERE uo.discord_id = $1
                      AND uo.guild_id = $2
                      AND uo.employment_end_date IS NULL
                """, self.user_id, interaction.guild.id)

                if not row:
                    await interaction.channel.send("⚠ Error: Could not determine your occupation rewards.")
                    return 0, 0

                wage = row["wage_per_shift"]
                xp_per = row["xp_per_shift"]

                cash = wage * random.randint(100, 150)
                xp = xp_per * random.randint(10, 15)

                await conn.execute("""
                    UPDATE users
                    SET checking_account_balance = checking_account_balance + $1,
                        xp = xp + $2
                    WHERE discord_id = $3 AND guild_id = $4
                """, cash, xp, self.user_id, interaction.guild.id)

            return cash, xp

        except Exception:
            logger.exception("apply_success_rewards crashed")
            return 0, 0

    @discord.ui.button(label="Enter Safe Code", style=discord.ButtonStyle.blurple)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if self.has_snitched or self.snitch_disabled:
                return await interaction.response.send_message(
                    "Someone snitched. The vault is locked down. You can't enter the code anymore.",
                    ephemeral=True
                )

            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "This isn't your vault to crack!",
                    ephemeral=True
                )

            await interaction.response.send_modal(VaultGuessModal(self))

        except Exception:
            logger.exception("Enter Safe Code button crashed")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Something went wrong opening the vault code modal.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Something went wrong opening the vault code modal.",
                        ephemeral=True
                    )
            except Exception:
                pass
