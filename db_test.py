import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

db_url = os.getenv("DATABASE_URL")

print("DB URL =", db_url)

async def test():
    print("Connecting...")
    conn = await asyncpg.connect(db_url)
    print("CONNECTED")
    await conn.close()

asyncio.run(test())