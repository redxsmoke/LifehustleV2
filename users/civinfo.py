# CIVINFO USING THE SQL VIEW

import json
import unicodedata
import discord
from discord import ui, Embed
from discord.ext import commands

from db.connection import get_pool


def normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


class CivInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="civinfo", description="Lookup a public CivInfo profile by nickname or username.")
    async def civinfo(self, ctx: commands.Context, *, query: str):
        guild = ctx.guild
        if guild is None:
            await ctx.reply("❌ CivInfo can only be used inside a server.")
            return

        q = normalize(query.strip())
        matches = []

        for member in guild.members:
            nickname = member.display_name or ""
            username = member.name or ""

            if q in normalize(nickname) or q in normalize(username):
                matches.append(member)

        if not matches:
            await ctx.reply("❌ No matching user found.")
            return

        if len(matches) == 1:
            await self.send_civinfo(ctx, matches[0])
            return

        view = CivInfoSelectView(matches, self)
        await ctx.reply("Multiple matches found. Select a user:", view=view, ephemeral=True)

    async def send_civinfo(self, ctx_or_interaction, target: discord.Member):
        pool = get_pool()
        guild_id = target.guild.id
        viewer_id = ctx_or_interaction.user.id if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author.id
        target_id = target.id

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT *
                FROM civinfo
                WHERE discord_id = $1 AND guild_id = $2
            """, target_id, guild_id)

            if not row:
                embed = Embed(
                    title=f"👤 CivInfo™ Public Record: {target.display_name}",
                    description="No CivInfo record found.",
                    color=0x3498DB
                )
                await self._send(ctx_or_interaction, embed=embed)
                return

            # Extract fields from the view
            username = row["username"]
            occupation = row["occupation"]
            level = row["level"]
            crimes_solved = row["crimes_solved"]
            checking = row["checking_account_balance"]
            savings = row["savings_account_balance"]
            networth = row["net_worth"]
            last_location = row["last_known_location"]
            vehicle = row["vehicle"]
            vehicle_color = row["vehicle_color"]
            license_plate = row["license_plate"]

            # Unlock state
            unlock_row = await conn.fetchrow("""
                SELECT unlocked_networth, unlocked_location, unlocked_vehicle_stats, unlocked_full
                FROM civinfo_unlocks
                WHERE viewer_id = $1 AND target_id = $2 AND guild_id = $3
            """, viewer_id, target_id, guild_id)

            unlocked_networth = unlock_row["unlocked_networth"] if unlock_row else False
            unlocked_location = unlock_row["unlocked_location"] if unlock_row else False
            unlocked_vehicle_stats = unlock_row["unlocked_vehicle_stats"] if unlock_row else False
            unlocked_full = unlock_row["unlocked_full"] if unlock_row else False

            if unlocked_full:
                unlocked_networth = unlocked_location = unlocked_vehicle_stats = True

            # Build embed
            embed = Embed(
                title=f"👤 CivInfo™ Public Record: {target.display_name}",
                color=0x3498DB
            )

            embed.add_field(name="Username", value=username, inline=False)
            embed.add_field(name="Occupation", value=occupation, inline=False)
            embed.add_field(name="Level", value=str(level), inline=True)
            embed.add_field(name="Crimes Solved", value=str(crimes_solved), inline=True)

            # Net worth
            if unlocked_networth:
                embed.add_field(name="💰 Net Worth", value=f"${networth/100:,.2f}", inline=False)
            else:
                embed.add_field(name="💰 Net Worth", value="🔒 Locked", inline=False)

            # Last known location
            if unlocked_location:
                embed.add_field(name="📍 Last Known Location", value=last_location, inline=False)
            else:
                embed.add_field(name="📍 Last Known Location", value="🔒 Locked", inline=False)

            # Vehicle stats
            if unlocked_vehicle_stats:
                embed.add_field(
                    name="🚗 Vehicle",
                    value=f"{vehicle} ({vehicle_color}) — Plate: {license_plate}",
                    inline=False
                )
            else:
                embed.add_field(name="🚗 Vehicle Stats", value="🔒 Locked", inline=False)

            # Unlock buttons
            view = CivInfoUnlockView(
                viewer_id=viewer_id,
                target_id=target_id,
                guild_id=guild_id,
                networth=networth,
                last_location=last_location,
                vehicle=vehicle,
                vehicle_color=vehicle_color,
                license_plate=license_plate,
                unlocked_networth=unlocked_networth,
                unlocked_location=unlocked_location,
                unlocked_vehicle_stats=unlocked_vehicle_stats,
                unlocked_full=unlocked_full,
                cog=self
            )

            await self._send(ctx_or_interaction, embed=embed, view=view)

    async def _send(self, ctx_or_interaction, embed=None, view=None, content=None):
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(
                content=content,
                embed=embed,
                view=view,
                ephemeral=True
            )
        else:
            await ctx_or_interaction.reply(content=content, embed=embed, view=view)
