import CompDisclosure from './components/CompDisclosure';
import './Disclosure.css';

export default function DisclosurePage({ reportData }) {
  // reportData.report가 있으면 AI 출력 형식 우선 사용, 없으면 disclosureData fallback
  const data = reportData?.report ? reportData : disclosureData;

  return (
    <div>
      {/* 페이지 헤더 */}
      <div className="na-page-header">
        <div className="na-title-group">
          <h2 className="na-page-title">AI 기반 변동 사유 분석</h2>
        </div>
      </div>

      <div className="dc-wrap">
        <CompDisclosure reportData={data} />
      </div>
    </div>
  );
}
