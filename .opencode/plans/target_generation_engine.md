# Target Generation Engine Implementation Plan

I will implement the target generation engine as a backend-only feature first, exposed via a new API endpoint.

## 1. Data Layer: Metric Series Query
**File:** `src/data/queries.py`

Add a helper function to fetch raw daily time-series data for any metric.
- **Function:** `get_metric_series(conn, tenant_id, table, metric_col, date_col, days=90)`
- **Purpose:** Returns a list of `(date, value)` tuples for the last 90 days.
- **Query:** `SELECT {date_col}, {metric_col} FROM {schema}.{table} WHERE {date_col} >= NOW() - INTERVAL '{days} days' ORDER BY {date_col} ASC`

## 2. Core Logic: Target Engine
**File:** `src/analytics/targets.py` (New File)

Create a `TargetEngine` class that uses `pandas` to implement the user's specific formulas.

**Key Methods:**
- `generate_targets(metrics: list[str]) -> list[dict]`
- `_calculate_target(metric: str, series: pd.Series) -> dict`

**Algorithm Steps (per metric):**
1.  **Data Fetching:** Get 90-day daily series. Reindex to fill missing dates with 0.
2.  **Baselines:** Calculate 7d, 30d, 90d rolling averages.
3.  **Volatility:** `std_dev(30d) / mean(30d)`.
4.  **Trends:** 
    - Short: `(7d - 30d) / 30d`
    - Long: `(30d - 90d) / 90d`
5.  **Benchmark Gap:** `(benchmark - 30d) / 30d` (clamped ±30%).
6.  **Lift Calculation:** `0.25*short + 0.25*long - 0.20*volatility + 0.30*gap`.
    - Clamped to range [-5%, +15%].
7.  **Target:** `30d_baseline * (1 + lift)`.
8.  **Confidence:** Weighted score based on `1-volatility` and trend consistency.

**Supported Metrics:**
- **AOV:** `avg_order_value` from `mart_daily_blended_performance`
- **ROAS:** `blended_roas` from `mart_daily_blended_performance`
- **CAC:** `blended_cac` from `mart_daily_blended_performance`
- **Repeat Rate:** `returning_customer_pct` from `mart_customer_cohorts`

## 3. API Layer: Endpoint
**File:** `src/api/analytics.py`

Add a new endpoint to expose the engine.
- **Route:** `GET /analytics/targets`
- **Response:** JSON list of target objects.
```json
[
  {
    "metric": "AOV",
    "current_value": 82.0,
    "target_value": 87.74,
    "lift_pct": 7.0,
    "confidence": 0.85,
    "components": { ... }
  }
]
```

## 4. Verification
- I will verify the implementation by calling the API endpoint and checking the JSON output against the expected logic.
