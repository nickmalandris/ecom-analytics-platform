"""Generate Shopify seed data matching Airbyte's output schema."""

import json
import random
from datetime import date, datetime, timedelta, timezone

from scripts.generators.helpers import (
    action_stats_list,
    daily_volume_curve_aligned,
    fake,
    fake_australian_address,
    generate_uuid,
    airbyte_meta,
    jitter,
    money_set,
    next_id,
    random_datetime_on_day,
    round_money,
    to_iso,
    weighted_choice,
)

SHOP_URL = "https://test-store.myshopify.com"
CURRENCY = "AUD"

# ──────────────────────────────────────────────
# Product Catalog Definition
# ──────────────────────────────────────────────

PRODUCT_CATALOG = [
    # Apparel - hero products
    {"title": "Classic Cotton Tee", "type": "Apparel", "vendor": "AUS Basics",
     "base_price": 39.95, "variants": ["Black/S", "Black/M", "Black/L", "Black/XL", "White/S", "White/M", "White/L", "White/XL"],
     "hero": True, "problem": False, "weight": 200},
    {"title": "Premium Hoodie", "type": "Apparel", "vendor": "AUS Basics",
     "base_price": 89.95, "variants": ["Charcoal/S", "Charcoal/M", "Charcoal/L", "Navy/M", "Navy/L"],
     "hero": True, "problem": False, "weight": 500},
    {"title": "Lightweight Bomber Jacket", "type": "Apparel", "vendor": "Urban Edge",
     "base_price": 149.95, "variants": ["Olive/S", "Olive/M", "Olive/L", "Black/M", "Black/L"],
     "hero": False, "problem": False, "weight": 700},
    {"title": "Linen Button-Up Shirt", "type": "Apparel", "vendor": "Coastal Co",
     "base_price": 69.95, "variants": ["Sky Blue/S", "Sky Blue/M", "Sky Blue/L", "White/M", "White/L"],
     "hero": False, "problem": False, "weight": 250},
    {"title": "Slim Fit Chinos", "type": "Apparel", "vendor": "AUS Basics",
     "base_price": 79.95, "variants": ["Khaki/30", "Khaki/32", "Khaki/34", "Navy/30", "Navy/32", "Navy/34"],
     "hero": False, "problem": False, "weight": 400},
    {"title": "Merino Wool Jumper", "type": "Apparel", "vendor": "Coastal Co",
     "base_price": 119.95, "variants": ["Grey Marle/S", "Grey Marle/M", "Grey Marle/L", "Black/M", "Black/L"],
     "hero": False, "problem": True, "weight": 350},  # HIGH REFUND RATE PRODUCT
    {"title": "Performance Polo", "type": "Apparel", "vendor": "Urban Edge",
     "base_price": 54.95, "variants": ["White/S", "White/M", "White/L", "Navy/M", "Navy/L"],
     "hero": False, "problem": False, "weight": 220},
    # Accessories
    {"title": "Canvas Tote Bag", "type": "Accessories", "vendor": "Coastal Co",
     "base_price": 34.95, "variants": ["Natural", "Black", "Navy"],
     "hero": False, "problem": False, "weight": 300},
    {"title": "Leather Bifold Wallet", "type": "Accessories", "vendor": "Urban Edge",
     "base_price": 59.95, "variants": ["Tan", "Black", "Dark Brown"],
     "hero": True, "problem": False, "weight": 100},
    {"title": "Wool Beanie", "type": "Accessories", "vendor": "AUS Basics",
     "base_price": 29.95, "variants": ["Charcoal", "Black", "Cream", "Burgundy"],
     "hero": False, "problem": False, "weight": 80},
    {"title": "Aviator Sunglasses", "type": "Accessories", "vendor": "Coastal Co",
     "base_price": 89.95, "variants": ["Gold/Green", "Silver/Blue", "Black/Grey"],
     "hero": False, "problem": False, "weight": 50},
    {"title": "Minimalist Watch", "type": "Accessories", "vendor": "Urban Edge",
     "base_price": 179.95, "variants": ["Silver/Black Leather", "Gold/Brown Leather", "Rose Gold/Mesh"],
     "hero": False, "problem": False, "weight": 80},
    # Home
    {"title": "Soy Wax Candle", "type": "Home", "vendor": "Homestead AU",
     "base_price": 24.95, "variants": ["Eucalyptus", "Lemon Myrtle", "Sandalwood"],
     "hero": False, "problem": False, "weight": 350},
    {"title": "Ceramic Coffee Mug", "type": "Home", "vendor": "Homestead AU",
     "base_price": 19.95, "variants": ["Matte White", "Matte Black", "Speckled Blue"],
     "hero": False, "problem": False, "weight": 400},
    {"title": "Linen Throw Blanket", "type": "Home", "vendor": "Homestead AU",
     "base_price": 99.95, "variants": ["Oatmeal", "Charcoal", "Sage"],
     "hero": False, "problem": False, "weight": 800},
    {"title": "Abstract Art Print", "type": "Home", "vendor": "Homestead AU",
     "base_price": 49.95, "variants": ["A3", "A2", "A1"],
     "hero": False, "problem": False, "weight": 200},
    {"title": "Stoneware Planter", "type": "Home", "vendor": "Homestead AU",
     "base_price": 44.95, "variants": ["Small/White", "Small/Terracotta", "Large/White", "Large/Terracotta"],
     "hero": False, "problem": False, "weight": 600},
    {"title": "Organic Cotton Towel Set", "type": "Home", "vendor": "Coastal Co",
     "base_price": 64.95, "variants": ["White", "Grey", "Sage"],
     "hero": False, "problem": False, "weight": 900},
    {"title": "Bamboo Cutting Board", "type": "Home", "vendor": "Homestead AU",
     "base_price": 39.95, "variants": ["Small", "Large"],
     "hero": False, "problem": False, "weight": 700},
    {"title": "Essential Oil Diffuser", "type": "Home", "vendor": "Homestead AU",
     "base_price": 54.95, "variants": ["White", "Wood Grain"],
     "hero": False, "problem": False, "weight": 300},
]

