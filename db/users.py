async def upsert_user(conn, discord_id: int, guild_id: int, username: str):
    await conn.execute(
        """
        INSERT INTO users (
            discord_id,
            guild_id,
            username,
            cd_location_id,
            xp,
            level
        )
        VALUES ($1, $2, $3, 1, 0, 1)
        ON CONFLICT (discord_id, guild_id)
        DO UPDATE SET username = EXCLUDED.username
        """,
        discord_id,
        guild_id,
        username
    )
