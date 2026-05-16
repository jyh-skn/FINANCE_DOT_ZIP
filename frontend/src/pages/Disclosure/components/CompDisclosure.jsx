/*
    CompDisclosure

    Author        - jyhong
    Created At    - 2026-05-09
    Description   - AI 리포트 기반 공시 분석 보고서 컴포넌트
    Features      -
      1. EXPECTED_AI_OUTPUT 형식(report 섹션) 렌더링
      2. 구형 { title, sections, warnings } 형식 fallback 지원
*/
// Report로 출력되는 key값
const REPORT_SECTIONS = [
  { key: 'executive_summary',       title: '경영 요약'      },
  { key: 'financial_change_summary', title: '재무 변동 요약' },
  { key: 'news_evidence_summary',    title: '관련 뉴스 요약' },
  { key: 'disclosure_evidence_summary',    title: '공시근거/사업보고서 기반' },
  { key: 'possible_causes',         title: '변동 가능 원인' },
  { key: 'interview_point',         title: '인터뷰 포인트'  },
  { key: 'limitations',             title: '분석의 한계'    },
];

/* ── AI 출력 형식 렌더러 ─────────────────────────────── */
function AIReportView({ reportData }) {
  const report      = reportData.report;
  const summary     = reportData.summary     ?? {};
  const companyInfo = reportData.company_info ?? {};
  const metadata    = reportData.metadata    ?? {};

  return (
    <div>
      {/* 헤더 카드: 기업명 + 리스크 등급 + 한줄 요약 */}
      <div className="na-card dc-header-card">
        <div className="dc-header-top">
          <span className="dc-company-name">{companyInfo.company_name ?? '-'}</span>
        </div>
        {summary.one_line_summary && (
          <p className="dc-one-liner">{summary.one_line_summary}</p>
        )}
        {summary.key_findings?.length > 0 && (
          <ul className="dc-findings-list">
            {summary.key_findings.map((f, i) => (
              <li key={i} className="dc-finding-item">{f}</li>
            ))}
          </ul>
        )}
      </div>

      {/* 리포트 섹션 카드들 */}
      {REPORT_SECTIONS.map(({ key, title }) => {
        const content = report[key];
        if (!content) return null;
        return (
          <div key={key} className="na-card dc-section-card">
            <h3 className="na-card-title">{title}</h3>
            <p className="dc-section-content">{content}</p>
          </div>
        );
      })}

      {/* 메타데이터 */}
      {(metadata.source_count || metadata.generated_at) && (
        <div className="dc-meta-row">
          {metadata.source_count > 0 && (
            <span className="dc-meta-item">뉴스 {metadata.source_count}건 참조</span>
          )}
          {metadata.model && (
            <span className="dc-meta-item">{metadata.model}</span>
          )}
          {metadata.generated_at && (
            <span className="dc-meta-item">
              생성: {metadata.generated_at.slice(0, 10)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ── 구형 { title, sections, warnings } 형식 렌더러 ─── */
function LegacyReportView({ d }) {
  return (
    <div className="na-card">
      <div className="dc-legacy-header">
        <span className="dc-company-name">{d.title}</span>
        {d.date && <span className="dc-meta-item">{d.date}</span>}
      </div>

      {d.sections?.map((sec) => (
        <div key={sec.id} className="dc-section-card" style={{ marginTop: 12 }}>
          <h3 className="na-card-title">
            <span className="dc-section-num">{sec.id}.</span>
            {sec.title}
          </h3>
          <ul className="dc-section-list">
            {sec.items.map((item, i) => (
              <li key={i} className="dc-section-item">{item}</li>
            ))}
          </ul>
        </div>
      ))}

      {d.warnings?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <h3 className="na-card-title dc-warnings-title">위험 경보(Warning Signals) 감지</h3>
          <div className="dc-warnings-list">
            {d.warnings.map((w, i) => (
              <div key={i} className={`dc-warning-item dc-warning-${w.level}`}>
                <span className="dc-warning-dot" />
                <span className="dc-warning-text">{w.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── 메인 컴포넌트 ───────────────────────────────────── */
export default function CompDisclosure({ reportData }) {
  // AI 출력 형식 (report 필드 존재 여부로 판단)
  if (reportData?.report) {
    return <AIReportView reportData={reportData} />;
  }

  // 구형 형식 fallback
  if (reportData?.sections) {
    return <LegacyReportView d={reportData} />;
  }

  return (
    <div className="na-card">
      <p style={{ color: 'var(--text-muted, #888)', textAlign: 'center', padding: '40px 0' }}>
        공시 데이터가 없습니다.
      </p>
    </div>
  );
}
