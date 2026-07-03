import random
import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user

# Import the lotto handler
from cogs.lottery.lottery import LottoView, LOTTO_COST, get_next_draw_from_db




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

        await interaction.response.defer()

        ticket_cost = amount * 100
        pool = get_pool()

        async with pool.acquire() as conn:
            await upsert_user(conn, interaction.user.id, 0, interaction.user.name)

            user = await conn.fetchrow(
                "SELECT checking_account_balance FROM users WHERE discord_id = $1",
                interaction.user.id
            )

        balance = user["checking_account_balance"] or 0

        if balance < ticket_cost:
            return await interaction.followup.send("Not enough money.")

        new_balance = balance - ticket_cost

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET checking_account_balance = $1 WHERE discord_id = $2",
                new_balance,
                interaction.user.id
            )

        winning_numbers = random.sample(range(1, 37), 3)
        ticket_numbers = random.sample(range(1, 37), 9)

        from cogs.gambling.scratchview import ScratchView

        view = ScratchView(
            interaction.user.id,
            ticket_numbers,
            winning_numbers,
            ticket_cost,
            pool
        )

        embed = discord.Embed(
            title="🎟 Scratch-Off Ticket",
            description=f"🏆 Winning Numbers: {', '.join(map(str, winning_numbers))}"
        )

        await interaction.followup.send(embed=embed, view=view)

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
    async def highlow(self, interaction: discord.Interaction, wager: app_commands.Choice[int]):

        pool = get_pool()
        wager_cents = wager.value * 100

        async with pool.acquire() as conn:
            await upsert_user(conn, interaction.user.id, 0, interaction.user.name)

            user = await conn.fetchrow(
                "SELECT checking_account_balance FROM users WHERE discord_id = $1",
                interaction.user.id
            )

        balance = user["checking_account_balance"] or 0

        if balance < wager_cents:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="💸 Insufficient Funds",
                    description=f"You need {money(wager_cents)}",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        first_number = random.randint(1, 100)

        embed = discord.Embed(
            title="🎲 High Low",
            description=(
                f"First number: **{first_number}**\n"
                f"Wager: **{money(wager_cents)}**\n\n"
                "Higher / Lower or Double Down first."
            )
        )

        from cogs.gambling.highlowview import HighLowView

        view = HighLowView(interaction.user.id, pool, first_number, wager_cents)

        await interaction.response.send_message(embed=embed, view=view)

    # =========================================================
    # 🎰 /gambling lotto
    # =========================================================
    @app_commands.command(name="lotto", description="Buy a lotto ticket")
    async def lotto(self, interaction: discord.Interaction):

        try:
            pool = get_pool()

            embed = discord.Embed(
                title="🎰 Lotto Ticket",
                description=(
                    f"Buy a lotto ticket for **{money(LOTTO_COST)}**.\n\n"
                    "Choose your own numbers or let the system generate them. Winning numbers are announced every Tuesday at 8:00 PM EST!"
                ),
                color=discord.Color.gold()
            )

            view = LottoView(interaction.user.id, interaction.guild.id, pool)

            # Defer FIRST (ephemeral)
            await interaction.response.defer(ephemeral=True)

            # Then send the UI
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            import traceback
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
            except Exception as e2:
                traceback.print_exc()


async def setup(bot):
    await bot.add_cog(Gambling(bot))
