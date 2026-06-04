import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def parse_amount(raw: str):
    cleaned = raw.strip().lower()

    if cleaned in ["all", "max"]:
        return "all"

    cleaned = cleaned.replace("$", "").replace(",", "").strip()

    try:
        return int(round(float(cleaned) * 100))
    except ValueError:
        return -1


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your bank accounts")
    async def balance(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:
            await upsert_user(conn, interaction.user.id, str(interaction.user))

            user = await conn.fetchrow(
                """
                SELECT checking_account_balance, savings_account_balance
                FROM users
                WHERE discord_id = $1
                """,
                interaction.user.id
            )

        checking = user["checking_account_balance"] or 0
        savings = user["savings_account_balance"] or 0

        embed = discord.Embed(
            title=f"💰 {interaction.user.name}'s Bank Account",
            description="Your money is being judged silently.",
            color=discord.Color.gold()
        )

        embed.add_field(name="🏦 Checking", value=money(checking), inline=True)
        embed.add_field(name="🏦 Savings", value=money(savings), inline=True)
        embed.add_field(name="📊 Net Worth", value=money(checking + savings), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="wirefunds", description="Transfer money between accounts")
    @app_commands.describe(
        amount="Amount ('ALL', 500, $500, 500.50,)",
        direction="Transfer direction"
    )
    @app_commands.choices(direction=[
        app_commands.Choice(name="Checking → Savings", value="to_savings"),
        app_commands.Choice(name="Savings → Checking", value="to_checking")
    ])
    async def wirefunds(
        self,
        interaction: discord.Interaction,
        amount: str,
        direction: app_commands.Choice[str]
    ):
        pool = get_pool()
        amt = parse_amount(amount)

        if amt == -1:
            embed = discord.Embed(
                title="🤨 Invalid Amount",
                description="Use numbers like `500`, `$500`, `500.50`, or `all`.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        async with pool.acquire() as conn:
            await upsert_user(conn, interaction.user.id, str(interaction.user))

            user = await conn.fetchrow(
                """
                SELECT checking_account_balance, savings_account_balance
                FROM users
                WHERE discord_id = $1
                """,
                interaction.user.id
            )

            checking = user["checking_account_balance"] or 0
            savings = user["savings_account_balance"] or 0

            roast = [
                "Your bank account is questioning your life choices.",
                "Financial intelligence was not installed.",
                "The money gods are watching… and disappointed.",
                "Budgeting? Never heard of her.",
                "You're one bad transfer away from chaos."
            ]

            # HANDLE ALL MODE
            if amt == "all":
                if direction.value == "to_savings":
                    if checking <= 0:
                        return await interaction.response.send_message(
                            embed=discord.Embed(
                                title="🚫 Transfer Failed",
                                description="Your checking account is already empty. Respectfully… how?",
                                color=discord.Color.red()
                            ),
                            ephemeral=True
                        )

                    amt_cents = checking
                    checking = 0
                    savings += amt_cents
                    direction_text = "Checking → Savings"

                else:
                    if savings <= 0:
                        return await interaction.response.send_message(
                            embed=discord.Embed(
                                title="🚫 Transfer Failed",
                                description="Your savings account is empty. Future you is not impressed.",
                                color=discord.Color.red()
                            ),
                            ephemeral=True
                        )

                    amt_cents = savings
                    savings = 0
                    checking += amt_cents
                    direction_text = "Savings → Checking"

            else:
                amt_cents = amt

                if amt_cents <= 0:
                    embed = discord.Embed(
                        title="🤨 Invalid Amount",
                        description="Try `$500`, `500.50`, or `all`.",
                        color=discord.Color.red()
                    )
                    return await interaction.response.send_message(embed=embed, ephemeral=True)

                # CHECKING → SAVINGS
                if direction.value == "to_savings":
                    if amt_cents > checking:
                        return await interaction.response.send_message(
                            embed=discord.Embed(
                                title="🚫 Transfer Failed",
                                description=roast[hash(interaction.user.id) % len(roast)],
                                color=discord.Color.red()
                            ).add_field(
                                name="📉 Breakdown",
                                value=f"You tried {money(amt_cents)} but only had {money(checking)}.",
                                inline=False
                            ),
                            ephemeral=True
                        )

                    checking -= amt_cents
                    savings += amt_cents
                    direction_text = "Checking → Savings"

                else:
                    if amt_cents > savings:
                        return await interaction.response.send_message(
                            embed=discord.Embed(
                                title="🚫 Transfer Failed",
                                description=roast[hash(interaction.user.id) % len(roast)],
                                color=discord.Color.red()
                            ).add_field(
                                name="📉 Breakdown",
                                value=f"You tried {money(amt_cents)} but only had {money(savings)}.",
                                inline=False
                            ),
                            ephemeral=True
                        )

                    savings -= amt_cents
                    checking += amt_cents
                    direction_text = "Savings → Checking"

            await conn.execute(
                """
                UPDATE users
                SET checking_account_balance = $1,
                    savings_account_balance = $2
                WHERE discord_id = $3
                """,
                checking,
                savings,
                interaction.user.id
            )

        embed = discord.Embed(
            title="🏦 Wire Complete",
            description="Transfer processed successfully.",
            color=discord.Color.green()
        )

        embed.add_field(name="💸 Amount", value=money(amt_cents), inline=True)
        embed.add_field(name="🔁 Direction", value=direction_text, inline=True)
        embed.add_field(name="🏦 Checking", value=money(checking), inline=False)
        embed.add_field(name="🏦 Savings", value=money(savings), inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Economy(bot))