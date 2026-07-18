import discord
import logging
from db.connection import get_pool

from police.police_reported_logic.intimidation_engine import process_snitch as handle_universal_snitch
from police.police_reported_logic.police_items import PoliceItemView

logger = logging.getLogger("crime.universal_snitch")
logger.setLevel(logging.ERROR)

CRIME_TEXT = {
    "vault": {
        "witness_title": "👀 Witness Decision",
        "witness_description": (
            "Someone is cracking a vault!\n\n"
            "Will you snitch or stay quiet?\n\n"
            "😎 I Ain't No Snitch → **+10 street cred**\n"
            "🚨 Snitch → **-10 street cred**"
        ),
    },

    "grand_theft_auto": {
        "witness_title": "🚨Vehicle Breakin in Progress",
        "witness_description": (
            "A thief is trying to break into someone's vehicle!!\n\n"
            "Will you snitch or stay quiet?\n\n"
            "😎 I Ain't No Snitch → **+10 street cred**\n"
            "🚨 Snitch → **-10 street cred**"
        ),
    },
}


class UniversalSnitchView(discord.ui.View):
    def __init__(self, controller, channel, crime_owner_id, lockout_target=None):
        super().__init__(timeout=15)  # ⭐ FIXED — 15 seconds
        self.controller = controller
        self.channel = channel
        self.crime_owner_id = crime_owner_id
        self.lockout_target = lockout_target

        self.snitchers = set()
        self.no_snitchers = set()

        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="😎 I Ain't No Snitch", style=discord.ButtonStyle.secondary)
    async def no_snitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user_id = interaction.user.id

            if user_id == self.crime_owner_id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚫 Nice Try",
                        description="You can’t NOT snitch on your own crime.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            await interaction.response.defer(ephemeral=True)

            if user_id in self.no_snitchers or user_id in self.snitchers:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        title="⚠️ Already Voted",
                        description="You've already made your choice.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            self.no_snitchers.add(user_id)

            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_stats (discord_id, guild_id, street_cred)
                    VALUES ($1, $2, 10)
                    ON CONFLICT (discord_id, guild_id)
                    DO UPDATE SET street_cred = LEAST(250, COALESCE(user_stats.street_cred, 0) + 10),
                                  last_updated = NOW();
                """, user_id, interaction.guild.id)

            await interaction.followup.send(
                embed=discord.Embed(
                    title="😎 You Stayed Quiet",
                    description="You kept your mouth shut. **+10 street cred.**",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

            # ⭐ DO NOT EDIT THE VIEW HERE — prevents timeout reset

        except Exception:
            logger.exception("UniversalSnitchView.no_snitch crashed")

    @discord.ui.button(label="🚨 Snitch", style=discord.ButtonStyle.red)
    async def snitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user_id = interaction.user.id

            if user_id == self.crime_owner_id:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚫 Absolutely Not",
                        description="Are you the dumbest criminal alive?",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            await interaction.response.defer(ephemeral=True)

            if user_id in self.no_snitchers or user_id in self.snitchers:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        title="⚠️ Already Voted",
                        description="You've already made your choice.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

            self.snitchers.add(user_id)

            if self.lockout_target is not None:
                if hasattr(self.lockout_target, "has_snitched"):
                    self.lockout_target.has_snitched = True
                if hasattr(self.lockout_target, "snitch_disabled"):
                    self.lockout_target.snitch_disabled = True

            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_stats (discord_id, guild_id, street_cred)
                    VALUES ($1, $2, -10)
                    ON CONFLICT (discord_id, guild_id)
                    DO UPDATE SET street_cred = GREATEST(-250, COALESCE(user_stats.street_cred, 0) - 10),
                                  last_updated = NOW();
                """, user_id, interaction.guild.id)

            # Disable both buttons globally
            for child in self.children:
                child.disabled = True

            # ⭐ FIXED — does NOT reset timeout
            await interaction.message.edit(view=self)

            blocked = await handle_universal_snitch(
                self.controller,
                interaction,
                user_id
            )

            if blocked:
                return

            user_items = await self.controller.get_user_items()
            police_view = PoliceItemView(self.controller, user_items)

            msg = await self.channel.send(
                embed=discord.Embed(
                    title="🚨 Someone alerted the police!",
                    description="⚠️ Choose your move! You have 20 seconds before the police leave the station!",
                    color=0xE74C3C
                ),
                view=police_view
            )

            await police_view.wait_for_choice()
            await police_view.finalize_choice(interaction)

        except Exception:
            logger.exception("UniversalSnitchView.snitch crashed")

    async def on_timeout(self):
        try:
            for child in self.children:
                child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            logger.exception("UniversalSnitchView timeout crashed")


async def start_snitch_flow(controller, channel, lockout_target=None):
    crime_type = controller.crime_type
    text = CRIME_TEXT.get(crime_type, CRIME_TEXT["vault"])

    view = UniversalSnitchView(controller, channel, controller.user_id, lockout_target=lockout_target)

    msg = await channel.send(
        embed=discord.Embed(
            title=text["witness_title"],
            description=text["witness_description"],
            color=discord.Color.red()
        ),
        view=view
    )

    view.message = msg
