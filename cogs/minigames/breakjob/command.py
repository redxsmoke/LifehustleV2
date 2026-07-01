import discord

async def start_vault_game(interaction: discord.Interaction, bot):
    """
    Starts the BreakJob vault minigame.

    FIXED VERSION:
    - Lazy‑imports VaultGameView to avoid circular import
    - Sends a NEW message directly to the channel
    - Prevents webhook expiration crashes
    """

    # ⭐ FIX: Import INSIDE the function to avoid circular import
    from .views_main import VaultGameView

    # Build the view
    view = VaultGameView(
        user_id=interaction.user.id,
        bot=bot,
        channel=interaction.channel,
        guild_id=interaction.guild.id
    )

    # Build the embed
    embed = discord.Embed(
        title="🔐 Vault Heist",
        description=(
            "Crack the 3‑digit vault code.\n"
            "You have **5 attempts**.\n\n"
        ),
        color=0x2ECC71
    )

    # Send a NEW message directly to the channel
    await interaction.channel.send(embed=embed, view=view)
