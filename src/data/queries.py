"""
Query functions that execute against the analytics marts.

These are the data-access layer used by the agent's tools.
All functions take a psycopg2 connection and a tenant_id, and return
dicts/lists suitable for LLM consumption.
"""

from datetime import date, timedelta

import psycopg2
import psycopg2.errors


def _schema(tenant_id: int) -> str:
    return f"tenant_{tenant_id}"


def get_revenue_summary(
    conn, tenant_id: int, start_date: date, end_date: date
) -> dict:
    """Get revenue summary for a date range."""
    s = _schema(tenant_id)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                SUM(gross_revenue) AS gross_revenue,
                SUM(net_revenue) AS net_revenue,
                SUM(order_count) AS total_orders,
                ROUND(AVG(avg_order_value), 2) AS avg_aov,
                SUM(total_discounts) AS total_discounts,
                SUM(total_tax) AS total_tax,
                SUM(total_shipping) AS total_shipping,
                SUM(total_items_sold) AS total_items_sold,
                SUM(unique_customers) AS unique_customers,
                ROUND(AVG(discount_usage_rate), 2) AS avg_discount_usage_rate
            FROM {s}.mart_daily_revenue
            WHERE order_date BETWEEN %s AND %s
        """, (start_date, end_date))
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"error": "No data for this period"}
        return {
            "period": f"{start_date} to {end_date}",
            "gross_revenue": float(row[0]),
            "net_revenue": float(row[1]),
            "total_orders": int(row[2]),
            "avg_order_value": float(row[3]),
            "total_discounts": float(row[4]),
            "total_tax": float(row[5]),
            "total_shipping": float(row[6]),
            "total_items_sold": int(row[7]),
            "unique_customers": int(row[8]),
            "avg_discount_usage_rate": float(row[9]),
        }


def get_orders_and_refunds(
    conn, tenant_id: int, start_date: date, end_date: date
) -> dict:
    """Get order and refund metrics for a date range."""
    s = _schema(tenant_id)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                SUM(total_orders) AS total_orders,
                SUM(total_revenue) AS total_revenue,
                ROUND(AVG(avg_order_value), 2) AS avg_aov,
                SUM(paid_orders) AS paid_orders,
                SUM(partially_refunded_orders) AS partially_refunded,
                SUM(fully_refunded_orders) AS fully_refunded,
                SUM(refunds_processed) AS refunds_processed,
                SUM(refund_amount) AS refund_amount,
                SUM(refund_item_count) AS refund_items,
                ROUND(AVG(refund_rate_pct), 2) AS avg_refund_rate
            FROM {s}.mart_daily_orders
            WHERE order_date BETWEEN %s AND %s
        """, (start_date, end_date))
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"error": "No data for this period"}
        return {
            "period": f"{start_date} to {end_date}",
            "total_orders": int(row[0]),
            "total_revenue": float(row[1]),
            "avg_order_value": float(row[2]),
            "paid_orders": int(row[3]),
            "partially_refunded_orders": int(row[4]),
            "fully_refunded_orders": int(row[5]),
            "refunds_processed": int(row[6]),
            "refund_amount": float(row[7]),
            "refund_items": int(row[8]),
            "avg_daily_refund_rate_pct": float(row[9]),
        }


def get_ad_performance(
    conn, tenant_id: int, start_date: date, end_date: date
) -> list[dict]:
    """Get ad performance by campaign for a date range."""
    s = _schema(tenant_id)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                campaign_name,
                objective,
                SUM(spend) AS total_spend,
                SUM(impressions) AS total_impressions,
                SUM(clicks) AS total_clicks,
                SUM(link_clicks) AS total_link_clicks,
                SUM(purchases) AS total_purchases,
                SUM(purchase_revenue) AS total_revenue,
                ROUND(SUM(purchase_revenue) / NULLIF(SUM(spend), 0), 2) AS roas,
                ROUND(SUM(spend) / NULLIF(SUM(purchases), 0), 2) AS cpa,
                ROUND(SUM(clicks)::NUMERIC / NULLIF(SUM(impressions), 0) * 100, 2) AS ctr,
                ROUND(SUM(spend) / NULLIF(SUM(impressions), 0) * 1000, 2) AS cpm,
                ROUND(SUM(purchases)::NUMERIC / NULLIF(SUM(clicks), 0) * 100, 4) AS conv_rate
            FROM {s}.mart_daily_ad_performance
            WHERE insight_date BETWEEN %s AND %s
            GROUP BY campaign_name, objective
            ORDER BY total_revenue DESC
        """, (start_date, end_date))
        columns = [desc[0] for desc in cur.description]
        return [
            {col: (float(val) if isinstance(val, __import__('decimal').Decimal) else val)
             for col, val in zip(columns, row)}
            for row in cur.fetchall()
        ]


def get_blended_metrics(
    conn, tenant_id: int, start_date: date, end_date: date
) -> dict:
    """Get blended cross-platform metrics for a date range."""
    s = _schema(tenant_id)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                SUM(total_revenue) AS total_revenue,
                SUM(total_orders) AS total_orders,
                ROUND(AVG(avg_order_value), 2) AS avg_aov,
                SUM(total_ad_spend) AS total_ad_spend,
                SUM(meta_attributed_revenue) AS meta_revenue,
                ROUND(SUM(total_revenue) / NULLIF(SUM(total_ad_spend), 0), 2) AS blended_roas,
                ROUND(SUM(meta_attributed_revenue) / NULLIF(SUM(total_ad_spend), 0), 2) AS meta_roas,
                ROUND(SUM(total_ad_spend) / NULLIF(SUM(unique_customers), 0), 2) AS blended_cac,
                ROUND(AVG(meta_attribution_pct), 1) AS avg_meta_attribution_pct,
                SUM(total_refunds) AS total_refunds,
                SUM(total_refund_amount) AS total_refund_amount,
                SUM(net_profit_proxy) AS net_profit_proxy
            FROM {s}.mart_daily_blended_performance
            WHERE report_date BETWEEN %s AND %s
        """, (start_date, end_date))
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"error": "No data for this period"}
        return {
            "period": f"{start_date} to {end_date}",
            "total_revenue": float(row[0]),
            "total_orders": int(row[1]),
            "avg_order_value": float(row[2]),
            "total_ad_spend": float(row[3]),
            "meta_attributed_revenue": float(row[4]),
            "blended_roas": float(row[5]) if row[5] else 0,
            "meta_roas": float(row[6]) if row[6] else 0,
            "blended_cac": float(row[7]) if row[7] else 0,
            "avg_meta_attribution_pct": float(row[8]) if row[8] else 0,
            "total_refunds": int(row[9]),
            "total_refund_amount": float(row[10]),
            "net_profit_proxy": float(row[11]),
        }


