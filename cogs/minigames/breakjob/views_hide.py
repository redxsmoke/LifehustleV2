import discord
import asyncio
import random


class HideButton(discord.ui.Button):
    """
    A button representing a hiding spot.
    When clicked, it sets the chosen hiding spot and triggers police logic.
    """

    def __init__(self, emoji: str, spot: str, view):
        super().__init__(label=spot, emoji=emoji, style=discord.ButtonStyle.blurple)
        self.spot = spot
        self.vault_view = view

    async def callback(self, interaction: discord.Interaction):
        # Only the robber can choose a hiding spot
        if interaction.user.id != self.vault_view.user_id:
            return await interaction.response.send_message(
                "This isn't your robbery.", ephemeral=True
            )

        # Mark hide spot chosen
        self.vault_view.hide_spot_chosen = True
        self.vault_view.chosen_spot = self.spot

        await interaction.response.send_message(
            f"You hid **{self.spot}**. The police are on their way...",
            ephemeral=True
        )

        # Trigger police search
        asyncio.create_task(
            self.vault_view.trigger_police_search(interaction, self.spot)
        )


class HideOnlyView(discord.ui.View):
    """
    A view containing only hiding spot buttons.
    """

    def __init__(self, vault_view):
        super().__init__(timeout=30)
        self.vault_view = vault_view

        # Pick 4 random hiding spots from the full list of 12
        spots_to_show = random.sample(vault_view.hide_spots, 4)

        # Add only those 4 buttons
        for emoji, spot in spots_to_show:
            self.add_item(HideButton(emoji, spot, vault_view))

    async def on_timeout(self):
        # If user already chose a spot or robbery ended, do nothing
        if self.vault_view.hide_spot_chosen or self.vault_view.robbery_complete.is_set():
            return

        # ⭐ NEW: If Smoke Bomb was used, DO NOT auto-arrest
        if self.vault_view.smoke_bomb_used:
            # Let police logic handle guaranteed escape
            asyncio.create_task(
                self.vault_view.trigger_police_search(None, None)
            )
            return

        # Otherwise → normal auto-arrest
        asyncio.create_task(
            self.vault_view.handle_hide_timeout()
        )
