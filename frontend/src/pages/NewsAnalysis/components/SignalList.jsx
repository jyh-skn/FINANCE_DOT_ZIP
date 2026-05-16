/* 최근 주요 이슈 요약 + 뉴스 기반 변동 사유 */
import { useMemo } from 'react';


const SIGNAL_COLOR = {
  positive: { color: '#4ade80', bg: 'rgba(74,222,128,0.12)' },
  negative: { color: '#f87171', bg: 'rgba(248,113,113,0.12)' },
  neutral:  { color: '#94a3b8', bg: 'rgba(148,163,184,0.12)' },
};

function toSignal(direction, severity) {
  if (direction === 'increase') return 'positive';
  if (direction === 'decrease') return severity === 'low' ? 'neutral' : 'negative';
  return 'neutral';
}

function extractRateFromDesc(description) {
  const match = description?.match(/(\d+(?:\.\d+)?)\s*%/);
  return match ? parseFloat(match[1]) : null;
}

function toLabel(direction, yoyRate, description) {
  const rate = yoyRate ?? extractRateFromDesc(description);
  if (rate == null) {
    if (direction === 'increase') return '▲';
    if (direction === 'decrease') return '▼';
    return '→';
  }
  const abs = Math.abs(rate).toFixed(1);
  if (direction === 'increase') return `▲ +${abs}%`;
  if (direction === 'decrease') return `▼ -${abs}%`;
  return `→ 0.0%`;
}

export default function SignalList({ detectedChanges }) {
  const changeReasons = useMemo(() => {
    if (!detectedChanges?.length) return [];
    const seen = new Set();
    return detectedChanges
      .map((item, i) => ({
        id: i + 1,
        signal: toSignal(item.direction, item.severity),
        label: toLabel(item.direction, item.yoy_change_rate, item.description),
        reason: item.description ?? '',
      }))
      .filter(item => {
        if (seen.has(item.reason)) return false;
        seen.add(item.reason);
        return true;
      });
  }, [detectedChanges]);

  return (
    <div className="na-card">
      <h3 className="na-card-title">뉴스 기반 변동 사유</h3>
      {changeReasons.length > 0 ? (
        <ul className="na-change-list">
          {changeReasons.map((item) => {
            const style = SIGNAL_COLOR[item.signal];
            return (
              <li key={item.id} className="na-change-item">
                <span
                  className="na-change-badge"
                  style={{ color: style.color, background: style.bg }}
                >
                  {item.label}
                </span>
                <span className="na-change-reason">{item.reason}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="na-empty-msg">변동 사유를 불러오지 못했습니다.</p>
      )}
    </div>
  );
}
