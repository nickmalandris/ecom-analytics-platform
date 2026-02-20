-- Mart: Daily Orders
-- Detailed order metrics including refund impact by day.
-- Source: {analytics_schema}.stg_shopify_orders, {analytics_schema}.stg_shopify_refunds

DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.mart_daily_orders CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.mart_daily_orders AS

WITH daily_orders AS (
    SELECT
        o.order_date,
        COUNT(DISTINCT o.order_id)                      AS total_orders,
        SUM(o.total_price)                              AS total_revenue,
        ROUND(AVG(o.total_price), 2)                    AS avg_order_value,
        SUM(o.total_item_quantity)                       AS total_items,
        ROUND(AVG(o.total_line_items::NUMERIC), 2)      AS avg_line_items_per_order,
        COUNT(DISTINCT o.customer_id)                   AS unique_customers,
        -- Financial status breakdown
        COUNT(*) FILTER (WHERE o.financial_status = 'paid')
                                                        AS paid_orders,
        COUNT(*) FILTER (WHERE o.financial_status = 'partially_refunded')
                                                        AS partially_refunded_orders,
        COUNT(*) FILTER (WHERE o.financial_status = 'refunded')
                                                        AS fully_refunded_orders
    FROM {analytics_schema}.stg_shopify_orders o
    GROUP BY o.order_date
),

daily_refunds AS (
    SELECT
        r.refund_date,
        COUNT(DISTINCT r.refund_id)                     AS refund_count,
        COUNT(DISTINCT r.order_id)                      AS orders_with_refunds,
        SUM(r.refund_total)                             AS refund_amount,
        SUM(r.refund_quantity)                          AS refund_item_count
    FROM {analytics_schema}.stg_shopify_refunds r
    GROUP BY r.refund_date
)

SELECT
    d_ord.order_date,
    d_ord.total_orders,
    d_ord.total_revenue,
    d_ord.avg_order_value,
    d_ord.total_items,
    d_ord.avg_line_items_per_order,
    d_ord.unique_customers,
    d_ord.paid_orders,
    d_ord.partially_refunded_orders,
    d_ord.fully_refunded_orders,
    -- Refund metrics (by refund date, not order date)
    COALESCE(dr.refund_count, 0)                        AS refunds_processed,
    COALESCE(dr.orders_with_refunds, 0)                 AS orders_refunded,
    COALESCE(dr.refund_amount, 0)                       AS refund_amount,
    COALESCE(dr.refund_item_count, 0)                   AS refund_item_count,
    -- Refund rate
    ROUND(
        COALESCE(dr.refund_amount, 0) / NULLIF(d_ord.total_revenue, 0) * 100, 2
    )                                                   AS refund_rate_pct,
    -- Net revenue after refunds
    d_ord.total_revenue - COALESCE(dr.refund_amount, 0) AS net_revenue_after_refunds
FROM daily_orders d_ord
LEFT JOIN daily_refunds dr ON d_ord.order_date = dr.refund_date
ORDER BY d_ord.order_date;
