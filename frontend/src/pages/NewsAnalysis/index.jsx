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
          <span className="na-badge">LLM 베타</span>
        </div>
        {newsLoading && (
          <div className="na-news-loading">
            <BeatLoader color="#c084fc" size={6} />
            <span className="na-news-loading-text">뉴스 분석 중...</span>
          </div>
        )}
      </div>

      {/* 최근 이슈 + 변동 사유 (2열) */}
      <SignalList evidenceNews={evidenceNews} detectedChanges={detectedChanges} />

      {/* 주요 경영 판단 요약 + 뉴스 출처 (2열) */}
      <div className="na-bottom-row">
        <div className="na-bottom-main">
          <NewsSummary detectedChanges={detectedChanges} />
        </div>
        <div className="na-bottom-side">
          <NewsSource evidenceNews={evidenceNews} />
        </div>
      </div>
    </div>
  );
}
