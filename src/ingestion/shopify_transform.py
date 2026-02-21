"""
Transform Shopify GraphQL Admin API responses to our raw table schema.

The GraphQL API returns camelCase, nested connections, and GID strings.
Our raw tables expect snake_case, flat JSONB arrays, and integer IDs.
This module bridges the gap so downstream staging SQL needs zero changes.

Key transformations:
  - GID → int64:  "gid://shopify/Order/123456" → 123456
  - camelCase → snake_case for column names
  - Connection edges → flat JSONB arrays (lineItems, variants, etc.)
  - MoneyV2 / MoneyBag → our money_set JSONB format
  - Add Airbyte system columns (_airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta)
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any

# ─── Utility helpers ─────────────────────────────────────


def extract_gid(gid_str: str | None) -> int | None:
    """
    Extract numeric ID from a Shopify GID string.

    "gid://shopify/Order/123456" → 123456
    "gid://shopify/ProductVariant/789" → 789
    "gid://shopify/MailingAddress/989?model_name=..." → 989
    """
    if not gid_str:
        return None
    # Match digits at the end of path, ignoring query params
    match = re.search(r"/(\d+)(?:\?|$)", str(gid_str))
    return int(match.group(1)) if match else None


def extract_gid_str(gid_str: str | None) -> str | None:
    """Extract numeric ID as string (for columns that are VARCHAR)."""
    nid = extract_gid(gid_str)
    return str(nid) if nid is not None else None


def _money_set(money_bag: dict | None) -> dict | None:
    """
    Convert GraphQL MoneyBag to our money_set JSONB format.

    Input:  {"shopMoney": {"amount": "100.00", "currencyCode": "AUD"},
             "presentmentMoney": {"amount": "100.00", "currencyCode": "AUD"}}
    Output: {"shop_money": {"amount": "100.00", "currency_code": "AUD"},
             "presentment_money": {"amount": "100.00", "currency_code": "AUD"}}
    """
    if not money_bag:
        return None
    result = {}
    for gql_key, db_key in [("shopMoney", "shop_money"), ("presentmentMoney", "presentment_money")]:
        m = money_bag.get(gql_key)
        if m:
            result[db_key] = {
                "amount": m.get("amount", "0.00"),
                "currency_code": m.get("currencyCode", "AUD"),
            }
    return result if result else None


def _money_amount(money_bag: dict | None) -> str | None:
    """Extract the shopMoney amount string from a MoneyBag."""
    if not money_bag:
        return None
    shop = money_bag.get("shopMoney")
    return shop.get("amount") if shop else None


def _airbyte_columns() -> dict:
    """Generate standard Airbyte system columns."""
    return {
        "_airbyte_raw_id": str(uuid.uuid4()),
        "_airbyte_extracted_at": datetime.now(timezone.utc).isoformat(),
        "_airbyte_meta": {"changes": []},
    }


def _edges_to_list(connection: dict | None) -> list[dict]:
    """Extract nodes from a GraphQL connection (edges/node pattern)."""
    if not connection:
        return []
    edges = connection.get("edges", [])
    return [e["node"] for e in edges if "node" in e]


# ─── Product transformer ────────────────────────────────


def transform_product(product: dict, shop_url: str) -> tuple[dict, list[dict]]:
    """
    Transform a GraphQL Product node → (product_row, [variant_rows]).

    Returns a tuple of:
      - The product dict matching our `products` table schema
      - A list of variant dicts matching our `product_variants` table schema
    """
    pid = extract_gid(product.get("id"))
    gql_id = product.get("id")

    # Extract variants from connection (paginated) or direct list (bulk reassembled)
    raw_variants = product.get("variants", [])
    if isinstance(raw_variants, dict):
        raw_variants = _edges_to_list(raw_variants)

    # Build variant JSONB array (embedded in product row, Airbyte style)
    variants_jsonb = []
    variant_rows = []

    for v in raw_variants:
        vid = extract_gid(v.get("id"))
        v_gql_id = v.get("id")

        # Extract option values from selectedOptions
        selected = v.get("selectedOptions", [])
        option1 = selected[0]["value"] if len(selected) > 0 else None
        option2 = selected[1]["value"] if len(selected) > 1 else None
        option3 = selected[2]["value"] if len(selected) > 2 else None

        # Inventory item ID
        inv_item = v.get("inventoryItem", {})
        inv_item_id = extract_gid(inv_item.get("id")) if inv_item else None

        # Image — `image` field removed from ProductVariant in 2026-01
        v_image_id = None
        v_image_src = None

        variant_row = {
            "id": vid,
            "product_id": pid,
            "title": v.get("title"),
            "price": v.get("price"),
            "compare_at_price": v.get("compareAtPrice"),
            "sku": v.get("sku"),
            "barcode": v.get("barcode"),
            "position": v.get("position"),
            "option1": option1,
            "option2": option2,
            "option3": option3,
            "grams": None,  # GraphQL doesn't return grams directly
            "weight": None,  # Removed from ProductVariant in newer API versions
            "weight_unit": None,  # Removed from ProductVariant in newer API versions
            "taxable": v.get("taxable"),
            "tax_code": None,  # Deprecated on ProductVariant in 2026-01
            "inventory_item_id": inv_item_id,
            "inventory_quantity": v.get("inventoryQuantity"),
            "old_inventory_quantity": None,
            "inventory_policy": v.get("inventoryPolicy", "").lower() if v.get("inventoryPolicy") else None,
            "requires_shipping": None,  # Removed from ProductVariant in newer API versions
            "image_id": v_image_id,
            "image_src": v_image_src,
            "available_for_sale": v.get("availableForSale"),
            "display_name": v.get("displayName"),
            "admin_graphql_api_id": v_gql_id,
            "created_at": v.get("createdAt"),
            "updated_at": v.get("updatedAt"),
            "shop_url": shop_url,
            **_airbyte_columns(),
        }
        variant_rows.append(variant_row)

        # Simplified variant for embedding in product JSONB
        variants_jsonb.append({
            "id": vid,
            "product_id": pid,
            "title": v.get("title"),
            "price": v.get("price"),
            "compare_at_price": v.get("compareAtPrice"),
            "sku": v.get("sku"),
            "barcode": v.get("barcode"),
            "position": v.get("position"),
            "option1": option1,
            "option2": option2,
            "option3": option3,
            "inventory_quantity": v.get("inventoryQuantity"),
            "inventory_policy": v.get("inventoryPolicy", "").lower() if v.get("inventoryPolicy") else None,
        })

    # Options
    raw_options = product.get("options", [])
    options_jsonb = [
        {
            "id": extract_gid(o.get("id")),
            "product_id": pid,
            "name": o.get("name"),
            "position": o.get("position"),
            "values": o.get("values", []),
        }
        for o in raw_options
    ]

    # Images — `images` replaced by `media` in 2026-01
    raw_media = product.get("media", product.get("images", []))
    if isinstance(raw_media, dict):
        raw_media = _edges_to_list(raw_media)
    images_jsonb = []
    for m in raw_media:
        # media nodes are MediaImage unions; extract nested image
        img = m.get("image", m)  # fallback to node itself if no nested image
        images_jsonb.append({
            "id": extract_gid(m.get("id")),
            "product_id": pid,
            "src": img.get("url"),
            "alt": img.get("altText"),
            "width": img.get("width"),
            "height": img.get("height"),
        })

    # Featured image — `featuredImage` replaced by `featuredMedia` in 2026-01
    feat = product.get("featuredMedia", product.get("featuredImage"))
    image_jsonb = None
    if feat:
        feat_img = feat.get("image", feat)  # MediaImage has nested image
        image_jsonb = {
            "id": extract_gid(feat.get("id")),
            "product_id": pid,
            "src": feat_img.get("url"),
            "alt": feat_img.get("altText"),
            "width": feat_img.get("width"),
            "height": feat_img.get("height"),
        }

    product_row = {
        "id": pid,
        "title": product.get("title"),
        "body_html": product.get("descriptionHtml", product.get("bodyHtml")),
        "vendor": product.get("vendor"),
        "product_type": product.get("productType"),
        "handle": product.get("handle"),
        "status": product.get("status", "").lower() if product.get("status") else None,
        "tags": ", ".join(product.get("tags", [])) if isinstance(product.get("tags"), list) else product.get("tags"),
        "template_suffix": product.get("templateSuffix"),
        "published_at": product.get("publishedAt"),
        "published_scope": "global",
        "created_at": product.get("createdAt"),
        "updated_at": product.get("updatedAt"),
        "shop_url": shop_url,
        "admin_graphql_api_id": gql_id,
        "variants": variants_jsonb,
        "options": options_jsonb,
        "image": image_jsonb,
        "images": images_jsonb,
        "total_inventory": product.get("totalInventory"),
        "total_variants": len(raw_variants),  # totalVariants removed in 2026-01, compute from variants list
        **_airbyte_columns(),
    }

    return product_row, variant_rows


# ─── Customer transformer ───────────────────────────────


def transform_customer(customer: dict, shop_url: str) -> dict:
    """Transform a GraphQL Customer node → customer_row for our `customers` table."""
    cid = extract_gid(customer.get("id"))
    gql_id = customer.get("id")

    # Email — 2026-01: `email` deprecated → use `defaultEmailAddress.emailAddress`
    default_email_obj = customer.get("defaultEmailAddress") or {}
    email = default_email_obj.get("emailAddress") or customer.get("email")

    # Phone — 2026-01: `phone` deprecated → use `defaultPhoneNumber.phoneNumber`
    default_phone_obj = customer.get("defaultPhoneNumber") or {}
    phone = default_phone_obj.get("phoneNumber") or customer.get("phone")

    # Amount spent
    amount_spent = customer.get("amountSpent", {})
    total_spent = amount_spent.get("amount") if amount_spent else None
    currency = amount_spent.get("currencyCode", "AUD") if amount_spent else "AUD"

    # Last order
    last_order = customer.get("lastOrder")
    last_order_id = extract_gid(last_order.get("id")) if last_order else None
    last_order_name = last_order.get("name") if last_order else None

    # Default address
    default_addr = customer.get("defaultAddress")
    default_address_jsonb = None
    if default_addr:
        default_address_jsonb = _transform_address(default_addr)

    # All addresses — 2026-01: `addresses` deprecated → `addressesV2` (connection)
    raw_addresses_v2 = customer.get("addressesV2")
    raw_addresses = customer.get("addresses", [])
    if raw_addresses_v2:
        addresses_list = _edges_to_list(raw_addresses_v2) if isinstance(raw_addresses_v2, dict) else raw_addresses_v2
    else:
        addresses_list = raw_addresses or []
    addresses_jsonb = [_transform_address(a) for a in addresses_list] if addresses_list else []

    # Email marketing consent — 2026-01: derived from defaultEmailAddress
    email_marketing_state = default_email_obj.get("marketingState")
    email_opt_in_level = default_email_obj.get("marketingOptInLevel")
    # Fallback to deprecated emailMarketingConsent if present
    emc = customer.get("emailMarketingConsent")
    if not email_marketing_state and emc:
        email_marketing_state = emc.get("marketingState")
        email_opt_in_level = emc.get("marketingOptInLevel")

    email_marketing_consent = None
    if email_marketing_state:
        email_marketing_consent = {
            "state": email_marketing_state.lower() if email_marketing_state else None,
            "opt_in_level": email_opt_in_level,
            "consent_updated_at": emc.get("consentUpdatedAt") if emc else None,
        }

    # SMS marketing consent — 2026-01: derived from defaultPhoneNumber
    sms_marketing_state = default_phone_obj.get("marketingState")
    sms_opt_in_level = default_phone_obj.get("marketingOptInLevel")
    # Fallback to deprecated smsMarketingConsent if present
    smc = customer.get("smsMarketingConsent")
    if not sms_marketing_state and smc:
        sms_marketing_state = smc.get("marketingState")
        sms_opt_in_level = smc.get("marketingOptInLevel")

    sms_marketing_consent = None
    if sms_marketing_state:
        sms_marketing_consent = {
            "state": sms_marketing_state.lower() if sms_marketing_state else None,
            "opt_in_level": sms_opt_in_level,
            "consent_updated_at": smc.get("consentUpdatedAt") if smc else None,
        }

    # Accepts marketing (derived from email consent state)
    accepts_marketing = email_marketing_state in ("SUBSCRIBED",) if email_marketing_state else False

    return {
        "id": cid,
        "email": email,
        "first_name": customer.get("firstName"),
        "last_name": customer.get("lastName"),
        "phone": phone,
        "state": customer.get("state", "").lower() if customer.get("state") else None,
        "tags": ", ".join(customer.get("tags", [])) if isinstance(customer.get("tags"), list) else customer.get("tags"),
        "currency": currency,
        "note": customer.get("note"),
        "verified_email": customer.get("verifiedEmail"),
        "tax_exempt": customer.get("taxExempt"),
        "tax_exemptions": ", ".join(customer.get("taxExemptions", [])) if customer.get("taxExemptions") else None,
        "accepts_marketing": accepts_marketing,
        "accepts_marketing_updated_at": emc.get("consentUpdatedAt") if emc else None,
        "marketing_opt_in_level": email_opt_in_level,
        "orders_count": customer.get("numberOfOrders"),
        "total_spent": total_spent,
        "last_order_id": last_order_id,
        "last_order_name": last_order_name,
        "admin_graphql_api_id": gql_id,
        "created_at": customer.get("createdAt"),
        "updated_at": customer.get("updatedAt"),
        "shop_url": shop_url,
        "default_address": default_address_jsonb,
        "addresses": addresses_jsonb,
        "email_marketing_consent": email_marketing_consent,
        "sms_marketing_consent": sms_marketing_consent,
        **_airbyte_columns(),
    }


def _transform_address(addr: dict | None) -> dict | None:
    """Transform a GraphQL address to our JSONB format."""
    if not addr:
        return None
    return {
        "id": extract_gid(addr.get("id")),
        "first_name": addr.get("firstName"),
        "last_name": addr.get("lastName"),
        "company": addr.get("company"),
        "address1": addr.get("address1"),
        "address2": addr.get("address2"),
        "city": addr.get("city"),
        "province": addr.get("province"),
        "province_code": addr.get("provinceCode"),
        "country": addr.get("country"),
        "country_code": addr.get("countryCodeV2") or addr.get("countryCode"),
        "zip": addr.get("zip"),
        "phone": addr.get("phone"),
    }


# ─── Order transformer ──────────────────────────────────


def transform_order(order: dict, shop_url: str) -> tuple[dict, list[dict]]:
    """
    Transform a GraphQL Order node → (order_row, [refund_rows]).

    Returns:
      - order_row: Dict matching our `orders` table schema
      - refund_rows: List of dicts matching our `order_refunds` table schema
    """
    oid = extract_gid(order.get("id"))
    gql_id = order.get("id")

    # Source name — now a direct scalar field on Order in 2026-01
    source_name = order.get("sourceName")

    # Financial / fulfillment status — GraphQL returns UPPERCASE
    financial_status = order.get("financialStatus", "")
    if financial_status:
        financial_status = financial_status.lower()

    fulfillment_status = order.get("fulfillmentStatus", "")
    if fulfillment_status:
        fulfillment_status = fulfillment_status.lower()
        if fulfillment_status == "unfulfilled":
            fulfillment_status = None  # Match Shopify REST convention

    # Customer JSONB — email/phone deprecated on Customer in 2026-01, use order-level email/phone
    raw_customer = order.get("customer")
    customer_jsonb = None
    if raw_customer:
        customer_jsonb = {
            "id": extract_gid(raw_customer.get("id")),
            "email": order.get("email"),  # Order still has email
            "first_name": raw_customer.get("firstName"),
            "last_name": raw_customer.get("lastName"),
            "phone": order.get("phone"),  # Order still has phone
        }

    # Addresses
    billing_address = _transform_address(order.get("billingAddress"))
    shipping_address = _transform_address(order.get("shippingAddress"))

    # Discount codes
    discount_codes = order.get("discountCodes", [])

    # Discount applications
    raw_disc_apps = order.get("discountApplications")
    discount_applications = None
    if raw_disc_apps:
        disc_app_nodes = _edges_to_list(raw_disc_apps)
        discount_applications = _transform_discount_applications(disc_app_nodes)

    # Shipping lines
    raw_shipping = order.get("shippingLines")
    shipping_lines = None
    if raw_shipping:
        sl_nodes = _edges_to_list(raw_shipping)
        shipping_lines = _transform_shipping_lines(sl_nodes)

    # Tax lines (currentTaxLines in 2026-01)
    raw_tax_lines = order.get("currentTaxLines", order.get("taxLines", []))
    tax_lines = _transform_tax_lines(raw_tax_lines)

    # Line items
    raw_line_items = order.get("lineItems")
    line_items_jsonb = []
    if raw_line_items:
        li_nodes = _edges_to_list(raw_line_items) if isinstance(raw_line_items, dict) else raw_line_items
        line_items_jsonb = _transform_line_items(li_nodes, oid)

    # Refunds
    raw_refunds = order.get("refunds", [])
    refunds_jsonb = []
    refund_rows = []
    for r in raw_refunds:
        refund_row, refund_embedded = _transform_refund(r, oid, shop_url)
        refund_rows.append(refund_row)
        refunds_jsonb.append(refund_embedded)

    # Money fields — 2026-01 renames:
    #   currency → currencyCode
    #   orderNumber → number
    #   buyerAcceptsMarketing → customerAcceptsMarketing
    #   totalWeight → currentTotalWeight
    #   subtotalPriceSet/totalPriceSet/totalDiscountsSet/totalTaxSet → removed, use current* or original*
    #   totalShippingPriceSet → currentShippingPriceSet
    #   taxLines → currentTaxLines
    #   test, taxExempt, taxesIncluded → removed from Order
    order_row = {
        "id": oid,
        "admin_graphql_api_id": gql_id,
        "app_id": None,
        "browser_ip": None,
        "buyer_accepts_marketing": order.get("customerAcceptsMarketing"),
        "cancel_reason": order.get("cancelReason", "").lower() if order.get("cancelReason") else None,
        "cancelled_at": order.get("cancelledAt"),
        "cart_token": None,
        "checkout_id": None,
        "checkout_token": None,
        "closed_at": order.get("closedAt"),
        "confirmed": order.get("confirmed"),
        "confirmation_number": None,
        "contact_email": order.get("email"),
        "created_at": order.get("createdAt"),
        "currency": order.get("currencyCode"),
        "current_subtotal_price": _money_amount(order.get("currentSubtotalPriceSet")),
        "current_subtotal_price_set": _money_set(order.get("currentSubtotalPriceSet")),
        "current_total_discounts": _money_amount(order.get("currentTotalDiscountsSet")),
        "current_total_discounts_set": _money_set(order.get("currentTotalDiscountsSet")),
        "current_total_price": _money_amount(order.get("currentTotalPriceSet")),
        "current_total_price_set": _money_set(order.get("currentTotalPriceSet")),
        "current_total_tax": _money_amount(order.get("currentTotalTaxSet")),
        "current_total_tax_set": _money_set(order.get("currentTotalTaxSet")),
        "customer_locale": order.get("customerLocale"),
        "discount_applications": discount_applications,
        "discount_codes": discount_codes if discount_codes else [],
        "email": order.get("email"),
        "financial_status": financial_status,
        "fulfillment_status": fulfillment_status,
        "landing_site": None,
        "name": order.get("name"),
        "note": order.get("note"),
        "note_attributes": None,
        "number": order.get("number"),
        "order_number": order.get("number"),
        "order_status_url": None,
        "payment_gateway_names": None,
        "phone": order.get("phone"),
        "presentment_currency": order.get("presentmentCurrencyCode"),
        "processed_at": order.get("processedAt"),
        "source_name": source_name,
        "subtotal_price": _money_amount(order.get("currentSubtotalPriceSet")),
        "subtotal_price_set": _money_set(order.get("currentSubtotalPriceSet")),
        "tags": ", ".join(order.get("tags", [])) if isinstance(order.get("tags"), list) else order.get("tags", ""),
        "tax_exempt": None,  # Removed from Order in 2026-01
        "tax_lines": tax_lines,
        "taxes_included": order.get("estimatedTaxes"),
        "test": None,  # Removed from Order in 2026-01
        "token": None,
        "total_discounts": _money_amount(order.get("currentTotalDiscountsSet")),
        "total_discounts_set": _money_set(order.get("currentTotalDiscountsSet")),
        "total_line_items_price": None,
        "total_line_items_price_set": None,
        "total_outstanding": None,
        "total_price": _money_amount(order.get("originalTotalPriceSet")),
        "total_price_set": _money_set(order.get("originalTotalPriceSet")),
        "total_price_usd": None,
        "total_shipping_price_set": _money_set(order.get("currentShippingPriceSet")),
        "total_tax": _money_amount(order.get("currentTotalTaxSet")),
        "total_tax_set": _money_set(order.get("currentTotalTaxSet")),
        "total_tip_received": "0.00",
        "total_weight": order.get("currentTotalWeight"),
        "updated_at": order.get("updatedAt"),
        "customer": customer_jsonb,
        "billing_address": billing_address,
        "shipping_address": shipping_address,
        "shipping_lines": shipping_lines,
        "line_items": line_items_jsonb,
        "fulfillments": [],
        "refunds": refunds_jsonb,
        "shop_url": shop_url,
        **_airbyte_columns(),
    }

    return order_row, refund_rows


def _transform_line_items(li_nodes: list[dict], order_id: int | None) -> list[dict]:
    """Transform GraphQL line item nodes to our JSONB array format."""
    items = []
    for li in li_nodes:
        variant = li.get("variant") or {}
        product_ref = variant.get("product") or {}

        item = {
            "id": extract_gid(li.get("id")),
            "product_id": extract_gid(product_ref.get("id")),
            "variant_id": extract_gid(variant.get("id")),
            "title": li.get("title"),
            "variant_title": li.get("variantTitle"),
            "name": li.get("name"),
            "quantity": li.get("quantity"),
            "sku": li.get("sku"),
            "vendor": li.get("vendor"),
            "price": _money_amount(li.get("originalUnitPriceSet")),
            "total_discount": _money_amount(li.get("totalDiscountSet")) or "0.00",
            "grams": None,
            "taxable": li.get("taxable"),
            "requires_shipping": li.get("requiresShipping"),
            "gift_card": li.get("isGiftCard"),
            "price_set": _money_set(li.get("originalUnitPriceSet")),
            "total_discount_set": _money_set(li.get("totalDiscountSet")),
        }
        items.append(item)
    return items


def _transform_refund(
    refund: dict, order_id: int | None, shop_url: str
) -> tuple[dict, dict]:
    """
    Transform a GraphQL Refund → (refund_table_row, refund_embedded_jsonb).

    Returns:
      - refund_table_row: For the `order_refunds` table
      - refund_embedded_jsonb: For embedding in the order's `refunds` JSONB array
    """
    rid = extract_gid(refund.get("id"))
    gql_id = refund.get("id")

    # Refund line items
    raw_rli = refund.get("refundLineItems")
    rli_nodes = _edges_to_list(raw_rli) if isinstance(raw_rli, dict) else (raw_rli or [])

    refund_line_items = []
    for rli in rli_nodes:
        line_item = rli.get("lineItem") or {}
        li_variant = line_item.get("variant") or {}
        li_product = li_variant.get("product") or {}

        refund_line_items.append({
            "id": extract_gid(rli.get("id")),
            "line_item_id": extract_gid(line_item.get("id")),
            "quantity": rli.get("quantity"),
            "subtotal": _money_amount(rli.get("subtotalSet")) or "0.00",
            "total_tax": _money_amount(rli.get("totalTaxSet")) or "0.00",
            "restock_type": rli.get("restockType", "").lower() if rli.get("restockType") else None,
            "subtotal_set": _money_set(rli.get("subtotalSet")),
            "total_tax_set": _money_set(rli.get("totalTaxSet")),
            "line_item": {
                "id": extract_gid(line_item.get("id")),
                "product_id": extract_gid(li_product.get("id")),
                "variant_id": extract_gid(li_variant.get("id")),
                "title": line_item.get("title"),
                "variant_title": line_item.get("variantTitle"),
                "name": line_item.get("name"),
                "sku": line_item.get("sku"),
                "vendor": line_item.get("vendor"),
                "quantity": line_item.get("quantity"),
                "price": _money_amount(line_item.get("originalUnitPriceSet")),
            },
        })

    # Transactions
    raw_transactions = refund.get("transactions")
    txn_nodes = _edges_to_list(raw_transactions) if isinstance(raw_transactions, dict) else (raw_transactions or [])
    transactions = []
    for t in txn_nodes:
        transactions.append({
            "id": extract_gid(t.get("id")),
            "kind": t.get("kind", "").lower() if t.get("kind") else None,
            "status": t.get("status", "").lower() if t.get("status") else None,
            "gateway": t.get("gateway"),
            "amount": _money_amount(t.get("amountSet")),
            "processed_at": t.get("processedAt"),
        })

    refund_table_row = {
        "id": rid,
        "order_id": order_id,
        "admin_graphql_api_id": gql_id,
        "created_at": refund.get("createdAt"),
        "processed_at": refund.get("createdAt"),  # GraphQL doesn't have separate processedAt for refunds
        "note": refund.get("note"),
        "restock": any(rli.get("restock_type") == "return" for rli in refund_line_items),
        "user_id": None,
        "duties": None,
        "shop_url": shop_url,
        "return": None,
        "total_duties_set": None,
        "order_adjustments": [],
        "refund_line_items": refund_line_items,
        "transactions": transactions,
        **_airbyte_columns(),
    }

    # Embedded version for the order's refunds JSONB array
    refund_embedded = {
        "id": rid,
        "created_at": refund.get("createdAt"),
        "note": refund.get("note"),
        "refund_line_items": refund_line_items,
        "transactions": transactions,
    }

    return refund_table_row, refund_embedded


def _transform_discount_applications(nodes: list[dict]) -> list[dict]:
    """Transform discount application nodes to JSONB format."""
    result = []
    for n in nodes:
        value = n.get("value", {})
        result.append({
            "allocation_method": n.get("allocationMethod", "").lower() if n.get("allocationMethod") else None,
            "target_selection": n.get("targetSelection", "").lower() if n.get("targetSelection") else None,
            "target_type": n.get("targetType", "").lower() if n.get("targetType") else None,
            "value": value.get("amount") or value.get("percentage"),
            "value_type": "fixed_amount" if "amount" in value else "percentage",
        })
    return result


def _transform_shipping_lines(nodes: list[dict]) -> list[dict]:
    """Transform shipping line nodes to JSONB format."""
    result = []
    for n in nodes:
        result.append({
            "title": n.get("title"),
            "code": n.get("code"),
            "source": n.get("source"),
            "price": _money_amount(n.get("discountedPriceSet")) or "0.00",
            "price_set": _money_set(n.get("discountedPriceSet")),
            "discounted_price": _money_amount(n.get("discountedPriceSet")) or "0.00",
            "discounted_price_set": _money_set(n.get("discountedPriceSet")),
        })
    return result


def _transform_tax_lines(tax_lines: list[dict]) -> list[dict]:
    """Transform tax line nodes to JSONB format."""
    result = []
    for t in tax_lines:
        result.append({
            "title": t.get("title"),
            "rate": t.get("rate") or t.get("ratePercentage"),
            "price": _money_amount(t.get("priceSet")) or "0.00",
            "price_set": _money_set(t.get("priceSet")),
        })
    return result
