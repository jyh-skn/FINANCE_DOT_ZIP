import { useState } from 'react';

const STMT_KEYS  = ['revenue', 'operating_income', 'net_income'];
const RATIO_KEYS = ['operating_margin', 'debt_ratio', 'current_ratio'];

function fmtValue(val, unit) {
  // null, undefined, NaN 모두 '-' 처리
  if (val == null) return '-';
  
  const num = Number(val);
  if (isNaN(num)) return '-';
  
  if (unit === 'KRW') {
    const eok = num / 100_000_000;
    return eok.toLocaleString('ko-KR', { maximumFractionDigits: 0 }) + '억';
  }
  if (unit === '%') return `${num.toFixed(1)}%`;
  return String(val);
}

function buildTable(reportData, keys) {
  const summary = reportData?.finance_summary;
  const metrics = reportData?.financial_metrics ?? {};
  if (!summary?.length) return null;

  const sorted = [...summary].sort((a, b) => a.year - b.year);
  const years  = sorted.map((s) => String(s.year));

  const rows = keys
    .filter((key) => metrics[key] || sorted.some((s) => s[key] != null))
    .map((key) => {
      const m     = metrics[key] ?? {};
      const label = m.label ?? key;
      const unit  = m.unit  ?? '';

      const values = sorted.map((s) => fmtValue(s[key], unit));
      const dir    = sorted.map((s, i) => {
        if (i === 0) return 0;
        const prev = sorted[i - 1][key];
        const curr = s[key];
        if (curr == null || prev == null) return 0;
        return curr > prev ? 1 : curr < prev ? -1 : 0;
      });

      return { label: `${label}(${unit || '-'})`, values, dir };
    });

  // yoy_change_rate 행 추가 (분석연도 기준)
const yoyRow = {
  label: 'YoY 변동률',
  values: sorted.map((s, i) => {
    if (i === 0) return '-';
    const key = keys[0];
    const yoyVal = s[`${key}_yoy`];  // revenue_yoy, operating_income_yoy, etc.

    if (yoyVal == null || isNaN(Number(yoyVal))) return '-';
    if (yoyVal == null || isNaN(Number(yoyVal))) return '-';
    const rate = Number(yoyVal);
    return `${rate > 0 ? '+' : ''}${rate.toFixed(1)}%`;
  }),
  dir: sorted.map(() => 0),
};
  rows.push(yoyRow);

  return { years, rows };
}

const TABS = [
  { id: 'stmt',  label: '재무제표' },
  { id: 'ratio', label: '주요 지표' },
];

function dirClass(d) {
  if (d > 0) return 'ft-val-up';
  if (d < 0) return 'ft-val-down';
  return '';
}

export default function FinancialTable({ reportData }) {
  const [activeTab, setActiveTab] = useState('stmt');

  const keys = activeTab === 'stmt' ? STMT_KEYS : RATIO_KEYS;
  const data = buildTable(reportData, keys);

  return (
    <div className="na-card ft-wrap">
      <div className="ft-header">
        <span className="na-card-title" style={{ margin: 0 }}>
          {activeTab === 'stmt' ? '재무제표' : '주요 지표'}
        </span>
        <div className="ft-tabs">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              className={`ft-tab-btn${activeTab === id ? ' active' : ''}`}
              onClick={() => setActiveTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {data ? (
        <table className="ft-table">
          <thead>
            <tr>
              <th>항목</th>
              {data.years.map((y) => <th key={y}>{y}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map(({ label, values, dir }) => (
              <tr key={label}>
                <td>{label}</td>
                {values.map((v, i) => (
                  <td key={i} className={dirClass(dir[i])}>{v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: '20px 0' }}>
          재무 데이터가 없습니다.
        </p>
      )}
    </div>
  );
}