# Discount codes
DISCOUNT_CODES = [
    {"code": "WELCOME10", "amount": "10.00", "type": "percentage"},
    {"code": "SUMMER20", "amount": "20.00", "type": "percentage"},
    {"code": "FLAT15", "amount": "15.00", "type": "fixed_amount"},
    {"code": "VIP25", "amount": "25.00", "type": "percentage"},
]

# Hero product weights for order selection (hero products are ordered more frequently)
HERO_WEIGHT = 4.0
NORMAL_WEIGHT = 1.0
PROBLEM_WEIGHT = 1.5  # Slightly above normal (popular but problematic)


def generate_products(start_date: date) -> tuple[list[dict], list[dict]]:
    """Generate products and product_variants tables. Returns (products, variants)."""
    products = []
    variants = []

    for catalog_item in PRODUCT_CATALOG:
        product_id = next_id()
        created_at = random_datetime_on_day(start_date - timedelta(days=random.randint(30, 180)))
        handle = catalog_item["title"].lower().replace(" ", "-").replace("'", "")

        product_variants = []
        for i, variant_name in enumerate(catalog_item["variants"]):
            variant_id = next_id()
            # Slight price variation for size/type
            price_adj = random.uniform(-0.00, 10.00) if "Large" in variant_name or "XL" in variant_name or "A1" in variant_name else 0
            variant_price = round_money(catalog_item["base_price"] + price_adj)

            parts = variant_name.split("/")
            option1 = parts[0] if len(parts) >= 1 else variant_name
            option2 = parts[1] if len(parts) >= 2 else None

            sku_base = catalog_item["title"][:3].upper()
            sku_variant = variant_name.replace("/", "-").replace(" ", "")[:8].upper()
            sku = f"{sku_base}-{sku_variant}"

            variant_row = {
                "id": variant_id,
                "product_id": product_id,
                "title": variant_name,
                "price": str(variant_price),
                "compare_at_price": str(round_money(variant_price * 1.3)) if random.random() < 0.3 else None,
                "sku": sku,
                "barcode": str(random.randint(1000000000000, 9999999999999)),
                "position": i + 1,
                "option1": option1,
                "option2": option2,
                "option3": None,
                "grams": catalog_item["weight"],
                "weight": catalog_item["weight"],
                "weight_unit": "g",
                "taxable": True,
                "tax_code": None,
                "inventory_item_id": next_id(),
                "inventory_quantity": random.randint(10, 500),
                "old_inventory_quantity": random.randint(10, 500),
                "inventory_policy": "deny",
                "requires_shipping": True,
                "image_id": None,
                "image_src": None,
                "available_for_sale": True,
                "display_name": f"{catalog_item['title']} - {variant_name}",
                "admin_graphql_api_id": f"gid://shopify/ProductVariant/{variant_id}",
                "created_at": to_iso(created_at),
                "updated_at": to_iso(created_at + timedelta(days=random.randint(0, 30))),
                "shop_url": SHOP_URL,
                "_airbyte_raw_id": generate_uuid(),
                "_airbyte_extracted_at": to_iso(datetime.now(timezone.utc)),
                "_airbyte_meta": airbyte_meta(),
            }
            variants.append(variant_row)
            product_variants.append(variant_row)

        # Build embedded variants list for product row (subset of fields)
        embedded_variants = []
        for v in product_variants:
            embedded_variants.append({
                "id": v["id"],
                "product_id": product_id,
                "title": v["title"],
                "price": v["price"],
                "sku": v["sku"],
                "position": v["position"],
                "option1": v["option1"],
                "option2": v["option2"],
                "option3": v["option3"],
                "grams": v["grams"],
                "weight": v["weight"],
                "weight_unit": v["weight_unit"],
                "inventory_quantity": v["inventory_quantity"],
                "inventory_policy": v["inventory_policy"],
                "barcode": v["barcode"],
                "requires_shipping": v["requires_shipping"],
                "taxable": v["taxable"],
            })

        products.append({
            "id": product_id,
            "title": catalog_item["title"],
            "body_html": f"<p>Premium quality {catalog_item['title'].lower()} from {catalog_item['vendor']}.</p>",
            "vendor": catalog_item["vendor"],
            "product_type": catalog_item["type"],
            "handle": handle,
            "status": "active",
            "tags": f"{catalog_item['type'].lower()}, {catalog_item['vendor'].lower().replace(' ', '-')}",
            "template_suffix": None,
            "published_at": to_iso(created_at),
            "published_scope": "global",
            "created_at": to_iso(created_at),
            "updated_at": to_iso(created_at + timedelta(days=random.randint(0, 30))),
            "shop_url": SHOP_URL,
            "admin_graphql_api_id": f"gid://shopify/Product/{product_id}",
            "variants": embedded_variants,
            "options": [
                {"id": next_id(), "product_id": product_id, "name": "Colour" if "/" in catalog_item["variants"][0] else "Option", "position": 1}
            ],
            "image": None,
            "images": [],
            "total_inventory": sum(v["inventory_quantity"] for v in product_variants),
            "total_variants": len(product_variants),
            "_airbyte_raw_id": generate_uuid(),
            "_airbyte_extracted_at": to_iso(datetime.now(timezone.utc)),
            "_airbyte_meta": airbyte_meta(),
            # Metadata for generation (not stored in DB)
            "_meta_hero": catalog_item["hero"],
            "_meta_problem": catalog_item["problem"],
            "_meta_base_price": catalog_item["base_price"],
        })

    return products, variants


