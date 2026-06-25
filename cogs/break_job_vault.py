import discord
import random
import asyncio
from datetime import timedelta, datetime
from utils.snitch_engine import handle_snitch

from db.connection import get_pool


COLOR_PRIMARY = 0x5865F2
PROTECT_ASSETS_ITEM_ID = 11


async def apply_protect_assets(conn, user_id, guild_id, money_loss):
    if money_loss <= 0:
        return money_loss, False

    row = await conn.fetchrow("""
        SELECT quantity
        FROM user_items
        WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
    """, user_id, guild_id, PROTECT_ASSETS_ITEM_ID)

    if row and row["quantity"] > 0:
        await conn.execute("""
            UPDATE user_items
            SET quantity = quantity - 1
            WHERE discord_id = $1 AND guild_id = $2 AND item_id = $3
        """, user_id, guild_id, PROTECT_ASSETS_ITEM_ID)
        return 0, True

    return money_loss, False


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


async def set_bail_for_user(discord_id: int, guild_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        bail_total = await conn.fetchval("""
            SELECT COALESCE(SUM(c.bail_amount), 0)
            FROM user_criminal_record ucr
            JOIN cd_crime c ON c.cd_crime_id = ucr.cd_crime_id
            WHERE ucr.discord_id = $1
              AND ucr.guild_id = $2
        """, discord_id, guild_id)

        await conn.execute("""
            INSERT INTO user_bail (discord_id, guild_id, bail_total, bail_paid, is_active)
            VALUES ($1, $2, $3, 0, TRUE)
            ON CONFLICT (discord_id, guild_id)
            DO UPDATE SET bail_total = EXCLUDED.bail_total,
                          bail_paid = 0,
                          is_active = TRUE
        """, discord_id, guild_id, bail_total)
class VaultGameView(discord.ui.View):
    def __init__(self, user_id, bot, channel=None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.bot = bot
        self.channel = channel
        self.game = VaultGame()
        self.robbery_complete = asyncio.Event()

        self.outcome = None
        self.snitched = False
        self.snitcher_id = None
        self.snitch_disabled = False
        self.hide_spot_chosen = False

        self.chosen_spot = None
        self.hide_used = False

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

        self.available_hide_spots = random.sample(self.hide_spots, 4)

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
    async def submit(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your vault to crack!", ephemeral=True)

        await interaction.response.send_modal(VaultGuessModal(self))

    @discord.ui.button(label="Snitch", style=discord.ButtonStyle.red)
    async def snitch(self, interaction, button):

        if self.snitched:
            sn = interaction.guild.get_member(self.snitcher_id)
            name = sn.mention if sn else "someone"

            if interaction.user.id == self.snitcher_id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="💀 Calm Down, Squealer",
                        description=(
                            "You already tried to snitch once.\n\n"
                            "The precinct has your number saved as “Desperate Informant #3.”"
                        ),
                        color=0xF04747
                    ),
                    ephemeral=True
                )

            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🍩 Too Late",
                    description=f"{name} already snitched. The cops are busy carbo‑loading on donuts.",
                    color=0xF04747
                ),
                ephemeral=True
            )

        if self.snitch_disabled:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🕵️‍♂️ Too Slow",
                    description="You missed your chance to snitch.",
                    color=0x747F8D
                ),
                ephemeral=True
            )

        if interaction.user.id == self.user_id:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚫 Nope!",
                    description="You can't snitch on yourself.",
                    color=0xF04747
                ),
                ephemeral=True
            )

        self.snitched = True
        self.snitcher_id = interaction.user.id

        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Confirm Snitch",
                description="Are you sure you want to snitch?",
                color=0xF04747
            ),
            view=SnitchConfirmView(self),
            ephemeral=True
        )

    async def on_timeout(self):
        if self.robbery_complete.is_set():
            return

        if self.outcome in ("success", "failure", "Caught", "Evaded Police", "snitched"):
            return

        if self.channel:
            try:
                await self.channel.send(
                    embed=discord.Embed(
                        title="⏳ Timeout or Abandoned",
                        description="You gave up or the game timed out.",
                        color=0x747F8D,
                    )
                )
            except:
                pass

        self.stop()

    async def disable_snitch_button_later(self, message):
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=10))
        self.snitch_disabled = True

        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Snitch":
                child.disabled = True

        try:
            await message.edit(view=self)
        except:
            pass
