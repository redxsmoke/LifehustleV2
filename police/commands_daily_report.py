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
            return await interaction.response.send_message(
                "No crimes selected for today yet.",
                ephemeral=True
            )

        view = DailyCrimeReportView(crimes, interaction.guild.id)

        await interaction.response.send_message(
            embed=view.build_page(),
            view=view
        )


async def setup(bot):
    await bot.add_cog(DailyReportCommands(bot))
