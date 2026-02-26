"""Generate Meta Ads seed data."""

import random
from datetime import date, datetime, timedelta, timezone

import numpy as np

from scripts.generators.helpers import (
    action_stats_list,
    jitter,
    next_id,
    round_money,
    to_iso,
)

ACCOUNT_ID = "act_1234567890"
ACCOUNT_NAME = "Test Store AU"
ACCOUNT_CURRENCY = "AUD"


# ──────────────────────────────────────────────
# Campaign Definitions (with performance profiles)
# ──────────────────────────────────────────────

CAMPAIGN_DEFS = [
    {
        "name": "Prospecting - Conversions",
        "objective": "OUTCOME_SALES",
        "status": "ACTIVE",
        "daily_budget": 400_00,  # cents
        "num_ad_sets": 3,
        "num_ads_per_set": 3,
        "profile": {
            "cpm_range": (12.0, 18.0),
            "ctr_range": (1.0, 2.0),
            "conversion_rate": (0.020, 0.035),  # % of clicks -> purchase
            "avg_order_value": (65.0, 95.0),
            "roas_target": (2.0, 3.5),
        },
        "active_from_day": 0,
        "active_to_day": None,  # Always active
    },
    {
        "name": "Retargeting - DPA",
        "objective": "OUTCOME_SALES",
        "status": "ACTIVE",
        "daily_budget": 200_00,
        "num_ad_sets": 2,
        "num_ads_per_set": 3,
        "profile": {
            "cpm_range": (18.0, 28.0),
            "ctr_range": (2.0, 3.5),
            "conversion_rate": (0.050, 0.080),  # High conversion
            "avg_order_value": (75.0, 120.0),
            "roas_target": (4.0, 7.0),  # Best performer
        },
        "active_from_day": 0,
        "active_to_day": None,
    },
    {
        "name": "Brand Awareness - Reach",
        "objective": "OUTCOME_AWARENESS",
        "status": "ACTIVE",
        "daily_budget": 100_00,
        "num_ad_sets": 2,
        "num_ads_per_set": 2,
        "profile": {
            "cpm_range": (6.0, 10.0),
            "ctr_range": (0.3, 0.8),
            "conversion_rate": (0.002, 0.005),  # Very low direct conversions
            "avg_order_value": (50.0, 70.0),
            "roas_target": (0.2, 0.5),
        },
        "active_from_day": 0,
        "active_to_day": None,
    },
    {
        "name": "Summer Sale - Conversions",
        "objective": "OUTCOME_SALES",
        "status": "PAUSED",
        "daily_budget": 500_00,
        "num_ad_sets": 3,
        "num_ads_per_set": 3,
        "profile": {
            "cpm_range": (10.0, 16.0),
            "ctr_range": (1.5, 2.8),
            "conversion_rate": (0.035, 0.060),
            "avg_order_value": (55.0, 85.0),
            "roas_target": (3.0, 5.0),
        },
        "active_from_day": 40,
        "active_to_day": 55,  # Only active during sale period
    },
    {
        "name": "Lookalike - Traffic",
        "objective": "OUTCOME_TRAFFIC",
        "status": "ACTIVE",
        "daily_budget": 250_00,
        "num_ad_sets": 3,
        "num_ads_per_set": 2,
        "profile": {
            "cpm_range": (8.0, 14.0),
            "ctr_range": (0.8, 1.5),
            "conversion_rate": (0.008, 0.015),  # Poor conversion
            "avg_order_value": (45.0, 65.0),
            "roas_target": (0.7, 1.3),  # Underperformer — agent should flag
        },
        "active_from_day": 0,
        "active_to_day": None,
    },
    {
        "name": "Holiday Push - Conversions",
        "objective": "OUTCOME_SALES",
        "status": "ACTIVE",
        "daily_budget": 350_00,
        "num_ad_sets": 3,
        "num_ads_per_set": 3,
        "profile": {
            "cpm_range": (14.0, 22.0),
            "ctr_range": (1.2, 2.2),
            "conversion_rate": (0.030, 0.050),
            "avg_order_value": (70.0, 110.0),
            "roas_target": (2.5, 4.5),
        },
        "active_from_day": 75,  # Recent — ramping up
        "active_to_day": None,
    },
]

