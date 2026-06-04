import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your bank accounts")
    async def balance(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:

            # ALWAYS ensure user exists through central system
            await upsert_user(conn, interaction.user.id, str(interaction.user))

            user = await conn.fetchrow(
                """
                SELECT checking_account_balance, savings_account_balance
                FROM users
                WHERE discord_id = $1
                """,
                interaction.user.id
            )

        net_worth = (
            user["checking_account_balance"]
            + user["savings_account_balance"]
        )

        await interaction.response.send_message(
            f"""
**{interaction.user.name}'s Balance**

💰 Checking: {user['checking_account_balance']}
🏦 Savings: {user['savings_account_balance']}
📊 Net Worth: {net_worth}
"""
        )


async def setup(bot):
    await bot.add_cog(Economy(bot))