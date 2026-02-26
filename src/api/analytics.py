"""
Analytics API endpoints for the dashboard.

Provides KPI summaries, time-series data, and period comparisons
for the authenticated user's tenant.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.auth.db import User
from src.auth.manager import current_active_user
from src.config import settings
from src.data.queries import (
    compare_periods,
    get_ad_performance,
    get_blended_metrics,
    get_customer_metrics,
    get_top_products,
)
from src.analytics.targets import TargetEngine, TargetResult

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(settings.database_url)


def _resolve_dates(period: str, start: Optional[date], end: Optional[date]):
    """Resolve a period string or explicit dates into (start_date, end_date)."""
    if start and end:
        return start, end
    today = date.today()
    mapping = {
        "7d": 7,
        "14d": 14,
        "30d": 30,
        "90d": 90,
    }
    days = mapping.get(period, 30)
    return today - timedelta(days=days), today


def _require_tenant(user: User) -> int:
    if not user.tenant_id:
        raise HTTPException(
            status_code=400,
            detail="No tenant linked. Connect Shopify first.",
        )
    return user.tenant_id


# ── Schemas ──────────────────────────────────────────────


class KPIResponse(BaseModel):
    # Core metrics
    total_revenue: float = 0
    total_orders: int = 0
    avg_order_value: float = 0
    total_ad_spend: float = 0
    blended_roas: float = 0
    meta_roas: float = 0
    blended_cac: float = 0
    net_profit_proxy: float = 0
    total_refunds: int = 0
    total_refund_amount: float = 0
    # New KPI metrics
    cvr: float = 0               # Conversion rate (%)
    ltv: float = 0               # Avg customer lifetime value ($)
    repeat_purchase_rate: float = 0  # Returning customer % 
    return_rate: float = 0       # Refund rate (%)
    ad_efficiency: float = 0     # Net profit per $1 ad spend
    # Period comparison (vs previous period)
    revenue_change_pct: Optional[float] = None
    orders_change_pct: Optional[float] = None
    aov_change_pct: Optional[float] = None
    ad_spend_change_pct: Optional[float] = None
    roas_change_pct: Optional[float] = None
    cac_change_pct: Optional[float] = None
    cvr_change_pct: Optional[float] = None
    ltv_change_pct: Optional[float] = None
    rpr_change_pct: Optional[float] = None
    return_rate_change_pct: Optional[float] = None
    ad_efficiency_change_pct: Optional[float] = None


class TimeseriesPoint(BaseModel):
    date: str
    value: float


class TimeseriesResponse(BaseModel):
    metric: str
    period: str
    data: list[TimeseriesPoint]


# ── Endpoints ────────────────────────────────────────────


def _safe_query_scalar(conn, query: str, params: tuple, schema: str) -> float:
    """Execute a query that returns a single scalar value, returning 0 on failure."""
    try:
        with conn.cursor() as cur:
            cur.execute(query.replace("{schema}", schema), params)
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except psycopg2.errors.UndefinedTable:
        conn.rollback()
        return 0.0
    except Exception:
        conn.rollback()
        return 0.0


def _pct_change(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _fetch_extra_kpis(conn, schema: str, start_date: date, end_date: date) -> dict:
    """Fetch the additional KPI metrics (CVR, LTV, RPR, Return Rate, Ad Efficiency)."""
    params = (start_date, end_date)

    cvr = _safe_query_scalar(conn, """
        SELECT CASE WHEN SUM(clicks) = 0 THEN 0
                    ELSE ROUND(SUM(purchases)::NUMERIC / SUM(clicks) * 100, 2)
               END
        FROM {schema}.mart_daily_ad_performance
        WHERE insight_date BETWEEN %s AND %s
    """, params, schema)

    ltv = _safe_query_scalar(conn, """
        SELECT ROUND(AVG(avg_ltv), 2)
        FROM {schema}.mart_customer_ltv
        WHERE order_date BETWEEN %s AND %s
    """, params, schema)

    rpr = _safe_query_scalar(conn, """
        SELECT ROUND(
            SUM(returning_customers)::NUMERIC / NULLIF(SUM(unique_customers), 0) * 100, 2
        )
        FROM {schema}.mart_customer_cohorts
        WHERE order_date BETWEEN %s AND %s
    """, params, schema)

    return_rate = _safe_query_scalar(conn, """
        SELECT ROUND(
            SUM(refund_amount) / NULLIF(SUM(total_revenue), 0) * 100, 2
        )
        FROM {schema}.mart_daily_orders
        WHERE order_date BETWEEN %s AND %s
    """, params, schema)

    ad_efficiency = _safe_query_scalar(conn, """
        SELECT CASE WHEN SUM(total_ad_spend) = 0 THEN 0
                    ELSE ROUND(SUM(net_profit_proxy)::NUMERIC / SUM(total_ad_spend), 2)
               END
        FROM {schema}.mart_daily_blended_performance
        WHERE report_date BETWEEN %s AND %s
    """, params, schema)

    return {
        "cvr": cvr,
        "ltv": ltv,
        "repeat_purchase_rate": rpr,
        "return_rate": return_rate,
        "ad_efficiency": ad_efficiency,
    }


@router.get("/kpis", response_model=KPIResponse)
async def get_kpis(
    period: str = Query("30d", pattern="^(7d|14d|30d|90d)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    user: User = Depends(current_active_user),
):
    """
    Get key performance indicators for the dashboard.
    Returns blended metrics plus period-over-period change percentages.
    """
    tenant_id = _require_tenant(user)
    start_date, end_date = _resolve_dates(period, start, end)
    schema = f"tenant_{tenant_id}"

    # Calculate previous period of equal length for comparison
    period_length = (end_date - start_date).days
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_length)

    conn = _get_conn()
    try:
        try:
            blended = get_blended_metrics(conn, tenant_id, start_date, end_date)
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            logger.warning("Mart views not yet created for tenant %s", tenant_id)
            return KPIResponse()

        if "error" in blended:
            return KPIResponse()

        # Fetch extra KPI metrics
        extra = _fetch_extra_kpis(conn, schema, start_date, end_date)
        extra_prev = _fetch_extra_kpis(conn, schema, prev_start, prev_end)

        # Get comparison data for core metrics
        try:
            comparison = compare_periods(
                conn, tenant_id, start_date, end_date, prev_start, prev_end
            )
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            comparison = {"error": "no data"}

        change: dict = {}
        if "error" not in comparison:
            change = {
                "revenue_change_pct": comparison["revenue"]["change_pct"],
                "orders_change_pct": comparison["orders"]["change_pct"],
                "aov_change_pct": comparison["aov"]["change_pct"],
                "ad_spend_change_pct": comparison["ad_spend"]["change_pct"],
                "roas_change_pct": comparison["blended_roas"]["change_pct"],
                "cac_change_pct": comparison["cac"]["change_pct"],
            }

        # Compute change % for new metrics
        change["cvr_change_pct"] = _pct_change(extra["cvr"], extra_prev["cvr"])
        change["ltv_change_pct"] = _pct_change(extra["ltv"], extra_prev["ltv"])
        change["rpr_change_pct"] = _pct_change(extra["repeat_purchase_rate"], extra_prev["repeat_purchase_rate"])
        change["return_rate_change_pct"] = _pct_change(extra["return_rate"], extra_prev["return_rate"])
        change["ad_efficiency_change_pct"] = _pct_change(extra["ad_efficiency"], extra_prev["ad_efficiency"])

        return KPIResponse(
            total_revenue=blended["total_revenue"],
            total_orders=blended["total_orders"],
            avg_order_value=blended["avg_order_value"],
            total_ad_spend=blended["total_ad_spend"],
            blended_roas=blended["blended_roas"],
            meta_roas=blended["meta_roas"],
            blended_cac=blended["blended_cac"],
            net_profit_proxy=blended["net_profit_proxy"],
            total_refunds=blended["total_refunds"],
            total_refund_amount=blended["total_refund_amount"],
            **extra,
            **change,
        )
    finally:
        conn.close()


@router.get("/timeseries", response_model=TimeseriesResponse)
async def get_timeseries(
    metric: str = Query(
        "revenue",
        pattern="^(revenue|orders|ad_spend|roas|aov|refunds|net_profit)$",
    ),
    period: str = Query("30d", pattern="^(7d|14d|30d|90d)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    user: User = Depends(current_active_user),
):
    """
    Get daily time-series data for a given metric.
    Queries mart_daily_blended_performance for day-by-day values.
    """
    tenant_id = _require_tenant(user)
    start_date, end_date = _resolve_dates(period, start, end)
    schema = f"tenant_{tenant_id}"

    # Map metric names to SQL column names
    column_map = {
        "revenue": "total_revenue",
        "orders": "total_orders",
        "ad_spend": "total_ad_spend",
        "roas": "blended_roas",
        "aov": "avg_order_value",
        "refunds": "total_refund_amount",
        "net_profit": "net_profit_proxy",
    }
    column = column_map[metric]

    conn = _get_conn()
    try:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT report_date, COALESCE({column}, 0)
                    FROM {schema}.mart_daily_blended_performance
                    WHERE report_date BETWEEN %s AND %s
                    ORDER BY report_date
                    """,
                    (start_date, end_date),
                )
                rows = cur.fetchall()
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            logger.warning("Mart views not yet created for tenant %s", tenant_id)
            rows = []

        data = [
            TimeseriesPoint(date=row[0].isoformat(), value=float(row[1]))
            for row in rows
        ]
        return TimeseriesResponse(metric=metric, period=period, data=data)
    finally:
        conn.close()


