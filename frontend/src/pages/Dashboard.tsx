// frontend/src/pages/Dashboard.tsx
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import KpiCard from '../components/KpiCard';
import MetricChart from '../components/MetricChart';
import CampaignTable from '../components/CampaignTable';
import InsightsPanel from '../components/InsightsPanel';

type Period = '7d' | '14d' | '30d' | '90d';

interface KPIs {
  total_revenue: number;
  total_orders: number;
  avg_order_value: number;
  total_ad_spend: number;
  blended_roas: number;
  meta_roas: number;
  blended_cac: number;
  net_profit_proxy: number;
  total_refunds: number;
  total_refund_amount: number;
  cvr: number;
  ltv: number;
  repeat_purchase_rate: number;
  return_rate: number;
  ad_efficiency: number;
  revenue_change_pct: number | null;
  orders_change_pct: number | null;
  aov_change_pct: number | null;
  ad_spend_change_pct: number | null;
  roas_change_pct: number | null;
  cac_change_pct: number | null;
  cvr_change_pct: number | null;
  ltv_change_pct: number | null;
  rpr_change_pct: number | null;
  return_rate_change_pct: number | null;
  ad_efficiency_change_pct: number | null;
}

interface TimeseriesPoint {
  date: string;
  value: number;
}

interface Campaign {
  campaign_name: string;
  objective: string;
  total_spend: number;
  total_impressions: number;
  total_clicks: number;
  total_purchases: number;
  total_revenue: number;
  roas: number | null;
  cpa: number | null;
  ctr: number | null;
}

interface Target {
  metric: string;
  current_value: number;
  target_value: number;
  lift_pct: number;
  confidence: number;
  format: string;
}

