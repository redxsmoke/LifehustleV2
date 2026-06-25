INTIMIDATION_ITEM_ID = 15

async def process_snitch(robber_id: int, guild_id: int, snitcher_id: int):
    """
    Determines whether intimidation blocks the snitch.
    Returns a dict:
    {
        "intimidation_blocked": bool,
        "revealed": bool,
        "snitcher_id": int
    }
    """

    from db.connection import get_pool
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT quantity
            FROM user_items
            WHERE discord_id = $1
              AND guild_id = $2
              AND item_id = $3
        """, robber_id, guild_id, INTIMIDATION_ITEM_ID)

        has_intimidation = row and row["quantity"] > 0

        if has_intimidation:
            # Consume ONE intimidation item
            await conn.execute("""
                UPDATE user_items
                SET quantity = quantity - 1
                WHERE discord_id = $1
                  AND guild_id = $2
                  AND item_id = $3
            """, robber_id, guild_id, INTIMIDATION_ITEM_ID)

            return {
                "intimidation_blocked": True,
                "revealed": True,
                "snitcher_id": snitcher_id
            }

        # No intimidation → snitch proceeds normally
        return {
            "intimidation_blocked": False,
            "revealed": False,
            "snitcher_id": snitcher_id
        }
