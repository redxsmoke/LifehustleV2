import asyncpg
from db.connection import get_pool
from utils.crime_system import log_crime, get_user_company
import random


async def apply_padlock_protection(conn: asyncpg.Connection, user_id: int, guild_id: int, money_loss: int):
    try:
        row = await conn.fetchrow(
            """
            SELECT quantity
            FROM user_items
            WHERE discord_id = $1 AND guild_id = $2 AND item_id = 11
            """,
            user_id, guild_id
        )

        padlock_qty = row["quantity"] if row else 0

        if padlock_qty <= 0:
            return money_loss, False

        await conn.execute(
            """
            UPDATE user_items
            SET quantity = quantity - 1
            WHERE discord_id = $1 AND guild_id = $2 AND item_id = 11
            """,
            user_id, guild_id
        )

        return 0, True

    except Exception:
        return money_loss, False


async def apply_money_seizure(conn: asyncpg.Connection, user_id: int, guild_id: int, amount: int):
    await conn.execute("""
        UPDATE users
        SET checking_account_balance = GREATEST(checking_account_balance - $1, 0)
        WHERE discord_id = $2 AND guild_id = $3
    """, amount, user_id, guild_id)


async def apply_employment_firing(conn: asyncpg.Connection, user_id: int, guild_id: int):
    await conn.execute("""
        UPDATE user_occupations
        SET employment_end_date = NOW()
        WHERE discord_id = $1
          AND guild_id = $2
          AND employment_end_date IS NULL
    """, user_id, guild_id)


async def apply_criminal_record(conn: asyncpg.Connection, user_id: int, guild_id: int):
    await conn.execute("""
        INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
        VALUES ($1, $2, 1, NOW())
    """, user_id, guild_id)

    await conn.execute("""
        INSERT INTO user_criminal_record (discord_id, guild_id, cd_crime_id, date_of_offense)
        VALUES ($1, $2, 4, NOW())
    """, user_id, guild_id)


async def apply_bail(conn: asyncpg.Connection, user_id: int, guild_id: int):
    """
    Correct bail system:
    - Base bail = $5000 → convert to pennies
    - Multiplier = 1.5x – 3.5x
    - Store final bail in pennies
    """

    try:
        # Base bail in pennies
        base_bail_cents = 5000 * 100

        # Random multiplier
        multiplier = random.uniform(1.5, 3.5)

        # Final bail in pennies
        final_bail = int(base_bail_cents * multiplier)

        row = await conn.fetchrow(
            """
            SELECT bail_total, is_active
            FROM user_bail
            WHERE discord_id = $1 AND guild_id = $2
            """,
            user_id, guild_id
        )

        if row:
            await conn.execute(
                """
                UPDATE user_bail
                SET bail_total = $3,
                    is_active = TRUE
                WHERE discord_id = $1 AND guild_id = $2
                """,
                user_id, guild_id, final_bail
            )
        else:
            await conn.execute(
                """
                INSERT INTO user_bail (discord_id, guild_id, bail_total, is_active)
                VALUES ($1, $2, $3, TRUE)
                """,
                user_id, guild_id, final_bail
            )

    except Exception:
        pass


async def apply_protect_assets(conn, user_id, guild_id, money_loss):
    return await apply_padlock_protection(conn, user_id, guild_id, money_loss)


async def set_bail_for_user(user_id, guild_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        await apply_bail(conn, user_id, guild_id)


async def apply_police_consequences(controller, chosen_spot: str | None):
    pool = get_pool()
    async with pool.acquire() as conn:

        guild_id = controller.guild_id
        user_id = controller.user_id
        config = controller.get_config()

        if config.get("use_money_seizure"):
            balance = await conn.fetchval("""
                SELECT checking_account_balance
                FROM users
                WHERE discord_id = $1 AND guild_id = $2
            """, user_id, guild_id) or 0

            money_loss = balance

            if config.get("use_padlock"):
                final_loss, used_padlock = await apply_padlock_protection(
                    conn, user_id, guild_id, money_loss
                )
            else:
                final_loss, used_padlock = money_loss, False

            if final_loss > 0:
                await apply_money_seizure(conn, user_id, guild_id, final_loss)

        else:
            final_loss = 0
            used_padlock = False

        if config.get("use_employment_firing"):
            await apply_employment_firing(conn, user_id, guild_id)

        if config.get("use_criminal_record"):
            await apply_criminal_record(conn, user_id, guild_id)

        if config.get("use_bail"):
            await apply_bail(conn, user_id, guild_id)

        company_name, occupation_name = await get_user_company(guild_id, user_id)

        if controller.crime_type.startswith("vault"):
            location_text = "vault"
        elif controller.crime_type.startswith("gta"):
            location_text = "house"
        else:
            location_text = company_name or "unknown"

        await log_crime(
            guild_id=guild_id,
            perpetrator_id=user_id,
            crime_type=controller.crime_type,
            crime_description=f"Arrested while hiding at {location_text}",
            clue_description=None,
            evidence_list=[],
            status="solved",
            location=location_text,
        )

        return final_loss, used_padlock
