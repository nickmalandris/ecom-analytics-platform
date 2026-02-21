"""
Tests for the Shopify GraphQL → raw table schema transformer.

Uses mock GraphQL responses to verify the transformer produces
output matching our exact DDL column names and data types.
"""

import json

import pytest

from src.ingestion.shopify_transform import (
    _money_set,
    _money_amount,
    _airbyte_columns,
    _edges_to_list,
    extract_gid,
    extract_gid_str,
    transform_customer,
    transform_order,
    transform_product,
)

SHOP_URL = "https://test-store.myshopify.com"


# ─── GID extraction ─────────────────────────────────────

class TestExtractGid:
    def test_order_gid(self):
        assert extract_gid("gid://shopify/Order/123456") == 123456

    def test_product_variant_gid(self):
        assert extract_gid("gid://shopify/ProductVariant/789") == 789

    def test_none_returns_none(self):
        assert extract_gid(None) is None

    def test_empty_string_returns_none(self):
        assert extract_gid("") is None

    def test_invalid_format_returns_none(self):
        assert extract_gid("not-a-gid") is None

    def test_gid_str(self):
        assert extract_gid_str("gid://shopify/Customer/42") == "42"


# ─── Money helpers ───────────────────────────────────────

class TestMoneyHelpers:
    def test_money_set_full(self):
        bag = {
            "shopMoney": {"amount": "100.00", "currencyCode": "AUD"},
            "presentmentMoney": {"amount": "100.00", "currencyCode": "AUD"},
        }
        result = _money_set(bag)
        assert result["shop_money"]["amount"] == "100.00"
        assert result["shop_money"]["currency_code"] == "AUD"
        assert result["presentment_money"]["amount"] == "100.00"

    def test_money_set_none(self):
        assert _money_set(None) is None

    def test_money_set_empty(self):
        assert _money_set({}) is None

    def test_money_amount(self):
        bag = {"shopMoney": {"amount": "59.95", "currencyCode": "AUD"}}
        assert _money_amount(bag) == "59.95"

    def test_money_amount_none(self):
        assert _money_amount(None) is None


# ─── Airbyte columns ────────────────────────────────────

class TestAirbyteColumns:
    def test_has_required_keys(self):
        cols = _airbyte_columns()
        assert "_airbyte_raw_id" in cols
        assert "_airbyte_extracted_at" in cols
        assert "_airbyte_meta" in cols

    def test_raw_id_is_uuid_format(self):
        cols = _airbyte_columns()
        assert len(cols["_airbyte_raw_id"]) == 36  # UUID format

    def test_meta_has_changes(self):
        cols = _airbyte_columns()
        assert cols["_airbyte_meta"] == {"changes": []}


# ─── Edges helper ────────────────────────────────────────

class TestEdgesToList:
    def test_normal_connection(self):
        conn = {"edges": [{"node": {"id": "1"}}, {"node": {"id": "2"}}]}
        result = _edges_to_list(conn)
        assert len(result) == 2
        assert result[0]["id"] == "1"

    def test_empty_connection(self):
        assert _edges_to_list({"edges": []}) == []

    def test_none(self):
        assert _edges_to_list(None) == []


# ─── Product transformer ────────────────────────────────

