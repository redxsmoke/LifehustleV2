import discord
from discord.ext import commands


class System(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if getattr(interaction, "_user_created", False):
            try:
                await interaction.followup.send(
                    "🎉 User account created",
                    ephemeral=True
                )
            except:
                pass


async def setup(bot):
    await bot.add_cog(System(bot))