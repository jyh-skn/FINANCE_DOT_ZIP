import { BeatLoader } from 'react-spinners';
import SignalList from './components/SignalList';
import NewsSummary from './components/NewsSummary';
import NewsSource from './components/NewsSource';
import './NewsAnalysis.css';

function getLatestChanges(changes) {
  if (!changes?.length) return changes;
  const maxYear = Math.max(...changes.map(c => c.year ?? 0));
  return changes.filter(c => c.year === maxYear);
}

export default function NewsAnalysis({ newsData, newsLoading = false }) {
  const rawChanges      = newsData?.detected_changes ?? null;
  const detectedChanges = rawChanges ? getLatestChanges(rawChanges) : null;
  const evidenceNews    = newsData?.evidence_news    ?? null;

  return (
    <div>
      {/* 페이지 헤더 */}
      <div className="na-page-header">
        <div className="na-title-group">
          <h2 className="na-page-title">뉴스 기반 변동 사유 분석</h2>
        </div>
        {newsLoading && (
          <div className="na-news-loading">
            <BeatLoader color="#c084fc" size={6} />
            <span className="na-news-loading-text">뉴스 분석 중...</span>
          </div>
        )}
      </div>

      {/* 3열 가로 배치 */}
      <div className="na-three-col">
        <SignalList detectedChanges={detectedChanges} />
        <NewsSummary detectedChanges={detectedChanges} />
        <NewsSource evidenceNews={evidenceNews} />
      </div>
    </div>
  );
}
