import discord
from .views_main import VaultGameView


async def start_vault_game(interaction: discord.Interaction, bot):
    """
    Starts the BreakJob vault minigame.
    Uses followup.send() because the interaction was already responded to.
    """

    view = VaultGameView(
        user_id=interaction.user.id,
        bot=bot,
        channel=interaction.channel
    )

    embed = discord.Embed(
        title="🔐 Vault Heist",
        description=(
            "Crack the 3‑digit vault code.\n"
            "You have **5 attempts**.\n\n"
           
        ),
        color=0x2ECC71
    )

    # ⭐ IMPORTANT: use followup.send because the interaction was already responded to
    await interaction.followup.send(embed=embed, view=view)
