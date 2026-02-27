# Shopify & Meta Ads Analytics Platform

Multi-tenant analytics platform that ingests Shopify and Meta Ads data, builds analytical models in PostgreSQL, and generates weekly performance reports via an LLM agent.

**Stack:** Python 3.13, FastAPI, PostgreSQL 16, Pydantic AI, uv

**Multi-tenancy:** Each tenant gets a single PostgreSQL schema (`tenant_{id}`) containing raw tables, staging views, and mart materialized views.

---

## Quick Start

```bash
# 1. Start the database
docker compose up -d

# 2. Copy and configure environment variables
cp .env.example .env
# Edit .env with your credentials

# 3. Seed test data
uv run python -m scripts.seed --clean

# 4. Build analytics models
uv run python -m src.data.model_runner --tenant-id 1

# 5. Start the API server
uv run uvicorn src.main:app --reload --port 8000

# 6. Run tests
uv run pytest
```

### Frontend (Vite React)

```
cd frontend
npm install
cp .env.example .env
# Leave VITE_BACKEND_HOST empty for local dev (Vite proxy -> http://localhost:8000)
# Set it to your deployed FastAPI URL in production, e.g. https://backend.up.railway.app
VITE_BACKEND_HOST=https://your-backend.example.com
npm run dev    # or npm run build && npm run preview
```

---

## Commands

### Database

```bash
docker compose up -d       # Start PostgreSQL (port 5435)
docker compose down        # Stop (data persists)
docker compose down -v     # Stop and delete all data
```

### Seed Data

Generate realistic test data (20 products, 300 customers, ~2,072 orders, 6 Meta campaigns, 90 days).

```bash
uv run python -m scripts.seed --clean
```

| Flag | Default | Description |
|------|---------|-------------|
| `--tenant-id` | `1` | Tenant ID to seed |
| `--days` | `90` | Days of historical data |
| `--clean` | off | Drop and recreate schemas first |
| `--db-url` | from `.env` | Database URL override |

### Shopify Sync

Sync live Shopify data via GraphQL Admin API. Requires `SHOPIFY_CLIENT_ID`, `SHOPIFY_SECRET_KEY`, and `SHOPIFY_STORE_URL` in `.env`.

```bash
uv run python -m src.ingestion.shopify_sync --tenant-id 1 --full
uv run python -m src.ingestion.shopify_sync --tenant-id 1 --incremental
```

| Flag | Description |
|------|-------------|
| `--tenant-id` | Tenant ID (default: 1) |
| `--full` | Full sync via Bulk Operations API (truncate + reload) |
| `--incremental` | Incremental sync (upsert records updated since last sync) |
| `--db-url` | Database URL override |

Authentication uses client credentials grant. Tokens are obtained automatically and refreshed before the 24-hour expiry.

### Data Models

Build staging views and mart materialized views from raw data.

```bash
uv run python -m src.data.model_runner --tenant-id 1
```

| Flag | Description |
|------|-------------|
| `--tenant-id` | Tenant ID (default: 1) |
| `--staging-only` | Only run staging models |
| `--marts-only` | Only run mart models |
| `--models <name>` | Run specific model(s) by name |
| `--db-url` | Database URL override |

**Execution order:**
1. Staging: `stg_shopify_orders`, `stg_shopify_refunds`, `stg_shopify_customers`, `stg_shopify_products`, `stg_meta_ad_insights`, `stg_meta_campaigns`
2. Marts: `mart_daily_revenue`, `mart_daily_orders`, `mart_daily_ad_performance`, `mart_daily_blended_performance`, `mart_product_performance`, `mart_customer_cohorts`

### Report Generation (CLI)

Generate an analytics report using the LLM agent. Requires an LLM API key in `.env`.

```bash
uv run python -m src.agent.agent --tenant-id 1
uv run python -m src.agent.agent --tenant-id 1 --end-date 2026-02-19
```

| Flag | Description |
|------|-------------|
| `--tenant-id` | Tenant ID (default: 1) |
| `--end-date` | Report end date, YYYY-MM-DD (default: yesterday) |
| `--db-url` | Database URL override |

### API Server

```bash
uv run uvicorn src.main:app --reload --port 8000
```

