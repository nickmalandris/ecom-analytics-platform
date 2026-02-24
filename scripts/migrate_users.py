"""
Script to create the users table in the database.
"""

import asyncio
from src.auth.db import engine, Base

async def create_users_table():
    async with engine.begin() as conn:
        print("Creating users table...")
        await conn.run_sync(Base.metadata.create_all)
        print("Done.")

if __name__ == "__main__":
    asyncio.run(create_users_table())