@router.get("/campaigns")
async def get_campaigns(
    period: str = Query("30d", pattern="^(7d|14d|30d|90d)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    user: User = Depends(current_active_user),
):
    """Get ad performance broken down by campaign."""
    tenant_id = _require_tenant(user)
    start_date, end_date = _resolve_dates(period, start, end)

    conn = _get_conn()
    try:
        try:
            return get_ad_performance(conn, tenant_id, start_date, end_date)
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            return []
    finally:
        conn.close()


@router.get("/products")
async def get_products(
    period: str = Query("30d", pattern="^(7d|14d|30d|90d)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(current_active_user),
):
    """Get top products by revenue."""
    tenant_id = _require_tenant(user)
    start_date, end_date = _resolve_dates(period, start, end)

    conn = _get_conn()
    try:
        try:
            return get_top_products(conn, tenant_id, start_date, end_date, limit)
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            return []
    finally:
        conn.close()


@router.get("/customers")
async def get_customers(
    period: str = Query("30d", pattern="^(7d|14d|30d|90d)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    user: User = Depends(current_active_user),
):
    """Get new vs returning customer metrics."""
    tenant_id = _require_tenant(user)
    start_date, end_date = _resolve_dates(period, start, end)

    conn = _get_conn()
    try:
        try:
            return get_customer_metrics(conn, tenant_id, start_date, end_date)
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            return {"error": "No data available yet"}
    finally:
        conn.close()


# ── AI Insights ──────────────────────────────────────────

INSIGHTS_PROMPT = """\
You are an expert e-commerce analyst for an Australian online store. \
Analyse the data for the last 7 days and produce exactly 3 concise insights. \
Each insight should be 1-2 sentences, lead with the key finding, and reference \
specific numbers. Focus on what changed, what stands out, and what needs attention.

After the 3 insights, add a short "Dig deeper" section with 2 specific questions \
the store owner should ask to understand their business better. Format these as \
questions they could type into a chat assistant.

## Format
Return ONLY this structure (no markdown headers, no bullet points for insights):

1. [First insight with specific numbers]
2. [Second insight with specific numbers]
3. [Third insight with specific numbers]

Dig deeper:
- [Question 1]
- [Question 2]

## Rules
- All currency in AUD
- Be direct and specific — no filler
- Today's date is {today}
- Reference WoW changes where available
- Keep the entire output under 200 words
"""


@router.get("/targets", response_model=list[TargetResult])
async def get_targets(
    user: User = Depends(current_active_user),
):
    """
    Get calculated targets for key metrics based on historical performance.
    """
    tenant_id = _require_tenant(user)
    conn = _get_conn()
    try:
        engine = TargetEngine(conn, tenant_id)
        return engine.generate_targets()
    finally:
        conn.close()


@router.get("/insights")
async def get_insights(
    user: User = Depends(current_active_user),
):
    """
    Generate AI-powered weekly insights. Streams as SSE.
    The agent queries the data tools to produce 3 key findings.
    """
    tenant_id = _require_tenant(user)

    async def generate():
        from src.agent.agent import AgentDeps, analytics_agent

        conn = _get_conn()
        try:
            today = date.today()
            deps = AgentDeps(
                conn=conn,
                tenant_id=tenant_id,
                report_end_date=today,
                report_start_date=today - timedelta(days=7),
            )

            prompt = INSIGHTS_PROMPT.format(today=today.isoformat())

            user_prompt = (
                f"Generate insights for the week "
                f"{today - timedelta(days=7)} to {today}. "
                f"Compare against the previous week "
                f"{today - timedelta(days=14)} to {today - timedelta(days=7)}."
            )

            async with analytics_agent.run_stream(
                user_prompt,
                deps=deps,
                instructions=prompt,
            ) as stream:
                async for chunk in stream.stream_text(delta=True):
                    yield f"data: {json.dumps({'type': 'delta', 'content': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            yield f"data: {json.dumps({'type': 'error', 'content': 'No data available yet. Connect and sync your store first.'})}\n\n"
        except Exception as e:
            logger.error("Insights generation error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Failed to generate insights.'})}\n\n"
        finally:
            conn.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
