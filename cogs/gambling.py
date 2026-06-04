import random
import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user


# =========================================================
# 💰 MONEY FORMAT (CENTS → DISPLAY)
# =========================================================
def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


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

    def get_result_message(self, matches, payout):
        if matches == 0:
            return "💀 You got NOTHING. The universe laughed at you."

        elif matches == 1:
            return f"🪙 1 match. You won {money(payout)}. Barely profitable behavior."

        elif matches == 2:
            return f"🔥 Two matches! {money(payout)}. You're dangerously close to competence."

        else:
            return f"🎰 JACKPOT! {money(payout)}. This is statistically offensive."

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
            await self.finish_game(interaction)

    def calculate_payout(self, matches):
        if matches == 1:
            return self.ticket_cost * random.choice([1, 2, 3, 4, 5])

        elif matches == 2:
            return self.ticket_cost * random.choice([10, 25, 50])

        elif matches == 3:
            return self.ticket_cost * 100

        return 0

    async def finish_game(self, interaction: discord.Interaction):
        matches = len(set(self.winning_numbers) & set(self.numbers))
        payout = self.calculate_payout(matches)

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

        embed = discord.Embed(
            title="🎟 Scratch Complete",
            description=self.get_result_message(matches, payout)
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
            value=money(payout),
            inline=True
        )

        await interaction.message.edit(embed=embed, view=self)


# =========================================================
# 🎰 GAMBLING COG
# =========================================================
class Gambling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scratchoff", description="Buy a scratch-off ticket")
    @app_commands.choices(amount=[
        app_commands.Choice(name="$10", value=10),
        app_commands.Choice(name="$100", value=100),
        app_commands.Choice(name="$1,000", value=1000),
        app_commands.Choice(name="$10,000", value=10000),
    ])
    async def scratchoff(self, interaction: discord.Interaction, amount: int):

        ticket_cost = amount * 100  # cents

        pool = get_pool()

        async with pool.acquire() as conn:

            await upsert_user(conn, interaction.user.id, str(interaction.user))

            await conn.execute(
                """
                INSERT INTO user_scratchoff (discord_id, total_winnings)
                VALUES ($1, 0)
                ON CONFLICT (discord_id) DO NOTHING
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

            balance = user["checking_account_balance"] or 0

            if balance < ticket_cost:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="💸 Insufficient Funds",
                        description=f"You need {money(ticket_cost)} but only have {money(balance)}.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            new_balance = balance - ticket_cost

            await conn.execute(
                """
                UPDATE users
                SET checking_account_balance = $1
                WHERE discord_id = $2
                """,
                new_balance,
                interaction.user.id
            )

        # =====================================================
        # PURCHASE EMBED (NEW)
        # =====================================================

        purchase_embed = discord.Embed(
            title="🎟 Ticket Purchased",
            color=discord.Color.green()
        )

        purchase_embed.add_field(name="💰 Old Balance", value=money(balance), inline=True)
        purchase_embed.add_field(name="🎫 Cost", value=money(ticket_cost), inline=True)
        purchase_embed.add_field(name="🏦 New Balance", value=money(new_balance), inline=True)

        # =====================================================
        # ODDS
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
            ticket_numbers.extend(random.sample(winning_numbers, target_matches))

        non_winning = [n for n in range(1, 37) if n not in winning_numbers]

        ticket_numbers.extend(random.sample(non_winning, 9 - len(ticket_numbers)))

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
            description=f"🏆 Winning Numbers: {', '.join(map(str, winning_numbers))}"
        )

        await interaction.response.send_message(
            embeds=[purchase_embed, embed],
            view=view
        )


async def setup(bot):
    await bot.add_cog(Gambling(bot))