# ============================================================
# SHOW HIDE BUTTONS
# ============================================================
async def show_hide_button(self, interaction):
    view = HideOnlyView(self)

    await self.channel.send(
        "Choose your escape method...",
        view=view
    )

    asyncio.create_task(self._hide_timeout(interaction))


async def _hide_timeout(self, interaction):
    await asyncio.sleep(10)

    if self.hide_spot_chosen or self.robbery_complete.is_set():
        return

    self.outcome = "failure"
    self.chosen_spot = None

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            balance = await conn.fetchval("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, self.user_id, interaction.guild.id) or 0

            money_loss = balance

            final_loss, used_padlock = await apply_protect_assets(
                conn,
                self.user_id,
                interaction.guild.id,
                money_loss
            )

            if used_padlock and money_loss > 0:
                desc = (
                    "You stood there looking like an idiot! The police arrested you.\n\n"
                    "**Your Pad Lock protected your checking account from being seized.** 🔐"
                )
            else:
                desc = (
                    "You stood there looking like an idiot! The police arrested you and "
                    "seized your checking account funds for investigation."
                )

            await self.channel.send(
                embed=discord.Embed(
                    title="🚨 Arrested!",
                    description=desc,
                    color=0xF04747
                )
            )

            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance - $1,
                    cd_location_id = 8,
                    is_incarcerated = TRUE
                WHERE discord_id = $2 AND guild_id = $3
            """, final_loss, self.user_id, interaction.guild.id)

            await conn.execute("""
                UPDATE user_occupations
                SET employment_end_date = NOW()
                WHERE discord_id = $1
                  AND guild_id = $2
                  AND employment_end_date IS NULL
            """, self.user_id, interaction.guild.id)

            await conn.execute("""
                INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
                VALUES ($1, $2, 1, NOW())
            """, self.user_id, interaction.guild.id)

            await conn.execute("""
                INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
                VALUES ($1, $2, 4, NOW())
            """, self.user_id, interaction.guild.id)

        await set_bail_for_user(self.user_id, interaction.guild.id)

    except Exception as e:
        print(f"[ERROR] Timeout arrest DB update: {e}")

    self.robbery_complete.set()
    self.stop()
    return


# ============================================================
# POLICE SEARCH LOGIC
# ============================================================
async def process_police_search(self, interaction, chosen_spot):

    if not self.hide_spot_chosen:
        return
    if self.outcome == "success":
        return
    if self.robbery_complete.is_set():
        return

    searched = random.sample(self.hide_spots, 3)
    caught = False

    await asyncio.sleep(5)
    await interaction.channel.send(
        embed=discord.Embed(
            title="🚨 Police Arrival",
            description="The police have arrived on scene...",
            color=0xF04747,
        )
    )

    for emoji, spot in searched:
        await asyncio.sleep(5)
        await interaction.channel.send(
            embed=discord.Embed(
                title="🔍 Police Search",
                description=f"The police search **{spot}**...",
                color=0xFAA61A,
            )
        )
        if spot == chosen_spot:
            caught = True
            break

    await asyncio.sleep(5)

    pool = get_pool()

    if caught:
        self.outcome = "failure"
        self.chosen_spot = chosen_spot
        self.robbery_complete.set()

        async with pool.acquire() as conn:
            balance = await conn.fetchval("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, self.user_id, interaction.guild.id) or 0

            money_loss = balance

            final_loss, used_padlock = await apply_protect_assets(
                conn,
                self.user_id,
                interaction.guild.id,
                money_loss
            )

            if used_padlock and money_loss > 0:
                desc = (
                    f"The police searched **{chosen_spot}** and found you hiding there.\n"
                    "**Your Pad Lock protected your checking account from being seized.** 🔐"
                )
            else:
                desc = (
                    f"The police searched **{chosen_spot}** and found you hiding there.\n"
                    "You've been arrested and fired. Your checking_account_balance has been seized."
                )

            await interaction.channel.send(
                embed=discord.Embed(
                    title="🚨 Caught!",
                    description=desc,
                    color=0xF04747
                )
            )

            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance - $1,
                    cd_location_id = 8,
                    is_incarcerated = TRUE
                WHERE discord_id = $2 AND guild_id = $3
            """, final_loss, self.user_id, interaction.guild.id)

            await conn.execute("""
                UPDATE user_occupations
                SET employment_end_date = NOW()
                WHERE discord_id = $1
                  AND guild_id = $2
                  AND employment_end_date IS NULL
            """, self.user_id, interaction.guild.id)

            await conn.execute("""
                INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
                VALUES ($1, $2, 1, NOW())
            """, self.user_id, interaction.guild.id)

            await conn.execute("""
                INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
                VALUES ($1, $2, 4, NOW())
            """, self.user_id, interaction.guild.id)

        await set_bail_for_user(self.user_id, interaction.guild.id)

    else:
        self.outcome = "success"
        cash, xp = await self.apply_success_rewards(interaction)

        await interaction.channel.send(
            embed=discord.Embed(
                title="💰 Vault Cracked!",
                description=(
                    "You successfully cracked the vault and escaped!\n\n"
                    f"**Payout:** ${cash/100:,.2f}\n"
                    f"**XP Gained:** {xp}"
                ),
                color=discord.Color.green()
            )
        )

    self.stop()
