import discord
from db.connection import get_pool

from police.police_reported_logic.intimidation_engine import process_snitch as handle_universal_snitch
from police.police_reported_logic.police_items import PoliceItemView


class SnitchConfirmView(discord.ui.View):
    """
    IDENTICAL to Vault SnitchDecisionView, but used for GTA Stage 1.
    The only difference is crime_type='grand_theft_auto' in the controller.
    """
    def __init__(self, controller):
        super().__init__(timeout=120)
        self.controller = controller
        self.message: discord.Message | None = None

        self.snitchers = set()
        self.no_snitchers = set()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Allow crook to click so they get insult message instead of "interaction failed"
        return True

    # ============================================================
    # 😎 I Ain't No Snitch
    # ============================================================
    @discord.ui.button(label="😎 I Ain't No Snitch", style=discord.ButtonStyle.secondary)
    async def no_snitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        # Crook cannot vote
        if user_id == self.controller.user_id:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚫 Nice Try",
                    description="Do you need a reminder not to snitch on yourself? A Real Einstein you are.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        await interaction.response.defer()

        # Already voted
        if user_id in self.no_snitchers or user_id in self.snitchers:
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Already Voted",
                    description="You've already made your choice.",
                    color=discord.Color.orange()
                ),
                ephemeral=True
            )

        self.no_snitchers.add(user_id)

        # Street cred reward
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

        # Disable only for THIS user
        button.disabled = True
        if self.message:
            await self.message.edit(view=self)

    # ============================================================
    # 🚨 Report to Police
    # ============================================================
    @discord.ui.button(label="🚨 Report to Police", style=discord.ButtonStyle.red)
    async def snitch(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        # Crook cannot snitch on themselves
        if user_id == self.controller.user_id:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="🚫 Absolutely Not",
                    description="Are you the dumbest criminal alive?",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

        await interaction.response.defer()

        # Already voted
        if user_id in self.no_snitchers or user_id in self.snitchers:
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Already Voted",
                    description="You've already made your choice.",
                    color=discord.Color.orange()
                ),
                ephemeral=True
            )

        self.snitchers.add(user_id)

        # Street cred penalty
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
        if self.message:
            await self.message.edit(view=self)

        # Intimidation item check
        blocked = await handle_universal_snitch(
            self.controller,
            interaction,
            user_id
        )

        if blocked:
            return

        # Police alerted
        await self.controller.channel.send(
            embed=discord.Embed(
                title="🚨 Crime Report Filed!",
                description="A witness reported the car theft to the police!",
                color=0xE74C3C
            )
        )

        # Police item selection (smoke bomb, corrupt cop, take chances)
        user_items = await self.controller.get_user_items()
        police_view = PoliceItemView(self.controller, user_items)

        msg = await self.controller.channel.send(
            embed=discord.Embed(
                title="🚨 Someone alerted the police!",
                description="⚠️ Choose your move! You have 20 seconds before the police leave the station!",
                color=0xE74C3C
            ),
            view=police_view
        )
        police_view.message = msg

        await police_view.wait_for_choice()
        await police_view.finalize_choice(interaction)

    # ============================================================
    # TIMEOUT
    # ============================================================
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)
