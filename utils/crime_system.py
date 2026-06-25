import json
from db.connection import get_pool


# ------------------------------------------------------------
#  GET USER COMPANY + OCCUPATION
# ------------------------------------------------------------

async def get_user_company(guild_id: int, user_id: int):
    """
    Returns (company_name, occupation_name) for the user's current job.
    Falls back to defaults if unemployed.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 
                c.company_name,
                c.description AS occupation_name
            FROM user_occupations uo
            JOIN cd_occupations c 
                ON uo.cd_occupation_id = c.cd_occupation_id
            WHERE uo.discord_id = $1
              AND uo.guild_id = $2
              AND (uo.employment_end_date IS NULL OR uo.employment_end_date > NOW())
        """, user_id, guild_id)

    if row:
        return row["company_name"], row["occupation_name"]

    return "Unknown Location", "Unemployed"


# ------------------------------------------------------------
#  LOG CRIME INTO police_crimes TABLE
# ------------------------------------------------------------

async def log_crime(
    guild_id: int,
    perpetrator_id: int,
    crime_type: str,
    crime_description: str,
    clue_description: str,
    evidence_list: list,
    status: str,
    location: str
):
    """
    Inserts a crime record into police_crimes.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO police_crimes (
                guild_id,
                perpetrator_id,
                crime_type,
                crime_description,
                clue_description,
                evidence_list,
                status,
                location
            )
            VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8)
        """,
        guild_id,
        perpetrator_id,
        crime_type,
        crime_description,
        clue_description,
        json.dumps(evidence_list),   # <-- FIXED
        status,
        location
        )
