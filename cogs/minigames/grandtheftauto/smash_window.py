import discord
import asyncio
import random
import logging

from police.police_reported_logic.police_flow_controller import PoliceFlowController
from police.police_reported_logic.universal_snitch_system import start_snitch_flow

from cogs.minigames.grandtheftauto.stage2_hotwire import start_gta_stage2

logger = logging.getLogger("crime.gta.smashwindow")
logger.setLevel(logging.DEBUG)


class SmashWindowView(discord.ui.View):
    def __init__(self, user_id: int, victim: discord.Member, bot):
        super().__init__(timeout=10)
        self.user_id = user_id
        self.victim = victim
        self.bot = bot

        self.message: discord.Message | None = None
        self.ready_to_smash = False
        self.smashed = False
        self.loud_break_triggered = False

        self.smash_button = SmashButton(self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def start_sequence(self, message: discord.Message):
        self.message = message

        try:
            # Initial phase: no button shown
            embed = discord.Embed(
                title="💥 Window Breach Sequence",
                description=(
                    "You're preparing to break the window without drawing attention.\n"
                    "Stay focused.\n\n"
                    "The perfect moment is approaching..."
                ),
                color=discord.Color.orange()
            )
            await message.edit(embed=embed, view=None)

            # Prime window timing (unchanged)
            await asyncio.sleep(random.uniform(1.5, 3.5))

            self.ready_to_smash = True

            # Show smash button ONLY during prime window
            self.clear_items()
            self.add_item(self.smash_button)

            embed = discord.Embed(
                title="💥 Silent Opportunity",
                description=(
                    "**This is your moment.**\n"
                    "Break the window *quietly*.\n\n"
                    "Tap the button immediately to keep the noise down."
                ),
                color=discord.Color.green()
            )
            await message.edit(embed=embed, view=self)

            # Prime window duration (unchanged)
            await asyncio.sleep(1.5)

            if not self.smashed and not self.loud_break_triggered:
                self.loud_break_triggered = True
                await self.handle_loud_break()

        except Exception as e:
            logger.exception(f"[start_sequence] ERROR: {e}")

    async def handle_quiet_break(self):
        try:
            embed = discord.Embed(
                title="🤫 Silent Break",
                description=(
                    "Perfect timing.\n"
                    "No one heard a thing.\n\n"
                    "Proceeding to Stage 2..."
                ),
                color=discord.Color.green()
            )

            if self.message:
                await self.message.edit(embed=embed, view=None)

            for child in self.children:
                child.disabled = True

            self.stop()

            await start_gta_stage2(
                self.message.channel,
                self.bot,
                self.victim,
                self.user_id
            )

        except Exception as e:
            logger.exception(f"[handle_quiet_break] ERROR: {e}")

    async def handle_loud_break(self):
        try:
            embed = discord.Embed(
                title="🔊 Car Alarm Activated",
                description=(
                    "Your timing was off.\n"
                    "The window shattered loudly and it set off the car alarm.\n\n"
                    "The game has ended.."
                ),
                color=discord.Color.red()
            )

            if self.message:
                await self.message.edit(embed=embed, view=None)

            for child in self.children:
                child.disabled = True

            self.stop()

            await trigger_noise_broadcast(
                self.message.channel,
                self.victim,
                self.user_id
            )

        except Exception as e:
            logger.exception(f"[handle_loud_break] ERROR: {e}")

    async def on_timeout(self):
        try:
            if not self.smashed and not self.loud_break_triggered:
                self.loud_break_triggered = True
                await self.handle_loud_break()
        except Exception as e:
            logger.exception(f"[on_timeout] ERROR: {e}")


class SmashButton(discord.ui.Button):
    def __init__(self, parent_view: SmashWindowView):
        super().__init__(label="💥 Smash Window", style=discord.ButtonStyle.danger)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        try:
            if interaction.user.id != self.parent_view.user_id:
                return await interaction.response.send_message(
                    "This isn't your break‑in.", ephemeral=True
                )

            for child in self.parent_view.children:
                child.disabled = True

            await interaction.response.defer()
            self.parent_view.smashed = True

            if self.parent_view.ready_to_smash:
                await self.parent_view.handle_quiet_break()
            else:
                if not self.parent_view.loud_break_triggered:
                    self.parent_view.loud_break_triggered = True
                    await self.parent_view.handle_loud_break()

        except Exception as e:
            logger.exception(f"[SmashButton.callback] ERROR: {e}")
            try:
                await interaction.response.send_message("❌ Error smashing window.", ephemeral=True)
            except Exception:
                pass


async def trigger_noise_broadcast(
    channel: discord.TextChannel,
    victim: discord.Member,
    criminal_id: int
):
    try:
        controller = PoliceFlowController(
            user_id=criminal_id,
            guild_id=victim.guild.id,
            channel=channel,
            crime_type="grand_theft_auto",
            stolen_amount=None,
            company_name=None,
        )

        await start_snitch_flow(controller, channel)

    except Exception as e:
        logger.exception(f"[trigger_noise_broadcast] ERROR: {e}")
