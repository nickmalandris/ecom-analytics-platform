import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from pydantic import BaseModel

from src.data.queries import get_metric_series

logger = logging.getLogger(__name__)

# Metric configuration
METRICS = {
    "AOV": {
        "table": "mart_daily_blended_performance",
        "metric_expr": "MAX(avg_order_value)",  # Already aggregated daily
        "date_col": "report_date",
        "benchmark": 90.0,
        "format": "currency",
    },
    "CVR": {
        "table": "mart_daily_ad_performance",  # Using ad performance for CVR proxy
        "metric_expr": "CASE WHEN SUM(clicks) = 0 THEN 0 ELSE CAST(SUM(purchases) AS FLOAT) / SUM(clicks) * 100 END",
        "date_col": "insight_date",
        "benchmark": 2.8, # 2.8%
        "format": "percentage",
    },
    "ROAS": {
        "table": "mart_daily_blended_performance",
        "metric_expr": "MAX(blended_roas)", # Already aggregated daily
        "date_col": "report_date",
        "benchmark": 3.5,
        "format": "decimal",
    },
    "CAC": {
        "table": "mart_daily_blended_performance",
        "metric_expr": "MAX(blended_cac)", # Already aggregated daily
        "date_col": "report_date",
        "benchmark": 45.0,
        "format": "currency",
    },
    "RPR": {
        "table": "mart_customer_cohorts",
        "metric_expr": "MAX(returning_customer_pct)",  # Already aggregated daily
        "date_col": "order_date",
        "benchmark": 25.0,
        "format": "percentage",
    },
    "LTV": {
        "table": "mart_customer_ltv",
        "metric_expr": "MAX(avg_ltv)",  # Already aggregated daily
        "date_col": "order_date",
        "benchmark": 150.0,  # AUD
        "format": "currency",
    },
    "Return Rate": {
        "table": "mart_daily_orders",
        "metric_expr": "MAX(refund_rate_pct)",  # Already aggregated daily
        "date_col": "order_date",
        "benchmark": 5.0,  # 5% industry benchmark
        "format": "percentage",
        "lower_is_better": True,
    },
    "Ad Efficiency": {
        "table": "mart_daily_blended_performance",
        "metric_expr": "CASE WHEN MAX(total_ad_spend) = 0 THEN 0 ELSE MAX(net_profit_proxy)::FLOAT / MAX(total_ad_spend) END",
        "date_col": "report_date",
        "benchmark": 2.0,  # $2 net profit per $1 ad spend
        "format": "decimal",
    },
}


class TargetComponent(BaseModel):
    trend_short: float
    trend_long: float
    volatility: float
    benchmark_gap: float
    lift_raw: float
    lift_clamped: float


class TargetResult(BaseModel):
    metric: str
    current_value: float
    target_value: float
    lift_pct: float
    confidence: float
    format: str
    components: TargetComponent
    short_term_direction: str
    long_term_direction: str


