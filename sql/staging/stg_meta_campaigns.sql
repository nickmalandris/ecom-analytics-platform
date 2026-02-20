-- Staging: Meta Ads Campaigns, Ad Sets, and Ads
-- Cleans and joins the campaign hierarchy.
-- Source: {raw_schema}.campaigns, {raw_schema}.ad_sets, {raw_schema}.ads

-- Campaigns
DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_meta_campaigns CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_meta_campaigns AS
SELECT
    c.id                                                AS campaign_id,
    c.account_id,
    c.name                                              AS campaign_name,
    c.status                                            AS campaign_status,
    c.effective_status                                  AS campaign_effective_status,
    c.objective,
    c.buying_type,
    c.bid_strategy,
    (c.daily_budget::NUMERIC / 100)::NUMERIC(12,2)      AS daily_budget,
    c.start_time                                        AS campaign_start_time,
    c.stop_time                                         AS campaign_stop_time,
    c.created_time                                      AS campaign_created_at,
    c.updated_time                                      AS campaign_updated_at
FROM {raw_schema}.campaigns c;

-- Ad Sets
DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_meta_ad_sets CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_meta_ad_sets AS
SELECT
    ads.id                                              AS ad_set_id,
    ads.account_id,
    ads.campaign_id,
    ads.name                                            AS ad_set_name,
    ads.effective_status                                AS ad_set_status,
    (ads.daily_budget::NUMERIC / 100)::NUMERIC(12,2)    AS daily_budget,
    ads.bid_strategy,
    ads.targeting,
    ads.start_time                                      AS ad_set_start_time,
    ads.end_time                                        AS ad_set_end_time,
    ads.created_time                                    AS ad_set_created_at,
    ads.updated_time                                    AS ad_set_updated_at,
    ads.learning_stage_info->>'status'                  AS learning_status
FROM {raw_schema}.ad_sets ads;

-- Ads
DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_meta_ads CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_meta_ads AS
SELECT
    a.id                                                AS ad_id,
    a.account_id,
    a.campaign_id,
    a.adset_id                                          AS ad_set_id,
    a.name                                              AS ad_name,
    a.status                                            AS ad_status,
    a.effective_status                                  AS ad_effective_status,
    a.creative->>'creative_id'                          AS creative_id,
    a.created_time                                      AS ad_created_at,
    a.updated_time                                      AS ad_updated_at
FROM {raw_schema}.ads a;
