from datetime import datetime
import random
from db.connection import get_pool


async def get_world_weather():
    pool = get_pool()

    async with pool.acquire() as conn:

        # Get current active weather
        weather = await conn.fetchrow("""
            SELECT type, icon, bucket
            FROM active_weather
            WHERE id = 'global'
        """)

        now = datetime.now()
        current_bucket = now.hour // 3

        # =========================
        # SAFETY: missing row fallback
        # =========================
        if not weather:
            fallback_type = "sunny"
            fallback_icon = "☀️"

            await conn.execute("""
                INSERT INTO active_weather (id, type, icon, bucket)
                VALUES ('global', $1, $2, $3)
            """, fallback_type, fallback_icon, current_bucket)

            return fallback_type, fallback_icon

        # =========================
        # REROLL WEATHER IF OUTDATED
        # =========================
        if weather["bucket"] != current_bucket:

            pool_rows = await conn.fetch("""
                SELECT type, icon
                FROM weather_conditions
            """)

            new = random.choice(pool_rows)

            await conn.execute("""
                UPDATE active_weather
                SET type = $1,
                    icon = $2,
                    bucket = $3,
                    updated_at = NOW()
                WHERE id = 'global'
            """, new["type"], new["icon"], current_bucket)

            return new["type"], new["icon"]

        # =========================
        # RETURN CURRENT WEATHER
        # =========================
        return weather["type"], weather["icon"]