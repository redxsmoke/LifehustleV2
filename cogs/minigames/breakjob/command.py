import discord

async def start_vault_game(interaction: discord.Interaction, bot):
    """
    Starts the BreakJob vault minigame.

    IMPORTANT:
    - This function is called using a DummyInteraction inside handle_rob_job.
    - DummyInteraction CANNOT use interaction.response.defer() or followup.
    - Therefore: we ONLY send messages directly to the channel here.
    - The REAL interaction must be deferred inside handle_rob_job.
    """

    # Lazy import to avoid circular dependency
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

    # IMPORTANT:
    # DummyInteraction cannot use interaction.response or followup.
    # So we send directly to the channel.
    await interaction.channel.send(embed=embed, view=view)
