"""
Shared test fixtures.

Tests run against the live local database with seed data.
Requires: docker-compose up -d && uv run python -m scripts.seed --clean
"""

import os

# Inject dummy keys before ANY other imports so pydantic-ai doesn't crash during pytest collection
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "dummy-key-for-tests")
os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "dummy-key-for-tests")

import psycopg2
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://analytics_user:analytics_pass@localhost:5435/analytics",
)
TENANT_ID = 1
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "sk_admin_dev_key_001")
TENANT_API_KEY = "sk_test_analytics_key_001"


@pytest.fixture(scope="session")
def db_conn():
    """Session-scoped database connection."""
    conn = psycopg2.connect(DB_URL)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def api_client():
    """FastAPI test client."""
    from src.main import app
    with TestClient(app) as client:
        yield client
