-- Staging: Shopify Orders
-- Flattens orders and explodes line_items JSONB into individual rows.
-- Source: {raw_schema}.orders

DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_shopify_orders CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_shopify_orders AS

WITH orders_base AS (
    SELECT
        o.id                                            AS order_id,
        o.order_number,
        o.name                                          AS order_name,
        DATE(o.created_at)                              AS order_date,
        o.created_at                                    AS order_created_at,
        o.updated_at                                    AS order_updated_at,
        o.cancelled_at,
        o.closed_at,
        o.financial_status,
        o.fulfillment_status,
        o.currency,
        CAST(o.subtotal_price AS NUMERIC(12,2))         AS subtotal_price,
        CAST(o.total_discounts AS NUMERIC(12,2))        AS total_discounts,
        CAST(o.total_tax AS NUMERIC(12,2))              AS total_tax,
        CAST(o.total_price AS NUMERIC(12,2))            AS total_price,
        (o.total_shipping_price_set->'shop_money'->>'amount')::NUMERIC(12,2)
                                                        AS shipping_price,
        o.source_name,
        o.landing_site,
        o.discount_codes,
        -- Customer fields (embedded JSONB)
        (o.customer->>'id')::BIGINT                     AS customer_id,
        o.customer->>'email'                            AS customer_email,
        o.customer->>'first_name'                       AS customer_first_name,
        o.customer->>'last_name'                        AS customer_last_name,
        -- Shipping address
        o.shipping_address->>'city'                     AS shipping_city,
        o.shipping_address->>'province'                 AS shipping_province,
        o.shipping_address->>'province_code'            AS shipping_province_code,
        o.shipping_address->>'country'                  AS shipping_country,
        o.shipping_address->>'country_code'             AS shipping_country_code,
        o.shipping_address->>'zip'                      AS shipping_zip,
        o.line_items,
        o.cancel_reason,
        o.tags,
        o.test
    FROM {raw_schema}.orders o
    WHERE o.test = FALSE
),

line_items_exploded AS (
    SELECT
        ob.order_id,
        ob.order_date,
        ob.order_created_at,
        ob.financial_status,
        ob.fulfillment_status,
        ob.currency,
        ob.customer_id,
        (li->>'id')::BIGINT                             AS line_item_id,
        (li->>'product_id')::BIGINT                     AS product_id,
        (li->>'variant_id')::BIGINT                     AS variant_id,
        li->>'title'                                    AS product_title,
        li->>'variant_title'                            AS variant_title,
        li->>'sku'                                      AS sku,
        li->>'vendor'                                   AS vendor,
        (li->>'quantity')::INT                           AS quantity,
        (li->>'price')::NUMERIC(12,2)                   AS unit_price,
        (li->>'quantity')::INT * (li->>'price')::NUMERIC(12,2)
                                                        AS line_total,
        (li->>'total_discount')::NUMERIC(12,2)          AS line_discount,
        (li->>'grams')::INT                             AS weight_grams,
        (li->>'taxable')::BOOLEAN                       AS taxable,
        (li->>'requires_shipping')::BOOLEAN             AS requires_shipping,
        (li->>'gift_card')::BOOLEAN                     AS is_gift_card
    FROM orders_base ob,
         jsonb_array_elements(ob.line_items) AS li
)

SELECT
    ob.order_id,
    ob.order_number,
    ob.order_name,
    ob.order_date,
    ob.order_created_at,
    ob.order_updated_at,
    ob.cancelled_at,
    ob.closed_at,
    ob.financial_status,
    ob.fulfillment_status,
    ob.currency,
    ob.subtotal_price,
    ob.total_discounts,
    ob.total_tax,
    ob.total_price,
    ob.shipping_price,
    ob.source_name,
    ob.customer_id,
    ob.customer_email,
    ob.customer_first_name,
    ob.customer_last_name,
    ob.shipping_city,
    ob.shipping_province,
    ob.shipping_province_code,
    ob.shipping_country_code,
    ob.shipping_zip,
    ob.cancel_reason,
    ob.tags,
    -- Aggregated line item info at order level
    (SELECT COUNT(*) FROM jsonb_array_elements(ob.line_items))::INT
                                                        AS total_line_items,
    (SELECT SUM((x->>'quantity')::INT) FROM jsonb_array_elements(ob.line_items) x)::INT
                                                        AS total_item_quantity,
    -- Discount code info
    CASE WHEN jsonb_array_length(COALESCE(ob.discount_codes, '[]'::jsonb)) > 0
         THEN (ob.discount_codes->0->>'code')
         ELSE NULL
    END                                                 AS discount_code
FROM orders_base ob;

-- Also create the line-item level view for product analysis
DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_shopify_order_lines CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_shopify_order_lines AS
SELECT
    o.id                                                AS order_id,
    DATE(o.created_at)                                  AS order_date,
    o.created_at                                        AS order_created_at,
    o.financial_status,
    o.currency,
    (o.customer->>'id')::BIGINT                         AS customer_id,
    (li->>'id')::BIGINT                                 AS line_item_id,
    (li->>'product_id')::BIGINT                         AS product_id,
    (li->>'variant_id')::BIGINT                         AS variant_id,
    li->>'title'                                        AS product_title,
    li->>'variant_title'                                AS variant_title,
    li->>'sku'                                          AS sku,
    li->>'vendor'                                       AS vendor,
    (li->>'quantity')::INT                              AS quantity,
    (li->>'price')::NUMERIC(12,2)                       AS unit_price,
    (li->>'quantity')::INT * (li->>'price')::NUMERIC(12,2)
                                                        AS line_total,
    (li->>'total_discount')::NUMERIC(12,2)              AS line_discount,
    (li->>'grams')::INT                                 AS weight_grams,
    (li->>'taxable')::BOOLEAN                           AS taxable,
    (li->>'requires_shipping')::BOOLEAN                 AS requires_shipping,
    (li->>'gift_card')::BOOLEAN                         AS is_gift_card
FROM {raw_schema}.orders o,
     jsonb_array_elements(o.line_items) AS li
WHERE o.test = FALSE;
