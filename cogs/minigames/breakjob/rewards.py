import random
from db.connection import get_pool

PADLOCK_ITEM_ID = 11

# ============================================================
# SUCCESS REWARD (cash + XP)
# ============================================================
async def apply_success_rewards(interaction, user_id: int):
    """
    Awards cash + XP for successfully cracking the vault.
    Returns (cash_awarded_in_pennies, xp_awarded)
    """

    pool = get_pool()
    async with pool.acquire() as conn:

        # Fetch occupation wage/xp values
        row = await conn.fetchrow(
            """
            SELECT c.wage_per_shift, c.xp_per_shift
            FROM cd_occupations c
            JOIN user_occupations uo ON uo.cd_occupation_id = c.cd_occupation_id
            WHERE uo.discord_id = $1 AND uo.guild_id = $2
            """,
            user_id,
            interaction.guild.id
        )

        wage_per_shift = row["wage_per_shift"]      # stored in cents
        xp_per_shift   = row["xp_per_shift"]        # stored as integer

        # Apply multipliers
        cash_multiplier = random.randint(100, 150)
        xp_multiplier   = random.randint(10, 15)

        cash_pennies = wage_per_shift * cash_multiplier
        xp_awarded   = xp_per_shift * xp_multiplier

        # Apply rewards
        await conn.execute(
            """
            UPDATE users
            SET checking_account_balance = checking_account_balance + $1,
                xp = xp + $2
            WHERE discord_id = $3 AND guild_id = $4
            """,
            cash_pennies,
            xp_awarded,
            user_id,
            interaction.guild.id
        )

    return cash_pennies, xp_awarded


# ============================================================
# ASSET PROTECTION (Pad Lock item)
# ============================================================
async def apply_protect_assets(conn, user_id: int, guild_id: int, money_loss: int):
    """
    If the user has a Pad Lock in user_items, consume ONE and protect funds.
    Returns (final_loss, used_padlock):
      - final_loss: amount to actually deduct from checking_account_balance
      - used_padlock: True if a pad lock was consumed, else False
    """

    # Check if user has at least one Pad Lock
    padlock_row = await conn.fetchrow(
        """
        SELECT quantity
        FROM user_items
        WHERE discord_id = $1
          AND guild_id = $2
          AND item_id = $3
        """,
        user_id,
        guild_id,
        PADLOCK_ITEM_ID
    )

    if padlock_row and padlock_row["quantity"] > 0:
        # Consume one Pad Lock
        await conn.execute(
            """
            UPDATE user_items
            SET quantity = quantity - 1
            WHERE discord_id = $1
              AND guild_id = $2
              AND item_id = $3
            """,
            user_id,
            guild_id,
            PADLOCK_ITEM_ID
        )

        # Pad Lock protects all funds → no loss
        return 0, True

    # No Pad Lock → full loss applies
    return money_loss, False


# ============================================================
# SET BAIL AMOUNT (used when police catch the user)
# ============================================================
async def set_bail_for_user(user_id: int, guild_id: int):
    """
    Sets a bail amount for the user after being arrested.
    """

    bail_total = random.randint(5000, 20000) * 100  # pennies

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_bail (discord_id, guild_id, bail_total, is_active)
            VALUES ($1, $2, $3, TRUE)
            """,
            user_id,
            guild_id,
            bail_total
        )

    return bail_total