MOCK_PRODUCT = {
    "id": "gid://shopify/Product/1001",
    "title": "Classic Cotton Tee",
    "descriptionHtml": "<p>A classic tee</p>",
    "vendor": "TestBrand",
    "productType": "Apparel",
    "handle": "classic-cotton-tee",
    "status": "ACTIVE",
    "tags": ["cotton", "tee", "classic"],
    "templateSuffix": None,
    "publishedAt": "2025-11-22T00:00:00Z",
    "createdAt": "2025-11-22T00:00:00Z",
    "updatedAt": "2026-02-19T12:00:00Z",
    "totalInventory": 150,
    "options": [
        {"id": "gid://shopify/ProductOption/100", "name": "Size", "position": 1, "values": ["S", "M", "L"]},
    ],
    "featuredMedia": {
        "id": "gid://shopify/MediaImage/500",
        "image": {
            "url": "https://cdn.shopify.com/image.jpg",
            "altText": "Tee",
            "width": 800,
            "height": 600,
        },
    },
    "media": {"edges": [
        {"node": {
            "id": "gid://shopify/MediaImage/500",
            "image": {"url": "https://cdn.shopify.com/image.jpg", "altText": "Tee", "width": 800, "height": 600},
        }},
    ]},
    "variants": {"edges": [
        {"node": {
            "id": "gid://shopify/ProductVariant/2001",
            "title": "S",
            "price": "49.95",
            "compareAtPrice": "59.95",
            "sku": "CCT-S",
            "barcode": "123456",
            "position": 1,
            "selectedOptions": [{"name": "Size", "value": "S"}],
            "inventoryQuantity": 50,
            "inventoryPolicy": "DENY",
            "inventoryItem": {"id": "gid://shopify/InventoryItem/3001"},
            "taxable": True,
            "availableForSale": True,
            "displayName": "Classic Cotton Tee - S",
            "createdAt": "2025-11-22T00:00:00Z",
            "updatedAt": "2026-02-19T12:00:00Z",
        }},
        {"node": {
            "id": "gid://shopify/ProductVariant/2002",
            "title": "M",
            "price": "49.95",
            "compareAtPrice": None,
            "sku": "CCT-M",
            "barcode": None,
            "position": 2,
            "selectedOptions": [{"name": "Size", "value": "M"}],
            "inventoryQuantity": 60,
            "inventoryPolicy": "DENY",
            "inventoryItem": {"id": "gid://shopify/InventoryItem/3002"},
            "taxable": True,
            "availableForSale": True,
            "displayName": "Classic Cotton Tee - M",
            "createdAt": "2025-11-22T00:00:00Z",
            "updatedAt": "2026-02-19T12:00:00Z",
        }},
    ]},
}


class TestTransformProduct:
    def test_product_id_is_int(self):
        row, _ = transform_product(MOCK_PRODUCT, SHOP_URL)
        assert row["id"] == 1001
        assert isinstance(row["id"], int)

    def test_product_has_all_columns(self):
        row, _ = transform_product(MOCK_PRODUCT, SHOP_URL)
        required = [
            "id", "title", "body_html", "vendor", "product_type", "handle",
            "status", "tags", "published_at", "created_at", "updated_at",
            "shop_url", "admin_graphql_api_id", "variants", "options",
            "image", "images", "total_inventory", "total_variants",
            "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
        ]
        for col in required:
            assert col in row, f"Missing column: {col}"

    def test_status_is_lowercase(self):
        row, _ = transform_product(MOCK_PRODUCT, SHOP_URL)
        assert row["status"] == "active"

    def test_tags_is_string(self):
        row, _ = transform_product(MOCK_PRODUCT, SHOP_URL)
        assert isinstance(row["tags"], str)
        assert "cotton" in row["tags"]

    def test_variants_count(self):
        _, variants = transform_product(MOCK_PRODUCT, SHOP_URL)
        assert len(variants) == 2

    def test_variant_has_required_columns(self):
        _, variants = transform_product(MOCK_PRODUCT, SHOP_URL)
        v = variants[0]
        assert v["id"] == 2001
        assert v["product_id"] == 1001
        assert v["price"] == "49.95"
        assert v["sku"] == "CCT-S"
        assert v["option1"] == "S"
        assert v["inventory_quantity"] == 50
        assert v["weight_unit"] is None  # Removed from API in newer versions
        assert v["requires_shipping"] is None  # Removed from API in newer versions
        assert v["inventory_policy"] == "deny"

    def test_variant_has_airbyte_columns(self):
        _, variants = transform_product(MOCK_PRODUCT, SHOP_URL)
        assert "_airbyte_raw_id" in variants[0]

    def test_product_variants_jsonb_is_list(self):
        row, _ = transform_product(MOCK_PRODUCT, SHOP_URL)
        assert isinstance(row["variants"], list)
        assert len(row["variants"]) == 2


# ─── Customer transformer ───────────────────────────────

MOCK_CUSTOMER = {
    "id": "gid://shopify/Customer/5001",
    "email": "jane@example.com",
    "firstName": "Jane",
    "lastName": "Smith",
    "phone": "+61400000000",
    "state": "ENABLED",
    "tags": ["vip", "repeat"],
    "note": None,
    "locale": "en-AU",
    "verifiedEmail": True,
    "taxExempt": False,
    "taxExemptions": [],
    "createdAt": "2025-12-01T00:00:00Z",
    "updatedAt": "2026-02-19T12:00:00Z",
    "numberOfOrders": "5",
    "amountSpent": {"amount": "450.00", "currencyCode": "AUD"},
    "lastOrder": {"id": "gid://shopify/Order/9001", "name": "#1005"},
    "emailMarketingConsent": {
        "marketingState": "SUBSCRIBED",
        "marketingOptInLevel": "SINGLE_OPT_IN",
        "consentUpdatedAt": "2025-12-01T00:00:00Z",
    },
    "smsMarketingConsent": None,
    "defaultAddress": {
        "id": "gid://shopify/MailingAddress/7001",
        "firstName": "Jane",
        "lastName": "Smith",
        "company": None,
        "address1": "42 Wallaby Way",
        "address2": None,
        "city": "Sydney",
        "province": "New South Wales",
        "provinceCode": "NSW",
        "country": "Australia",
        "countryCodeV2": "AU",
        "zip": "2000",
        "phone": "+61400000000",
    },
    "addresses": [],
}


