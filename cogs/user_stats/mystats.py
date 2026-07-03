import discord
from discord import app_commands
from discord.ext import commands
import asyncpg

def build_smash_style_bar(street_cred: int) -> str:
    street_cred = max(-250, min(250, street_cred))

    bar_length = 12
    index = int(((street_cred + 250) / 500) * (bar_length - 1))

    bar = []
    for i in range(bar_length):
        if i < bar_length // 2:
            bar.append("🟥")
        else:
            bar.append("🟩")

    bar[index] = "🔘"
    return "".join(bar)

def street_cred_title(street_cred: int) -> str:
    if street_cred <= -150:
        return "🚨 Certified Snitch"
    elif street_cred <= -50:
        return "⚠️ Questionable Reputation"
    elif street_cred < 50:
        return "😐 Neutral Standing"
    elif street_cred < 150:
        return "🔥 Local Hustler"
    else:
        return "💎 Street Legend"

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mystats", description="View your personal stats.")
    async def mystats(self, interaction: discord.Interaction):
        discord_id = interaction.user.id
        guild_id = interaction.guild.id

        async with self.bot.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT street_cred, last_updated
                FROM user_stats
                WHERE discord_id = $1 AND guild_id = $2
            """, discord_id, guild_id)

        if not row:
            return await interaction.response.send_message(
                "You don't have any stats yet.", ephemeral=True
            )

        street_cred = row["street_cred"]
        bar = build_smash_style_bar(street_cred)
        title = street_cred_title(street_cred)

        embed_color = discord.Color.green() if street_cred >= 0 else discord.Color.red()

        embed = discord.Embed(
            title=f"📊 Your Stats Profile",
            color=embed_color
        )

        embed.add_field(
            name=title,
            value=(
                f"**Street Cred:** `{street_cred}/250`\n"
                f"```\n{bar}\n```"
            ),
            inline=False
        )

        embed.set_footer(text="Your reputation determines how the streets treat you.")

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
