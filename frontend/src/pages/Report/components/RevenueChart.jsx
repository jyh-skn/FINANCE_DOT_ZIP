import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

const MOCK_DATA = [
  { year: "'20", revenue: 236807, operating: 35994, yoy: 2.8   },
  { year: "'21", revenue: 279605, operating: 51634, yoy: 18.1  },
  { year: "'22", revenue: 302231, operating: 43377, yoy: 8.1   },
  { year: "'23", revenue: 258935, operating: 6567,  yoy: -14.3 },
  { year: "'24", revenue: 300871, operating: 32726, yoy: 16.2  },
];

const COLORS = { revenue: '#4f8ef7', operating: '#f7c94f', yoy: '#ff6b6b' };

const fmtEok = (v) => `${(v).toFixed(0)}억`;

function buildChartData(financeSummary) {
  if (!financeSummary?.length) return MOCK_DATA;
  const sorted = [...financeSummary].sort((a, b) => a.year - b.year);
  return sorted.map((item, i) => {
    const prevRevenue = sorted[i - 1]?.revenue ?? null;
    const yoy = prevRevenue != null && prevRevenue !== 0
      ? parseFloat((((item.revenue ?? 0) - prevRevenue) / Math.abs(prevRevenue) * 100).toFixed(1))
      : null;
    return {
      year:      `'${String(item.year).slice(2)}`,
      revenue:   Math.round((item.revenue           ?? 0) / 100_000_000),
      operating: Math.round((item.operating_income  ?? 0) / 100_000_000),
      yoy,
    };
  });
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: '#1a2035', border: '1px solid #252d3d', borderRadius: 6, padding: '8px 12px', fontSize: 11 }}>
      <p style={{ color: '#8899bb', marginBottom: 4 }}>{label}년</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color, margin: '2px 0' }}>
          {p.name}: {p.name === 'YoY%' ? `${p.value}%` : fmtEok(p.value)}
        </p>
      ))}
    </div>
  );
};

export default function RevenueChart({ reportData }) {
  const chartData = buildChartData(reportData?.finance_summary);

  return (
    <div className="na-card rc-wrap">
      <div className="rc-header">
        <span className="na-card-title" style={{ margin: 0 }}>매출 vs 영업이익</span>
        <div className="rc-legend">
          {[
            { label: '매출',     color: COLORS.revenue   },
            { label: '영업이익', color: COLORS.operating },
            { label: 'YoY%',    color: COLORS.yoy        },
          ].map(({ label, color }) => (
            <div className="rc-legend-item" key={label}>
              <span className="rc-legend-dot" style={{ background: color }} />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="rc-chart-area">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 4, right: 24, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(37,45,61,0.8)" vertical={false} />
            <XAxis dataKey="year" tick={{ fontSize: 10, fill: '#8899bb' }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left" tickFormatter={fmtEok} tick={{ fontSize: 10, fill: '#8899bb' }} axisLine={false} tickLine={false} width={48} />
            <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10, fill: '#8899bb' }} axisLine={false} tickLine={false} width={32} />
            <Tooltip content={<CustomTooltip />} />
            <Bar yAxisId="left" dataKey="revenue"   name="매출"     fill={COLORS.revenue}   opacity={0.85} radius={[2,2,0,0]} barSize={14} />
            <Bar yAxisId="left" dataKey="operating" name="영업이익" fill={COLORS.operating} opacity={0.85} radius={[2,2,0,0]} barSize={14} />
            <Line yAxisId="right" type="monotone" dataKey="yoy" name="YoY%" stroke={COLORS.yoy} strokeWidth={1.5} dot={{ r: 2.5, fill: COLORS.yoy }} activeDot={{ r: 4 }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
