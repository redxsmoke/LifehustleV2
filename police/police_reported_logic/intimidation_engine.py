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

            # Intimidation item is ID 15
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

                # Build intimidation message
                snitch_user = interaction.guild.get_member(snitcher_id)
                snitch_name = snitch_user.mention if snitch_user else "Unknown"

                # ⭐ FIX: Send PUBLIC message to the robbery channel
                await controller.channel.send(
                    embed=discord.Embed(
                        title="👁️ Intimidation Activated!",
                        description=(
                            "The snitch got cold feet and called off the police.\n"
                            "**Get out of there before someone else spots you!**\n\n"
                            f"**Snitch:** {snitch_name}"
                        ),
                        color=0x9B59B6
                    )
                )

                # ⭐ IMPORTANT: DO NOT respond to the interaction here
                # The main snitch flow will continue safely.

                return True  # intimidation blocked the snitch

        return False  # no intimidation item → snitch succeeds normally

    except Exception as e:
        logger.exception("Error in process_snitch: %s", e)
        return False