function fmtAUD(val: number): string {
  return val.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatTargetValue(value: number, format: string): string {
  switch (format) {
    case 'currency':
      return '$' + value.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    case 'percentage':
      return value.toFixed(1) + '%';
    case 'decimal':
      return value.toFixed(2) + 'x';
    default:
      return value.toFixed(2);
  }
}

const PERIODS: { key: Period; label: string }[] = [
  { key: '7d', label: '7D' },
  { key: '14d', label: '14D' },
  { key: '30d', label: '30D' },
  { key: '90d', label: '90D' },
];

type ChartTab = 'revenue' | 'orders' | 'ad_spend' | 'roas';

const CHART_TABS: { key: ChartTab; label: string; color: string; prefix: string }[] = [
  { key: 'revenue', label: 'Revenue', color: '#10b981', prefix: '$' },
  { key: 'orders', label: 'Orders', color: '#6366f1', prefix: '' },
  { key: 'ad_spend', label: 'Ad Spend', color: '#f59e0b', prefix: '$' },
  { key: 'roas', label: 'ROAS', color: '#3b82f6', prefix: '' },
];

interface UserData {
  email: string;
  [key: string]: unknown;
}

export default function Dashboard() {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<Period>('30d');
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [timeseries, setTimeseries] = useState<Record<ChartTab, TimeseriesPoint[]>>({
    revenue: [],
    orders: [],
    ad_spend: [],
    roas: [],
  });
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeChart, setActiveChart] = useState<ChartTab>('revenue');
  const navigate = useNavigate();

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await axios.get('/users/me');
        setUser(response.data);
      } catch {
        navigate('/login');
      } finally {
        setLoading(false);
      }
    };
    fetchUser();
  }, [navigate]);

  // Fetch targets once (not period-dependent)
  useEffect(() => {
    if (!user) return;
    const fetchTargets = async () => {
      try {
        const res = await axios.get('/api/analytics/targets');
        setTargets(res.data);
      } catch {
        // Targets are optional — ignore errors
      }
    };
    fetchTargets();
  }, [user]);

  const fetchDashboardData = useCallback(async (p: Period) => {
    setDataLoading(true);
    setError(null);
    try {
      const [kpiRes, revRes, ordRes, spendRes, roasRes, campRes] = await Promise.all([
        axios.get(`/api/analytics/kpis?period=${p}`),
        axios.get(`/api/analytics/timeseries?metric=revenue&period=${p}`),
        axios.get(`/api/analytics/timeseries?metric=orders&period=${p}`),
        axios.get(`/api/analytics/timeseries?metric=ad_spend&period=${p}`),
        axios.get(`/api/analytics/timeseries?metric=roas&period=${p}`),
        axios.get(`/api/analytics/campaigns?period=${p}`),
      ]);
      setKpis(kpiRes.data);
      setTimeseries({
        revenue: revRes.data.data,
        orders: ordRes.data.data,
        ad_spend: spendRes.data.data,
        roas: roasRes.data.data,
      });
      setCampaigns(campRes.data);
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 400) {
        setError('Connect Shopify first to see analytics data.');
      } else {
        setError('Failed to load analytics data.');
      }
    } finally {
      setDataLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      fetchDashboardData(period);
    }
  }, [user, period, fetchDashboardData]);

  // Build target lookup by metric name
  const targetMap = new Map<string, Target>();
  for (const t of targets) {
    targetMap.set(t.metric, t);
  }

  function getTarget(metricName: string) {
    const t = targetMap.get(metricName);
    if (!t) return undefined;
    return {
      target_value: t.target_value,
      formatted_target: formatTargetValue(t.target_value, t.format),
      confidence: t.confidence,
      lift_pct: t.lift_pct,
    };
  }

  if (loading) {
    return <div className="flex justify-center items-center h-screen text-gray-500">Loading...</div>;
  }

  const currentChart = CHART_TABS.find(c => c.key === activeChart)!;

  return (
    <Layout email={user?.email}>
      {/* Header + Period Selector */}
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Welcome back, {user?.email}</p>
        </div>
        <div className="flex gap-0.5 rounded-lg bg-gray-100 p-1">
          {PERIODS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setPeriod(key)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                period === key
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="mb-6 rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
          {error}
        </div>
      )}

      {dataLoading && (
        <div className="mb-6 text-sm text-gray-400">Loading data...</div>
      )}

      {/* KPI Cards — 2x4 grid with embedded targets */}
      {kpis && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <KpiCard
            title="AOV"
            value={fmtAUD(kpis.avg_order_value)}
            prefix="$"
            changePct={kpis.aov_change_pct}
            target={getTarget('AOV')}
          />
          <KpiCard
            title="CVR"
            value={kpis.cvr.toFixed(2) + '%'}
            changePct={kpis.cvr_change_pct}
            target={getTarget('CVR')}
          />
          <KpiCard
            title="CAC"
            value={fmtAUD(kpis.blended_cac)}
            prefix="$"
            changePct={kpis.cac_change_pct}
            invertChange
            target={getTarget('CAC')}
          />
          <KpiCard
            title="ROAS"
            value={kpis.blended_roas.toFixed(2) + 'x'}
            changePct={kpis.roas_change_pct}
            target={getTarget('ROAS')}
          />
          <KpiCard
            title="LTV"
            value={fmtAUD(kpis.ltv)}
            prefix="$"
            changePct={kpis.ltv_change_pct}
            target={getTarget('LTV')}
          />
          <KpiCard
            title="RPR"
            value={kpis.repeat_purchase_rate.toFixed(1) + '%'}
            changePct={kpis.rpr_change_pct}
            target={getTarget('RPR')}
          />
          <KpiCard
            title="Return Rate"
            value={kpis.return_rate.toFixed(2) + '%'}
            changePct={kpis.return_rate_change_pct}
            invertChange
            target={getTarget('Return Rate')}
          />
          <KpiCard
            title="Ad Efficiency"
            value={kpis.ad_efficiency.toFixed(2) + 'x'}
            changePct={kpis.ad_efficiency_change_pct}
            target={getTarget('Ad Efficiency')}
          />
        </div>
      )}

      {/* Two-column: Chart (2/3) + Insights (1/3) */}
      {kpis && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          {/* Chart card with tabs */}
          <div className="lg:col-span-2 rounded-xl border border-gray-200/80 bg-white p-5 shadow-card">
            <div className="flex items-center gap-1 mb-4">
              {CHART_TABS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setActiveChart(key)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                    activeChart === key
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <MetricChart
              data={timeseries[activeChart]}
              title={currentChart.label}
              color={currentChart.color}
              prefix={currentChart.prefix}
              height={320}
              minimal
            />
          </div>

          {/* Insights sidebar */}
          <div className="lg:col-span-1">
            <InsightsPanel />
          </div>
        </div>
      )}

      {/* Campaign Table */}
      <div className="mb-6">
        <CampaignTable campaigns={campaigns} />
      </div>
    </Layout>
  );
}
