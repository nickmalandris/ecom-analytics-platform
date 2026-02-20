-- Mart: Daily Revenue
-- Aggregates Shopify revenue metrics by day.
-- Source: {analytics_schema}.stg_shopify_orders

DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.mart_daily_revenue CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.mart_daily_revenue AS

SELECT
    o.order_date,
    COUNT(DISTINCT o.order_id)                          AS order_count,
    SUM(o.total_price)                                  AS gross_revenue,
    SUM(o.subtotal_price)                               AS subtotal_revenue,
    SUM(o.total_discounts)                              AS total_discounts,
    SUM(o.total_tax)                                    AS total_tax,
    SUM(o.shipping_price)                               AS total_shipping,
    SUM(o.total_price) - SUM(o.total_tax) - SUM(o.shipping_price)
                                                        AS net_revenue,
    ROUND(AVG(o.total_price), 2)                        AS avg_order_value,
    SUM(o.total_item_quantity)                           AS total_items_sold,
    ROUND(AVG(o.total_item_quantity::NUMERIC), 2)       AS avg_items_per_order,
    COUNT(DISTINCT o.order_id) FILTER (
        WHERE o.discount_code IS NOT NULL
    )                                                   AS discounted_order_count,
    ROUND(
        COUNT(DISTINCT o.order_id) FILTER (WHERE o.discount_code IS NOT NULL)::NUMERIC
        / NULLIF(COUNT(DISTINCT o.order_id), 0) * 100, 2
    )                                                   AS discount_usage_rate,
    COUNT(DISTINCT o.customer_id)                       AS unique_customers,
    -- Fulfillment breakdown
    COUNT(DISTINCT o.order_id) FILTER (
        WHERE o.fulfillment_status = 'fulfilled'
    )                                                   AS fulfilled_orders,
    COUNT(DISTINCT o.order_id) FILTER (
        WHERE o.fulfillment_status IS NULL
    )                                                   AS unfulfilled_orders
FROM {analytics_schema}.stg_shopify_orders o
WHERE o.financial_status NOT IN ('refunded', 'voided')
   OR o.financial_status = 'partially_refunded'
GROUP BY o.order_date
ORDER BY o.order_date;
