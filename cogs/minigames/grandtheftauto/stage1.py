import discord
import asyncio
import logging
import random
from db.connection import get_pool

logger = logging.getLogger("crime.gta.stage1")
logger.setLevel(logging.ERROR)


# ============================================================
# STREET CRED
# ============================================================

class ReportToPoliceButton(discord.ui.Button):
    def __init__(self, victim: discord.Member):
        super().__init__(label="🚨 Report to Police", style=discord.ButtonStyle.danger)
        self.victim = victim

    async def callback(self, interaction: discord.Interaction):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE user_stats
                    SET street_cred = street_cred - 10
                    WHERE discord_id = $1 AND guild_id = $2
                """, interaction.user.id, interaction.guild.id)

            embed = discord.Embed(
                title="🚨 You Reported the Crime",
                description="You snitched. **-10 street cred.**",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

            logger.info(f"[GTA] {interaction.user.id} reported vehicle theft on {self.victim.id}")

        except Exception as e:
            logger.exception("Error in ReportToPoliceButton: %s", e)
            try:
                await interaction.response.send_message("❌ Error reporting to police.", ephemeral=True)
            except Exception:
                pass


class NoSnitchButton(discord.ui.Button):
    def __init__(self, victim: discord.Member):
        super().__init__(label="😎 I Ain't No Snitch", style=discord.ButtonStyle.secondary)
        self.victim = victim

    async def callback(self, interaction: discord.Interaction):
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE user_stats
                    SET street_cred = street_cred + 10
                    WHERE discord_id = $1 AND guild_id = $2
                """, interaction.user.id, interaction.guild.id)

            embed = discord.Embed(
                title="😎 You Stayed Quiet",
                description="You kept your mouth shut. **+10 street cred.**",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

            logger.info(f"[GTA] {interaction.user.id} ignored vehicle theft on {self.victim.id}")

        except Exception as e:
            logger.exception("Error in NoSnitchButton: %s", e)
            try:
                await interaction.response.send_message("❌ Error processing street cred.", ephemeral=True)
            except Exception:
                pass


class GTAReportView(discord.ui.View):
    def __init__(self, victim: discord.Member, criminal_id: int):
        super().__init__(timeout=15)
        self.victim = victim
        self.criminal_id = criminal_id
        self.message: discord.Message | None = None

        self.add_item(ReportToPoliceButton(victim))
        self.add_item(NoSnitchButton(victim))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Criminal CANNOT interact with the report buttons
        if interaction.user.id == self.criminal_id:
            await interaction.response.send_message(
                "You cannot report your own crime.", ephemeral=True
            )
            return False

        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception as e:
            logger.exception("Error updating GTAReportView on timeout: %s", e)




# ============================================================
# KEYPAD GAME
# ============================================================

class GTAKeypadGame:
    def __init__(self):
        self.code = [random.randint(0, 9) for _ in range(3)]
        self.attempts = 0
        self.noise = 0.0

        logger.info(f"[Stage1] Keypad code generated: {self.code}")

    def check_guess(self, guess_str: str):
        if len(guess_str) != 3 or not guess_str.isdigit():
            return "invalid", None, False

        self.attempts += 1
        guess = [int(d) for d in guess_str]
        clues = []

        for i in range(3):
            if guess[i] == self.code[i]:
                clues.append("✅")
            elif guess[i] in self.code:
                clues.append("⚠️")
            else:
                clues.append("❌")

        clues_str = " ".join(clues)

        if guess == self.code:
            return "unlocked", clues_str, False

        self.noise += 20.0
        if self.noise > 100.0:
            self.noise = 100.0

        noise_full = self.noise >= 100.0
        return "clues", clues_str, noise_full


# ============================================================
# STAGE 1 ENTRY POINT
# ============================================================

async def start_gta_stage1(interaction: discord.Interaction, bot, victim: discord.Member):
    try:
        view = GTAStage1View(interaction.user.id, bot, victim, interaction.channel)

        embed = discord.Embed(
            title="🚗 GTA Stage 1 — Vehicle Heist",
            description=(
                f"You approach **{victim.mention}**'s vehicle.\n\n"
                "Choose how you want to proceed:\n\n"
                "🔢 Enter Car Code\n"
                "💥 Smash Window\n\n"
                "Wrong guesses increase noise by 20%.\n"
                "At 100% noise, a broadcast goes out."
            ),
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    except Exception as e:
        logger.exception("Error starting GTA Stage 1: %s", e)
        try:
            await interaction.response.send_message("❌ Error starting GTA Stage 1.", ephemeral=True)
        except Exception:
            pass
# ============================================================
# STAGE 1 VIEW (CHOICE: CAR CODE OR SMASH WINDOW)
# ============================================================

class GTAStage1View(discord.ui.View):
    def __init__(self, user_id: int, bot, victim: discord.Member, channel: discord.TextChannel):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.bot = bot
        self.victim = victim
        self.channel = channel
        self.broadcast_triggered = False

        self.add_item(EnterCarCodeButton(self))
        self.add_item(SmashWindowButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id


class EnterCarCodeButton(discord.ui.Button):
    def __init__(self, parent_view: GTAStage1View):
        super().__init__(label="🔢 Enter Car Code", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user_id:
            return await interaction.response.send_message(
                "This isn't your break‑in.", ephemeral=True
            )

        # Disable both buttons
        for child in self.parent_view.children:
            child.disabled = True

        # FIXED: ephemeral message must be edited via response.edit_message()
        try:
            await interaction.response.edit_message(view=self.parent_view)
        except Exception as e:
            logger.exception("Failed to edit ephemeral message in EnterCarCodeButton: %s", e)

        try:
            game = GTAKeypadGame()
            keypad_view = GTAKeypadView(
                user_id=self.parent_view.user_id,
                bot=self.parent_view.bot,
                victim=self.parent_view.victim,
                channel=self.parent_view.channel,
                game=game,
                stage1_view=self.parent_view
            )

            embed = discord.Embed(
                title="🔢 Vehicle Keypad",
                description=(
                    "Crack the **3-digit** keypad code.\n\n"
                    "**Enter Code:** `___`\n"
                    "**Noise Level:** 0%\n"
                    "**Attempts:** 0\n\n"
                    "✅ = Correct digit in the correct position\n"
                    "⚠️ = Digit exists in the code but in a different position\n"
                    "❌ = Digit not in the code\n"
                ),
                color=discord.Color.blue()
            )

            msg = await self.parent_view.channel.send(embed=embed, view=keypad_view)
            keypad_view.status_message = msg

            await interaction.followup.send(
                "Keypad initialized. Use the number pad below to enter the code.",
                ephemeral=True
            )

        except Exception as e:
            logger.exception("Error initializing keypad: %s", e)
            try:
                await interaction.followup.send("❌ Error initializing keypad.", ephemeral=True)
            except Exception:
                pass


class SmashWindowButton(discord.ui.Button):
    def __init__(self, parent_view: GTAStage1View):
        super().__init__(label="💥 Smash Window", style=discord.ButtonStyle.danger)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user_id:
            return await interaction.response.send_message(
                "This isn't your break‑in.", ephemeral=True
            )

        # Disable both buttons
        for child in self.parent_view.children:
            child.disabled = True

        # FIXED: ephemeral message must be edited via response.edit_message()
        try:
            await interaction.response.edit_message(view=self.parent_view)
        except Exception as e:
            logger.exception("Failed to edit ephemeral message in SmashWindowButton: %s", e)

        try:
            from .smash_window import SmashWindowView

            async def stage2_callback():
                try:
                    await start_stage2(interaction, self.parent_view.bot, self.parent_view.victim)
                except Exception as e:
                    logger.exception("Error in stage2_callback (SmashWindowButton): %s", e)

            view = SmashWindowView(
                user_id=self.parent_view.user_id,
                victim=self.parent_view.victim,
                stage2_callback=stage2_callback
            )

            embed = discord.Embed(
                title="💥 Smash Window Minigame",
                description=(
                    "Time your smash to avoid making noise!\n\n"
                    "**You have 20 seconds to break the window.**"
                ),
                color=discord.Color.orange()
            )

            msg = await self.parent_view.channel.send(embed=embed, view=view)
            await view.start_animation(msg)

            try:
                await interaction.response.defer()
            except Exception:
                pass

        except Exception as e:
            logger.exception("Error starting Smash Window minigame: %s", e)
            try:
                await interaction.followup.send("❌ Error starting Smash Window.", ephemeral=True)
            except Exception:
                pass


# ============================================================
# KEYPAD VIEW (NUMBER PAD + STATUS EMBED)
# ============================================================

class GTAKeypadView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        bot,
        victim: discord.Member,
        channel: discord.TextChannel,
        game: GTAKeypadGame,
        stage1_view: GTAStage1View
    ):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.bot = bot
        self.victim = victim
        self.channel = channel
        self.game = game
        self.stage1_view = stage1_view

        self.status_message: discord.Message | None = None
        self.buffer: str = ""
        self.last_clues: str | None = None
        self.broadcast_triggered: bool = stage1_view.broadcast_triggered

        # Keypad layout
        self.add_item(DigitButton("1", self))
        self.add_item(DigitButton("2", self))
        self.add_item(DigitButton("3", self))

        self.add_item(DigitButton("4", self))
        self.add_item(DigitButton("5", self))
        self.add_item(DigitButton("6", self))

        self.add_item(DigitButton("7", self))
        self.add_item(DigitButton("8", self))
        self.add_item(DigitButton("9", self))

        self.add_item(ClearButton(self))
        self.add_item(DigitButton("0", self))
        self.add_item(SubmitButton(self))

        # Smash Window inside keypad
        self.add_item(SmashWindowDuringCodeButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    async def update_status_embed(self):
        if not self.status_message:
            logger.error("update_status_embed called with no status_message")
            return

        enter_code_line = "`___`"
        if self.last_clues is not None:
            enter_code_line = self.last_clues

        noise_display = f"{self.game.noise:.0f}%"
        if self.game.noise > 100.0:
            noise_display = "100%"

        desc = (
            f"Crack the **3-digit** keypad code.\n\n"
            f"**Enter Code:** {enter_code_line}\n"
            f"**Noise Level:** {noise_display}\n"
            f"**Attempts:** {self.game.attempts}\n\n"
            "✅ = Correct digit in the correct position\n"
            "⚠️ = Digit exists in the code but in a different position\n"
            "❌ = Digit not in the code\n\n"
            f"Current Entry Buffer: `{self.buffer or '___'}`"
        )

        embed = discord.Embed(
            title="🔢 Vehicle Keypad",
            description=desc,
            color=discord.Color.blue()
        )

        try:
            await self.status_message.edit(embed=embed, view=self)
        except Exception as e:
            logger.exception("Error updating status embed: %s", e)


class SmashWindowDuringCodeButton(discord.ui.Button):
    def __init__(self, keypad_view: GTAKeypadView):
        super().__init__(label="💥 Smash Window", style=discord.ButtonStyle.danger)
        self.keypad_view = keypad_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.keypad_view.user_id:
            return await interaction.response.send_message(
                "This isn't your break‑in.", ephemeral=True
            )

        # Disable keypad buttons
        for child in self.keypad_view.children:
            child.disabled = True

        try:
            await self.keypad_view.status_message.edit(view=self.keypad_view)
        except Exception as e:
            logger.exception("Failed to disable keypad buttons: %s", e)

        # Cancel keypad game
        embed = discord.Embed(
            title="💥 Smash Window",
            description=(
                "Keypad cancelled.\n"
                "Starting Smash Window minigame...\n\n"
                "**You have 20 seconds to break the window.**"
            ),
            color=discord.Color.orange()
        )
        await self.keypad_view.channel.send(embed=embed)

        # Start Smash Window minigame
        from .smash_window import SmashWindowView

        async def stage2_callback():
            try:
                await start_stage2(interaction, self.keypad_view.bot, self.keypad_view.victim)
            except Exception as e:
                logger.exception("Error in stage2_callback (keypad smash): %s", e)

        view = SmashWindowView(
            user_id=self.keypad_view.user_id,
            victim=self.keypad_view.victim,
            stage2_callback=stage2_callback
        )

        msg = await self.keypad_view.channel.send(view=view)
        await view.start_animation(msg)

        try:
            await interaction.response.defer()
        except Exception:
            pass


class DigitButton(discord.ui.Button):
    def __init__(self, digit: str, keypad_view: GTAKeypadView):
        super().__init__(label=digit, style=discord.ButtonStyle.secondary)
        self.digit = digit
        self.keypad_view = keypad_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.keypad_view.user_id:
            return await interaction.response.send_message(
                "This isn't your break‑in.", ephemeral=True
            )

        if len(self.keypad_view.buffer) >= 3:
            return await interaction.response.send_message(
                "You already entered 3 digits. Use **Submit** or **Clear**.",
                ephemeral=True
            )

        self.keypad_view.buffer += self.digit
        await self.keypad_view.update_status_embed()

        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass


class ClearButton(discord.ui.Button):
    def __init__(self, keypad_view: GTAKeypadView):
        super().__init__(label="Clear", style=discord.ButtonStyle.secondary)
        self.keypad_view = keypad_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.keypad_view.user_id:
            return await interaction.response.send_message(
                "This isn't your break‑in.", ephemeral=True
            )

        self.keypad_view.buffer = ""
        await self.keypad_view.update_status_embed()

        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass


class SubmitButton(discord.ui.Button):
    def __init__(self, keypad_view: GTAKeypadView):
        super().__init__(label="Submit", style=discord.ButtonStyle.success)
        self.keypad_view = keypad_view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.keypad_view.user_id:
            return await interaction.response.send_message(
                "This isn't your break‑in.", ephemeral=True
            )

        if len(self.keypad_view.buffer) != 3:
            return await interaction.response.send_message(
                "You must enter exactly **3 digits** before submitting.",
                ephemeral=True
            )

        try:
            status, clues_str, noise_full = self.keypad_view.game.check_guess(self.keypad_view.buffer)

            if status == "invalid":
                return await interaction.response.send_message(
                    "Invalid code. Enter a **3-digit numeric** code.",
                    ephemeral=True
                )

            self.keypad_view.last_clues = clues_str

            if status == "clues":
                self.keypad_view.buffer = ""

            await self.keypad_view.update_status_embed()

            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass

            if status == "unlocked":
                embed = discord.Embed(
                    title="🔓 Vehicle Unlocked!",
                    description=(
                        "You successfully cracked the keypad and unlocked the vehicle.\n\n"
                        f"**Clues:** {clues_str}\n"
                        f"**Attempts:** {self.keypad_view.game.attempts}\n"
                        f"**Noise:** {min(self.keypad_view.game.noise, 100):.0f}%"
                    ),
                    color=discord.Color.green()
                )
                await self.keypad_view.channel.send(embed=embed)
                return await start_stage2(interaction, self.keypad_view.bot, self.keypad_view.victim)

            if noise_full and not self.keypad_view.broadcast_triggered:
                self.keypad_view.broadcast_triggered = True
                self.keypad_view.stage1_view.broadcast_triggered = True
                await trigger_noise_broadcast(interaction, self.keypad_view.victim)

        except Exception as e:
            logger.exception("Error in SubmitButton.callback: %s", e)
            try:
                await interaction.followup.send("❌ Error processing keypad submission.", ephemeral=True)
            except Exception:
                pass


# ============================================================
# NOISE BROADCAST
# ============================================================

async def trigger_noise_broadcast(interaction: discord.Interaction, victim: discord.Member):
    try:
        channel = interaction.channel

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

        criminal_id = interaction.user.id  # the one who caused the noise

        view = GTAReportView(victim, criminal_id)
        msg = await channel.send(embed=embed, view=view)
        view.message = msg

    except Exception as e:
        logger.exception("Error sending noise broadcast: %s", e)


# ============================================================
# STAGE 2 STUB
# ============================================================

async def start_stage2(interaction: discord.Interaction, bot, victim: discord.Member):
    try:
        embed = discord.Embed(
            title="🔧 Stage 2 — Hotwire (Coming Soon)",
            description=(
                "You’re inside the vehicle.\n"
                "Next up: **Hotwire** minigame (to be implemented)."
            ),
            color=discord.Color.blue()
        )
        await interaction.channel.send(embed=embed)

    except Exception as e:
        logger.exception("Error starting Stage 2: %s", e)