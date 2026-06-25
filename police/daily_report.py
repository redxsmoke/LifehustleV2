import random
from db.connection import get_pool


async def select_daily_crimes(guild_id: int):
    """
    Selects up to 10 crimes for the daily police report.
    Priority:
    1. Yesterday's crimes
    2. Today's crimes (if yesterday has none or not enough)
    3. Older unsolved crimes
    """

    pool = get_pool()
    async with pool.acquire() as conn:

        # ------------------------------------------------------------
        # 1. YESTERDAY'S CRIMES
        # ------------------------------------------------------------
        yesterday_rows = await conn.fetch("""
            SELECT
                crime_id,
                guild_id,
                perpetrator_id,
                crime_type,
                crime_description,
                location,
                timestamp,
                status,
                reward_given
            FROM police_crimes
            WHERE guild_id = $1
              AND status = 'unsolved'
              AND timestamp::date = CURRENT_DATE - INTERVAL '1 day'
            ORDER BY timestamp ASC
        """, guild_id)

        selected = list(yesterday_rows)

        if len(selected) >= 10:
            selected = random.sample(selected, 10)
            await rotate_inactive_crimes(conn, guild_id, [c["crime_id"] for c in selected])
            return selected

        # ------------------------------------------------------------
        # 2. TODAY'S CRIMES
        # ------------------------------------------------------------
        needed = 10 - len(selected)

        today_rows = await conn.fetch("""
            SELECT
                crime_id,
                guild_id,
                perpetrator_id,
                crime_type,
                crime_description,
                location,
                timestamp,
                status,
                reward_given
            FROM police_crimes
            WHERE guild_id = $1
              AND status = 'unsolved'
              AND timestamp::date = CURRENT_DATE
            ORDER BY timestamp ASC
            LIMIT $2
        """, guild_id, needed)

        selected.extend(today_rows)

        if len(selected) >= 10:
            selected = selected[:10]
            await rotate_inactive_crimes(conn, guild_id, [c["crime_id"] for c in selected])
            return selected

        # ------------------------------------------------------------
        # 3. OLDER CRIMES
        # ------------------------------------------------------------
        needed = 10 - len(selected)

        older_rows = await conn.fetch("""
            SELECT
                crime_id,
                guild_id,
                perpetrator_id,
                crime_type,
                crime_description,
                location,
                timestamp,
                status,
                reward_given
            FROM police_crimes
            WHERE guild_id = $1
              AND status = 'unsolved'
              AND timestamp < CURRENT_DATE - INTERVAL '1 day'
            ORDER BY timestamp ASC
            LIMIT $2
        """, guild_id, needed)

        selected.extend(older_rows)

        selected_ids = [c["crime_id"] for c in selected]
        await rotate_inactive_crimes(conn, guild_id, selected_ids)

        return selected


# ------------------------------------------------------------
# DELETE CLUES FOR A CRIME
# ------------------------------------------------------------
async def delete_clues_for_crime(conn, crime_id: int, guild_id: int):
    await conn.execute("""
        DELETE FROM police_crime_tips
        WHERE crime_id = $1
          AND guild_id = $2
    """, crime_id, guild_id)


# ------------------------------------------------------------
# ROTATE INACTIVE CRIMES + DELETE THEIR CLUES
# ------------------------------------------------------------
async def rotate_inactive_crimes(conn, guild_id: int, selected_ids: list):
    """
    Marks older crimes as inactive ONLY if they were not selected.
    Also deletes all clues for crimes that become inactive.
    """

    if not selected_ids:
        selected_ids = [-1]

    # Find crimes that will be marked inactive
    inactive_rows = await conn.fetch("""
        SELECT crime_id
        FROM police_crimes
        WHERE guild_id = $1
          AND status = 'unsolved'
          AND crime_id NOT IN (SELECT UNNEST($2::int[]))
    """, guild_id, selected_ids)

    # Mark them inactive
    await conn.execute("""
        UPDATE police_crimes
        SET status = 'inactive'
        WHERE guild_id = $1
          AND status = 'unsolved'
          AND crime_id NOT IN (SELECT UNNEST($2::int[]))
    """, guild_id, selected_ids)

    # Delete clues for newly inactive crimes
    for row in inactive_rows:
        crime_id = row["crime_id"]
        await delete_clues_for_crime(conn, crime_id, guild_id)