AD_SET_NAMES = [
    "Broad - 25-44 Interests",
    "Narrow - Purchase Intent",
    "Retargeting - 7d Viewers",
    "Retargeting - 30d ATC",
    "LAL 1% Purchasers",
    "LAL 3% Website Visitors",
    "Interest - Home & Garden",
    "Interest - Fashion & Apparel",
    "Males 25-34",
    "Females 25-44",
    "All Genders 18-65",
    "Custom Audience - Email List",
    "Engaged Shoppers",
    "High Value Lookalike",
    "Top of Funnel - Video Viewers",
    "Cart Abandoners - 14d",
    "New Visitor Prospecting",
    "Value Based LAL",
    "Broad Auto Targeting",
    "Category Specific Interest",
]

AD_NAMES = [
    "Carousel - Best Sellers v2",
    "Video - UGC Testimonial",
    "Static - Hero Product Lifestyle",
    "Carousel - New Arrivals",
    "Video - Brand Story 30s",
    "Static - Discount Offer",
    "DPA - Retargeting Feed",
    "Video - Product Demo",
    "Static - Social Proof",
    "Carousel - Gift Guide",
    "Video - Behind the Scenes",
    "Static - Free Shipping Banner",
    "Collection - Summer Essentials",
    "Video - Customer Review",
    "Static - Urgency CTA",
    "Carousel - Category Highlight",
    "Video - Unboxing Experience",
    "Static - Minimal Product Shot",
    "DPA - Cross-sell Feed",
    "Video - Lifestyle Montage",
    "Static - Bold Typography",
    "Carousel - Bestseller Bundle",
    "Video - Quick Tips",
    "Static - Before After",
]

TARGETING_TEMPLATE = {
    "geo_locations": {
        "countries": ["AU"],
        "location_types": ["home", "recent"],
    },
    "age_min": 25,
    "age_max": 55,
    "publisher_platforms": ["facebook", "instagram"],
    "facebook_positions": ["feed", "instant_article", "marketplace"],
    "instagram_positions": ["stream", "story", "explore"],
}


def generate_campaigns(start_date: date) -> list[dict]:
    """Generate Meta Ads campaign records."""
    campaigns = []
    for cdef in CAMPAIGN_DEFS:
        campaign_id = str(next_id())
        created = datetime(
            start_date.year, start_date.month, start_date.day,
            10, 0, 0, tzinfo=timezone.utc
        ) - timedelta(days=random.randint(5, 30))

        campaigns.append({
            "id": campaign_id,
            "account_id": ACCOUNT_ID,
            "name": cdef["name"],
            "status": cdef["status"],
            "effective_status": cdef["status"],
            "configured_status": cdef["status"],
            "objective": cdef["objective"],
            "buying_type": "AUCTION",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "daily_budget": str(cdef["daily_budget"]),
            "lifetime_budget": "0",
            "budget_remaining": str(cdef["daily_budget"] * 30),
            "spend_cap": None,
            "start_time": to_iso(created),
            "stop_time": None,
            "created_time": to_iso(created),
            "updated_time": to_iso(created + timedelta(days=random.randint(1, 60))),
            "special_ad_category": "NONE",
            "special_ad_category_country": [],
            "adlabels": [],
            "issues_info": [],
            # Internal metadata
            "_cdef": cdef,
        })

    return campaigns


