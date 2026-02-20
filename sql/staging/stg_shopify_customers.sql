-- Staging: Shopify Customers
-- Cleans and normalizes customer data.
-- Source: {raw_schema}.customers

DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_shopify_customers CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_shopify_customers AS

SELECT
    c.id                                                AS customer_id,
    c.email,
    c.first_name,
    c.last_name,
    CONCAT(c.first_name, ' ', c.last_name)             AS full_name,
    c.phone,
    c.state                                             AS customer_state,
    c.currency,
    c.orders_count,
    CAST(c.total_spent AS NUMERIC(12,2))                AS total_spent,
    c.last_order_id,
    c.last_order_name,
    c.accepts_marketing,
    c.verified_email,
    c.tax_exempt,
    c.tags,
    -- Address fields
    c.default_address->>'city'                          AS city,
    c.default_address->>'province'                      AS province,
    c.default_address->>'province_code'                 AS province_code,
    c.default_address->>'country'                       AS country,
    c.default_address->>'country_code'                  AS country_code,
    c.default_address->>'zip'                           AS zip,
    -- Email marketing
    c.email_marketing_consent->>'state'                 AS email_marketing_state,
    -- Timestamps
    DATE(c.created_at)                                  AS customer_created_date,
    c.created_at                                        AS customer_created_at,
    c.updated_at                                        AS customer_updated_at,
    -- Derived
    CASE
        WHEN c.orders_count = 0 THEN 'never_purchased'
        WHEN c.orders_count = 1 THEN 'single_purchase'
        WHEN c.orders_count BETWEEN 2 AND 3 THEN 'repeat_buyer'
        ELSE 'loyal_buyer'
    END                                                 AS customer_segment
FROM {raw_schema}.customers c;
