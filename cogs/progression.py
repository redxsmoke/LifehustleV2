import discord
from discord.ext import commands
from discord import app_commands

from db.connection import get_pool
from db.users import upsert_user


class Progression(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="level", description="Check your XP and level")
    async def level(self, interaction: discord.Interaction):
        pool = get_pool()

        async with pool.acquire() as conn:

            # ALWAYS ensure user exists via central system
            await upsert_user(conn, interaction.user.id, str(interaction.user))

            user = await conn.fetchrow(
                """
                SELECT xp, level
                FROM users
                WHERE discord_id = $1
                """,
                interaction.user.id
            )

        await interaction.response.send_message(
            f"""
**{interaction.user.name}'s Progress**

⭐ XP: {user['xp']}
📈 Level: {user['level']}
"""
        )


async def setup(bot):
    await bot.add_cog(Progression(bot))