class TestTransformCustomer:
    def test_customer_id(self):
        row = transform_customer(MOCK_CUSTOMER, SHOP_URL)
        assert row["id"] == 5001

    def test_customer_required_columns(self):
        row = transform_customer(MOCK_CUSTOMER, SHOP_URL)
        required = [
            "id", "email", "first_name", "last_name", "phone", "state",
            "tags", "currency", "orders_count", "total_spent",
            "last_order_id", "last_order_name", "accepts_marketing",
            "default_address", "email_marketing_consent",
            "created_at", "updated_at", "shop_url",
            "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
        ]
        for col in required:
            assert col in row, f"Missing column: {col}"

    def test_state_is_lowercase(self):
        row = transform_customer(MOCK_CUSTOMER, SHOP_URL)
        assert row["state"] == "enabled"

    def test_accepts_marketing_derived(self):
        row = transform_customer(MOCK_CUSTOMER, SHOP_URL)
        assert row["accepts_marketing"] is True

    def test_default_address_has_fields(self):
        row = transform_customer(MOCK_CUSTOMER, SHOP_URL)
        addr = row["default_address"]
        assert addr["city"] == "Sydney"
        assert addr["province_code"] == "NSW"
        assert addr["country_code"] == "AU"

    def test_total_spent_is_string(self):
        row = transform_customer(MOCK_CUSTOMER, SHOP_URL)
        assert row["total_spent"] == "450.00"


# ─── Order transformer ──────────────────────────────────

