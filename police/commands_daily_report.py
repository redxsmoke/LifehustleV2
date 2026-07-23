import discord
from discord import app_commands
from discord.ext import commands

from police.views_daily_report import DailyCrimeReportView

class DailyReportCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------
    # /dailypolicereport
    # ------------------------------------------------------------
    @app_commands.command(
        name="dailypolicereport",
        description="View today's police crime report."
    )
    async def dailypolicereport(self, interaction: discord.Interaction):

        scheduler = self.bot.get_cog("DailyCrimeScheduler")

        if scheduler is None:
            return await interaction.response.send_message(
                "Daily scheduler not loaded.",
                ephemeral=True
            )

        crimes = scheduler.daily_crimes.get(interaction.guild.id)

        if not crimes:
            embed = discord.Embed(
                title="🚓Daily Police Report",
                description="📡 No crimes selected for today yet.",
                color=discord.Color.orange()
            )

            return await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

        view = DailyCrimeReportView(crimes, interaction.guild.id)

        # ------------------------------------------------------------
        # ⭐ FIXED LINE — MUST AWAIT build_page()
        # ------------------------------------------------------------
        embed = await view.build_page()

        await interaction.response.send_message(
            embed=embed,
            view=view
        )


async def setup(bot):
    await bot.add_cog(DailyReportCommands(bot))