def generate_customers(num_customers: int, start_date: date) -> list[dict]:
    """Generate customer records."""
    customers = []
    for _ in range(num_customers):
        customer_id = next_id()
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@{random.choice(['gmail.com', 'outlook.com', 'yahoo.com.au', 'hotmail.com'])}"
        created_at = random_datetime_on_day(
            start_date - timedelta(days=random.randint(0, 365))
        )
        address = fake_australian_address()
        address["id"] = next_id()
        address["customer_id"] = customer_id
        address["default"] = True

        customers.append({
            "id": customer_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone": fake.phone_number(),
            "state": "enabled",
            "tags": "",
            "currency": CURRENCY,
            "note": None,
            "verified_email": True,
            "tax_exempt": False,
            "tax_exemptions": None,
            "accepts_marketing": random.random() < 0.4,
            "accepts_marketing_updated_at": to_iso(created_at),
            "marketing_opt_in_level": "single_opt_in" if random.random() < 0.4 else None,
            "orders_count": 0,  # Updated after orders generated
            "total_spent": "0.00",  # Updated after orders generated
            "last_order_id": None,  # Updated after orders generated
            "last_order_name": None,  # Updated after orders generated
            "admin_graphql_api_id": f"gid://shopify/Customer/{customer_id}",
            "created_at": to_iso(created_at),
            "updated_at": to_iso(created_at),
            "shop_url": SHOP_URL,
            "default_address": address,
            "addresses": [address],
            "email_marketing_consent": {
                "state": "subscribed" if random.random() < 0.4 else "not_subscribed",
                "opt_in_level": "single_opt_in",
                "consent_updated_at": to_iso(created_at),
            },
            "sms_marketing_consent": None,
            "_airbyte_raw_id": generate_uuid(),
            "_airbyte_extracted_at": to_iso(datetime.now(timezone.utc)),
            "_airbyte_meta": airbyte_meta(),
        })

    return customers