MOCK_ORDER = {
    "id": "gid://shopify/Order/9001",
    "name": "#1001",
    "email": "jane@example.com",
    "phone": None,
    "createdAt": "2026-02-15T10:00:00Z",
    "updatedAt": "2026-02-15T10:00:00Z",
    "cancelledAt": None,
    "closedAt": None,
    "processedAt": "2026-02-15T10:00:00Z",
    "currencyCode": "AUD",
    "presentmentCurrencyCode": "AUD",
    "confirmed": True,
    "cancelReason": None,
    "tags": [],
    "note": None,
    "sourceIdentifier": None,
    "sourceName": "web",
    "financialStatus": "PAID",
    "fulfillmentStatus": "UNFULFILLED",
    "customerLocale": "en-AU",
    "number": 1001,
    "customerAcceptsMarketing": True,
    "originalTotalPriceSet": {
        "shopMoney": {"amount": "109.89", "currencyCode": "AUD"},
        "presentmentMoney": {"amount": "109.89", "currencyCode": "AUD"},
    },
    "currentSubtotalPriceSet": {
        "shopMoney": {"amount": "99.90", "currencyCode": "AUD"},
        "presentmentMoney": {"amount": "99.90", "currencyCode": "AUD"},
    },
    "currentTotalDiscountsSet": {
        "shopMoney": {"amount": "0.00", "currencyCode": "AUD"},
        "presentmentMoney": {"amount": "0.00", "currencyCode": "AUD"},
    },
    "currentTotalPriceSet": {
        "shopMoney": {"amount": "109.89", "currencyCode": "AUD"},
        "presentmentMoney": {"amount": "109.89", "currencyCode": "AUD"},
    },
    "currentTotalTaxSet": {
        "shopMoney": {"amount": "9.99", "currencyCode": "AUD"},
        "presentmentMoney": {"amount": "9.99", "currencyCode": "AUD"},
    },
    "currentShippingPriceSet": {
        "shopMoney": {"amount": "0.00", "currencyCode": "AUD"},
        "presentmentMoney": {"amount": "0.00", "currencyCode": "AUD"},
    },
    "currentTotalWeight": 600,
    "estimatedTaxes": False,
    "billingAddress": {
        "firstName": "Jane", "lastName": "Smith", "company": None,
        "address1": "42 Wallaby Way", "address2": None,
        "city": "Sydney", "province": "New South Wales",
        "provinceCode": "NSW", "country": "Australia",
        "countryCodeV2": "AU", "zip": "2000", "phone": None,
    },
    "shippingAddress": {
        "firstName": "Jane", "lastName": "Smith", "company": None,
        "address1": "42 Wallaby Way", "address2": None,
        "city": "Sydney", "province": "New South Wales",
        "provinceCode": "NSW", "country": "Australia",
        "countryCodeV2": "AU", "zip": "2000", "phone": None,
    },
    "customer": {
        "id": "gid://shopify/Customer/5001",
        "firstName": "Jane",
        "lastName": "Smith",
    },
    "discountCodes": [],
    "discountApplications": {"edges": []},
    "shippingLines": {"edges": []},
    "currentTaxLines": [
        {
            "title": "GST",
            "rate": 0.1,
            "ratePercentage": 10.0,
            "priceSet": {
                "shopMoney": {"amount": "9.99", "currencyCode": "AUD"},
                "presentmentMoney": {"amount": "9.99", "currencyCode": "AUD"},
            },
        }
    ],
    "lineItems": {"edges": [
        {"node": {
            "id": "gid://shopify/LineItem/8001",
            "name": "Classic Cotton Tee - M",
            "title": "Classic Cotton Tee",
            "variantTitle": "M",
            "quantity": 2,
            "sku": "CCT-M",
            "vendor": "TestBrand",
            "requiresShipping": True,
            "taxable": True,
            "isGiftCard": False,
            "originalUnitPriceSet": {
                "shopMoney": {"amount": "49.95", "currencyCode": "AUD"},
                "presentmentMoney": {"amount": "49.95", "currencyCode": "AUD"},
            },
            "discountedUnitPriceSet": {
                "shopMoney": {"amount": "49.95", "currencyCode": "AUD"},
                "presentmentMoney": {"amount": "49.95", "currencyCode": "AUD"},
            },
            "totalDiscountSet": {
                "shopMoney": {"amount": "0.00", "currencyCode": "AUD"},
                "presentmentMoney": {"amount": "0.00", "currencyCode": "AUD"},
            },
            "variant": {
                "id": "gid://shopify/ProductVariant/2002",
                "product": {"id": "gid://shopify/Product/1001"},
            },
        }},
    ]},
    "refunds": [],
}


