// frontend/src/components/TargetsPanel.tsx
import { useEffect, useState, useRef } from 'react';
import { api } from '@/lib/api';

interface TargetComponent {
  trend_short: number;
  trend_long: number;
  volatility: number;
  benchmark_gap: number;
  lift_raw: number;
  lift_clamped: number;
}

interface Target {
  metric: string;
  current_value: number;
  target_value: number;
  lift_pct: number;
  confidence: number;
  format: string;
  components: TargetComponent;
  short_term_direction: string;
  long_term_direction: string;
}

type Status = 'idle' | 'loading' | 'done' | 'error';

function formatValue(value: number, format: string): string {
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

function confidenceLabel(score: number): { text: string; color: string } {
  if (score >= 0.8) return { text: 'High', color: 'text-green-700 bg-green-100' };
  if (score >= 0.5) return { text: 'Medium', color: 'text-amber-700 bg-amber-100' };
  return { text: 'Low', color: 'text-red-700 bg-red-100' };
}

function directionIcon(dir: string): string {
  if (dir === 'up') return '\u2191';    // ↑
  if (dir === 'down') return '\u2193';  // ↓
  return '\u2192';                       // →
}

function directionColor(dir: string): string {
  if (dir === 'up') return 'text-green-600';
  if (dir === 'down') return 'text-red-600';
  return 'text-gray-500';
}

/** Progress towards target as a percentage (capped 0–100) */
function progressPct(current: number, target: number): number {
  if (target === 0) return 0;
  return Math.max(0, Math.min(100, (current / target) * 100));
}

function progressBarColor(pct: number): string {
  if (pct >= 90) return 'bg-green-500';
  if (pct >= 60) return 'bg-indigo-500';
  return 'bg-amber-500';
}

export default function TargetsPanel() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const fetchTargets = async () => {
      setStatus('loading');
      try {
        const res = await api.get('/api/analytics/targets');
        setTargets(res.data);
        setStatus('done');
      } catch {
        setStatus('error');
      }
    };

    fetchTargets();
  }, []);

  // Loading skeleton
  if (status === 'loading') {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="flex items-center gap-2 mb-4">
          <svg className="h-5 w-5 text-indigo-500 animate-pulse" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
          <h2 className="text-lg font-semibold text-gray-900">Performance Targets</h2>
          <span className="ml-auto text-xs text-indigo-500 font-medium animate-pulse">Calculating...</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="animate-pulse rounded-lg border border-gray-100 p-4 space-y-3">
              <div className="h-4 bg-gray-200 rounded w-1/3" />
              <div className="h-6 bg-gray-200 rounded w-2/3" />
              <div className="h-2 bg-gray-200 rounded w-full" />
              <div className="h-3 bg-gray-200 rounded w-1/2" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (status === 'error') {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6">
        <div className="flex items-center gap-2 mb-2">
          <svg className="h-5 w-5 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <h2 className="text-lg font-semibold text-red-800">Targets</h2>
        </div>
        <p className="text-sm text-red-700">Failed to load performance targets.</p>
      </div>
    );
  }

  // Empty state
  if (status === 'done' && targets.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="flex items-center gap-2 mb-2">
          <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
          <h2 className="text-lg font-semibold text-gray-900">Performance Targets</h2>
        </div>
        <p className="text-sm text-gray-500">Not enough historical data to generate targets yet. Check back after a few more days of data.</p>
      </div>
    );
  }

  // Render targets
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      {/* Header */}
      <div className="flex items-center gap-2 mb-5">
        <svg className="h-5 w-5 text-indigo-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
        </svg>
        <h2 className="text-lg font-semibold text-gray-900">Performance Targets</h2>
        <span className="ml-auto text-xs text-gray-400">Based on 90-day trend analysis</span>
      </div>

      {/* Target cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {targets.map(t => {
          const pct = progressPct(t.current_value, t.target_value);
          const conf = confidenceLabel(t.confidence);
          const isPositiveLift = t.lift_pct > 0;

          return (
            <div key={t.metric} className="rounded-lg border border-gray-100 bg-gray-50 p-4">
              {/* Metric header */}
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-700">{t.metric}</h3>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${conf.color}`}>
                  {conf.text}
                </span>
              </div>

              {/* Current vs Target */}
              <div className="flex items-baseline gap-3 mb-3">
                <div>
                  <p className="text-xs text-gray-500">Current</p>
                  <p className="text-xl font-bold text-gray-900">{formatValue(t.current_value, t.format)}</p>
                </div>
                <svg className="h-4 w-4 text-gray-300 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
                <div>
                  <p className="text-xs text-gray-500">Target</p>
                  <p className="text-xl font-bold text-indigo-600">{formatValue(t.target_value, t.format)}</p>
                </div>
              </div>

              {/* Progress bar */}
              <div className="mb-3">
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>Progress</span>
                  <span>{pct.toFixed(0)}%</span>
                </div>
                <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${progressBarColor(pct)}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>

              {/* Lift + Trend */}
              <div className="flex items-center justify-between text-xs">
                <span className={isPositiveLift ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
                  {isPositiveLift ? '+' : ''}{t.lift_pct.toFixed(1)}% lift
                </span>
                <div className="flex items-center gap-2 text-gray-500">
                  <span className={directionColor(t.short_term_direction)} title="Short-term trend">
                    S {directionIcon(t.short_term_direction)}
                  </span>
                  <span className={directionColor(t.long_term_direction)} title="Long-term trend">
                    L {directionIcon(t.long_term_direction)}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
