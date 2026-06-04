import asyncpg
import os

pool = None


async def init_db():
    global pool

    database_url = os.getenv("DATABASE_URL")

    pool = await asyncpg.create_pool(database_url)

    print("Database connected")


def get_pool():
    return pool