Starts the FastAPI server with the weekly report scheduler. OpenAPI docs at `http://localhost:8000/docs`.

### Tests

```bash
uv run pytest                              # All tests
uv run pytest tests/test_shopify_client.py  # Single file
```

Requires the database running with seed data.

---

## API Endpoints

All endpoints under `/api` require the `X-API-Key` header.

- **Admin key** (`ADMIN_API_KEY`): access to all endpoints
- **Tenant key** (per-tenant): scoped to that tenant's data

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |

### Tenants

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/tenants/me` | Tenant | Get current tenant |
| GET | `/api/tenants` | Admin | List all tenants |
| GET | `/api/tenants/{id}` | Admin | Get tenant by ID |
| POST | `/api/tenants` | Admin | Create tenant |
| PATCH | `/api/tenants/{id}` | Admin | Update tenant |
| DELETE | `/api/tenants/{id}` | Admin | Delete tenant |

### Sync

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/sync/shopify` | Tenant | Trigger sync (body: `{"mode": "full"}` or `"incremental"`) |
| POST | `/api/sync/shopify/{id}` | Admin | Trigger sync for specific tenant |
| GET | `/api/sync/status` | Tenant | Get sync status |
| GET | `/api/sync/status/{id}` | Admin | Get sync status for specific tenant |

### Reports

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/reports/generate` | Tenant | Generate report (body: `{"end_date": "YYYY-MM-DD"}`) |
| POST | `/api/reports/generate/{id}` | Admin | Generate report for specific tenant |
| POST | `/api/reports/trigger-all` | Admin | Trigger reports for all tenants |

---

## Scheduler

The weekly report scheduler starts automatically with the API server.

| Job | Schedule | Description |
|-----|----------|-------------|
| Weekly report | Sunday 21:00 UTC (Monday 08:00 AEST) | For each tenant: incremental sync, refresh models, generate report, send email |

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `POSTGRES_USER` | Yes | DB user (for Docker Compose) |
| `POSTGRES_PASSWORD` | Yes | DB password (for Docker Compose) |
| `POSTGRES_DB` | Yes | DB name (for Docker Compose) |
| `ADMIN_API_KEY` | Yes | Admin API key for management endpoints |
| `SHOPIFY_CLIENT_ID` | For sync | Shopify app client ID |
| `SHOPIFY_SECRET_KEY` | For sync | Shopify app secret key |
| `SHOPIFY_STORE_URL` | For sync | Store domain (e.g. `your-store.myshopify.com`) |
| `LLM_PROVIDER` | For reports | `openai`, `anthropic`, or `google` |
| `LLM_MODEL` | For reports | Model ID (e.g. `gpt-4o`) |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key |
| `ANTHROPIC_API_KEY` | If using Anthropic | Anthropic API key |
| `GOOGLE_API_KEY` | If using Google | Google AI API key |
| `SMTP_HOST` | For email | SMTP server (default: `smtp.gmail.com`) |
| `SMTP_PORT` | For email | SMTP port (default: `587`) |
| `SMTP_USER` | For email | SMTP username |
| `SMTP_PASSWORD` | For email | SMTP password |
| `EMAIL_FROM` | For email | Sender email address |
| `VITE_BACKEND_HOST` | Frontend deploy | Base URL that the Vite build should call for API requests. Leave blank locally to use the Vite proxy; set to your backend URL (e.g. `https://api.example.com`) in production. |

---

## Project Structure

```
shopify-meta-analytics/
├── docker-compose.yml          # PostgreSQL 16 on port 5435
├── pyproject.toml              # Dependencies and config
├── .env.example                # Environment variable template
├── scripts/
│   ├── seed.py                 # Test data generator
│   └── generators/             # Data generation helpers
├── sql/
│   ├── staging/                # 6 staging SQL models
│   └── marts/                  # 6 mart SQL models
├── src/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Pydantic settings
│   ├── db.py                   # Database connection
│   ├── agent/                  # LLM agent + prompts
│   ├── api/                    # REST endpoints
│   ├── data/                   # Query layer + model runner
│   ├── email/                  # SMTP sender
│   ├── ingestion/              # Shopify GraphQL sync
│   ├── reports/                # HTML report builder
│   └── scheduler/              # APScheduler jobs
└── tests/                      # 126 tests
```
