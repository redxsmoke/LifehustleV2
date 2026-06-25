import discord
import asyncio
from .snitch_engine import process_snitch   # intimidation/snitch logic


class SnitchConfirmView(discord.ui.View):
    """
    Confirmation UI for snitching.
    """

    def __init__(self, vault_view):
        super().__init__(timeout=20)
        self.vault_view = vault_view

    @discord.ui.button(label="Yes, report to police", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button):

        # ⭐ MUST defer FIRST to avoid "This interaction failed"
        await interaction.response.defer(ephemeral=True)

        # Only the snitcher can confirm
        if interaction.user.id != self.vault_view.snitcher_id:
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="🐀 Not Your Squeal",
                    description="You're not the one who opened the snitch menu.",
                    color=0xF04747
                ),
                ephemeral=True
            )

        # ============================================================
        # PROCESS SNITCH → CHECK FOR INTIMIDATION
        # ============================================================
        result = await process_snitch(
            robber_id=self.vault_view.user_id,
            guild_id=interaction.guild.id,
            snitcher_id=interaction.user.id
        )

        # ============================================================
        # ⭐ INTIMIDATION BLOCKS THE SNITCH — STOP EVERYTHING
        # ============================================================
        if result.get("intimidation_blocked", False):

            # Reveal snitcher if configured
            if result.get("revealed", False):
                snitch_user = interaction.guild.get_member(result["snitcher_id"])
                snitch_name = snitch_user.mention if snitch_user else "Unknown"

                await interaction.channel.send(
                    embed=discord.Embed(
                        title="👁️ Intimidation Activated!",
                        description=(
                            "Your snitch got cold feet and called off the police.\n"
                            "**You're not done yet. Keep cracking the vault code!**\n\n"
                            f"**Snitch:** {snitch_name}"
                        ),
                        color=0x9B59B6
                    )
                )

            # Reset snitch state
            self.vault_view.snitched = False
            self.vault_view.outcome = None

            # DO NOT CONTINUE THE SNITCH FLOW
            self.stop()
            return

        # ============================================================
        # NORMAL SNITCH FLOW (NO INTIMIDATION)
        # ============================================================
        await interaction.followup.send(
            embed=discord.Embed(
                title="🚨 You alerted the police!",
                description="You made the call. The cops are rolling in.",
                color=0xF04747
            ),
            ephemeral=True
        )

        self.vault_view.snitched = True
        self.vault_view.outcome = "snitched"

        # Public announcement
        await self.vault_view.channel.send(
            embed=discord.Embed(
                title="🚨 Police Alerted!",
                description="Someone snitched! The police are on their way!",
                color=0xF04747
            )
        )

        # ⭐ NEW: Trigger police item choice BEFORE hide sequence
        asyncio.create_task(
            self.vault_view.start_police_item_choice(interaction)
        )

        self.stop()

    @discord.ui.button(label="I ain't no snitch", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="👍 Respect.",
                description="You chose loyalty over squealing.",
                color=0x2ECC71
            ),
            ephemeral=True
        )
        self.stop()


async def handle_snitch(vault_view, interaction):
    """
    Called when a user presses the Snitch button.
    """

    # Prevent snitching on yourself
    if interaction.user.id == vault_view.user_id:
        return await interaction.response.send_message(
            embed=discord.Embed(
                title="🤦 Are You the Dumbest Criminal Alive?",
                description=(
                    "You can't snitch on yourself.\n"
                    "That's not how crime — or common sense — works."
                ),
                color=0xF04747
            ),
            ephemeral=True
        )

    # Prevent double snitching
    if vault_view.snitched:
        return await interaction.response.send_message(
            embed=discord.Embed(
                title="🐀 Easy There, Squealer",
                description=(
                    "The snitch line is already lit up like a Christmas tree.\n\n"
                    "Whoever squealed first already earned their **official rat badge**.\n"
                    "You trying to snitch again just makes you look **desperate for attention**."
                ),
                color=0xF04747
            ),
            ephemeral=True
        )

    vault_view.snitched = True
    vault_view.snitcher_id = interaction.user.id

    # Show confirmation UI
    await interaction.response.send_message(
        embed=discord.Embed(
            title="⚠️ Confirm Snitch",
            description="Are you sure you want to report this crime to the police?",
            color=0xF04747
        ),
        view=SnitchConfirmView(vault_view),
        ephemeral=True
    )

