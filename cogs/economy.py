import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user


# =========================================================
# 💰 MONEY FORMAT
# =========================================================
def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# =========================================================
# 🔢 PARSE AMOUNT (FIXED: NOW RETURNS CENTS CORRECTLY)
# =========================================================
def parse_amount(raw: str):
    cleaned = raw.strip().lower()

    # ALL / MAX
    if cleaned in ["all", "max"]:
        return "all"

    # Remove symbols
    cleaned = cleaned.replace("$", "").replace(",", "").strip()

    multiplier = 1

    # K / THOUSAND
    if cleaned.endswith("k") or cleaned.endswith("thousand"):
        multiplier = 1_000
        cleaned = cleaned.replace("k", "").replace("thousand", "").strip()

    # M / MILLION
    elif cleaned.endswith("m") or cleaned.endswith("million"):
        multiplier = 1_000_000
        cleaned = cleaned.replace("m", "").replace("million", "").strip()

    # B / BILLION
    elif cleaned.endswith("b") or cleaned.endswith("billion"):
        multiplier = 1_000_000_000
        cleaned = cleaned.replace("b", "").replace("billion", "").strip()

    # Convert to number
    try:
        base = float(cleaned)
        dollars = base * multiplier
        return int(round(dollars * 100))  # convert to cents
    except ValueError:
        return -1


# =========================================================
# 💼 ECONOMY COG
# =========================================================
class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =====================================================
    # 💰 BALANCE COMMAND
    # =====================================================
    @app_commands.command(name="balance", description="Check your bank accounts")
    async def balance(self, interaction: discord.Interaction):

        pool = get_pool()
        guild_id = interaction.guild.id if interaction.guild else 0

        async with pool.acquire() as conn:

            await upsert_user(
                conn,
                interaction.user.id,
                guild_id,
                interaction.user.name
            )

            user = await conn.fetchrow(
                """
                SELECT checking_account_balance, savings_account_balance
                FROM users
                WHERE discord_id = $1
                  AND guild_id = $2
                """,
                interaction.user.id,
                guild_id
            )

        if not user:
            return await interaction.response.send_message(
                "User not found in database.",
                ephemeral=True
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

    # =====================================================
    # 🔁 WIREFUNDS COMMAND
    # =====================================================
    @app_commands.command(name="wirefunds", description="Transfer money between accounts")
    @app_commands.describe(
        amount="Amount ('ALL', 500, $500, 500.50, 10k, 2.5m, etc.)",
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
        guild_id = interaction.guild.id if interaction.guild else 0

        if amt == -1:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🤨 Invalid Amount",
                    description="Use numbers like `500`, `$500`, `10k`, `2.5m`, or `all`.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        async with pool.acquire() as conn:

            await upsert_user(
                conn,
                interaction.user.id,
                guild_id,
                interaction.user.name
            )

            user = await conn.fetchrow(
                """
                SELECT checking_account_balance, savings_account_balance
                FROM users
                WHERE discord_id = $1
                  AND guild_id = $2
                """,
                interaction.user.id,
                guild_id
            )

        if not user:
            return await interaction.response.send_message(
                "User not found in database.",
                ephemeral=True
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

        direction_text = ""
        amt_cents = 0

        # =========================
        # ALL TRANSFER
        # =========================
        if amt == "all":

            if direction.value == "to_savings":

                if checking <= 0:
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            title="🚫 Transfer Failed",
                            description="Your checking account is already empty.",
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
                            description="Your savings account is empty.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )

                amt_cents = savings
                savings = 0
                checking += amt_cents
                direction_text = "Savings → Checking"

        # =========================
        # NORMAL AMOUNT
        # =========================
        else:

            amt_cents = amt  # already in cents now

            if amt_cents <= 0:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🤨 Invalid Amount",
                        description="Try `$500`, `10k`, `2.5m`, or `all`.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

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

        # =========================
        # UPDATE DB
        # =========================
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET checking_account_balance = $1,
                    savings_account_balance = $2
                WHERE discord_id = $3
                  AND guild_id = $4
                """,
                checking,
                savings,
                interaction.user.id,
                guild_id
            )

        # =========================
        # RESPONSE
        # =========================
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
