"""
Database models for user authentication (FastAPI Users).
"""

import datetime
from typing import AsyncGenerator

from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTable, SQLAlchemyUserDatabase
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import settings

# ─── Database Setup ──────────────────────────────────────

# We need an async engine for fastapi-users
# Convert the existing sync DATABASE_URL to async (postgresql -> postgresql+asyncpg)
ASYNC_DB_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(ASYNC_DB_URL)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─── User Model ──────────────────────────────────────────

class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Removing ForeignKey("tenants.id") temporarily because SQLAlchemy can't see the tenants table
    # since it was created via raw SQL/psycopg2, not SQLAlchemy metadata.
    # We'll enforce this relationship at the application level for now.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=True)
    
    # Custom fields can be added here if needed
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc)
    )


# ─── Dependency Injection ────────────────────────────────

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)