class TargetEngine:
    def __init__(self, conn, tenant_id: int):
        self.conn = conn
        self.tenant_id = tenant_id

    def generate_targets(self) -> list[TargetResult]:
        results = []
        for name, config in METRICS.items():
            try:
                result = self._calculate_target(name, config)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Failed to calculate target for {name}: {e}")
        return results

    def _calculate_target(self, name: str, config: dict) -> Optional[TargetResult]:
        try:
            # 1. Fetch Data (90 days)
            raw_data = get_metric_series(
                self.conn,
                self.tenant_id,
                config["table"],
                config["metric_expr"],
                config["date_col"],
                days=90,
            )

            if not raw_data:
                return None

            # Convert to DataFrame
            df = pd.DataFrame(raw_data, columns=["date", "value"])
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")

            # Reindex to fill missing dates with 0 (or previous value depending on metric type)
            full_idx = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
            df = df.reindex(full_idx).ffill().fillna(0)
            
            # Ensure we have enough data points (at least 2 to calculate a trend)
            if len(df) < 2:
                return None

            # 2. Baselines (Rolling Averages)
            # Use min_periods=1 to allow calculation with partial data
            baseline_7d = df["value"].rolling(window=7, min_periods=1).mean().iloc[-1]
            baseline_30d = df["value"].rolling(window=30, min_periods=1).mean().iloc[-1]
            baseline_90d = df["value"].rolling(window=90, min_periods=1).mean().iloc[-1]

            # Handle NaNs if not enough history
            if pd.isna(baseline_30d):
                baseline_30d = baseline_7d
            if pd.isna(baseline_90d):
                baseline_90d = baseline_30d
                
            if baseline_30d == 0:
                return None

            # 3. Volatility Score (std_dev / mean over 30d)
            window_30d = df["value"].tail(30)
            mean_30d = window_30d.mean()
            std_30d = window_30d.std()
            
            volatility_score = 0.0
            if mean_30d > 0:
                volatility_score = std_30d / mean_30d
            
            # Clamp volatility to reasonable range [0, 1]
            volatility_score = max(0.0, min(volatility_score, 1.0))

            # 4. Trends
            # Short: (7d - 30d) / 30d
            trend_short = (baseline_7d - baseline_30d) / baseline_30d if baseline_30d != 0 else 0
            
            # Long: (30d - 90d) / 90d
            trend_long = (baseline_30d - baseline_90d) / baseline_90d if baseline_90d != 0 else 0

            # Classify directions
            short_term_direction = "flat"
            if trend_short > 0.05: short_term_direction = "up"
            elif trend_short < -0.05: short_term_direction = "down"

            long_term_direction = "flat"
            if trend_long > 0.05: long_term_direction = "up"
            elif trend_long < -0.05: long_term_direction = "down"

            # 5. Benchmark Calibration
            benchmark = config["benchmark"]
            lower_is_better = config.get("lower_is_better", False)

            if lower_is_better:
                # For metrics like Return Rate, being below benchmark is good
                # Gap is positive when current is above benchmark (bad), negative when below (good)
                gap = (baseline_30d - benchmark) / baseline_30d if baseline_30d != 0 else 0
                gap = -gap  # Invert so positive gap = room to improve (reduce)
            else:
                gap = (benchmark - baseline_30d) / baseline_30d if baseline_30d != 0 else 0
            
            # Clamp gap to ±30%
            gap_clamped = max(-0.30, min(gap, 0.30))

            # 6. Predictive Lift Estimation
            # lift = w1*short + w2*long + w3*(-volatility) + w4*gap
            w1, w2, w3, w4 = 0.25, 0.25, 0.20, 0.30
            
            lift = (
                w1 * trend_short +
                w2 * trend_long +
                w3 * (-volatility_score) +
                w4 * gap_clamped
            )

            # Clamp lift: Max +15%, Max -5%
            lift_clamped = max(-0.05, min(lift, 0.15))

            # 7. Target Calculation
            target = baseline_30d * (1 + lift_clamped)

            # 8. Confidence Score
            # c1*(1-vol) + c2*|trend_long| + c3*consistency + c4*freshness
            # historical_consistency: 1.0 if short/long align, 0.5 otherwise
            consistency = 1.0 if (trend_short * trend_long) > 0 else 0.5
            
            # data_freshness: using simple logic (1.0 if last data is today/yesterday)
            last_date = df.index.max().date()
            days_lag = (date.today() - last_date).days
            freshness = max(0.0, 1.0 - (days_lag * 0.1)) # Decay by 0.1 per day lag

            c1, c2, c3, c4 = 0.40, 0.20, 0.25, 0.15
            confidence = (
                c1 * (1 - volatility_score) +
                c2 * abs(trend_long) +
                c3 * consistency +
                c4 * freshness
            )
            confidence = max(0.0, min(confidence, 1.0))

            return TargetResult(
                metric=name,
                current_value=round(float(baseline_30d), 2),
                target_value=round(float(target), 2),
                lift_pct=round(float(lift_clamped * 100), 2),
                confidence=round(float(confidence), 2),
                format=config["format"],
                components=TargetComponent(
                    trend_short=round(float(trend_short), 4),
                    trend_long=round(float(trend_long), 4),
                    volatility=round(float(volatility_score), 4),
                    benchmark_gap=round(float(gap_clamped), 4),
                    lift_raw=round(float(lift), 4),
                    lift_clamped=round(float(lift_clamped), 4),
                ),
                short_term_direction=short_term_direction,
                long_term_direction=long_term_direction,
            )
        except Exception as e:
            logger.error(f"Error calculating target for {name}: {e}")
            self.conn.rollback()
            return None
