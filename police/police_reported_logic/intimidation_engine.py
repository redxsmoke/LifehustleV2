import discord
import logging
from db.connection import get_pool

logger = logging.getLogger("crime.intimidation")
logger.setLevel(logging.ERROR)


async def process_snitch(controller, interaction: discord.Interaction, snitcher_id: int):
    try:
        controller.snitcher_id = snitcher_id

        pool = get_pool()
        async with pool.acquire() as conn:

            # ⭐ FIXED: intimidation item is ID 15 (NOT 14)
            intimidation_row = await conn.fetchrow("""
                SELECT quantity
                FROM user_items
                WHERE discord_id = $1 AND guild_id = $2 AND item_id = 15
            """, controller.user_id, controller.guild_id)

            has_intimidation = intimidation_row and intimidation_row["quantity"] > 0

            if has_intimidation:
                # Consume intimidation item
                await conn.execute("""
                    UPDATE user_items
                    SET quantity = quantity - 1
                    WHERE discord_id = $1 AND guild_id = $2 AND item_id = 15
                """, controller.user_id, controller.guild_id)

                # Intimidation triggers
                snitch_user = interaction.guild.get_member(snitcher_id)
                snitch_name = snitch_user.mention if snitch_user else "Unknown"

                # ⭐ FIXED: consume interaction so Snitch button doesn't fail
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="👁️ Intimidation Activated!",
                        description=(
                            "Your snitch got cold feet and called off the police.\n"
                            "**You're not done yet. Keep cracking the vault code!**\n\n"
                            f"**Snitch:** {snitch_name}"
                        ),
                        color=0x9B59B6
                    ),
                    ephemeral=True
                )

                return True  # blocked

        return False  # snitch succeeds normally

    except Exception as e:
        logger.exception("Error in process_snitch: %s", e)
        return False
