-- Mart: Product Performance
-- Aggregates sales and refund metrics by product by day.
-- Source: {schema}.stg_shopify_order_lines, {schema}.stg_shopify_refunds

DROP MATERIALIZED VIEW IF EXISTS {schema}.mart_product_performance CASCADE;

CREATE MATERIALIZED VIEW {schema}.mart_product_performance AS

WITH daily_product_sales AS (
    SELECT
        ol.order_date,
        ol.product_id,
        ol.product_title,
        ol.vendor,
        SUM(ol.quantity)                                AS units_sold,
        SUM(ol.line_total)                              AS gross_revenue,
        SUM(ol.line_discount)                           AS total_discount,
        SUM(ol.line_total) - SUM(ol.line_discount)      AS net_revenue,
        COUNT(DISTINCT ol.order_id)                     AS order_count,
        COUNT(DISTINCT ol.customer_id)                  AS unique_customers,
        ROUND(AVG(ol.unit_price), 2)                    AS avg_selling_price
    FROM {schema}.stg_shopify_order_lines ol
    GROUP BY ol.order_date, ol.product_id, ol.product_title, ol.vendor
),

daily_product_refunds AS (
    SELECT
        r.refund_date                                   AS refund_date,
        r.product_id,
        SUM(r.refund_quantity)                          AS refund_units,
        SUM(r.refund_total)                             AS refund_amount,
        COUNT(DISTINCT r.refund_id)                     AS refund_count
    FROM {schema}.stg_shopify_refunds r
    GROUP BY r.refund_date, r.product_id
)

SELECT
    s.order_date,
    s.product_id,
    s.product_title,
    s.vendor,
    s.units_sold,
    s.gross_revenue,
    s.total_discount,
    s.net_revenue,
    s.order_count,
    s.unique_customers,
    s.avg_selling_price,
    -- Refund metrics (same day)
    COALESCE(r.refund_units, 0)                         AS refund_units,
    COALESCE(r.refund_amount, 0)                        AS refund_amount,
    COALESCE(r.refund_count, 0)                         AS refund_count,
    -- Refund rate
    ROUND(
        COALESCE(r.refund_units, 0)::NUMERIC / NULLIF(s.units_sold, 0) * 100, 2
    )                                                   AS refund_rate_pct,
    -- Net after refunds
    s.net_revenue - COALESCE(r.refund_amount, 0)        AS net_revenue_after_refunds
FROM daily_product_sales s
LEFT JOIN daily_product_refunds r
    ON s.order_date = r.refund_date
    AND s.product_id = r.product_id
ORDER BY s.order_date, s.gross_revenue DESC;
