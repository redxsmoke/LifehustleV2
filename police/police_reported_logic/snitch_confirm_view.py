import discord
from discord.ui import View, Button

from .intimidation_engine import process_snitch
from .police_items import PoliceItemView


class SnitchConfirmView(View):
    def __init__(self, controller):
        super().__init__(timeout=20)
        self.controller = controller

        # Track snitch state
        if not hasattr(self.controller, "has_snitched"):
            self.controller.has_snitched = False

        self.add_item(ConfirmSnitchButton(controller))
        self.add_item(CancelSnitchButton())


class ConfirmSnitchButton(Button):
    def __init__(self, controller):
        super().__init__(label="🚨 Confirm Snitch", style=discord.ButtonStyle.danger)
        self.controller = controller

    async def callback(self, interaction: discord.Interaction):

        # ⭐ Crook cannot snitch on themselves
        if interaction.user.id == self.controller.user_id:
            return await interaction.response.send_message(
                "You can't snitch on yourself.",
                ephemeral=True
            )

        # ⭐ Prevent double snitching
        if self.controller.has_snitched:
            return await interaction.response.send_message(
                "Someone already snitched.",
                ephemeral=True
            )

        # Mark snitch as used
        self.controller.has_snitched = True

        # ⭐ Disable ONLY this button globally
        self.disabled = True
        await interaction.message.edit(view=self.view)

        # Continue with intimidation logic
        blocked = await process_snitch(self.controller, interaction, interaction.user.id)

        if blocked:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="😨 Intimidated!",
                    description="You backed down. The criminal scared you off.",
                    color=0xF04747,
                ),
                ephemeral=True
            )
            return

        # Snitch succeeded
        await interaction.followup.send(
            embed=discord.Embed(
                title="🚨 You alerted the police!",
                description="You made the call. The cops are rolling in.",
                color=0xF04747,
            ),
            ephemeral=True
        )

        await self.controller.channel.send(
            embed=discord.Embed(
                title="🚨 Police Alerted!",
                description="Someone snitched! The police are on their way!",
                color=0xF04747,
            )
        )

        user_items = await self.controller.get_user_items()
        view = PoliceItemView(self.controller, user_items)

        await self.controller.channel.send(
            "Choose how to handle the police:",
            view=view
        )


class CancelSnitchButton(Button):
    def __init__(self):
        super().__init__(label="❌ Cancel", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Snitching canceled.", ephemeral=True)
