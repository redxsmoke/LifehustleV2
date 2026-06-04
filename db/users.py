async def upsert_user(conn, discord_id: int, username: str):
    # Create/update user
    await conn.execute(
        """
        INSERT INTO users (
            discord_id,
            username,
            cd_location_id,
            xp,
            level
        )
        VALUES ($1, $2, 1, 0, 1)
        ON CONFLICT (discord_id)
        DO UPDATE SET
            username = EXCLUDED.username,
            cd_location_id = COALESCE(users.cd_location_id, 1),
            xp = COALESCE(users.xp, 0),
            level = COALESCE(users.level, 1)
        """,
        discord_id,
        username
    )

    # Create default occupation if one doesn't exist
    await conn.execute(
        """
        INSERT INTO user_occupations (
            discord_id,
            cd_occupation_id
        )
        VALUES ($1, 1)
        ON CONFLICT DO NOTHING
        """,
        discord_id
    )