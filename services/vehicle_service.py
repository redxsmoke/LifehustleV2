import random
from db.connection import get_pool


# =========================
# CONDITION SYSTEM
# =========================
def compute_condition(commutes: int) -> int:
    """
    Condition is fully deterministic based on commute count.
    MUST match cd_vehicle_conditions table.
    """

    if commutes <= 50:
        return 7   # New
    elif commutes <= 200:
        return 8   # Excellent
    elif commutes <= 300:
        return 9   # Worn
    elif commutes <= 500:
        return 10  # Rusty
    else:
        return 11  # Poor (WARNING: ensure DB supports this id)


# =========================
# STATUS SYSTEM (RANDOM EVENTS)
# =========================
def compute_status(commutes: int) -> int:
    """
    6 = Operational
    8 = Broken Down
    9 = Flat Tire
    10 = Stolen (possible future extension)
    """

    # Base safe state
    status = 6

    # Flat tire (allowed after 30 commutes)
    if commutes >= 30:
        flat_chance = min(0.03 + (commutes / 1200), 0.25)
        if random.random() < flat_chance:
            return 9

    # Broken down (heavier scaling after 200)
    if commutes >= 200:
        break_chance = min(0.05 + (commutes / 500), 0.5)
        if random.random() < break_chance:
            return 8

    return status


# =========================
# MAIN UPDATE FUNCTION
# =========================
async def apply_commute_and_update(user_vehicle_id: int, discord_id: int):
    """
    SINGLE SOURCE OF TRUTH:
    - increments commute
    - recalculates condition
    - recalculates status
    - writes everything back
    """

    pool = get_pool()

    async with pool.acquire() as conn:

        # =========================
        # SAFE: update ONLY specific vehicle
        # =========================
        row = await conn.fetchrow("""
            UPDATE user_vehicles
            SET commute_count = commute_count + 1
            WHERE user_vehicle_id = $1
              AND discord_id = $2
            RETURNING commute_count
        """, user_vehicle_id, discord_id)

        if not row:
            return None

        commutes = row["commute_count"]

        condition = compute_condition(commutes)
        status = compute_status(commutes)

        await conn.execute("""
            UPDATE user_vehicles
            SET vehicle_condition_id = $1,
                vehicle_status_id = $2
            WHERE user_vehicle_id = $3
              AND discord_id = $4
        """, condition, status, user_vehicle_id, discord_id)

        return {
            "commutes": commutes,
            "condition": condition,
            "status": status
        }