-- Mart: Daily Ad Performance
-- Aggregates Meta Ads metrics by day at campaign and ad set level.
-- Source: {analytics_schema}.stg_meta_ad_insights

DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.mart_daily_ad_performance CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.mart_daily_ad_performance AS

SELECT
    i.insight_date,
    i.campaign_id,
    i.campaign_name,
    i.objective,
    i.adset_id,
    i.adset_name,
    -- Delivery
    SUM(i.impressions)                                  AS impressions,
    SUM(i.clicks)                                       AS clicks,
    SUM(i.spend)                                        AS spend,
    SUM(i.reach)                                        AS reach,
    -- Engagement
    SUM(i.link_clicks)                                  AS link_clicks,
    SUM(i.landing_page_views)                           AS landing_page_views,
    SUM(i.add_to_carts)                                 AS add_to_carts,
    -- Conversions
    SUM(i.purchases)                                    AS purchases,
    SUM(i.purchase_revenue)                             AS purchase_revenue,
    -- Calculated metrics
    ROUND(SUM(i.spend) / NULLIF(SUM(i.clicks), 0), 2)
                                                        AS cpc,
    ROUND(SUM(i.spend) / NULLIF(SUM(i.impressions), 0) * 1000, 2)
                                                        AS cpm,
    ROUND(SUM(i.clicks)::NUMERIC / NULLIF(SUM(i.impressions), 0) * 100, 2)
                                                        AS ctr,
    ROUND(SUM(i.spend) / NULLIF(SUM(i.purchases), 0), 2)
                                                        AS cost_per_purchase,
    ROUND(SUM(i.purchase_revenue) / NULLIF(SUM(i.spend), 0), 2)
                                                        AS roas,
    -- Funnel rates
    ROUND(SUM(i.landing_page_views)::NUMERIC / NULLIF(SUM(i.link_clicks), 0) * 100, 2)
                                                        AS landing_page_rate,
    ROUND(SUM(i.add_to_carts)::NUMERIC / NULLIF(SUM(i.landing_page_views), 0) * 100, 2)
                                                        AS add_to_cart_rate,
    ROUND(SUM(i.purchases)::NUMERIC / NULLIF(SUM(i.clicks), 0) * 100, 4)
                                                        AS conversion_rate,
    -- Ad count
    COUNT(DISTINCT i.ad_id)                             AS active_ads
FROM {analytics_schema}.stg_meta_ad_insights i
GROUP BY
    i.insight_date,
    i.campaign_id,
    i.campaign_name,
    i.objective,
    i.adset_id,
    i.adset_name
ORDER BY i.insight_date, i.campaign_name;