def generate_ad_sets(campaigns: list[dict], start_date: date) -> list[dict]:
    """Generate ad set records for each campaign."""
    ad_sets = []
    ad_set_name_pool = list(AD_SET_NAMES)
    random.shuffle(ad_set_name_pool)
    name_idx = 0

    for campaign in campaigns:
        cdef = campaign["_cdef"]
        num_sets = cdef["num_ad_sets"]

        for i in range(num_sets):
            ad_set_id = str(next_id())
            set_budget = cdef["daily_budget"] // num_sets
            created = datetime.fromisoformat(campaign["created_time"]) + timedelta(hours=random.randint(1, 48))

            name = ad_set_name_pool[name_idx % len(ad_set_name_pool)]
            name_idx += 1

            targeting = TARGETING_TEMPLATE.copy()
            targeting["age_min"] = random.choice([18, 21, 25, 30])
            targeting["age_max"] = random.choice([44, 55, 65])

            ad_sets.append({
                "id": ad_set_id,
                "account_id": ACCOUNT_ID,
                "campaign_id": campaign["id"],
                "name": name,
                "effective_status": campaign["effective_status"],
                "daily_budget": str(set_budget),
                "lifetime_budget": "0",
                "budget_remaining": str(set_budget * 30),
                "bid_strategy": campaign.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
                "bid_amount": None,
                "bid_constraints": None,
                "bid_info": None,
                "start_time": campaign["start_time"],
                "end_time": None,
                "created_time": to_iso(created),
                "updated_time": to_iso(created + timedelta(days=random.randint(1, 30))),
                "targeting": targeting,
                "promoted_object": {
                    "pixel_id": "1234567890",
                    "custom_event_type": "PURCHASE",
                },
                "adlabels": [],
                "learning_stage_info": {
                    "status": "SUCCESS",
                },
                # Internal
                "_campaign_name": campaign["name"],
                "_cdef": cdef,
            })

    return ad_sets


def generate_ads(ad_sets: list[dict]) -> list[dict]:
    """Generate ad records for each ad set."""
    ads = []
    ad_name_pool = list(AD_NAMES)
    random.shuffle(ad_name_pool)
    name_idx = 0

    for ad_set in ad_sets:
        cdef = ad_set["_cdef"]
        num_ads = cdef["num_ads_per_set"]

        for i in range(num_ads):
            ad_id = str(next_id())
            created = datetime.fromisoformat(ad_set["created_time"]) + timedelta(hours=random.randint(1, 24))

            name = ad_name_pool[name_idx % len(ad_name_pool)]
            name_idx += 1

            # Mark one specific ad as a "creative winner" in Prospecting
            is_winner = (
                ad_set["_campaign_name"] == "Prospecting - Conversions"
                and i == 0
                and ad_set == [s for s in [ad_set]][0]  # First ad in the set
            )

            ads.append({
                "id": ad_id,
                "account_id": ACCOUNT_ID,
                "campaign_id": ad_set["campaign_id"],
                "adset_id": ad_set["id"],
                "name": name,
                "status": ad_set["effective_status"],
                "effective_status": ad_set["effective_status"],
                "bid_type": "ABSOLUTE_OCPM",
                "bid_amount": None,
                "bid_info": None,
                "creative": {"creative_id": str(next_id()), "id": str(next_id())},
                "created_time": to_iso(created),
                "updated_time": to_iso(created + timedelta(days=random.randint(1, 20))),
                "last_updated_by_app_id": None,
                "source_ad_id": None,
                "targeting": None,
                "tracking_specs": [
                    {"action.type": ["offsite_conversion"], "fb_pixel": ["1234567890"]}
                ],
                "conversion_specs": [
                    {"action.type": ["offsite_conversion"], "fb_pixel": ["1234567890"]}
                ],
                "adlabels": [],
                "recommendations": [],
                # Internal
                "_campaign_name": ad_set["_campaign_name"],
                "_cdef": cdef,
                "_is_winner": is_winner,
                "_ad_set_id": ad_set["id"],
            })

    return ads


