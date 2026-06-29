import discord
from discord.ext import commands

class DeleteMessages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="deletemessages", description="Delete ALL messages in this channel.")
    @commands.has_permissions(manage_messages=True)
    async def deletemessages(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        channel = ctx.channel
        deleted = 0

        # Bulk delete (only works for messages < 14 days old)
        try:
            while True:
                batch = await channel.purge(limit=100)
                if not batch:
                    break
                deleted += len(batch)
        except Exception:
            pass

        # Fallback: delete older messages one by one
        async for msg in channel.history(limit=None, oldest_first=True):
            try:
                await msg.delete()
                deleted += 1
            except Exception:
                pass

        await ctx.reply(
            f"🧹 **Channel cleaned.**\nDeleted **{deleted}** messages.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(DeleteMessages(bot))