def generate_orders(
    products: list[dict],
    variants: list[dict],
    customers: list[dict],
    start_date: date,
    num_days: int,
) -> tuple[list[dict], list[dict], dict[str, float]]:
    """
    Generate orders and order_refunds.

    Returns: (orders, refunds, daily_revenue_map)
    daily_revenue_map: {date_str: total_revenue} for Meta Ads alignment.
    """
    # Build product lookup
    product_by_id = {p["id"]: p for p in products}
    variants_by_product = {}
    for v in variants:
        variants_by_product.setdefault(v["product_id"], []).append(v)

    # Build product selection weights
    product_weights = []
    for p in products:
        if p.get("_meta_hero"):
            product_weights.append(HERO_WEIGHT)
        elif p.get("_meta_problem"):
            product_weights.append(PROBLEM_WEIGHT)
        else:
            product_weights.append(NORMAL_WEIGHT)

    # Customer selection: some customers buy more than others (power law)
    customer_weights = [1.0] * len(customers)
    # Make ~15% of customers "frequent buyers" with higher weight
    num_frequent = max(1, int(len(customers) * 0.15))
    for i in range(num_frequent):
        customer_weights[i] = 5.0

    # Generate daily volumes
    daily_volumes = daily_volume_curve_aligned(
        start_date=start_date,
        num_days=num_days,
        base_weekday=18.0,
        base_weekend=25.0,
        trend_pct=0.15,
        sale_start_day=45,
        sale_end_day=52,
        sale_multiplier=2.0,
        noise_std=0.12,
    )

    orders = []
    refunds = []
    daily_revenue = {}
    order_number = 1000

    for day_idx in range(num_days):
        current_date = start_date + timedelta(days=day_idx)
        day_str = current_date.isoformat()
        num_orders_today = max(1, int(round(daily_volumes[day_idx])))
        day_revenue = 0.0

        for _ in range(num_orders_today):
            order_id = next_id()
            order_number += 1
            order_dt = random_datetime_on_day(current_date)

            # Pick customer
            customer = random.choices(customers, weights=customer_weights, k=1)[0]

            # Pick 1-4 line items
            num_items = weighted_choice([1, 2, 3, 4], [40, 35, 18, 7])
            selected_products = random.choices(products, weights=product_weights, k=num_items)
            # Deduplicate by product_id
            seen_product_ids = set()
            unique_products = []
            for sp in selected_products:
                if sp["id"] not in seen_product_ids:
                    seen_product_ids.add(sp["id"])
                    unique_products.append(sp)
            selected_products = unique_products if unique_products else [random.choice(products)]

            line_items = []
            subtotal = 0.0
            total_weight = 0

            for li_product in selected_products:
                product_variants_list = variants_by_product.get(li_product["id"], [])
                if not product_variants_list:
                    continue
                variant = random.choice(product_variants_list)
                quantity = weighted_choice([1, 2, 3], [70, 25, 5])
                price = float(variant["price"])
                line_total = round_money(price * quantity)
                subtotal += line_total

                li_id = next_id()
                line_items.append({
                    "id": li_id,
                    "admin_graphql_api_id": f"gid://shopify/LineItem/{li_id}",
                    "fulfillable_quantity": quantity,
                    "fulfillment_service": "manual",
                    "fulfillment_status": None,
                    "gift_card": False,
                    "grams": variant["grams"] * quantity,
                    "name": f"{li_product['title']} - {variant['title']}",
                    "price": str(price),
                    "price_set": money_set(price),
                    "pre_tax_price": str(price),
                    "product_exists": True,
                    "product_id": li_product["id"],
                    "quantity": quantity,
                    "requires_shipping": True,
                    "sku": variant["sku"],
                    "taxable": True,
                    "title": li_product["title"],
                    "total_discount": "0.00",
                    "total_discount_set": money_set(0),
                    "variant_id": variant["id"],
                    "variant_inventory_management": "shopify",
                    "variant_title": variant["title"],
                    "vendor": li_product["vendor"],
                    "tax_lines": [
                        {
                            "channel_liable": False,
                            "price": str(round_money(line_total * 0.10)),
                            "price_set": money_set(round_money(line_total * 0.10)),
                            "rate": 0.10,
                            "title": "GST",
                        }
                    ],
                    "duties": [],
                    "discount_allocations": [],
                    "properties": [],
                })
                total_weight += variant["grams"] * quantity

            if not line_items:
                continue

            # Discount (15% chance)
            discount_amount = 0.0
            discount_codes = []
            discount_applications = []
            if random.random() < 0.15:
                disc = random.choice(DISCOUNT_CODES)
                if disc["type"] == "percentage":
                    discount_amount = round_money(subtotal * float(disc["amount"]) / 100)
                else:
                    discount_amount = min(float(disc["amount"]), subtotal)
                discount_codes.append({
                    "code": disc["code"],
                    "amount": str(round_money(discount_amount)),
                    "type": disc["type"],
                })
                discount_applications.append({
                    "type": "discount_code",
                    "title": disc["code"],
                    "description": disc["code"],
                    "value": disc["amount"],
                    "value_type": disc["type"],
                    "allocation_method": "across",
                    "target_selection": "all",
                    "target_type": "line_item",
                })

            # Shipping
            shipping_price = round_money(random.choice([0.0, 0.0, 9.95, 12.95, 14.95]))
            if subtotal > 100:
                shipping_price = 0.0  # Free shipping over $100

            # Tax (GST 10% on subtotal after discount)
            taxable_amount = subtotal - discount_amount
            total_tax = round_money(taxable_amount * 0.10)

            total_price = round_money(subtotal - discount_amount + shipping_price + total_tax)
            day_revenue += total_price

            # Financial status
            financial_status = "paid"

            # Fulfillment status
            if day_idx < num_days - 3:
                fulfillment_status = random.choice(["fulfilled", "fulfilled", "fulfilled", "partial", None])
            else:
                fulfillment_status = random.choice([None, "partial"])

            # Customer embed
            customer_embed = {
                "id": customer["id"],
                "email": customer["email"],
                "first_name": customer["first_name"],
                "last_name": customer["last_name"],
                "orders_count": customer["orders_count"],
                "state": customer["state"],
                "total_spent": customer["total_spent"],
            }

            address = customer["default_address"].copy()

            order_row = {
                "id": order_id,
                "admin_graphql_api_id": f"gid://shopify/Order/{order_id}",
                "app_id": 580111,
                "browser_ip": fake.ipv4(),
                "buyer_accepts_marketing": customer["accepts_marketing"],
                "cancel_reason": None,
                "cancelled_at": None,
                "cart_token": generate_uuid(),
                "checkout_id": next_id(),
                "checkout_token": generate_uuid(),
                "closed_at": to_iso(order_dt + timedelta(days=random.randint(1, 7))) if fulfillment_status == "fulfilled" else None,
                "confirmed": True,
                "confirmation_number": f"C{order_number}",
                "contact_email": customer["email"],
                "created_at": to_iso(order_dt),
                "currency": CURRENCY,
                "current_subtotal_price": str(round_money(subtotal - discount_amount)),
                "current_subtotal_price_set": money_set(round_money(subtotal - discount_amount)),
                "current_total_discounts": str(round_money(discount_amount)),
                "current_total_discounts_set": money_set(round_money(discount_amount)),
                "current_total_price": str(round_money(total_price)),
                "current_total_price_set": money_set(round_money(total_price)),
                "current_total_tax": str(total_tax),
                "current_total_tax_set": money_set(total_tax),
                "customer_locale": "en-AU",
                "discount_applications": discount_applications,
                "discount_codes": discount_codes,
                "email": customer["email"],
                "financial_status": financial_status,
                "fulfillment_status": fulfillment_status,
                "landing_site": "/",
                "name": f"#{order_number}",
                "note": None,
                "note_attributes": [],
                "number": order_number - 1000,
                "order_number": order_number,
                "order_status_url": f"{SHOP_URL}/orders/{order_id}",
                "payment_gateway_names": ["shopify_payments"],
                "phone": customer.get("phone"),
                "presentment_currency": CURRENCY,
                "processed_at": to_iso(order_dt),
                "source_name": "web",
                "subtotal_price": str(round_money(subtotal - discount_amount)),
                "subtotal_price_set": money_set(round_money(subtotal - discount_amount)),
                "tags": "",
                "tax_exempt": False,
                "tax_lines": [
                    {
                        "channel_liable": False,
                        "price": str(total_tax),
                        "price_set": money_set(total_tax),
                        "rate": 0.10,
                        "title": "GST",
                    }
                ],
                "taxes_included": False,
                "test": False,
                "token": generate_uuid(),
                "total_discounts": str(round_money(discount_amount)),
                "total_discounts_set": money_set(round_money(discount_amount)),
                "total_line_items_price": str(round_money(subtotal)),
                "total_line_items_price_set": money_set(round_money(subtotal)),
                "total_outstanding": "0.00",
                "total_price": str(round_money(total_price)),
                "total_price_set": money_set(round_money(total_price)),
                "total_price_usd": None,
                "total_shipping_price_set": money_set(shipping_price),
                "total_tax": str(total_tax),
                "total_tax_set": money_set(total_tax),
                "total_tip_received": "0.00",
                "total_weight": total_weight,
                "updated_at": to_iso(order_dt + timedelta(hours=random.randint(1, 48))),
                "customer": customer_embed,
                "billing_address": address,
                "shipping_address": address,
                "shipping_lines": [
                    {
                        "id": next_id(),
                        "title": "Standard Shipping" if shipping_price > 0 else "Free Shipping",
                        "price": str(shipping_price),
                        "price_set": money_set(shipping_price),
                        "code": "standard",
                        "source": "shopify",
                    }
                ],
                "line_items": line_items,
                "fulfillments": [],
                "refunds": [],
                "shop_url": SHOP_URL,
                "_airbyte_raw_id": generate_uuid(),
                "_airbyte_extracted_at": to_iso(datetime.now(timezone.utc)),
                "_airbyte_meta": airbyte_meta(),
                # Internal metadata (not stored)
                "_meta_line_items_raw": line_items,
            }
            orders.append(order_row)

            # Track customer order counts
            customer["orders_count"] += 1
            current_spent = float(customer["total_spent"])
            customer["total_spent"] = str(round_money(current_spent + total_price))
            customer["last_order_id"] = order_id
            customer["last_order_name"] = f"#{order_number}"

        daily_revenue[day_str] = round_money(day_revenue)

    # ── Generate Refunds ──
    # ~8% of orders get refunded, but problem product orders get ~25% refund rate
    problem_product_ids = {p["id"] for p in products if p.get("_meta_problem")}

    for order in orders:
        has_problem_item = any(
            li["product_id"] in problem_product_ids
            for li in order["_meta_line_items_raw"]
        )
        refund_chance = 0.25 if has_problem_item else 0.06

        if random.random() < refund_chance:
            refund_id = next_id()
            order_dt = datetime.fromisoformat(order["created_at"])
            refund_dt = order_dt + timedelta(days=random.randint(2, 14))

            # Pick line items to refund (full or partial)
            refund_line_items_data = []
            is_full_refund = random.random() < 0.4
            items_to_refund = order["_meta_line_items_raw"] if is_full_refund else [random.choice(order["_meta_line_items_raw"])]

            total_refund_amount = 0.0
            total_refund_tax = 0.0

            for li in items_to_refund:
                qty_to_refund = li["quantity"] if is_full_refund else random.randint(1, li["quantity"])
                li_subtotal = round_money(float(li["price"]) * qty_to_refund)
                li_tax = round_money(li_subtotal * 0.10)
                total_refund_amount += li_subtotal
                total_refund_tax += li_tax

                refund_line_items_data.append({
                    "id": next_id(),
                    "line_item_id": li["id"],
                    "quantity": qty_to_refund,
                    "subtotal": round_money(li_subtotal),
                    "total_tax": round_money(li_tax),
                    "restock_type": "return",
                    "location_id": None,
                    "subtotal_set": money_set(li_subtotal),
                    "total_tax_set": money_set(li_tax),
                    "line_item": {
                        "id": li["id"],
                        "title": li["title"],
                        "sku": li["sku"],
                        "price": li["price"],
                        "quantity": li["quantity"],
                        "product_id": li["product_id"],
                        "variant_id": li["variant_id"],
                        "variant_title": li["variant_title"],
                        "vendor": li["vendor"],
                        "name": li["name"],
                    },
                })

            total_refund = round_money(total_refund_amount + total_refund_tax)

            refund_row = {
                "id": refund_id,
                "order_id": order["id"],
                "admin_graphql_api_id": f"gid://shopify/Refund/{refund_id}",
                "created_at": to_iso(refund_dt),
                "processed_at": to_iso(refund_dt),
                "note": "Customer requested refund" if not has_problem_item else "Quality issue reported",
                "restock": True,
                "user_id": 1,
                "duties": None,
                "shop_url": SHOP_URL,
                "return": None,
                "total_duties_set": None,
                "order_adjustments": [
                    {
                        "id": next_id(),
                        "order_id": order["id"],
                        "refund_id": refund_id,
                        "amount": str(-total_refund),
                        "tax_amount": str(-total_refund_tax),
                        "kind": "refund_discrepancy",
                        "reason": "Refund",
                    }
                ],
                "refund_line_items": refund_line_items_data,
                "transactions": [
                    {
                        "id": next_id(),
                        "admin_graphql_api_id": f"gid://shopify/OrderTransaction/{next_id()}",
                        "amount": str(total_refund),
                        "authorization": None,
                        "created_at": to_iso(refund_dt),
                        "currency": CURRENCY,
                        "gateway": "shopify_payments",
                        "kind": "refund",
                        "message": "Refund",
                        "order_id": order["id"],
                        "parent_id": None,
                        "status": "success",
                        "test": False,
                    }
                ],
                "_airbyte_raw_id": generate_uuid(),
                "_airbyte_extracted_at": to_iso(datetime.now(timezone.utc)),
                "_airbyte_meta": airbyte_meta(),
            }
            refunds.append(refund_row)

            # Update order financial status
            if is_full_refund:
                order["financial_status"] = "refunded"
            else:
                order["financial_status"] = "partially_refunded"

    return orders, refunds, daily_revenue
