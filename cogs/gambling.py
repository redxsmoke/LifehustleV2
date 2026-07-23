import random
import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user

# Import LOTTO_COST + LottoView from your lottery cog
from cogs.lottery.lottery import LottoView, LOTTO_COST


# =========================================================
# 💰 MONEY FORMAT
# =========================================================
def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# =========================================================
# 🎲 CONTROLLED RNG (FIXED HIGHLOW BIAS)
# =========================================================
def generate_second_number(first_number: int) -> int:
    base = random.randint(1, 100)
    center_bias = (50 - first_number) * 0.15
    adjusted = base + center_bias
    return max(1, min(100, int(adjusted)))


# =========================================================
# 🔧 SAFE UPSERT (FIXED)
# =========================================================
async def safe_upsert_user(conn, discord_id: int, guild_id: int, username: str):
    print("[UPSERT] Running safe_upsert_user()")
    await conn.execute(
        """
        INSERT INTO users (discord_id, guild_id, username)
        VALUES ($1, $2, $3)
        ON CONFLICT (discord_id)
        DO NOTHING;
        """,
        discord_id,
        guild_id,
        username
    )


# =========================================================
# 🎟 SCRATCH VIEW
# =========================================================
class ScratchView(discord.ui.View):
    def __init__(self, user_id, numbers, winning_numbers, ticket_cost, pool):
        super().__init__(timeout=180)

        self.user_id = user_id
        self.numbers = numbers
        self.winning_numbers = winning_numbers
        self.ticket_cost = ticket_cost
        self.pool = pool
        self.revealed = set()

        self.build_buttons()

    def build_buttons(self):
        self.clear_items()

        for i in range(9):
            label = str(self.numbers[i]) if i in self.revealed else "⬛"

            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                disabled=i in self.revealed
            )

            async def callback(interaction: discord.Interaction, i=i):
                await self.handle_click(interaction, i)

            button.callback = callback
            self.add_item(button)

    async def handle_click(self, interaction: discord.Interaction, index: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your ticket.", ephemeral=True)

        if index in self.revealed:
            return await interaction.response.send_message("Already scratched.", ephemeral=True)

        self.revealed.add(index)
        self.build_buttons()

        embed = discord.Embed(
            title="🎟 Scratch-Off Ticket",
            description=f"🏆 Winning Numbers: {', '.join(map(str, self.winning_numbers))}"
        )

        await interaction.response.edit_message(embed=embed, view=self)

        if len(self.revealed) == 9:
            await self.finish(interaction)

    def calc_payout(self, matches):
        if matches == 1:
            return self.ticket_cost * random.choice([1, 2, 3, 4, 5])
        if matches == 2:
            return self.ticket_cost * random.choice([10, 25, 50])
        if matches == 3:
            return self.ticket_cost * 100
        return 0

    async def finish(self, interaction: discord.Interaction):
        matches_set = set(self.winning_numbers) & set(self.numbers)
        matches = len(matches_set)
        payout = self.calc_payout(matches)

        async with self.pool.acquire() as conn:
            if payout > 0:
                await conn.execute(
                    """
                    UPDATE users
                    SET checking_account_balance = checking_account_balance + $1
                    WHERE discord_id = $2
                    """,
                    payout,
                    self.user_id
                )

        self.revealed = set(range(9))
        self.build_buttons()

        embed = discord.Embed(
            title="🎟 Scratch Complete",
            description="Your ticket is fully revealed!"
        )

        embed.add_field(
            name="Winning Numbers",
            value=", ".join(map(str, self.winning_numbers)),
            inline=False
        )

        embed.add_field(
            name="Your Numbers",
            value=", ".join(map(str, self.numbers)),
            inline=False
        )

        embed.add_field(
            name="Matched Numbers",
            value=", ".join(map(str, matches_set)) if matches_set else "None",
            inline=False
        )

        embed.add_field(name="Total Matches", value=str(matches))
        embed.add_field(name="Payout", value=money(payout))

        await interaction.edit_original_response(embed=embed, view=self)


# =========================================================
# 🎲 HIGH LOW VIEW
# =========================================================
class HighLowView(discord.ui.View):
    def __init__(self, user_id, pool, first_number, wager):
        super().__init__(timeout=120)

        self.user_id = user_id
        self.pool = pool
        self.first_number = first_number
        self.wager = wager

        self.double_down = False
        self.resolved = False

    async def resolve(self, interaction: discord.Interaction, choice: str):

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)

        if self.resolved:
            return await interaction.response.send_message("Already finished.", ephemeral=True)

        self.resolved = True

        second_number = generate_second_number(self.first_number)

        is_higher = second_number > self.first_number
        win = (choice == "higher" and is_higher) or (choice == "lower" and not is_higher)

        if not self.double_down:
            win_amt = self.wager * 2
            loss_amt = self.wager
        else:
            win_amt = self.wager * 4
            loss_amt = self.wager * 2

        change = win_amt if win else -loss_amt

        async with self.pool.acquire() as conn:

            user = await conn.fetchrow(
                "SELECT checking_account_balance FROM users WHERE discord_id = $1",
                self.user_id
            )

            old = user["checking_account_balance"] or 0
            new = old + change

            await conn.execute(
                "UPDATE users SET checking_account_balance = $1 WHERE discord_id = $2",
                new,
                self.user_id
            )

        embed = discord.Embed(
            title="🎲 High Low Result",
            description=(
                f"First number: **{self.first_number}**\n"
                f"Second number: **{second_number}**\n\n"
                f"Choice: **{choice.upper()}**\n"
                f"Result: **{'WIN' if win else 'LOSS'}**\n"
                f"Double Down: **{'YES' if self.double_down else 'NO'}**"
            ),
            color=discord.Color.green() if win else discord.Color.red()
        )

        await interaction.response.edit_message(embed=embed, view=None)

        await interaction.followup.send(
            embed=discord.Embed(
                title="💰 Balance Update",
                description=(
                    f"{'Won' if change > 0 else 'Lost'} {money(abs(change))}\n\n"
                    f"Before: {money(old)}\n"
                    f"After: {money(new)}"
                ),
                color=discord.Color.green() if win else discord.Color.red()
            )
        )

    @discord.ui.button(label="Higher", style=discord.ButtonStyle.success)
    async def higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.resolve(interaction, "higher")

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.danger)
    async def lower(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.resolve(interaction, "lower")

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.primary)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)

        if self.resolved:
            return await interaction.response.send_message("Already finished.", ephemeral=True)

        if self.double_down:
            return await interaction.response.send_message("Already doubled down.", ephemeral=True)

        self.double_down = True

        await interaction.response.send_message("🔥 Double down activated! Now select Higher or Lower", ephemeral=True)
