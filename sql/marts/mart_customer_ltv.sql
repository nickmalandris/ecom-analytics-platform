-- Mart: Customer LTV (Lifetime Value)
-- Computes daily rolling average customer LTV from order history.
-- Source: {schema}.stg_shopify_orders

DROP MATERIALIZED VIEW IF EXISTS {schema}.mart_customer_ltv CASCADE;

CREATE MATERIALIZED VIEW {schema}.mart_customer_ltv AS

WITH customer_lifetime AS (
    -- Compute each customer's lifetime stats up to each order date
    SELECT
        o.customer_id,
        o.order_date,
        SUM(o.total_price) OVER (
            PARTITION BY o.customer_id
            ORDER BY o.order_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                                   AS running_ltv,
        COUNT(o.order_id) OVER (
            PARTITION BY o.customer_id
            ORDER BY o.order_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                                   AS running_orders
    FROM {schema}.stg_shopify_orders o
),

-- For each day, take each customer's latest running LTV as of that date
daily_snapshots AS (
    SELECT DISTINCT ON (customer_id, order_date)
        customer_id,
        order_date,
        running_ltv,
        running_orders
    FROM customer_lifetime
    ORDER BY customer_id, order_date, running_ltv DESC
)

SELECT
    ds.order_date,
    COUNT(DISTINCT ds.customer_id)                          AS customers_with_activity,
    ROUND(AVG(ds.running_ltv), 2)                           AS avg_ltv,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY ds.running_ltv
    )::NUMERIC, 2)                                          AS median_ltv,
    ROUND(AVG(ds.running_orders), 2)                        AS avg_lifetime_orders,
    ROUND(MAX(ds.running_ltv), 2)                           AS max_ltv,
    ROUND(MIN(ds.running_ltv), 2)                           AS min_ltv
FROM daily_snapshots ds
GROUP BY ds.order_date
ORDER BY ds.order_date;
