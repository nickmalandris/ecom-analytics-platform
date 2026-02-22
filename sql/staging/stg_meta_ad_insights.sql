-- Staging: Meta Ads Insights
-- Extracts key metrics from JSONB action arrays into flat columns.
-- Source: {schema}.ads_insights

DROP MATERIALIZED VIEW IF EXISTS {schema}.stg_meta_ad_insights CASCADE;

CREATE MATERIALIZED VIEW {schema}.stg_meta_ad_insights AS

WITH raw_insights AS (
    SELECT
        ai.date_start                                   AS insight_date,
        ai.account_id,
        ai.account_name,
        ai.account_currency,
        ai.campaign_id,
        ai.campaign_name,
        ai.adset_id,
        ai.adset_name,
        ai.ad_id,
        ai.ad_name,
        ai.objective,
        ai.buying_type,
        ai.attribution_setting,
        -- Core metrics
        ai.impressions,
        ai.clicks,
        CAST(ai.spend AS NUMERIC(12,2))                 AS spend,
        ai.reach,
        ai.frequency,
        CAST(ai.cpc AS NUMERIC(12,4))                   AS cpc,
        CAST(ai.cpm AS NUMERIC(12,4))                   AS cpm,
        CAST(ai.ctr AS NUMERIC(8,4))                    AS ctr,
        ai.unique_clicks,
        CAST(ai.unique_ctr AS NUMERIC(8,4))             AS unique_ctr,
        ai.inline_link_clicks,
        CAST(ai.inline_link_click_ctr AS NUMERIC(8,4))  AS inline_link_click_ctr,
        -- Quality rankings
        ai.quality_ranking,
        ai.engagement_rate_ranking,
        ai.conversion_rate_ranking,
        -- Actions JSONB (for extraction below)
        ai.actions,
        ai.action_values,
        ai.cost_per_action_type,
        ai.purchase_roas
    FROM {schema}.ads_insights ai
),

-- Extract specific action types from JSONB arrays
actions_extracted AS (
    SELECT
        ri.*,
        -- Purchases
        (SELECT (elem->>'value')::INT
         FROM jsonb_array_elements(ri.actions) elem
         WHERE elem->>'action_type' = 'purchase'
         LIMIT 1)                                       AS purchases,
        -- Link clicks (from actions)
        (SELECT (elem->>'value')::INT
         FROM jsonb_array_elements(ri.actions) elem
         WHERE elem->>'action_type' = 'link_click'
         LIMIT 1)                                       AS link_clicks,
        -- Landing page views
        (SELECT (elem->>'value')::INT
         FROM jsonb_array_elements(ri.actions) elem
         WHERE elem->>'action_type' = 'landing_page_view'
         LIMIT 1)                                       AS landing_page_views,
        -- Add to carts
        (SELECT (elem->>'value')::INT
         FROM jsonb_array_elements(ri.actions) elem
         WHERE elem->>'action_type' = 'add_to_cart'
         LIMIT 1)                                       AS add_to_carts,
        -- Purchase revenue (from action_values)
        (SELECT (elem->>'value')::NUMERIC(12,2)
         FROM jsonb_array_elements(ri.action_values) elem
         WHERE elem->>'action_type' = 'purchase'
         LIMIT 1)                                       AS purchase_revenue,
        -- CPA (from cost_per_action_type)
        (SELECT (elem->>'value')::NUMERIC(12,2)
         FROM jsonb_array_elements(ri.cost_per_action_type) elem
         WHERE elem->>'action_type' = 'purchase'
         LIMIT 1)                                       AS cost_per_purchase,
        -- ROAS (from purchase_roas)
        (SELECT (elem->>'value')::NUMERIC(10,4)
         FROM jsonb_array_elements(ri.purchase_roas) elem
         WHERE elem->>'action_type' = 'omni_purchase'
         LIMIT 1)                                       AS roas
    FROM raw_insights ri
)

SELECT
    ae.insight_date,
    ae.account_id,
    ae.account_name,
    ae.account_currency,
    ae.campaign_id,
    ae.campaign_name,
    ae.adset_id,
    ae.adset_name,
    ae.ad_id,
    ae.ad_name,
    ae.objective,
    ae.buying_type,
    ae.attribution_setting,
    -- Core delivery metrics
    ae.impressions,
    ae.clicks,
    ae.spend,
    ae.reach,
    ae.frequency,
    ae.cpc,
    ae.cpm,
    ae.ctr,
    ae.unique_clicks,
    ae.unique_ctr,
    ae.inline_link_clicks,
    ae.inline_link_click_ctr,
    -- Quality rankings
    ae.quality_ranking,
    ae.engagement_rate_ranking,
    ae.conversion_rate_ranking,
    -- Extracted conversion metrics (flat columns)
    COALESCE(ae.link_clicks, 0)                         AS link_clicks,
    COALESCE(ae.landing_page_views, 0)                  AS landing_page_views,
    COALESCE(ae.add_to_carts, 0)                        AS add_to_carts,
    COALESCE(ae.purchases, 0)                           AS purchases,
    COALESCE(ae.purchase_revenue, 0)                    AS purchase_revenue,
    COALESCE(ae.cost_per_purchase, 0)                   AS cost_per_purchase,
    COALESCE(ae.roas, 0)                                AS roas,
    -- Derived funnel metrics
    CASE WHEN ae.link_clicks > 0
         THEN ROUND(ae.landing_page_views::NUMERIC / ae.link_clicks * 100, 2)
         ELSE 0
    END                                                 AS landing_page_rate,
    CASE WHEN ae.landing_page_views > 0
         THEN ROUND(ae.add_to_carts::NUMERIC / ae.landing_page_views * 100, 2)
         ELSE 0
    END                                                 AS add_to_cart_rate,
    CASE WHEN ae.clicks > 0
         THEN ROUND(COALESCE(ae.purchases, 0)::NUMERIC / ae.clicks * 100, 4)
         ELSE 0
    END                                                 AS conversion_rate
FROM actions_extracted ae;
