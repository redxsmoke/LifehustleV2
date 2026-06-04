import random
import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user


# =========================================================
# 🎮 SCRATCH VIEW
# =========================================================
class ScratchView(discord.ui.View):
    def __init__(self, user_id, numbers, winning_numbers, ticket_cost, pool, revealed=None):
        super().__init__(timeout=180)

        self.user_id = user_id
        self.numbers = numbers
        self.winning_numbers = winning_numbers
        self.ticket_cost = ticket_cost
        self.pool = pool

        self.revealed = revealed or set()

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

    # =========================================================
    # FUNNY RESULT MESSAGES
    # =========================================================
    def get_result_message(self, matches, payout):
        if matches == 0:
            return "💀 You got NOTHING. The universe watched and laughed."

        elif matches == 1:
            return (
                f"🪙 You hit 1 number and won ${payout:,}. "
                f"Don't spend it all in one place."
            )

        elif matches == 2:
            return (
                f"🔥 Two matches! Somebody call the IRS. "
                f"You just won ${payout:,}."
            )

        else:
            return (
                f"🎰 JACKPOT! THREE MATCHES! "
                f"${payout:,} richer. Absolutely disgusting."
            )

    # =========================================================
    # CLICK HANDLER
    # =========================================================
    async def handle_click(self, interaction: discord.Interaction, index: int):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "Not your ticket.",
                ephemeral=True
            )

        if index in self.revealed:
            return await interaction.response.send_message(
                "Already scratched.",
                ephemeral=True
            )

        self.revealed.add(index)

        self.build_buttons()

        embed = discord.Embed(
            title="🎟 Scratch-Off Ticket",
            description=(
                f"🏆 Winning Numbers: "
                f"{', '.join(map(str, self.winning_numbers))}"
            )
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

        if len(self.revealed) == 9:
            await self.finish_game(interaction)

    # =========================================================
    # PAYOUTS
    # =========================================================
    def calculate_payout(self, matches):
        if matches == 1:
            return self.ticket_cost * random.choice([1, 2, 3, 4, 5])

        elif matches == 2:
            return self.ticket_cost * random.choice([10, 25, 50])

        elif matches == 3:
            return self.ticket_cost * 100

        return 0

    # =========================================================
    # FINISH GAME
    # =========================================================
    async def finish_game(self, interaction: discord.Interaction):
        matches = len(set(self.winning_numbers) & set(self.numbers))

        payout = self.calculate_payout(matches)

        if payout > 0:
            async with self.pool.acquire() as conn:

                await conn.execute(
                    """
                    UPDATE users
                    SET checking_account_balance =
                        checking_account_balance + $1
                    WHERE discord_id = $2
                    """,
                    payout,
                    self.user_id
                )

                await conn.execute(
                    """
                    UPDATE user_scratchoff
                    SET total_winnings = total_winnings + $1
                    WHERE discord_id = $2
                    """,
                    payout,
                    self.user_id
                )

        self.revealed = set(range(9))
        self.build_buttons()

        result_message = self.get_result_message(matches, payout)

        embed = discord.Embed(
            title="🎟 Scratch Complete",
            description=result_message
        )

        embed.add_field(
            name="🏆 Winning Numbers",
            value=", ".join(map(str, self.winning_numbers)),
            inline=False
        )

        embed.add_field(
            name="🎫 Your Numbers",
            value=", ".join(map(str, self.numbers)),
            inline=False
        )

        embed.add_field(
            name="🔢 Matches",
            value=str(matches),
            inline=True
        )

        embed.add_field(
            name="💰 Payout",
            value=f"${payout:,}",
            inline=True
        )

        await interaction.message.edit(
            embed=embed,
            view=self
        )


# =========================================================
# 🎰 GAMBLING COG
# =========================================================
class Gambling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="scratchoff",
        description="Buy a scratch-off ticket"
    )
    @app_commands.choices(
        amount=[
            app_commands.Choice(name="$10", value=10),
            app_commands.Choice(name="$100", value=100),
            app_commands.Choice(name="$1,000", value=1000),
            app_commands.Choice(name="$10,000", value=10000),
        ]
    )
    async def scratchoff(
        self,
        interaction: discord.Interaction,
        amount: int
    ):
        ticket_cost = amount

        pool = get_pool()

        async with pool.acquire() as conn:

            await upsert_user(
                conn,
                interaction.user.id,
                str(interaction.user)
            )

            await conn.execute(
                """
                INSERT INTO user_scratchoff
                (
                    discord_id,
                    total_winnings
                )
                VALUES
                (
                    $1,
                    0
                )
                ON CONFLICT (discord_id)
                DO NOTHING
                """,
                interaction.user.id
            )

            user = await conn.fetchrow(
                """
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1
                """,
                interaction.user.id
            )

            balance = user["checking_account_balance"]

            if balance < ticket_cost:
                return await interaction.response.send_message(
                    f"💸 You tried to buy a ${ticket_cost:,} ticket "
                    f"with ${balance:,}. That's not gambling. "
                    f"That's a cry for help."
                )

            await conn.execute(
                """
                UPDATE users
                SET checking_account_balance =
                    checking_account_balance - $1
                WHERE discord_id = $2
                """,
                ticket_cost,
                interaction.user.id
            )

        # =====================================================
        # WEIGHTED ODDS
        # =====================================================

        roll = random.random()

        if roll < 0.60:
            target_matches = 0
        elif roll < 0.90:
            target_matches = 1
        elif roll < 0.99:
            target_matches = 2
        else:
            target_matches = 3

        winning_numbers = random.sample(range(1, 37), 3)

        ticket_numbers = []

        if target_matches > 0:
            matched = random.sample(
                winning_numbers,
                target_matches
            )

            ticket_numbers.extend(matched)

        non_winning_numbers = [
            n for n in range(1, 37)
            if n not in winning_numbers
        ]

        ticket_numbers.extend(
            random.sample(
                non_winning_numbers,
                9 - len(ticket_numbers)
            )
        )

        random.shuffle(ticket_numbers)

        view = ScratchView(
            interaction.user.id,
            ticket_numbers,
            winning_numbers,
            ticket_cost,
            pool
        )

        embed = discord.Embed(
            title="🎟 Scratch-Off Ticket",
            description=(
                f"🏆 Winning Numbers: "
                f"{', '.join(map(str, winning_numbers))}"
            )
        )

        await interaction.response.send_message(
            embed=embed,
            view=view
        )


async def setup(bot):
    await bot.add_cog(Gambling(bot))