class TestTransformOrder:
    def test_order_id(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        assert row["id"] == 9001

    def test_order_required_columns(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        critical = [
            "id", "name", "email", "created_at", "updated_at", "currency",
            "financial_status", "fulfillment_status", "total_price",
            "subtotal_price", "total_tax", "total_discounts",
            "total_shipping_price_set", "line_items", "customer",
            "billing_address", "shipping_address",
            "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
        ]
        for col in critical:
            assert col in row, f"Missing column: {col}"

    def test_financial_status_lowercase(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        assert row["financial_status"] == "paid"

    def test_unfulfilled_becomes_none(self):
        """Shopify REST returns null for unfulfilled, so we match."""
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        assert row["fulfillment_status"] is None

    def test_total_price_is_string(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        assert row["total_price"] == "109.89"

    def test_line_items_is_list(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        assert isinstance(row["line_items"], list)
        assert len(row["line_items"]) == 1

    def test_line_item_has_product_id(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        li = row["line_items"][0]
        assert li["product_id"] == 1001
        assert li["variant_id"] == 2002
        assert li["quantity"] == 2
        assert li["price"] == "49.95"

    def test_customer_jsonb(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        c = row["customer"]
        assert c["id"] == 5001
        assert c["email"] == "jane@example.com"

    def test_shipping_address(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        addr = row["shipping_address"]
        assert addr["city"] == "Sydney"
        assert addr["province_code"] == "NSW"
        assert addr["country_code"] == "AU"

    def test_source_name_direct(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        assert row["source_name"] == "web"

    def test_tax_lines(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        assert len(row["tax_lines"]) == 1
        assert row["tax_lines"][0]["title"] == "GST"

    def test_money_set_format(self):
        row, _ = transform_order(MOCK_ORDER, SHOP_URL)
        tps = row["total_price_set"]
        assert "shop_money" in tps
        assert tps["shop_money"]["amount"] == "109.89"
        assert tps["shop_money"]["currency_code"] == "AUD"


# ─── Order with refund ──────────────────────────────────

MOCK_ORDER_WITH_REFUND = {
    **MOCK_ORDER,
    "financialStatus": "PARTIALLY_REFUNDED",
    "refunds": [
        {
            "id": "gid://shopify/Refund/6001",
            "createdAt": "2026-02-18T14:00:00Z",
            "note": "Wrong size",
            "totalRefundedSet": {
                "shopMoney": {"amount": "49.95", "currencyCode": "AUD"},
                "presentmentMoney": {"amount": "49.95", "currencyCode": "AUD"},
            },
            "refundLineItems": {"edges": [
                {"node": {
                    "quantity": 1,
                    "subtotalSet": {
                        "shopMoney": {"amount": "49.95", "currencyCode": "AUD"},
                        "presentmentMoney": {"amount": "49.95", "currencyCode": "AUD"},
                    },
                    "totalTaxSet": {
                        "shopMoney": {"amount": "4.99", "currencyCode": "AUD"},
                        "presentmentMoney": {"amount": "4.99", "currencyCode": "AUD"},
                    },
                    "restockType": "RETURN",
                    "lineItem": {
                        "id": "gid://shopify/LineItem/8001",
                        "name": "Classic Cotton Tee - M",
                        "title": "Classic Cotton Tee",
                        "variantTitle": "M",
                        "sku": "CCT-M",
                        "vendor": "TestBrand",
                        "quantity": 2,
                        "originalUnitPriceSet": {
                            "shopMoney": {"amount": "49.95", "currencyCode": "AUD"},
                            "presentmentMoney": {"amount": "49.95", "currencyCode": "AUD"},
                        },
                        "variant": {
                            "id": "gid://shopify/ProductVariant/2002",
                            "product": {"id": "gid://shopify/Product/1001"},
                        },
                    },
                }},
            ]},
            "transactions": {"edges": [
                {"node": {
                    "id": "gid://shopify/OrderTransaction/7001",
                    "kind": "REFUND",
                    "status": "SUCCESS",
                    "gateway": "shopify_payments",
                    "amountSet": {
                        "shopMoney": {"amount": "49.95", "currencyCode": "AUD"},
                        "presentmentMoney": {"amount": "49.95", "currencyCode": "AUD"},
                    },
                    "processedAt": "2026-02-18T14:00:00Z",
                }},
            ]},
        }
    ],
}


class TestTransformOrderWithRefund:
    def test_refund_rows_generated(self):
        _, refund_rows = transform_order(MOCK_ORDER_WITH_REFUND, SHOP_URL)
        assert len(refund_rows) == 1

    def test_refund_row_has_required_columns(self):
        _, refund_rows = transform_order(MOCK_ORDER_WITH_REFUND, SHOP_URL)
        r = refund_rows[0]
        assert r["id"] == 6001
        assert r["order_id"] == 9001
        assert r["note"] == "Wrong size"
        assert r["shop_url"] == SHOP_URL
        assert "_airbyte_raw_id" in r

    def test_refund_line_items(self):
        _, refund_rows = transform_order(MOCK_ORDER_WITH_REFUND, SHOP_URL)
        rli = refund_rows[0]["refund_line_items"]
        assert len(rli) == 1
        assert rli[0]["quantity"] == 1
        assert rli[0]["subtotal"] == "49.95"
        assert rli[0]["restock_type"] == "return"

    def test_refund_line_item_has_line_item(self):
        _, refund_rows = transform_order(MOCK_ORDER_WITH_REFUND, SHOP_URL)
        li = refund_rows[0]["refund_line_items"][0]["line_item"]
        assert li["product_id"] == 1001
        assert li["variant_id"] == 2002
        assert li["sku"] == "CCT-M"

    def test_refund_transactions(self):
        _, refund_rows = transform_order(MOCK_ORDER_WITH_REFUND, SHOP_URL)
        txns = refund_rows[0]["transactions"]
        assert len(txns) == 1
        assert txns[0]["kind"] == "refund"
        assert txns[0]["amount"] == "49.95"

    def test_order_refunds_jsonb_embedded(self):
        row, _ = transform_order(MOCK_ORDER_WITH_REFUND, SHOP_URL)
        assert len(row["refunds"]) == 1
        assert row["refunds"][0]["id"] == 6001

    def test_financial_status_partially_refunded(self):
        row, _ = transform_order(MOCK_ORDER_WITH_REFUND, SHOP_URL)
        assert row["financial_status"] == "partially_refunded"
