// frontend/src/components/KpiCard.tsx
import { cn } from '@/lib/utils';

interface TargetInfo {
  target_value: number;
  formatted_target: string;
  confidence: number;
  lift_pct: number;
}

interface KpiCardProps {
  title: string;
  value: string;
  changePct?: number | null;
  prefix?: string;
  subtitle?: string;
  /** If true, negative change% is good (e.g. Return Rate, CAC) */
  invertChange?: boolean;
  target?: TargetInfo;
}

function progressPct(current: string, target: number, prefix: string): number {
  // Strip prefix and parse numeric value
  const raw = current.replace(/[$,%x]/g, '').replace(/,/g, '');
  const val = parseFloat(raw);
  if (isNaN(val) || target === 0) return 0;
  return Math.max(0, Math.min(100, (val / target) * 100));
}

function progressBarColor(pct: number): string {
  if (pct >= 90) return 'bg-emerald-500';
  if (pct >= 60) return 'bg-brand';
  return 'bg-amber-500';
}

function confidenceDot(score: number): string {
  if (score >= 0.8) return 'bg-emerald-500';
  if (score >= 0.5) return 'bg-amber-500';
  return 'bg-red-500';
}

export default function KpiCard({
  title,
  value,
  changePct,
  prefix = '',
  subtitle,
  invertChange = false,
  target,
}: KpiCardProps) {
  const hasChange = changePct !== null && changePct !== undefined;
  const isPositive = hasChange && (invertChange ? changePct < 0 : changePct > 0);
  const isNegative = hasChange && (invertChange ? changePct > 0 : changePct < 0);

  const pct = target ? progressPct(value, target.target_value, prefix) : null;

  return (
    <div className="group rounded-xl border border-gray-200/80 bg-white p-5 shadow-card transition-shadow hover:shadow-card-hover">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-medium text-gray-500">{title}</p>
        {hasChange && (
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold',
              isPositive && 'bg-emerald-50 text-emerald-700',
              isNegative && 'bg-red-50 text-red-700',
              !isPositive && !isNegative && 'bg-gray-50 text-gray-500'
            )}
          >
            {changePct! > 0 ? '+' : ''}{changePct!.toFixed(1)}%
          </span>
        )}
      </div>

      {/* Value */}
      <p className="mt-2 text-2xl font-bold tracking-tight text-gray-900">
        {prefix}{value}
      </p>

      {/* Target progress */}
      {target && pct !== null && (
        <div className="mt-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] text-gray-400">
              Target: {target.formatted_target}
            </span>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-gray-400">{pct.toFixed(0)}%</span>
              <span
                className={cn('inline-block h-1.5 w-1.5 rounded-full', confidenceDot(target.confidence))}
                title={`Confidence: ${(target.confidence * 100).toFixed(0)}%`}
              />
            </div>
          </div>
          <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-700', progressBarColor(pct))}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Subtitle (no target) */}
      {!target && subtitle && (
        <p className="mt-1 text-[11px] text-gray-400">{subtitle}</p>
      )}
    </div>
  );
}