def generate_ads_insights(
    ads: list[dict],
    start_date: date,
    num_days: int,
    daily_shopify_revenue: dict[str, float],
) -> list[dict]:
    """
    Generate daily ads_insights rows for each active ad.

    Aligns total Meta purchase revenue to ~65% of Shopify daily revenue.
    """
    insights = []

    # Group ads by campaign for budget/performance allocation
    ads_by_campaign = {}
    for ad in ads:
        ads_by_campaign.setdefault(ad["_campaign_name"], []).append(ad)

    # Identify the creative winner ad (first ad in first Prospecting ad set)
    prospecting_ads = ads_by_campaign.get("Prospecting - Conversions", [])
    winner_ad_id = None
    if prospecting_ads:
        # Find first ad set's first ad
        first_set_id = prospecting_ads[0]["_ad_set_id"]
        for ad in prospecting_ads:
            if ad["_ad_set_id"] == first_set_id:
                winner_ad_id = ad["id"]
                break

    for day_idx in range(num_days):
        current_date = start_date + timedelta(days=day_idx)
        date_str = current_date.isoformat()

        # Target Meta revenue = ~65% of Shopify daily revenue
        shopify_rev = daily_shopify_revenue.get(date_str, 0)
        target_meta_revenue = shopify_rev * random.uniform(0.58, 0.72)

        # Collect all active ads for today with their raw spend proportions
        active_ads_today = []
        total_budget_weight = 0

        for ad in ads:
            cdef = ad["_cdef"]
            from_day = cdef.get("active_from_day", 0)
            to_day = cdef.get("active_to_day")

            if day_idx < from_day:
                continue
            if to_day is not None and day_idx > to_day:
                continue

            # Budget weight per ad = campaign daily budget / (num_ad_sets * num_ads_per_set)
            budget_per_ad = cdef["daily_budget"] / (cdef["num_ad_sets"] * cdef["num_ads_per_set"]) / 100  # Convert cents to dollars
            active_ads_today.append((ad, budget_per_ad))
            total_budget_weight += budget_per_ad

        if not active_ads_today or total_budget_weight == 0:
            continue

        # First pass: calculate raw metrics for each ad
        day_insights_raw = []
        total_raw_revenue = 0

        for ad, budget_per_ad in active_ads_today:
            cdef = ad["_cdef"]
            profile = cdef["profile"]

            # Spend with daily variance
            spend = jitter(budget_per_ad, 0.20)

            # Creative winner boost: last 7 days, one ad performs 3x better
            is_recent_winner = (
                ad["id"] == winner_ad_id
                and day_idx >= num_days - 10
            )

            # CPM
            cpm = random.uniform(*profile["cpm_range"])
            impressions = max(1, int(spend / cpm * 1000))

            # CTR
            ctr = random.uniform(*profile["ctr_range"])
            if is_recent_winner:
                ctr *= 2.0  # Winner has much higher CTR
            clicks = max(0, int(impressions * ctr / 100))

            # CPC
            cpc = round_money(spend / clicks) if clicks > 0 else 0

            # Reach / Frequency
            freq_factor = random.uniform(0.60, 0.85)
            reach = max(1, int(impressions * freq_factor))
            frequency = round(impressions / reach, 2) if reach > 0 else 1.0

            # Conversions
            conv_rate = random.uniform(*profile["conversion_rate"])
            if is_recent_winner:
                conv_rate *= 2.5  # Winner converts much better
            purchases = max(0, int(clicks * conv_rate))

            # Revenue per purchase
            aov = random.uniform(*profile["avg_order_value"])
            purchase_revenue = round_money(purchases * aov)
            total_raw_revenue += purchase_revenue

            # Link clicks (slightly less than total clicks)
            link_clicks = max(0, int(clicks * random.uniform(0.85, 0.95)))
            landing_page_views = max(0, int(link_clicks * random.uniform(0.70, 0.90)))
            add_to_carts = max(0, int(landing_page_views * random.uniform(0.08, 0.20)))

            day_insights_raw.append({
                "ad": ad,
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "cpc": cpc,
                "cpm": cpm,
                "ctr": ctr,
                "reach": reach,
                "frequency": frequency,
                "purchases": purchases,
                "purchase_revenue": purchase_revenue,
                "link_clicks": link_clicks,
                "landing_page_views": landing_page_views,
                "add_to_carts": add_to_carts,
            })

        # Second pass: scale revenue to align with Shopify (~65%)
        if total_raw_revenue > 0 and target_meta_revenue > 0:
            scale_factor = target_meta_revenue / total_raw_revenue
        else:
            scale_factor = 1.0

        for raw in day_insights_raw:
            ad = raw["ad"]
            spend = round_money(raw["spend"])
            purchases = raw["purchases"]
            purchase_revenue = round_money(raw["purchase_revenue"] * scale_factor)

            # Recalculate derived metrics
            roas = round(purchase_revenue / spend, 2) if spend > 0 else 0
            cpa = round_money(spend / purchases) if purchases > 0 else 0

            # Quality/ranking signals
            rankings = ["ABOVE_AVERAGE_35", "AVERAGE", "BELOW_AVERAGE_35"]
            ranking_weights = [30, 50, 20]

            # Build actions JSONB arrays
            actions = action_stats_list({
                "link_click": raw["link_clicks"],
                "landing_page_view": raw["landing_page_views"],
                "add_to_cart": raw["add_to_carts"],
                "purchase": purchases,
                "page_engagement": raw["clicks"] + random.randint(0, 10),
                "post_engagement": random.randint(0, max(1, raw["clicks"] // 2)),
            })

            action_values = action_stats_list({
                "purchase": round_money(purchase_revenue),
                "add_to_cart": round_money(raw["add_to_carts"] * random.uniform(40, 90)),
            })

            cost_per_action = action_stats_list({
                "link_click": round_money(spend / raw["link_clicks"]) if raw["link_clicks"] > 0 else 0,
                "landing_page_view": round_money(spend / raw["landing_page_views"]) if raw["landing_page_views"] > 0 else 0,
                "purchase": cpa,
            })

            purchase_roas_val = action_stats_list({
                "omni_purchase": roas,
            })

            insight_row = {
                "date_start": date_str,
                "date_stop": date_str,
                "account_id": ACCOUNT_ID,
                "account_name": ACCOUNT_NAME,
                "account_currency": ACCOUNT_CURRENCY,
                "campaign_id": ad["campaign_id"],
                "campaign_name": ad["_campaign_name"],
                "adset_id": ad["adset_id"],
                "adset_name": ad["name"],  # We'll use ad set name from the ad set
                "ad_id": ad["id"],
                "ad_name": ad["name"],
                "objective": ad["_cdef"]["objective"],
                "optimization_goal": "OFFSITE_CONVERSIONS",
                "buying_type": "AUCTION",
                "attribution_setting": "7d_click_1d_view",
                "impressions": raw["impressions"],
                "clicks": raw["clicks"],
                "spend": str(spend),
                "reach": raw["reach"],
                "frequency": raw["frequency"],
                "cpc": str(round_money(raw["cpc"])),
                "cpm": str(round_money(raw["cpm"])),
                "cpp": str(round_money(spend / raw["reach"] * 1000)) if raw["reach"] > 0 else "0",
                "ctr": str(round(raw["ctr"], 2)),
                "unique_clicks": max(0, raw["clicks"] - random.randint(0, max(1, raw["clicks"] // 10))),
                "unique_ctr": str(round(raw["ctr"] * 0.9, 2)),
                "cost_per_unique_click": str(round_money(spend / max(1, raw["clicks"]))),
                "inline_link_clicks": raw["link_clicks"],
                "inline_link_click_ctr": str(round(raw["link_clicks"] / max(1, raw["impressions"]) * 100, 2)),
                "inline_post_engagement": raw["clicks"] + random.randint(0, 20),
                "cost_per_inline_link_click": str(round_money(spend / max(1, raw["link_clicks"]))),
                "cost_per_inline_post_engagement": str(round_money(spend / max(1, raw["clicks"] + 10))),
                "social_spend": str(round_money(spend * random.uniform(0.0, 0.1))),
                "quality_ranking": random.choices(rankings, weights=ranking_weights, k=1)[0],
                "engagement_rate_ranking": random.choices(rankings, weights=ranking_weights, k=1)[0],
                "conversion_rate_ranking": random.choices(rankings, weights=ranking_weights, k=1)[0],
                "actions": actions,
                "action_values": action_values,
                "conversions": action_stats_list({"purchase": purchases}),
                "conversion_values": action_stats_list({"purchase": round_money(purchase_revenue)}),
                "cost_per_action_type": cost_per_action,
                "cost_per_conversion": action_stats_list({"purchase": cpa}),
                "purchase_roas": purchase_roas_val,
                "website_purchase_roas": purchase_roas_val,
                "outbound_clicks": action_stats_list({"outbound_click": raw["link_clicks"]}),
                "created_time": date_str,
                "updated_time": date_str,
            }
            insights.append(insight_row)

    return insights
