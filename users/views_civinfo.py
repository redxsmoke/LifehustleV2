import discord
from discord.ext import commands
from discord import Embed, ui
from db.connection import get_pool


# 250k dollars → 25,000,000 pennies
UNLOCK_COST = 25_000_000  


class UnlockView(ui.View):
    def __init__(self, target: discord.Member):
        super().__init__(timeout=60)
        self.target = target

    @ui.button(label="🔓 Unlock Full Report — $250,000", style=discord.ButtonStyle.green)
    async def unlock(self, interaction: discord.Interaction, button: ui.Button):

        viewer = interaction.user  # whoever clicked the button
        pool = get_pool()

        async with pool.acquire() as conn:

            # Check viewer balance
            balance = await conn.fetchval("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, viewer.id, interaction.guild.id)

            if balance < UNLOCK_COST:
                return await interaction.response.send_message(
                    f"❌ You need **${UNLOCK_COST/100:,.0f}** but only have **${balance/100:,.0f}**.",
                    ephemeral=True
                )

            # Deduct cost
            await conn.execute("""
                UPDATE users
                SET checking_account_balance = checking_account_balance - $1
                WHERE discord_id = $2 AND guild_id = $3
            """, UNLOCK_COST, viewer.id, interaction.guild.id)

        # Confirm purchase (ephemeral)
        await interaction.response.send_message(
            f"🔓 **Unlocked!** You paid **${UNLOCK_COST/100:,.0f}**.",
            ephemeral=True
        )

        # Send full report (ephemeral)
        cog = interaction.client.get_cog("CivInfo")
        await cog.send_full_report(interaction, self.target)


class CivInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_full_report(self, interaction, user):
        """Send the full report as an ephemeral followup message."""
        pool = get_pool()
        guild = interaction.guild

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT *
                FROM civinfo
                WHERE discord_id = $1 AND guild_id = $2
            """, user.id, guild.id)

        embed = Embed(
            title="👤 CivInfo Full Report",
            description=f"**{user.display_name}**",
            color=0xFFD700
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name="🪪 Identity",
            value=(
                f"**Name:** {row['UserName']}\n"
                f"**Occupation:** {row['Occupation']}\n"
                f"**Level:** {row['Level']}\n"
                f"**Crimes Solved:** {row['Crimes Solved']}\n"
                f"────────────────────────"
            ),
            inline=False
        )

        embed.add_field(
            name="💰 Financial Summary",
            value=f"**Net Worth:** `${row['Net Worth']:,}`\n────────────────────────",
            inline=False
        )

        embed.add_field(
            name="📍 Last Known Location",
            value=f"{row['Last Seen At']}\n────────────────────────",
            inline=False
        )

        embed.add_field(
            name="🚗 Vehicle Information",
            value=(
                f"**Vehicle:** {row['Vehicle']}\n"
                f"**Color:** {row['Vehicle Color']}\n"
                f"**Plate:** {row['License Plate']}"
            ),
            inline=False
        )

        embed.set_footer(text="CivInfo™ Full Report — LifeHustle RP")

        # Send ephemeral full report
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="civinfo",
        description="View the CivInfo profile for a user."
    )
    async def civinfo(self, ctx: commands.Context, user: discord.Member):
        guild = ctx.guild
        pool = get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT *
                FROM civinfo
                WHERE discord_id = $1 AND guild_id = $2
            """, user.id, guild.id)

        # Always show partial report (public)
        embed = Embed(
            title="👤 CivInfo Profile",
            description=f"**{user.display_name}**",
            color=0x00AEEF
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name="🪪 Identity",
            value=(
                f"**Name:** {row['UserName']}\n"
                f"**Occupation:** {row['Occupation']}\n"
                f"**Level:** {row['Level']}\n"
                f"**Crimes Solved:** {row['Crimes Solved']}\n"
                f"────────────────────────"
            ),
            inline=False
        )

        embed.add_field(
            name="🔒 Additional Info Locked",
            value=(
                "💰 **Net Worth**\n"
                "📍 **Last Known Location**\n"
                "🚗 **Vehicle Information**\n\n"
                f"Click **Unlock** to view the full report.\n"
                f"Cost: **$250,000**"
            ),
            inline=False
        )

        # Anyone can click the unlock button
        view = UnlockView(user)
        await ctx.reply(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(CivInfo(bot))
