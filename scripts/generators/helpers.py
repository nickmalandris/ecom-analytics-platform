"""Shared utilities for seed data generation."""

import json
import random
from datetime import date, datetime, timedelta, timezone

import numpy as np
from faker import Faker

fake = Faker("en_AU")

# Deterministic seed for reproducible data
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
Faker.seed(RANDOM_SEED)

# Global ID counter
_id_counter = 10000


def next_id() -> int:
    """Generate a sequential ID starting from 10000."""
    global _id_counter
    _id_counter += 1
    return _id_counter


def reset_id_counter(start: int = 10000) -> None:
    """Reset the ID counter (useful between generator runs)."""
    global _id_counter
    _id_counter = start


def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def to_iso(dt: datetime | date) -> str:
    """Convert a datetime/date to ISO 8601 string."""
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat()


def random_datetime_on_day(d: date) -> datetime:
    """Return a random datetime during business-ish hours on a given date."""
    hour = random.choices(
        range(24),
        weights=[1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 9, 9, 8, 8, 7, 7, 6, 6, 5, 5, 4, 3, 2, 1],
        k=1,
    )[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return datetime(d.year, d.month, d.day, hour, minute, second, tzinfo=timezone.utc)


def money_set(amount: float, currency: str = "AUD") -> dict:
    """Build Shopify's money_set JSONB structure."""
    amt_str = f"{amount:.2f}"
    return {
        "shop_money": {"amount": amt_str, "currency_code": currency},
        "presentment_money": {"amount": amt_str, "currency_code": currency},
    }


def action_stat(action_type: str, value: float | int) -> dict:
    """Build a Meta Ads action stats object."""
    return {"action_type": action_type, "value": str(value)}


def action_stats_list(stats: dict[str, float | int]) -> list[dict]:
    """Build a list of Meta Ads action stats from a dict of {action_type: value}."""
    return [action_stat(k, v) for k, v in stats.items()]


def daily_volume_curve(
    num_days: int,
    base_weekday: float = 18.0,
    base_weekend: float = 25.0,
    trend_pct: float = 0.15,
    sale_start_day: int = 45,
    sale_end_day: int = 52,
    sale_multiplier: float = 2.0,
    noise_std: float = 0.15,
) -> list[float]:
    """
    Generate a daily volume multiplier curve.

    Returns a list of floats (one per day) representing the expected order count.
    Includes:
    - Weekday/weekend pattern
    - Linear upward trend
    - Sale spike period
    - Random noise
    """
    volumes = []
    for day_idx in range(num_days):
        # Base volume: weekday vs weekend
        # day_idx 0 is the start_date; we use .weekday() later in the caller,
        # but here we just provide the base pattern
        weekday = (day_idx % 7)  # 0=Mon if start is Mon, etc.
        base = base_weekend if weekday >= 5 else base_weekday

        # Linear trend: +trend_pct over the full period
        trend = 1.0 + (trend_pct * day_idx / num_days)

        # Sale spike
        sale = sale_multiplier if sale_start_day <= day_idx <= sale_end_day else 1.0

        # Random noise
        noise = max(0.5, np.random.normal(1.0, noise_std))

        volumes.append(base * trend * sale * noise)

    return volumes


def daily_volume_curve_aligned(
    start_date: date,
    num_days: int,
    base_weekday: float = 18.0,
    base_weekend: float = 25.0,
    trend_pct: float = 0.15,
    sale_start_day: int = 45,
    sale_end_day: int = 52,
    sale_multiplier: float = 2.0,
    noise_std: float = 0.15,
) -> list[float]:
    """
    Like daily_volume_curve but aligned to actual day-of-week from start_date.
    """
    volumes = []
    for day_idx in range(num_days):
        current_date = start_date + timedelta(days=day_idx)
        weekday = current_date.weekday()  # 0=Mon, 6=Sun
        base = base_weekend if weekday >= 5 else base_weekday

        trend = 1.0 + (trend_pct * day_idx / num_days)
        sale = sale_multiplier if sale_start_day <= day_idx <= sale_end_day else 1.0
        noise = max(0.5, np.random.normal(1.0, noise_std))

        volumes.append(base * trend * sale * noise)

    return volumes


def fake_australian_address() -> dict:
    """Generate a realistic Australian address matching Shopify's address schema."""
    first_name = fake.first_name()
    last_name = fake.last_name()
    states = {
        "New South Wales": "NSW",
        "Victoria": "VIC",
        "Queensland": "QLD",
        "Western Australia": "WA",
        "South Australia": "SA",
        "Tasmania": "TAS",
    }
    province, province_code = random.choice(list(states.items()))

    return {
        "first_name": first_name,
        "last_name": last_name,
        "address1": fake.street_address(),
        "address2": random.choice(["", "", "", f"Unit {random.randint(1, 50)}"]),
        "city": fake.city(),
        "province": province,
        "province_code": province_code,
        "country": "Australia",
        "country_code": "AU",
        "zip": fake.postcode(),
        "phone": fake.phone_number(),
        "company": random.choice(["", "", "", fake.company()]),
        "name": f"{first_name} {last_name}",
        "latitude": round(random.uniform(-38.0, -25.0), 6),
        "longitude": round(random.uniform(115.0, 153.0), 6),
    }


def weighted_choice(options: list, weights: list):
    """Pick a single item from options using weights."""
    return random.choices(options, weights=weights, k=1)[0]


def jitter(value: float, pct: float = 0.1) -> float:
    """Add random jitter to a value (±pct%)."""
    return value * random.uniform(1.0 - pct, 1.0 + pct)


def round_money(value: float) -> float:
    """Round to 2 decimal places for money."""
    return round(value, 2)


def json_dumps(obj) -> str:
    """Serialize to JSON string for JSONB columns."""
    return json.dumps(obj)
