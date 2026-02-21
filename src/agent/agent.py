"""
Pydantic AI agent definition for the analytics report generator.

Usage:
    uv run python -m src.agent.agent --tenant-id 1
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from src.agent.prompts import WEEKLY_REPORT_SYSTEM_PROMPT
from src.data import queries


@dataclass
class AgentDeps:
    """Dependencies passed to the agent at runtime."""
    conn: object  # psycopg2 connection
    tenant_id: int
    report_end_date: date  # Last day of the reporting week
    report_start_date: date  # First day of the reporting week


def build_model_string() -> str:
    """Build the model string from environment variables."""
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o")

    # Map provider names to pydantic-ai prefixes
    prefix_map = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "google-gla",
        "gemini": "google-gla",
        "groq": "groq",
    }
    prefix = prefix_map.get(provider, provider)
    return f"{prefix}:{model}"


# ──────────────────────────────────────────────
# Agent Definition
# ──────────────────────────────────────────────

analytics_agent = Agent(
    model=build_model_string(),
    deps_type=AgentDeps,
    system_prompt=WEEKLY_REPORT_SYSTEM_PROMPT,
    retries=2,
)


# ──────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────

@analytics_agent.tool
def get_revenue_summary(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> dict:
    """Get revenue metrics (gross revenue, net revenue, AOV, discounts, tax, shipping) for a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
    """
    return queries.get_revenue_summary(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


@analytics_agent.tool
def get_orders_and_refunds(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> dict:
    """Get order counts and refund metrics (refund amount, refund rate, items refunded) for a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
    """
    return queries.get_orders_and_refunds(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


@analytics_agent.tool
def get_ad_performance(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> list[dict]:
    """Get Meta Ads performance broken down by campaign. Returns spend, revenue, ROAS, CPA, CTR, and conversion rate for each campaign.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
    """
    return queries.get_ad_performance(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


@analytics_agent.tool
def get_blended_metrics(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> dict:
    """Get blended cross-platform metrics including blended ROAS, Meta ROAS, CAC, MER, and ad attribution percentage.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
    """
    return queries.get_blended_metrics(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


@analytics_agent.tool
def get_top_products(ctx: RunContext[AgentDeps], start_date: str, end_date: str, limit: int = 10) -> list[dict]:
    """Get top-selling products ranked by revenue with refund rates.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        limit: Number of products to return (default 10).
    """
    return queries.get_top_products(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
        limit=limit,
    )


@analytics_agent.tool
def get_problem_products(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> list[dict]:
    """Get products with unusually high refund rates (above 1.5x the portfolio average). Only includes products with sufficient order volume.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
    """
    return queries.get_problem_products(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


@analytics_agent.tool
def get_customer_metrics(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> dict:
    """Get customer cohort metrics: new vs returning customer counts, revenue, and AOV comparison.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
    """
    return queries.get_customer_metrics(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )


@analytics_agent.tool
def compare_periods(
    ctx: RunContext[AgentDeps],
    current_start: str, current_end: str,
    previous_start: str, previous_end: str,
) -> dict:
    """Compare two time periods across all key metrics. Returns current values, previous values, and percentage changes for revenue, orders, AOV, ad spend, blended ROAS, refunds, and CAC.

    Args:
        current_start: Current period start date in YYYY-MM-DD format.
        current_end: Current period end date in YYYY-MM-DD format.
        previous_start: Previous period start date in YYYY-MM-DD format.
        previous_end: Previous period end date in YYYY-MM-DD format.
    """
    return queries.compare_periods(
        ctx.deps.conn,
        ctx.deps.tenant_id,
        date.fromisoformat(current_start),
        date.fromisoformat(current_end),
        date.fromisoformat(previous_start),
        date.fromisoformat(previous_end),
    )


# ──────────────────────────────────────────────
# Report Generation
# ──────────────────────────────────────────────

def generate_report(
    tenant_id: int = 1,
    report_end_date: date | None = None,
    db_url: str | None = None,
) -> str:
    """
    Generate a weekly analytics report for a tenant.

    Returns the report text.
    """
    load_dotenv()
    if db_url is None:
        db_url = os.getenv("DATABASE_URL")
    if report_end_date is None:
        report_end_date = date.today() - timedelta(days=1)  # Yesterday

    report_start_date = report_end_date - timedelta(days=6)  # 7-day window

    conn = psycopg2.connect(db_url)
    try:
        deps = AgentDeps(
            conn=conn,
            tenant_id=tenant_id,
            report_end_date=report_end_date,
            report_start_date=report_start_date,
        )

        user_prompt = (
            f"Generate the weekly performance report for the period "
            f"{report_start_date} to {report_end_date}. "
            f"The previous week for comparison is "
            f"{report_start_date - timedelta(days=7)} to {report_start_date - timedelta(days=1)}."
        )

        result = analytics_agent.run_sync(user_prompt, deps=deps)
        return result.output
    finally:
        conn.close()


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate weekly analytics report")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--end-date", type=str, default=None, help="Report end date (YYYY-MM-DD). Defaults to yesterday.")
    parser.add_argument("--db-url", type=str, default=None)
    args = parser.parse_args()

    end_date = date.fromisoformat(args.end_date) if args.end_date else None

    print("Generating weekly analytics report...")
    print(f"  Tenant: {args.tenant_id}")
    print(f"  End Date: {end_date or 'yesterday'}")
    print(f"  Model: {build_model_string()}")
    print()

    report = generate_report(
        tenant_id=args.tenant_id,
        report_end_date=end_date,
        db_url=args.db_url,
    )

    print("=" * 70)
    print(report)
    print("=" * 70)


if __name__ == "__main__":
    main()