# =========================================================
# 🎰 GAMBLING GROUP
# =========================================================
class Gambling(commands.GroupCog, name="gambling"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    # =========================================================
    # 🎟 /gambling scratchoff
    # =========================================================
    @app_commands.command(name="scratchoff", description="Buy a scratch-off ticket")
    @app_commands.choices(amount=[
        app_commands.Choice(name="$10", value=10),
        app_commands.Choice(name="$100", value=100),
        app_commands.Choice(name="$1,000", value=1000),
        app_commands.Choice(name="$10,000", value=10000),
        app_commands.Choice(name="$100,000", value=100000),
        app_commands.Choice(name="$1,000,000", value=1000000),
    ])
    async def scratchoff(self, interaction: discord.Interaction, amount: int):

        print(f"[SCRATCHOFF] START — user={interaction.user.id}, amount={amount}")

        try:
            await interaction.response.defer()
            print("[SCRATCHOFF] Interaction deferred")

            ticket_cost = amount * 100
            pool = get_pool()
            print(f"[SCRATCHOFF] Ticket cost: {ticket_cost}")

            async with pool.acquire() as conn:
                print("[SCRATCHOFF] Upserting user...")
                await safe_upsert_user(conn, interaction.user.id, 0, interaction.user.name)

                print("[SCRATCHOFF] Fetching balance...")
                user = await conn.fetchrow(
                    "SELECT checking_account_balance FROM users WHERE discord_id = $1",
                    interaction.user.id
                )

            balance = user["checking_account_balance"] or 0
            print(f"[SCRATCHOFF] Balance: {balance}")

            if balance < ticket_cost:
                print("[SCRATCHOFF] Insufficient funds")
                return await interaction.followup.send(
                    embed=discord.Embed(
                        title="💸 Insufficient Funds",
                        description=(
                            f"You need **{money(ticket_cost)}**.\n\n"
                            f"🏦 **Your Checking Account Balance:** {money(balance)}\n\n"
                            "Wire funds from your savings account using **/wirefunds**"
                        ),
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            new_balance = balance - ticket_cost
            print(f"[SCRATCHOFF] New balance: {new_balance}")

            async with pool.acquire() as conn:
                print("[SCRATCHOFF] Updating balance...")
                await conn.execute(
                    "UPDATE users SET checking_account_balance = $1 WHERE discord_id = $2",
                    new_balance,
                    interaction.user.id
                )

            winning_numbers = random.sample(range(1, 37), 3)
            ticket_numbers = random.sample(range(1, 37), 9)

            print(f"[SCRATCHOFF] Winning numbers: {winning_numbers}")
            print(f"[SCRATCHOFF] Ticket numbers: {ticket_numbers}")

            print("[SCRATCHOFF] Creating ScratchView...")
            view = ScratchView(
                interaction.user.id,
                ticket_numbers,
                winning_numbers,
                ticket_cost,
                pool
            )
            print("[SCRATCHOFF] ScratchView created successfully")

            embed = discord.Embed(
                title="🎟 Scratch-Off Ticket",
                description=f"🏆 Winning Numbers: {', '.join(map(str, winning_numbers))}"
            )

            print("[SCRATCHOFF] Sending followup...")
            await interaction.followup.send(embed=embed, view=view)
            print("[SCRATCHOFF] Followup sent successfully")

        except Exception as e:
            import traceback
            print("[SCRATCHOFF] ERROR:")
            traceback.print_exc()

            try:
                await interaction.followup.send(f"Scratchoff error: {e}")
            except:
                pass

    # =========================================================
    # 🎲 /gambling highlow
    # =========================================================
    @app_commands.command(name="highlow", description="Play High / Low")
    @app_commands.choices(wager=[
        app_commands.Choice(name="$1,000", value=1000),
        app_commands.Choice(name="$10,000", value=10000),
        app_commands.Choice(name="$100,000", value=100000),
        app_commands.Choice(name="$1,000,000", value=1000000),
    ])
    async def highlow(self, interaction: discord.Interaction, wager: int):

        print(f"[HIGHLOW] START — user={interaction.user.id}, wager={wager}")

        try:
            pool = get_pool()
            wager_cents = wager * 100
            print(f"[HIGHLOW] Wager cents: {wager_cents}")

            async with pool.acquire() as conn:
                print("[HIGHLOW] Upserting user...")
                await safe_upsert_user(conn, interaction.user.id, 0, interaction.user.name)

                print("[HIGHLOW] Fetching balance...")
                user = await conn.fetchrow(
                    "SELECT checking_account_balance FROM users WHERE discord_id = $1",
                    interaction.user.id
                )

            balance = user["checking_account_balance"] or 0
            print(f"[HIGHLOW] Balance: {balance}")

            if balance < wager_cents:
                print("[HIGHLOW] Insufficient funds")
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="💸 Insufficient Funds",
                        description=(
                            f"You need **{money(wager_cents)}**.\n\n"
                            f"🏦 **Your Checking Account Balance:** {money(balance)}\n\n"
                            "Wire funds from your savings account using **/wirefunds**"
                        ),
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            first_number = random.randint(1, 100)
            print(f"[HIGHLOW] First number: {first_number}")

            embed = discord.Embed(
                title="🎲 High Low",
                description=(
                    f"First number: **{first_number}**\n"
                    f"Wager: **{money(wager_cents)}**\n\n"
                    "Higher / Lower or Double Down first."
                )
            )

            print("[HIGHLOW] Creating HighLowView...")
            view = HighLowView(interaction.user.id, pool, first_number, wager_cents)
            print("[HIGHLOW] HighLowView created successfully")

            print("[HIGHLOW] Sending response...")
            await interaction.response.send_message(embed=embed, view=view)
            print("[HIGHLOW] Response sent successfully")

        except Exception as e:
            import traceback
            print("[HIGHLOW] ERROR:")
            traceback.print_exc()

            try:
                await interaction.followup.send(f"HighLow error: {e}")
            except:
                pass

    # =========================================================
    # 🎰 /gambling lotto
    # =========================================================
    @app_commands.command(name="lotto", description="Buy a lotto ticket")
    async def lotto(self, interaction: discord.Interaction):

        print(f"[LOTTO] START — user={interaction.user.id}")

        try:
            pool = get_pool()

            embed = discord.Embed(
                title="🎰 Lotto Ticket",
                description=(
                    f"Buy a lotto ticket for **{money(LOTTO_COST)}**.\n\n"
                    "Choose your own numbers or let the system generate them."
                ),
                color=discord.Color.gold()
            )

            print("[LOTTO] Creating LottoView...")
            view = LottoView(interaction.user.id, interaction.guild.id, pool)
            print("[LOTTO] LottoView created successfully")

            print("[LOTTO] Deferring interaction...")
            await interaction.response.defer(ephemeral=True)

            print("[LOTTO] Sending followup...")
            await interaction.followup.send(embed=embed, view=view)
            print("[LOTTO] Followup sent successfully")

        except Exception as e:
            import traceback
            print("[LOTTO] ERROR:")
            traceback.print_exc()

            try:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ Lotto Command Error",
                        description=str(e),
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except:
                pass


async def setup(bot):
    await bot.add_cog(Gambling(bot))