class HideButton(discord.ui.Button):
    def __init__(self, emoji, spot, vault_view):
        super().__init__(label=spot, emoji=emoji, style=discord.ButtonStyle.blurple)
        self.spot = spot
        self.vault_view = vault_view

    async def callback(self, interaction):
        if interaction.user.id != self.vault_view.user_id:
            return await interaction.response.send_message(
                "This isn't your robbery.", ephemeral=True
            )

        self.vault_view.hide_spot_chosen = True
        self.vault_view.chosen_spot = self.spot

        await interaction.response.send_message(
            f"You hid **{self.spot}**. The police are on their way...",
            ephemeral=True
        )

        await self.vault_view.process_police_search(interaction, self.spot)


class HideOnlyView(discord.ui.View):
    def __init__(self, vault_view):
        super().__init__(timeout=30)
        self.vault_view = vault_view

        for emoji, spot in vault_view.available_hide_spots:
            self.add_item(HideButton(emoji, spot, vault_view))


class VaultGuessModal(discord.ui.Modal, title="🔢 Enter Vault Code"):
    guess = discord.ui.TextInput(
        label="Enter a 3-digit code",
        max_length=3,
        required=True
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction):
        result = self.view.game.check_guess(self.guess.value)

        await interaction.response.defer(ephemeral=True)

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

            return await interaction.channel.send(
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
            return await self.view.show_hide_button(interaction)

        else:
            return await interaction.channel.send(result)
class SnitchConfirmView(discord.ui.View):
    def __init__(self, vault_view):
        super().__init__(timeout=20)
        self.vault_view = vault_view

    @discord.ui.button(label="Yes, Snitch", style=discord.ButtonStyle.red)
    async def confirm(self, interaction, button):
        if interaction.user.id != self.vault_view.snitcher_id:
            return await interaction.response.send_message(
                "You are not the snitcher.", ephemeral=True
            )

        await interaction.response.send_message(
            "🚨 You alerted the police!", ephemeral=True
        )

        self.vault_view.outcome = "snitched"

        await self.vault_view.channel.send(
            embed=discord.Embed(
                title="🚨 Police Alerted!",
                description="Someone snitched! The police are on their way!",
                color=0xF04747
            )
        )

        await self.vault_view.show_hide_button(interaction)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction, button):
        await interaction.response.send_message(
            "Snitch canceled.", ephemeral=True
        )
        self.stop()


async def handle_snitch(vault_view, interaction):
    if vault_view.snitched:
        return

    vault_view.snitched = True
    vault_view.snitcher_id = interaction.user.id

    await interaction.response.send_message(
        embed=discord.Embed(
            title="⚠️ Confirm Snitch",
            description="Are you sure you want to snitch?",
            color=0xF04747
        ),
        view=SnitchConfirmView(vault_view),
        ephemeral=True
    )
async def start_vault_game(interaction, bot):
    view = VaultGameView(interaction.user.id, bot, interaction.channel)

    embed = discord.Embed(
        title="🔐 Vault Heist",
        description=(
            "Crack the 3‑digit vault code.\n"
            "You have **5 attempts**.\n\n"
            "⚠ Someone may snitch.\n"
            "⚠ Failing the vault triggers police.\n"
            "⚠ Snitch + fail = snitch message first.\n"
            "⚠ Police ALWAYS arrive after hiding.\n"
        ),
        color=COLOR_PRIMARY
    )

    msg = await interaction.response.send_message(embed=embed, view=view)
    sent = await interaction.original_response()

    bot.loop.create_task(view.disable_snitch_button_later(sent))


async def setup(bot):
    @bot.tree.command(name="crime", description="Attempt to crack the vault.")
    async def crime(interaction: discord.Interaction):
        await start_vault_game(interaction, bot)





