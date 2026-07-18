import discord
import asyncio
import random
import logging

from police.police_reported_logic.police_flow_controller import PoliceFlowController
from police.police_reported_logic.universal_snitch_system import start_snitch_flow

logger = logging.getLogger("crime.gta.smashwindow")
logger.setLevel(logging.DEBUG)


class SmashWindowView(discord.ui.View):
    def __init__(self, user_id: int, victim: discord.Member, stage2_callback):
        super().__init__(timeout=10)
        self.user_id = user_id
        self.victim = victim
        self.stage2_callback = stage2_callback

        self.message: discord.Message | None = None
        self.ready_to_smash = False
        self.smashed = False

        # ⭐ Prevent duplicate loud breaks
        self.loud_break_triggered = False

        self.add_item(SmashButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def start_sequence(self, message: discord.Message):
        self.message = message

        try:
            # Intro embed
            embed = discord.Embed(
                title="💥 Window Breach Sequence",
                description=(
                    "You're preparing to break the window without drawing attention.\n"
                    "Stay focused.\n\n"
                    "The perfect moment is approaching..."
                ),
                color=discord.Color.orange()
            )
            await message.edit(embed=embed)

            # Suspense delay
            await asyncio.sleep(random.uniform(1.5, 3.5))

            # Quiet smash window opens
            self.ready_to_smash = True

            embed = discord.Embed(
                title="💥 Silent Opportunity",
                description=(
                    "**This is your moment.**\n"
                    "Break the window *quietly*.\n\n"
                    "Tap the button **immediately** to keep the noise down."
                ),
                color=discord.Color.green()
            )
            await message.edit(embed=embed, view=self)

            # Reaction window
            await asyncio.sleep(0.6)

            # ⭐ Loud break only once
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

            await self.stage2_callback()

        except Exception as e:
            logger.exception(f"[handle_quiet_break] ERROR: {e}")

    async def handle_loud_break(self):
        try:
            embed = discord.Embed(
                title="🔊 Noise Detected",
                description=(
                    "Your timing was off.\n"
                    "The window shattered loudly — the neighborhood heard it.\n\n"
                    "Alerting witnesses..."
                ),
                color=discord.Color.red()
            )

            if self.message:
                await self.message.edit(embed=embed, view=None)

            await trigger_noise_broadcast(
                self.message.channel,
                self.victim,
                self.user_id
            )

            await self.stage2_callback()

        except Exception as e:
            logger.exception(f"[handle_loud_break] ERROR: {e}")

    async def on_timeout(self):
        try:
            # ⭐ Prevent timeout from triggering loud break twice
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

            await interaction.response.defer()
            self.parent_view.smashed = True

            # Quiet or loud break — but loud break only once
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
