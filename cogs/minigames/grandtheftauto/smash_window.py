import discord
import asyncio
import random
import logging

logger = logging.getLogger("crime.gta.smashwindow")
logger.setLevel(logging.ERROR)


class SmashWindowView(discord.ui.View):
    def __init__(self, user_id: int, victim: discord.Member, stage2_callback, stage1_view):
        super().__init__(timeout=20)
        self.user_id = user_id
        self.victim = victim
        self.stage2_callback = stage2_callback

        # ⭐ REQUIRED FOR SNITCH DISABLING
        self.stage1_view = stage1_view

        # Optimized slider settings
        self.bar_length = 12
        self.marker_pos = 0
        self.direction = 1
        self.speed = 2
        self.tick_rate = 0.1

        quiet_start = random.randint(1, 7)
        quiet_end = quiet_start + random.randint(2, 4)
        self.quiet_zone = range(quiet_start, min(quiet_end, self.bar_length - 1))

        self.message: discord.Message | None = None
        self.smash_pressed = False

        self.add_item(SmashButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def start_animation(self, message: discord.Message):
        self.message = message

        try:
            for _ in range(200):
                if self.smash_pressed:
                    return

                self.marker_pos += self.direction * self.speed

                if self.marker_pos >= self.bar_length - 1:
                    self.marker_pos = self.bar_length - 1
                    self.direction = -1
                elif self.marker_pos <= 0:
                    self.marker_pos = 0
                    self.direction = 1

                await self.update_embed()
                await asyncio.sleep(self.tick_rate)

        except Exception as e:
            logger.exception("Error in smash window animation: %s", e)

    async def update_embed(self):
        try:
            if not self.message:
                return

            bar_list = ["🟩" if i in self.quiet_zone else "░" for i in range(self.bar_length)]
            bar_list[self.marker_pos] = "🔘"
            bar = "".join(bar_list)

            embed = discord.Embed(
                title="💥 Smash Window Minigame",
                description=(
                    "Time your smash to avoid making noise!\n\n"
                    "**You have 20 seconds to break the window.**\n\n"
                    f"`{bar}`"
                ),
                color=discord.Color.orange()
            )

            await self.message.edit(embed=embed)

        except Exception as e:
            logger.exception("SmashWindow.update_embed error: %s", e)

    async def on_timeout(self):
        try:
            if not self.smash_pressed:
                await self.handle_loud_break()
        except Exception as e:
            logger.exception("SmashWindow.on_timeout error: %s", e)

    async def handle_quiet_break(self, interaction: discord.Interaction):
        try:
            embed = discord.Embed(
                title="🤫 Silent Break!",
                description=(
                    "You smashed the window **quietly**.\n"
                    "No one noticed.\n\n"
                    "Proceeding to Stage 2..."
                ),
                color=discord.Color.green()
            )

            if self.message:
                await self.message.edit(embed=embed, view=None)

            # ⭐ FIX: pass correct arguments
            await self.stage2_callback(interaction, interaction.client, self.victim)

        except Exception as e:
            logger.exception("Error in handle_quiet_break: %s", e)

    async def handle_loud_break(self, interaction: discord.Interaction):
        try:
            embed = discord.Embed(
                title="🔊 Loud Break!",
                description=(
                    "You smashed the window **loudly**.\n"
                    "The neighborhood heard it!\n\n"
                    "Broadcasting alert..."
                ),
                color=discord.Color.red()
            )

            if self.message:
                await self.message.edit(embed=embed, view=None)

            from .stage1 import trigger_noise_broadcast

            # ⭐ FIX: GTAReportView now requires stage1_view
            await trigger_noise_broadcast(
                interaction.channel,
                self.victim,
                self.user_id,
                self.stage1_view
            )

            # ⭐ FIX: pass correct args
            await self.stage2_callback(interaction, interaction.client, self.victim)

        except Exception as e:
            logger.exception("Error in handle_loud_break: %s", e)


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

            try:
                await interaction.response.defer()
            except:
                pass

            self.parent_view.smash_pressed = True

            if self.parent_view.marker_pos in self.parent_view.quiet_zone:
                await self.parent_view.handle_quiet_break(interaction)
            else:
                await self.parent_view.handle_loud_break(interaction)

        except Exception as e:
            logger.exception(f"SmashButton.callback outer error: {e}")
            try:
                await interaction.response.send_message("❌ Error smashing window.", ephemeral=True)
            except:
                pass


async def trigger_noise_broadcast(
    channel: discord.TextChannel,
    victim: discord.Member,
    criminal_id: int,
    stage1_view
):
    try:
        embed = discord.Embed(
            title="🚨 Vehicle Break-In Detected!",
            description=(
                f"Someone is trying to break into {victim.mention}'s vehicle!\n\n"
                "You have **15 seconds** to report this crime.\n\n"
                "🔴 Report to Police — lose street cred\n"
                "🟢 I Ain't No Snitch — gain street cred"
            ),
            color=discord.Color.red()
        )

        from .stage1 import GTAReportView

        # ⭐ FIX: GTAReportView now requires stage1_view
        view = GTAReportView(victim, criminal_id, stage1_view)
        msg = await channel.send(embed=embed, view=view)
        view.message = msg

    except Exception as e:
        logger.exception("Error sending noise broadcast: %s", e)
