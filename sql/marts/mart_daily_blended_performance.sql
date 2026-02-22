-- Mart: Daily Blended Performance
-- Combines Shopify revenue with Meta Ads spend for cross-platform metrics.
-- Source: {schema}.stg_shopify_orders, {schema}.stg_meta_ad_insights

DROP MATERIALIZED VIEW IF EXISTS {schema}.mart_daily_blended_performance CASCADE;

CREATE MATERIALIZED VIEW {schema}.mart_daily_blended_performance AS

WITH daily_shopify AS (
    SELECT
        o.order_date,
        COUNT(DISTINCT o.order_id)                      AS total_orders,
        SUM(o.total_price)                              AS total_revenue,
        ROUND(AVG(o.total_price), 2)                    AS avg_order_value,
        COUNT(DISTINCT o.customer_id)                   AS unique_customers
    FROM {schema}.stg_shopify_orders o
    GROUP BY o.order_date
),

daily_meta AS (
    SELECT
        i.insight_date                                  AS ad_date,
        SUM(i.spend)                                    AS total_ad_spend,
        SUM(i.impressions)                              AS total_impressions,
        SUM(i.clicks)                                   AS total_clicks,
        SUM(i.purchases)                                AS meta_purchases,
        SUM(i.purchase_revenue)                         AS meta_revenue,
        COUNT(DISTINCT i.campaign_id)                   AS active_campaigns
    FROM {schema}.stg_meta_ad_insights i
    GROUP BY i.insight_date
),

daily_refunds AS (
    SELECT
        r.refund_date,
        SUM(r.refund_total)                             AS total_refund_amount,
        COUNT(DISTINCT r.refund_id)                     AS total_refunds
    FROM {schema}.stg_shopify_refunds r
    GROUP BY r.refund_date
)

SELECT
    COALESCE(s.order_date, m.ad_date)                   AS report_date,
    -- Shopify metrics
    COALESCE(s.total_orders, 0)                         AS total_orders,
    COALESCE(s.total_revenue, 0)                        AS total_revenue,
    COALESCE(s.avg_order_value, 0)                      AS avg_order_value,
    COALESCE(s.unique_customers, 0)                     AS unique_customers,
    -- Refund metrics
    COALESCE(rf.total_refunds, 0)                       AS total_refunds,
    COALESCE(rf.total_refund_amount, 0)                 AS total_refund_amount,
    -- Meta Ads metrics
    COALESCE(m.total_ad_spend, 0)                       AS total_ad_spend,
    COALESCE(m.total_impressions, 0)                    AS total_impressions,
    COALESCE(m.total_clicks, 0)                         AS total_clicks,
    COALESCE(m.meta_purchases, 0)                       AS meta_attributed_purchases,
    COALESCE(m.meta_revenue, 0)                         AS meta_attributed_revenue,
    COALESCE(m.active_campaigns, 0)                     AS active_campaigns,
    -- Blended metrics
    ROUND(
        COALESCE(s.total_revenue, 0) / NULLIF(COALESCE(m.total_ad_spend, 0), 0), 2
    )                                                   AS blended_roas,
    ROUND(
        COALESCE(m.meta_revenue, 0) / NULLIF(COALESCE(m.total_ad_spend, 0), 0), 2
    )                                                   AS meta_roas,
    -- MER (Marketing Efficiency Ratio = Revenue / Ad Spend)
    ROUND(
        COALESCE(s.total_revenue, 0) / NULLIF(COALESCE(m.total_ad_spend, 0), 0), 2
    )                                                   AS mer,
    -- CAC (Customer Acquisition Cost = Ad Spend / New Customers)
    ROUND(
        COALESCE(m.total_ad_spend, 0) / NULLIF(COALESCE(s.unique_customers, 0), 0), 2
    )                                                   AS blended_cac,
    -- Meta attribution percentage
    ROUND(
        COALESCE(m.meta_revenue, 0) / NULLIF(COALESCE(s.total_revenue, 0), 0) * 100, 1
    )                                                   AS meta_attribution_pct,
    -- Net revenue (after refunds and ad spend)
    COALESCE(s.total_revenue, 0)
        - COALESCE(rf.total_refund_amount, 0)
        - COALESCE(m.total_ad_spend, 0)                 AS net_profit_proxy
FROM daily_shopify s
FULL OUTER JOIN daily_meta m ON s.order_date = m.ad_date
LEFT JOIN daily_refunds rf ON COALESCE(s.order_date, m.ad_date) = rf.refund_date
ORDER BY COALESCE(s.order_date, m.ad_date);
