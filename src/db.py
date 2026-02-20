from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings

engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(bind=engine)


def get_engine(db_url: str | None = None):
    """Get a SQLAlchemy engine, optionally with a custom URL."""
    if db_url:
        return create_engine(db_url, echo=False)
    return engine
