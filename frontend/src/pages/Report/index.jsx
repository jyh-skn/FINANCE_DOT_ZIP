import BasicInfo from './components/BasicInfo';
import PriceSignal from './components/PriceSignal';
import RevenueChart from './components/RevenueChart';
import FinancialTable from './components/FinancialTable';
import './Report.css';

export default function Report({ reportData }) {
  return (
    <div>
      {/* 페이지 헤더 */}
      <div className="na-page-header">
        <div className="na-title-group">
          <h2 className="na-page-title">기업 분석 기본 정보</h2>
        </div>
      </div>

      <div className="rp-wrap">
        {/* 상단: 기본정보 + 차트 */}
        <div className="rp-top">
          <div className="rp-left-col">
            <BasicInfo reportData={reportData} />
            <PriceSignal />
          </div>
          <div className="rp-right-col">
            <RevenueChart reportData={reportData} />
          </div>
        </div>

        {/* 하단: 재무제표 */}
        <div className="rp-bottom">
          <FinancialTable reportData={reportData} />
        </div>
      </div>
    </div>
  );
}
