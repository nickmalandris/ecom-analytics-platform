// frontend/src/components/CampaignTable.tsx

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

interface CampaignTableProps {
  campaigns: Campaign[];
}

function fmt(val: number | null, prefix = '', decimals = 2): string {
  if (val === null || val === undefined) return '-';
  return `${prefix}${val.toLocaleString('en-AU', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

export default function CampaignTable({ campaigns }: CampaignTableProps) {
  if (campaigns.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200/80 bg-white p-5 shadow-card">
        <h3 className="text-[13px] font-medium text-gray-500 mb-4">Campaign Performance</h3>
        <p className="text-gray-400 text-sm text-center py-8">No campaign data available</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200/80 bg-white p-5 shadow-card overflow-x-auto">
      <h3 className="text-[13px] font-medium text-gray-500 mb-4">Campaign Performance</h3>
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            <th className="text-left py-2 pr-4 font-medium text-gray-500">Campaign</th>
            <th className="text-right py-2 px-3 font-medium text-gray-500">Spend</th>
            <th className="text-right py-2 px-3 font-medium text-gray-500">Revenue</th>
            <th className="text-right py-2 px-3 font-medium text-gray-500">ROAS</th>
            <th className="text-right py-2 px-3 font-medium text-gray-500">Purchases</th>
            <th className="text-right py-2 px-3 font-medium text-gray-500">CPA</th>
            <th className="text-right py-2 px-3 font-medium text-gray-500">Clicks</th>
            <th className="text-right py-2 px-3 font-medium text-gray-500">CTR</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c, i) => (
            <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
              <td className="py-2.5 pr-4">
                <div className="font-medium text-gray-900 truncate max-w-[200px]">{c.campaign_name}</div>
                <div className="text-xs text-gray-400">{c.objective}</div>
              </td>
              <td className="text-right py-2.5 px-3 text-gray-700">{fmt(c.total_spend, '$')}</td>
              <td className="text-right py-2.5 px-3 text-gray-700">{fmt(c.total_revenue, '$')}</td>
              <td className="text-right py-2.5 px-3">
                <span className={`font-medium ${(c.roas ?? 0) >= 2 ? 'text-green-600' : (c.roas ?? 0) >= 1 ? 'text-yellow-600' : 'text-red-600'}`}>
                  {fmt(c.roas, '', 1)}x
                </span>
              </td>
              <td className="text-right py-2.5 px-3 text-gray-700">{c.total_purchases?.toLocaleString() ?? '-'}</td>
              <td className="text-right py-2.5 px-3 text-gray-700">{fmt(c.cpa, '$')}</td>
              <td className="text-right py-2.5 px-3 text-gray-700">{c.total_clicks?.toLocaleString() ?? '-'}</td>
              <td className="text-right py-2.5 px-3 text-gray-700">{fmt(c.ctr, '', 1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
