import discord
import random
import asyncio
import logging
from datetime import timedelta, datetime

from db.connection import get_pool

from police.police_reported_logic.police_flow_controller import PoliceFlowController
from police.police_reported_logic.snitch_flow import handle_snitch as handle_universal_snitch
from police.police_reported_logic.police_items import PoliceItemsView

COLOR_PRIMARY = 0x5865F2

logger = logging.getLogger("crime.vault")
logger.setLevel(logging.ERROR)


class VaultGame:
    def __init__(self):
        self.code = [random.randint(0, 9) for _ in range(3)]
        self.attempts = 0
        self.max_attempts = 5

    def check_guess(self, guess_str):
        self.attempts += 1

        if len(guess_str) != 3 or not guess_str.isdigit():
            return "❌ Invalid guess. Enter a 3-digit code like `382`."

        guess = [int(d) for d in guess_str]
        clues = []

        for i in range(3):
            if guess[i] == self.code[i]:
                clues.append("✅")
            elif guess[i] in self.code:
                clues.append("⚠️")
            else:
                clues.append("❌")

        if guess == self.code:
            return "unlocked"
        elif self.attempts >= self.max_attempts:
            return "locked_out"
        else:
            return f"Attempt {self.attempts}/{self.max_attempts}: {' '.join(clues)}"


class VaultGameView(discord.ui.View):
    def __init__(self, user_id, bot, channel, guild_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bot = bot
        self.channel = channel
        self.guild_id = guild_id

        self.game = VaultGame()
        self.outcome = None

        self.vault_message: discord.Message | None = None

        self.controller = PoliceFlowController(
            robber_id=self.user_id,
            guild_id=self.guild_id,
            channel=self.channel,
            crime_type="vault_robbery",
            stolen_amount=None,
            company_name=None,
        )

        self.controller.has_snitched = False

    async def apply_success_rewards(self, interaction):
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

    @discord.ui.button(label="Enter Safe Code", style=discord.ButtonStyle.blurple)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # HARD BLOCK: if snitched, no code entry
            if self.controller.has_snitched:
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

        except Exception as e:
            logger.exception("Error in Enter Safe Code button: %s", e)
            try:
                await interaction.followup.send(
                    "❌ Error opening vault code modal.",
                    ephemeral=True
                )
            except:
                pass

    @discord.ui.button(label="Snitch", style=discord.ButtonStyle.red)
    async def snitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id == self.user_id:
                return await interaction.response.send_message(
                    "You can't snitch on yourself.",
                    ephemeral=True
                )

            if self.controller.has_snitched:
                return await interaction.response.send_message(
                    "Someone already snitched.",
                    ephemeral=True
                )

            self.controller.has_snitched = True

            # 🔥 Nuclear option: remove ALL buttons from the view
            self.clear_items()

            # Stop timeout
            self.stop()

            # Edit the original vault message to remove buttons for everyone
            target_msg = self.vault_message or interaction.message
            await target_msg.edit(view=self)

            # Continue snitch flow
            await handle_universal_snitch(self.controller, interaction)

        except Exception as e:
            logger.exception("Error in snitch button: %s", e)
            try:
                await interaction.followup.send(
                    "❌ Error during snitch attempt.",
                    ephemeral=True
                )
            except:
                pass

    async def on_timeout(self):
        if self.controller.has_snitched:
            return

        try:
            await self.channel.send(
                embed=discord.Embed(
                    title="⏳ Timeout or Abandoned",
                    description="You gave up or the game timed out.",
                    color=0x747F8D,
                )
            )
        except Exception as e:
            logger.exception("Error in on_timeout: %s", e)

        self.stop()

    async def disable_snitch_button_later(self, message: discord.Message):
        try:
            await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=10))

            if not self.controller.has_snitched:
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.label == "Snitch":
                        child.disabled = True

                await message.edit(view=self)

        except Exception as e:
            logger.exception("Error disabling snitch button: %s", e)


class VaultGuessModal(discord.ui.Modal):
    def __init__(self, view: VaultGameView):
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
            # HARD BLOCK: if snitched, modal cannot submit
            if self.view.controller.has_snitched:
                return await interaction.response.send_message(
                    "Someone snitched. The vault is locked down. You can't enter the code anymore.",
                    ephemeral=True
                )

            result = self.view.game.check_guess(self.guess.value)

            await interaction.response.defer()

            if result == "unlocked":
                self.view.outcome = "success"
                cash, xp = await self.view.apply_success_rewards(interaction)

                pool = get_pool()
                async with pool.acquire() as conn:
                    new_balance = await conn.fetchval("""
                        SELECT checking_account_balance
                        FROM users
                        WHERE discord_id = $1 AND guild_id = $2
                    """, self.view.user_id, interaction.guild.id)

                await interaction.channel.send(
                    embed=discord.Embed(
                        title="💰 Vault Cracked",
                        description=(
                            f"You made off with **${cash/100:,.2f}**.\n\n"
                            f"XP Bonus: {xp}\n\n"
                            f"💳 New checking account balance: ${new_balance/100:,.2f}"
                        ),
                        color=discord.Color.green()
                    )
                )

            elif result == "locked_out":
                self.view.outcome = "failure"

                await interaction.channel.send(
                    embed=discord.Embed(
                        title="🚨 Vault Locked Out",
                        description=(
                            "You failed to crack the vault.\n"
                            "The police have been alerted and are responding."
                        ),
                        color=0xF04747,
                    )
                )

                police_view = PoliceItemsView(self.view.controller)
                await interaction.channel.send(
                    "Police have been alerted! Choose how they respond:",
                    view=police_view
                )

            else:
                await interaction.channel.send(result)

        except Exception as e:
            logger.exception("Error in VaultGuessModal.on_submit: %s", e)
            try:
                await interaction.followup.send(
                    "❌ Error processing your vault guess.",
                    ephemeral=True
                )
            except:
                pass


async def start_vault_game(interaction: discord.Interaction, bot: discord.Client):
    try:
        view = VaultGameView(
            user_id=interaction.user.id,
            bot=bot,
            channel=interaction.channel,
            guild_id=interaction.guild.id,
        )

        embed = discord.Embed(
            title="🔐 Vault Heist",
            description=(
                "**Vault Heist Rules:**\n"
                "• **✅** Correct number in the correct position\n"
                "• **⚠️** Correct number in the wrong position\n"
                "• **❌** Number not in the code\n\n"
                "Crack the 3‑digit vault code.\n"
                "You have **5 attempts**.\n"
                "Snitching may occur.\n"
                "Police may respond.\n"
            ),
            color=COLOR_PRIMARY
        )

        await interaction.response.send_message(
            "⏳ Preparing your vault heist...",
            ephemeral=True
        )

        sent = await interaction.channel.send(embed=embed, view=view)

        view.vault_message = sent

        bot.loop.create_task(view.disable_snitch_button_later(sent))

    except Exception as e:
        logger.exception("Error in start_vault_game: %s", e)
        try:
            await interaction.followup.send(
                "❌ Error starting vault heist.",
                ephemeral=True
            )
        except:
            pass


async def setup(bot: discord.Client):
    @bot.tree.command(name="crime", description="Attempt to crack the vault.")
    async def crime(interaction: discord.Interaction):
        await start_vault_game(interaction, bot)
