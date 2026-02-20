-- Staging: Shopify Products & Variants
-- Joins products with product_variants for a denormalized view.
-- Source: {raw_schema}.products, {raw_schema}.product_variants

DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_shopify_products CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_shopify_products AS

SELECT
    p.id                                                AS product_id,
    p.title                                             AS product_title,
    p.product_type,
    p.vendor,
    p.handle,
    p.status                                            AS product_status,
    p.tags,
    p.total_inventory,
    p.total_variants,
    DATE(p.created_at)                                  AS product_created_date,
    p.created_at                                        AS product_created_at,
    p.published_at                                      AS product_published_at,
    -- Variant fields
    pv.id                                               AS variant_id,
    pv.title                                            AS variant_title,
    CAST(pv.price AS NUMERIC(12,2))                     AS variant_price,
    CAST(pv.compare_at_price AS NUMERIC(12,2))          AS compare_at_price,
    pv.sku,
    pv.barcode,
    pv.inventory_quantity,
    pv.inventory_policy,
    pv.weight,
    pv.weight_unit,
    pv.option1,
    pv.option2,
    pv.available_for_sale,
    -- Derived
    CASE
        WHEN pv.compare_at_price IS NOT NULL
             AND CAST(pv.compare_at_price AS NUMERIC) > 0
             AND CAST(pv.price AS NUMERIC) < CAST(pv.compare_at_price AS NUMERIC)
        THEN TRUE ELSE FALSE
    END                                                 AS is_on_sale,
    CASE
        WHEN pv.inventory_quantity <= 0 THEN 'out_of_stock'
        WHEN pv.inventory_quantity <= 10 THEN 'low_stock'
        ELSE 'in_stock'
    END                                                 AS stock_status
FROM {raw_schema}.products p
JOIN {raw_schema}.product_variants pv ON p.id = pv.product_id
WHERE p.status = 'active';
