import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(bind=engine)


def get_engine(db_url: str | None = None):
    """Get a SQLAlchemy engine, optionally with a custom URL."""
    if db_url:
        return create_engine(db_url, echo=False)
    return engine


def ensure_base_tables() -> None:
    """Create shared public-schema tables that are not managed by Alembic.

    These tables use ``CREATE TABLE IF NOT EXISTS`` so they are safe to call on
    every startup — the statements are no-ops when the tables already exist.
    """
    ddl_statements = [
        # ── tenants (originally in scripts/seed.py) ──────────
        """
        CREATE TABLE IF NOT EXISTS public.tenants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            shopify_store_url VARCHAR(255),
            meta_account_id VARCHAR(255),
            api_key VARCHAR(255) NOT NULL,
            email_recipients TEXT[],
            shopify_access_token TEXT,
            meta_access_token TEXT,
            meta_token_expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        # ── sync_state (originally in src/ingestion/sync_state.py) ──
        """
        CREATE TABLE IF NOT EXISTS public.sync_state (
            id SERIAL PRIMARY KEY,
            tenant_id INT NOT NULL,
            resource TEXT NOT NULL,
            last_synced_at TIMESTAMPTZ,
            sync_status TEXT DEFAULT 'idle',
            records_synced INT DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            UNIQUE(tenant_id, resource)
        )
        """,
    ]

    try:
        with engine.connect() as conn:
            for ddl in ddl_statements:
                conn.execute(text(ddl))
            conn.commit()
        logger.info("Base tables verified (tenants, sync_state)")
    except Exception as exc:
        logger.warning(
            "Could not verify base tables at startup (DB may be temporarily "
            "unreachable). Tables will be created on first use. Error: %s",
            exc,
        )
