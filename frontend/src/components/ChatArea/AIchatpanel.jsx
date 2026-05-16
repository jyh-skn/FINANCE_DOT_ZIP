import { useState, useRef, useEffect } from "react";
import { gfn_transaction } from "../../util/common-util";
import "./AIChatPanel.css";
import ratIcon from "../../assets/rat_icon.png";

// ── 아이콘 ──────────────────────────────────────────
function BotIcon() {
  return <img src={ratIcon} alt="AI" width="28" height="28" style={{ borderRadius: "50%", objectFit: "cover" }} />;
}

function UserIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

// ── 타이핑 인디케이터 ──────────────────────────────
function TypingBubble() {
  return (
    <div className="acp-row assistant">
      <div className="acp-avatar bot"><BotIcon /></div>
      <div className="acp-col">
        <div className="acp-bubble acp-typing">
          <span className="acp-dot" />
          <span className="acp-dot" />
          <span className="acp-dot" />
        </div>
      </div>
    </div>
  );
}

// ── 유틸 ─────────────────────────────────────────────
function getTime() {
  const now = new Date();
  const h = now.getHours();
  const m = String(now.getMinutes()).padStart(2, "0");
  const ampm = h >= 12 ? "오후" : "오전";
  const hour = h > 12 ? h - 12 : h === 0 ? 12 : h;
  return `${ampm} ${hour}:${m}`;
}

// ── 초기 메시지 ──────────────────────────────────────
const getInitialMessages = (name) => [
  {
    id: 1,
    role: "assistant",
    content: `안녕하세요! ${name}의 재무 분석 보고서에 대해 궁금하신 점이 있으시면 언제든지 질문해주세요.`,
    time: getTime(),
  },
];

// ── 컴포넌트 ─────────────────────────────────────────
export default function AIChatPanel({ companyName, stockCode }) {
  const [messages, setMessages] = useState(() => getInitialMessages(companyName));
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [aiReportResult, setAiReportResult] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const bodyRef = useRef(null);
  const inputRef = useRef(null);
  const typewriterRef = useRef(null);

  // 타이핑 인터벌 정리
  useEffect(() => {
    return () => {
      if (typewriterRef.current) clearInterval(typewriterRef.current);
    };
  }, []);

  // 회사가 바뀌면 메시지 초기화 + AI 리포트 생성
  useEffect(() => {
    if (typewriterRef.current) clearInterval(typewriterRef.current);
    setIsAnimating(false);
    setMessages(getInitialMessages(companyName));
    setAiReportResult(null);

    if (!stockCode) return;

    // setReportLoading(true);
    // axios
    //   .post(`/api/v1/report/comprehensive/${stockCode}/ai`, { use_mock_disclosures: true })
    //   .then((res) => {
    //     if (res.data?.status === "success") {
    //       setAiReportResult(res.data.data);
    //     }
    //   })
    //   .catch(() => {})
    //   .finally(() => setReportLoading(false));
  }, [companyName, stockCode]);

  // 새 메시지 올 때마다 스크롤 하단 이동
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const handleSend = async () => {
    const text = inputValue.trim();
    if (!text || isTyping || isAnimating) return;

    const userMsg = {
      id: Date.now(),
      role: "user",
      content: text,
      time: getTime(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputValue("");
    setIsTyping(true);

    // 현재 질문 포함한 전체 대화 이력 (role/content 만 추출)
    const history = [...messages, userMsg].map(({ role, content }) => ({ role, content }));

    console.log("history");
    console.log(history);

    const param = {
      question: text,
      messages: history,
      use_mock_disclosures: false,
    };
    if (aiReportResult) {
      param.ai_report_result = aiReportResult;
    } else {
      param.allow_generate_report = true;
    }

    try {
      await gfn_transaction({
        svcId:  'chat',
        strUrl: `/api/v1/report/comprehensive/${stockCode}/chat`,
        param,
        method: 'POST',
        pCall:  (svcId, responseData, errCd) => {
          if (errCd !== 0 || !responseData) {
            const errMsg = responseData?.message || "오류가 발생했습니다. 다시 시도해주세요.";
            setIsTyping(false);
            setMessages((prev) => [
              ...prev,
              { id: Date.now() + 1, role: "assistant", content: errMsg, time: getTime() },
            ]);
            inputRef.current?.focus();
            return;
          }

          const answer =
            responseData?.data?.answer ||
            responseData?.message ||
            "답변을 가져오지 못했습니다.";

          const botMsgId = Date.now() + 1;
          const msgTime  = getTime();

          setIsTyping(false);
          setMessages((prev) => [
            ...prev,
            { id: botMsgId, role: "assistant", content: "", time: msgTime },
          ]);

          let charIndex = 0;
          setIsAnimating(true);
          typewriterRef.current = setInterval(() => {
            charIndex = Math.min(charIndex + 4, answer.length);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === botMsgId ? { ...m, content: answer.slice(0, charIndex) } : m
              )
            );
            if (charIndex >= answer.length) {
              clearInterval(typewriterRef.current);
              typewriterRef.current = null;
              setIsAnimating(false);
              inputRef.current?.focus();
            }
          }, 18);
        },
      });
    } catch {
      // gfn_transaction이 pCall(errCd=-1) 호출 후 throw하므로 UI 처리는 pCall에서 완료
      // 여기서는 isTyping 안전 초기화만 담당
      setIsTyping(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="acp-panel">
      {/* 헤더 */}
      <div className="acp-header">
        <div className="acp-header-left">
          <div className="acp-bot-icon"><BotIcon /></div>
          <span className="acp-header-title">AI 분석 어시스턴트</span>
        </div>
        {reportLoading && (
          <span className="acp-report-loading">리포트 준비 중...</span>
        )}
      </div>

      {/* 메시지 목록 */}
      <div className="acp-body" ref={bodyRef}>
        <div className="acp-messages">
          {messages.map((msg) => (
            <div key={msg.id} className={`acp-row ${msg.role}`}>
              <div className={`acp-avatar ${msg.role === "assistant" ? "bot" : "user"}`}>
                {msg.role === "assistant" ? <BotIcon /> : <UserIcon />}
              </div>
              <div className="acp-col">
                <div className="acp-bubble">{msg.content}</div>
                <span className="acp-time">{msg.time}</span>
              </div>
            </div>
          ))}

          {/* 타이핑 인디케이터 */}
          {isTyping && <TypingBubble />}
        </div>
      </div>

      {/* 입력창 */}
      <div className="acp-input-area">
        <div className="acp-input-box">
          <input
            ref={inputRef}
            className="acp-input"
            placeholder={reportLoading ? "리포트 준비 중..." : "보고서에 대해 질문해보세요..."}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isTyping || isAnimating || reportLoading}
            maxLength={300}
          />
          <button
            className="acp-send-btn"
            onClick={handleSend}
            disabled={isTyping || isAnimating || reportLoading || !inputValue.trim()}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}
