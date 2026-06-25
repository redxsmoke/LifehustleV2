import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Test command")
    async def ping(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:
            await upsert_user(
                conn,
                interaction.user.id,
                str(interaction.user),
                interaction.guild.id
            )

        await interaction.response.send_message("pong")


async def setup(bot):
    await bot.add_cog(General(bot))