const RISK_LABEL = { high: '고위험', medium: '주의', low: '안정', normal: '안정' };
import { SAMPLE_NORMAL_AI_INPUT } from './../../../mock_data';
const RISK_COLOR = {
  HIGH:   { color: '#f87171', bg: 'rgba(248,113,113,0.12)' },
  MEDIUM: { color: '#fb923c', bg: 'rgba(251,146,60,0.12)'  },
  LOW:    { color: '#4ade80', bg: 'rgba(74,222,128,0.12)'  },
  NORMAL: { color: '#4ade80', bg: 'rgba(74,222,128,0.12)'  },
};

export default function BasicInfo({ reportData }) {
  const info     = reportData?.company_info ?? {};
  const signals  = reportData?.signals ?? {};
  const industry_info = reportData?.industry_info ?? {};
  const summary  = reportData?.summary ?? {};
  const riskLevel = summary.overall_risk_level ?? 'NORMAL';
  const riskStyle = RISK_COLOR[riskLevel] ?? RISK_COLOR.NORMAL;

  console.log(reportData)

  const rows = [
    { label: '기업명',   value: info.company_name   ?? '-' },
    { label: '종목코드', value: info.stock_code     ?? '-', highlight: true },
    { label: '산업정보', value: industry_info.industry_group_name      ?? '-' },
    { label: '분석연도', value: reportData?.analysis_year ? `${reportData.analysis_year}년` : '-' },
    { label: '기준연도', value: reportData?.base_year     ? `${reportData.base_year}년`     : '-' },
    { label: '주요발견', value: `${(reportData.detected_changes ?? []).length}건` },
  ];

  return (
    <div className="na-card bi-wrap">
      <div className="bi-title-row">
        <p className="na-card-title">기본 정보</p>
      </div>
      <div className="bi-row">
        {rows.map(({ label, value, highlight }) => (
          <div className="bi-item" key={label}>
            <span className="bi-label">{label}</span>
            <span className={highlight ? 'bi-value bi-ticker' : 'bi-value'}>{value}</span>
          </div>
        ))}
      </div>
      {summary.one_line_summary && (
        <p className="bi-summary">{summary.one_line_summary}</p>
      )}
    </div>
  );
}
