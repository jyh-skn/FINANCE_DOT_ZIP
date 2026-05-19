"""
chat_safety_filter.py

챗봇 입력에 명확한 욕설/공격적 표현이 포함된 경우 LLM 호출 전에 차단합니다.
MVP 단계에서는 과도한 오탐을 피하기 위해 비교적 명확한 표현 중심으로 처리합니다.
"""

import re
from datetime import datetime
from typing import Any, Dict, List


PROFANITY_PATTERNS: List[str] = [
    r"\b씨발\b", r"시발", r"ㅅㅂ", r"ㅆㅂ",
    r"병신", r"븅신", r"ㅂㅅ",
    r"개새끼", r"새끼", r"ㅅㄲ",
    r"미친놈", r"미친년", r"미친",
    r"좆", r"존나", r"졸라",
    r"꺼져", r"닥쳐",
    r"죽어", r"뒤져",
]


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\s+", "", text)
    return text


def check_chat_safety(question: str) -> Dict[str, Any]:
    normalized = normalize_text(question)
    matched = []

    for pattern in PROFANITY_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            matched.append(pattern)

    if matched:
        return {
            "blocked": True,
            "reason": "profanity_detected",
            "matched_patterns": matched[:5],
        }

    return {
        "blocked": False,
        "reason": "clean",
        "matched_patterns": [],
    }


def build_safety_block_response(
    question: str,
    safety_result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "answer": "원활한 서비스 이용을 위해 공격적이거나 부적절한 표현은 사용할 수 없습니다. 재무 리포트나 기업 분석에 대해 궁금한 점을 다시 질문해 주세요.",
        "used_sources": [],
        "limitations": "부적절한 표현이 감지되어 답변 생성을 중단했습니다.",
        "metadata": {
            "source": "safety_filter",
            "blocked": True,
            "reason": safety_result.get("reason", "profanity_detected"),
            "question": question,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "llm_used": False,
        },
    }
