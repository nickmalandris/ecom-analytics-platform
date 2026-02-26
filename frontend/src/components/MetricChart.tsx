// frontend/src/components/MetricChart.tsx
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';

interface DataPoint {
  date: string;
  value: number;
}

interface MetricChartProps {
  data: DataPoint[];
  title: string;
  color?: string;
  prefix?: string;
  height?: number;
  /** When true, renders without the outer card wrapper (for embedding in parent cards) */
  minimal?: boolean;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

function formatValue(val: number, prefix: string): string {
  if (Math.abs(val) >= 1000) {
    return `${prefix}${(val / 1000).toFixed(1)}k`;
  }
  return `${prefix}${val.toFixed(val % 1 === 0 ? 0 : 2)}`;
}

export default function MetricChart({
  data,
  title,
  color = '#3b82f6',
  prefix = '',
  height = 280,
  minimal = false,
}: MetricChartProps) {
  const chart = data.length === 0 ? (
    <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>
      No data available
    </div>
  ) : (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`gradient-${title}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.12} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={formatDate}
          tick={{ fontSize: 11, fill: '#9ca3af', fontFamily: 'Inter' }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(v) => formatValue(v, prefix)}
          tick={{ fontSize: 11, fill: '#9ca3af', fontFamily: 'Inter' }}
          axisLine={false}
          tickLine={false}
          width={55}
        />
        <Tooltip
          formatter={(value: unknown) => [
            `${prefix}${Number(value).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
            title,
          ]}
          labelFormatter={(label: unknown) => formatDate(String(label))}
          contentStyle={{
            backgroundColor: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: '10px',
            fontSize: '12px',
            fontFamily: 'Inter',
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)',
          }}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#gradient-${title})`}
          dot={false}
          activeDot={{ r: 4, fill: color, strokeWidth: 0 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );

  if (minimal) {
    return chart;
  }

  return (
    <div className="rounded-xl border border-gray-200/80 bg-white p-5 shadow-card">
      <h3 className="text-[13px] font-medium text-gray-500 mb-4">{title}</h3>
      {chart}
    </div>
  );
}
