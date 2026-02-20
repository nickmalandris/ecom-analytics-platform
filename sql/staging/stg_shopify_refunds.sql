-- Staging: Shopify Refunds
-- Flattens order_refunds and explodes refund_line_items JSONB.
-- Source: {raw_schema}.order_refunds

DROP MATERIALIZED VIEW IF EXISTS {analytics_schema}.stg_shopify_refunds CASCADE;

CREATE MATERIALIZED VIEW {analytics_schema}.stg_shopify_refunds AS

SELECT
    r.id                                                AS refund_id,
    r.order_id,
    DATE(r.created_at)                                  AS refund_date,
    r.created_at                                        AS refund_created_at,
    r.note                                              AS refund_note,
    r.restock,
    -- Refund line items (exploded)
    (rli->>'id')::BIGINT                                AS refund_line_item_id,
    (rli->>'line_item_id')::BIGINT                      AS original_line_item_id,
    (rli->>'quantity')::INT                             AS refund_quantity,
    (rli->>'subtotal')::NUMERIC(12,2)                   AS refund_subtotal,
    (rli->>'total_tax')::NUMERIC(12,2)                  AS refund_tax,
    (rli->>'subtotal')::NUMERIC(12,2) + (rli->>'total_tax')::NUMERIC(12,2)
                                                        AS refund_total,
    rli->>'restock_type'                                AS restock_type,
    -- Original line item info (embedded in refund_line_items)
    (rli->'line_item'->>'product_id')::BIGINT           AS product_id,
    (rli->'line_item'->>'variant_id')::BIGINT           AS variant_id,
    rli->'line_item'->>'title'                          AS product_title,
    rli->'line_item'->>'variant_title'                  AS variant_title,
    rli->'line_item'->>'sku'                            AS sku,
    rli->'line_item'->>'vendor'                         AS vendor,
    (rli->'line_item'->>'price')::NUMERIC(12,2)         AS original_unit_price,
    (rli->'line_item'->>'quantity')::INT                AS original_quantity
FROM {raw_schema}.order_refunds r,
     jsonb_array_elements(r.refund_line_items) AS rli;