def get_top_products(
    conn, tenant_id: int, start_date: date, end_date: date, limit: int = 10
) -> list[dict]:
    """Get top products by revenue with refund rates."""
    s = _schema(tenant_id)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                product_title,
                vendor,
                SUM(units_sold) AS total_units,
                SUM(gross_revenue) AS total_revenue,
                SUM(order_count) AS total_orders,
                SUM(refund_units) AS total_refund_units,
                SUM(refund_amount) AS total_refund_amount,
                ROUND(SUM(refund_units)::NUMERIC / NULLIF(SUM(units_sold), 0) * 100, 1) AS refund_rate_pct,
                ROUND(AVG(avg_selling_price), 2) AS avg_price
            FROM {s}.mart_product_performance
            WHERE order_date BETWEEN %s AND %s
            GROUP BY product_title, vendor
            ORDER BY total_revenue DESC
            LIMIT %s
        """, (start_date, end_date, limit))
        columns = [desc[0] for desc in cur.description]
        return [
            {col: (float(val) if isinstance(val, __import__('decimal').Decimal) else
                   int(val) if isinstance(val, int) else val)
             for col, val in zip(columns, row)}
            for row in cur.fetchall()
        ]


def get_problem_products(
    conn, tenant_id: int, start_date: date, end_date: date, min_orders: int = 10
) -> list[dict]:
    """Get products with unusually high refund rates."""
    s = _schema(tenant_id)
    with conn.cursor() as cur:
        cur.execute(f"""
            WITH product_stats AS (
                SELECT
                    product_title,
                    vendor,
                    SUM(units_sold) AS total_units,
                    SUM(gross_revenue) AS total_revenue,
                    SUM(refund_units) AS total_refund_units,
                    SUM(refund_amount) AS total_refund_amount,
                    ROUND(SUM(refund_units)::NUMERIC / NULLIF(SUM(units_sold), 0) * 100, 1) AS refund_rate_pct
                FROM {s}.mart_product_performance
                WHERE order_date BETWEEN %s AND %s
                GROUP BY product_title, vendor
                HAVING SUM(order_count) >= %s
            ),
            avg_refund AS (
                SELECT ROUND(AVG(refund_rate_pct), 1) AS avg_rate FROM product_stats
            )
            SELECT ps.*, ar.avg_rate AS portfolio_avg_refund_rate
            FROM product_stats ps, avg_refund ar
            WHERE ps.refund_rate_pct > ar.avg_rate * 1.5
            ORDER BY ps.refund_rate_pct DESC
        """, (start_date, end_date, min_orders))
        columns = [desc[0] for desc in cur.description]
        return [
            {col: (float(val) if isinstance(val, __import__('decimal').Decimal) else
                   int(val) if isinstance(val, int) else val)
             for col, val in zip(columns, row)}
            for row in cur.fetchall()
        ]


def get_customer_metrics(
    conn, tenant_id: int, start_date: date, end_date: date
) -> dict:
    """Get new vs returning customer metrics."""
    s = _schema(tenant_id)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                SUM(new_customers) AS new_customers,
                SUM(returning_customers) AS returning_customers,
                ROUND(AVG(returning_customer_pct), 1) AS avg_returning_pct,
                SUM(new_customer_revenue) AS new_customer_revenue,
                SUM(returning_customer_revenue) AS returning_customer_revenue,
                ROUND(AVG(new_customer_aov), 2) AS avg_new_aov,
                ROUND(AVG(returning_customer_aov), 2) AS avg_returning_aov
            FROM {s}.mart_customer_cohorts
            WHERE order_date BETWEEN %s AND %s
        """, (start_date, end_date))
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"error": "No data for this period"}
        return {
            "period": f"{start_date} to {end_date}",
            "new_customers": int(row[0]),
            "returning_customers": int(row[1]),
            "avg_returning_pct": float(row[2]) if row[2] else 0,
            "new_customer_revenue": float(row[3]) if row[3] else 0,
            "returning_customer_revenue": float(row[4]) if row[4] else 0,
            "avg_new_customer_aov": float(row[5]) if row[5] else 0,
            "avg_returning_customer_aov": float(row[6]) if row[6] else 0,
        }


