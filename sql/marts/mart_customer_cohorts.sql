-- Mart: Customer Cohorts
-- Tracks new vs returning customer metrics by day.
-- Source: {schema}.stg_shopify_orders, {schema}.stg_shopify_customers

DROP MATERIALIZED VIEW IF EXISTS {schema}.mart_customer_cohorts CASCADE;

CREATE MATERIALIZED VIEW {schema}.mart_customer_cohorts AS

WITH customer_first_order AS (
    -- Find each customer's first order date
    SELECT
        customer_id,
        MIN(order_date)                                 AS first_order_date
    FROM {schema}.stg_shopify_orders
    GROUP BY customer_id
),

orders_with_cohort AS (
    SELECT
        o.order_id,
        o.order_date,
        o.customer_id,
        o.total_price,
        cfo.first_order_date,
        CASE
            WHEN o.order_date = cfo.first_order_date THEN 'new'
            ELSE 'returning'
        END                                             AS customer_type
    FROM {schema}.stg_shopify_orders o
    JOIN customer_first_order cfo ON o.customer_id = cfo.customer_id
)

SELECT
    oc.order_date,
    -- Overall
    COUNT(DISTINCT oc.order_id)                         AS total_orders,
    SUM(oc.total_price)                                 AS total_revenue,
    COUNT(DISTINCT oc.customer_id)                      AS unique_customers,
    -- New customers
    COUNT(DISTINCT oc.order_id) FILTER (
        WHERE oc.customer_type = 'new'
    )                                                   AS new_customer_orders,
    SUM(oc.total_price) FILTER (
        WHERE oc.customer_type = 'new'
    )                                                   AS new_customer_revenue,
    COUNT(DISTINCT oc.customer_id) FILTER (
        WHERE oc.customer_type = 'new'
    )                                                   AS new_customers,
    -- Returning customers
    COUNT(DISTINCT oc.order_id) FILTER (
        WHERE oc.customer_type = 'returning'
    )                                                   AS returning_customer_orders,
    SUM(oc.total_price) FILTER (
        WHERE oc.customer_type = 'returning'
    )                                                   AS returning_customer_revenue,
    COUNT(DISTINCT oc.customer_id) FILTER (
        WHERE oc.customer_type = 'returning'
    )                                                   AS returning_customers,
    -- Rates
    ROUND(
        COUNT(DISTINCT oc.customer_id) FILTER (WHERE oc.customer_type = 'returning')::NUMERIC
        / NULLIF(COUNT(DISTINCT oc.customer_id), 0) * 100, 2
    )                                                   AS returning_customer_pct,
    -- AOV comparison
    ROUND(AVG(oc.total_price) FILTER (
        WHERE oc.customer_type = 'new'
    ), 2)                                               AS new_customer_aov,
    ROUND(AVG(oc.total_price) FILTER (
        WHERE oc.customer_type = 'returning'
    ), 2)                                               AS returning_customer_aov
FROM orders_with_cohort oc
GROUP BY oc.order_date
ORDER BY oc.order_date;