def compare_periods(
    conn, tenant_id: int, current_start: date, current_end: date,
    previous_start: date, previous_end: date,
) -> dict:
    """Compare two periods (e.g., WoW) across all key metrics."""
    current_blended = get_blended_metrics(conn, tenant_id, current_start, current_end)
    previous_blended = get_blended_metrics(conn, tenant_id, previous_start, previous_end)

    if "error" in current_blended or "error" in previous_blended:
        return {"error": "Insufficient data for comparison"}

    def pct_change(current: float, previous: float) -> float:
        if previous == 0:
            return 0.0
        return round((current - previous) / previous * 100, 1)

    return {
        "current_period": f"{current_start} to {current_end}",
        "previous_period": f"{previous_start} to {previous_end}",
        "revenue": {
            "current": current_blended["total_revenue"],
            "previous": previous_blended["total_revenue"],
            "change_pct": pct_change(current_blended["total_revenue"], previous_blended["total_revenue"]),
        },
        "orders": {
            "current": current_blended["total_orders"],
            "previous": previous_blended["total_orders"],
            "change_pct": pct_change(current_blended["total_orders"], previous_blended["total_orders"]),
        },
        "aov": {
            "current": current_blended["avg_order_value"],
            "previous": previous_blended["avg_order_value"],
            "change_pct": pct_change(current_blended["avg_order_value"], previous_blended["avg_order_value"]),
        },
        "ad_spend": {
            "current": current_blended["total_ad_spend"],
            "previous": previous_blended["total_ad_spend"],
            "change_pct": pct_change(current_blended["total_ad_spend"], previous_blended["total_ad_spend"]),
        },
        "blended_roas": {
            "current": current_blended["blended_roas"],
            "previous": previous_blended["blended_roas"],
            "change_pct": pct_change(current_blended["blended_roas"], previous_blended["blended_roas"]),
        },
        "refunds": {
            "current": current_blended["total_refund_amount"],
            "previous": previous_blended["total_refund_amount"],
            "change_pct": pct_change(current_blended["total_refund_amount"], previous_blended["total_refund_amount"]),
        },
        "cac": {
            "current": current_blended["blended_cac"],
            "previous": previous_blended["blended_cac"],
            "change_pct": pct_change(current_blended["blended_cac"], previous_blended["blended_cac"]),
        },
    }


def get_metric_series(
    conn,
    tenant_id: int,
    table: str,
    metric_expr: str,
    date_col: str,
    days: int = 90
) -> list[tuple[date, float]]:
    """
    Get daily time-series data for a metric.
    
    Args:
        conn: Database connection
        tenant_id: ID of the tenant
        table: Table name (without schema)
        metric_expr: SQL expression for the metric (e.g. "total_revenue" or "SUM(clicks)")
        date_col: Column name for the date
        days: Number of days to look back (default 90)
    
    Returns:
        List of (date, value) tuples sorted by date asc.
    """
    s = _schema(tenant_id)
    start_date = date.today() - timedelta(days=days)
    
    with conn.cursor() as cur:
        # Check if aggregation is likely needed (if expression contains parens)
        # This is a simple heuristic. A better way is to always Group By date.
        
        query = f"""
            SELECT {date_col}, {metric_expr}
            FROM {s}.{table}
            WHERE {date_col} >= %s
            GROUP BY {date_col}
            ORDER BY {date_col} ASC
        """
        try:
            cur.execute(query, (start_date,))
        except psycopg2.errors.GroupingError:
             # Fallback if not an aggregate expression but group by was forced
             # Actually, if we pass a raw column "total_revenue" and Group By date, 
             # Postgres requires it to be in Group By or aggregated.
             # So we must strictly pass aggregate expressions like "SUM(revenue)" 
             # OR ensure the table is already unique by date.
             conn.rollback()
             # If table is unique by date (like mart_daily_blended), we can simple select.
             # But to be safe and support CVR, we should encourage aggregate expressions.
             # For pre-aggregated marts, SUM(val) or MAX(val) works fine if there's only 1 row.
             raise
             
        rows = cur.fetchall()
        
        # Convert to list of (date, float)
        return [(row[0], float(row[1]) if row[1] is not None else 0.0) for row in rows]


