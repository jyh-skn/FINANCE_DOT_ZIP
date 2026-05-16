"""
report_chat_chain.py

AI 리포트 기반 Q&A 챗봇 Chain 모듈입니다.

역할:
1. chat_context_builder.py에서 생성한 chat_context를 입력받습니다.
2. 사용자 질문과 context_text를 바탕으로 답변 JSON을 생성합니다.
3. 제공된 리포트/재무 데이터/뉴스 근거/공시 근거 안에서만 답변하도록 제한합니다.
4. 투자 추천, 매수/매도/보유 판단, 목표주가 판단을 하지 않습니다.

입력:
- question: 사용자 질문
- chat_context: build_chat_context() 결과
- llm: llm_client.py에서 생성한 공통 LLM 객체

출력:
{
    "answer": "...",
    "used_sources": [...],
    "limitations": "...",
    "metadata": {...}
}
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

try:
    from src.ai.chat_history_builder import (
        build_chat_history_text,
        has_chat_history,
        normalize_chat_history,
    )
except ModuleNotFoundError:
    from chat_history_builder import (
        build_chat_history_text,
        has_chat_history,
        normalize_chat_history,
    )


# ---------------------------------------------------------------------
# 1. 공통 유틸 함수
# ---------------------------------------------------------------------

def safe_text(value: Any) -> str:
    """
    None 또는 비문자열 값을 안전하게 문자열로 변환합니다.
    """

    if value is None:
        return ""

    return str(value)


def shorten_text(text: Any, max_length: int = 8000) -> str:
    """
    LLM 입력이 너무 길어지지 않도록 텍스트를 자릅니다.
    """

    text = safe_text(text).strip()

    if not text:
        return ""

    if len(text) <= max_length:
        return text

    return text[:max_length] + "...(truncated)"


def get_model_name(llm: Any) -> str:
    """
    ChatOpenAI 객체에서 모델명을 추출합니다.
    """

    return (
        getattr(llm, "model_name", None)
        or getattr(llm, "model", None)
        or "unknown"
    )


def extract_json_from_llm_output(output: str) -> Dict[str, Any]:
    """
    LLM 응답 문자열에서 JSON을 파싱합니다.
    LLM이 코드블록 형태로 JSON을 반환하는 경우도 처리합니다.
    """

    cleaned = output.strip()
    fence = "`" * 3

    if cleaned.startswith(f"{fence}json"):
        cleaned = cleaned.replace(f"{fence}json", "", 1).strip()

    if cleaned.startswith(fence):
        cleaned = cleaned.replace(fence, "", 1).strip()

    if cleaned.endswith(fence):
        cleaned = cleaned[:-3].strip()

    return json.loads(cleaned)


# ---------------------------------------------------------------------
# 2. source 정리
# ---------------------------------------------------------------------

def build_available_sources(chat_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    chat_context에 포함된 뉴스/공시 근거를 used_sources 후보로 정리합니다.
    """

    sources = []

    for idx, item in enumerate(chat_context.get("evidence_news", []) or [], start=1):
        sources.append(
            {
                "source_id": f"news_{idx}",
                "source_type": "news",
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "metric_label": item.get("metric_label", ""),
                "year": item.get("year"),
                "summary": item.get("evidence_summary") or item.get("content", ""),
            }
        )

    for idx, item in enumerate(chat_context.get("evidence_disclosures", []) or [], start=1):
        source_name = item.get("source", "")
        section = item.get("section", "")
        page = item.get("page", "")

        sources.append(
            {
                "source_id": f"disclosure_{idx}",
                "source_type": item.get("source_type", "disclosure"),
                "title": f"{item.get('report_type', '공시/사업보고서')} - {section}",
                "source": source_name,
                "page": page,
                "metric_label": item.get("metric_label", ""),
                "year": item.get("year"),
                "summary": item.get("evidence_summary") or item.get("chunk_text", ""),
            }
        )

    report = chat_context.get("report", {}) or {}

    if report.get("executive_summary"):
        sources.insert(
            0,
            {
                "source_id": "report",
                "source_type": "ai_report",
                "title": "AI 종합 리포트",
                "summary": report.get("executive_summary", ""),
            },
        )

    return sources


def clean_used_sources(
    used_sources: Any,
    available_sources: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    LLM이 반환한 used_sources를 정리합니다.

    source_id가 available_sources에 존재하면 해당 source 정보를 보강합니다.
    """

    if not isinstance(used_sources, list):
        return []

    source_map = {
        source.get("source_id"): source
        for source in available_sources
        if source.get("source_id")
    }

    cleaned = []

    for item in used_sources:
        if not isinstance(item, dict):
            continue

        source_id = item.get("source_id")
        base = source_map.get(source_id, {})

        merged = {
            **base,
            **item,
        }

        cleaned.append(merged)

    return cleaned


# ---------------------------------------------------------------------
# 3. fallback 답변
# ---------------------------------------------------------------------

def build_fallback_answer(
    question: str,
    chat_context: Dict[str, Any],
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    LLM 답변 생성 실패 시 사용할 fallback 답변을 생성합니다.
    """

    company = chat_context.get("company", {}) or {}
    report = chat_context.get("report", {}) or {}

    company_name = company.get("company_name") or "해당 기업"

    answer = (
        f"{company_name}에 대한 질문을 처리하는 중 문제가 발생했습니다. "
        "다만 현재 제공된 리포트 기준으로는 다음 내용을 참고할 수 있습니다. "
        f"{report.get('executive_summary', '')} "
        f"{report.get('possible_causes', '')}"
    ).strip()

    limitations = (
        "LLM 기반 답변 생성에 실패하여 기본 리포트 요약을 반환했습니다. "
        "정확한 답변을 위해서는 리포트, 뉴스 근거, 공시 근거를 다시 확인해야 합니다."
    )

    if error_message:
        limitations += f" 오류 메시지: {error_message}"

    return {
        "answer": answer,
        "used_sources": [
            {
                "source_id": "report",
                "source_type": "ai_report",
                "title": "AI 종합 리포트",
            }
        ],
        "limitations": limitations,
        "metadata": {
            "source": "fallback",
            "question": question,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
    }


# ---------------------------------------------------------------------
# 4. Report Chat Chain
# ---------------------------------------------------------------------

REPORT_CHAT_SYSTEM_PROMPT = """
당신은 특정 기업의 재무 분석 리포트에 대해 질의응답을 수행하는 AI 챗봇입니다.

목표:
- 사용자의 질문에 대해 제공된 리포트 context 안에서만 답변합니다.
- 재무 데이터, signals, detected_changes, 뉴스 근거, 공시 근거를 바탕으로 설명합니다.
- 답변은 JSON 형식으로만 반환합니다.

중요 원칙:
1. 반드시 JSON만 반환하세요.
2. 마크다운, 코드블록, 추가 설명 문장을 출력하지 마세요.
3. 제공된 context에 없는 사실은 임의로 만들지 마세요.
4. 모르는 내용은 모른다고 말하고, 추가 확인이 필요하다고 작성하세요.
5. 뉴스나 공시 내용을 재무 변화의 직접 원인으로 단정하지 마세요.
6. "가능한 배경", "관련 요인", "언급됩니다", "추가 확인이 필요합니다"처럼 신중한 표현을 사용하세요.
7. 투자 추천, 매수, 매도, 보유, 목표주가 판단을 절대 하지 마세요.
8. 사용자가 투자 판단을 요구하면, 제공된 재무 정보와 리스크 요약까지만 설명하고 투자 조언은 할 수 없다고 답하세요.
9. 수치 질문에는 context에 있는 수치를 그대로 사용하고 새로 계산하지 마세요.
10. 답변에 사용한 근거가 있다면 used_sources에 source_id를 포함하세요.
11. 사용자가 "방금 답변", "그 내용", "두 번째 뉴스", "앞에서 말한 공시"처럼 이전 대화를 가리키는 경우 [이전 대화]를 참고하세요.
12. 단, 이전 대화에 있더라도 최종 답변의 근거는 반드시 제공된 리포트 context와 사용 가능한 근거 목록 안에서만 사용하세요.

반환 JSON 형식:
{{
  "answer": "",
  "used_sources": [
    {{
      "source_id": "",
      "source_type": "",
      "title": "",
      "reason": ""
    }}
  ],
  "limitations": ""
}}
"""


def build_report_chat_chain(llm):
    """
    Report Q&A 전용 Chain을 생성합니다.
    """

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", REPORT_CHAT_SYSTEM_PROMPT),
            (
                "human",
                """
다음은 특정 기업의 재무 분석 리포트 context입니다.

[Context]
{context_text}

[사용 가능한 근거 목록]
{available_sources_json}

[이전 대화]
{chat_history_text}

[현재 사용자 질문]
{question}

위 context와 이전 대화를 참고하되, 최종 답변은 제공된 근거 안에서만 생성하세요.
""",
            ),
        ]
    )

    return prompt | llm | StrOutputParser()


def clean_chat_answer(
    parsed: Dict[str, Any],
    question: str,
    chat_context: Dict[str, Any],
    llm: Any,
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    LLM이 반환한 답변 JSON을 최종 필드 기준으로 정리합니다.
    """

    available_sources = build_available_sources(chat_context)

    answer = safe_text(parsed.get("answer", "")).strip()
    limitations = safe_text(parsed.get("limitations", "")).strip()

    if not answer:
        answer = "제공된 리포트 context만으로는 해당 질문에 답변하기 어렵습니다."

    if not limitations:
        limitations = "본 답변은 제공된 AI 리포트, 재무 데이터, 뉴스 근거, 공시 근거에 한정됩니다."

    used_sources = clean_used_sources(
        used_sources=parsed.get("used_sources", []),
        available_sources=available_sources,
    )

    normalized_history = normalize_chat_history(chat_history)

    return {
        "answer": answer,
        "used_sources": used_sources,
        "limitations": limitations,
        "metadata": {
            "source": "llm",
            "question": question,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "model": get_model_name(llm),
            "available_source_count": len(available_sources),
            "used_source_count": len(used_sources),
            "chat_history_used": has_chat_history(chat_history),
            "chat_history_count": len(normalized_history),
        },
    }


def answer_report_question(
    llm,
    question: str,
    chat_context: Dict[str, Any],
    chat_history: Optional[List[Dict[str, Any]]] = None,
    max_context_chars: int = 10000,
) -> Dict[str, Any]:
    """
    리포트 기반 사용자 질문에 답변합니다.

    Args:
        llm: 공통 LLM 객체
        question: 사용자 질문
        chat_context: chat_context_builder.build_chat_context() 결과
        max_context_chars: LLM에 넣을 context_text 최대 길이

    Returns:
        답변 JSON dict
    """

    question = safe_text(question).strip()

    if not question:
        return {
            "answer": "질문이 비어 있습니다. 재무 리포트에 대해 궁금한 내용을 입력해 주세요.",
            "used_sources": [],
            "limitations": "질문이 제공되지 않아 답변을 생성하지 않았습니다.",
            "metadata": {
                "source": "rule_based",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "chat_history_used": has_chat_history(chat_history),
                "chat_history_count": len(normalize_chat_history(chat_history)),
            },
        }

    context_text = shorten_text(
        chat_context.get("context_text", ""),
        max_length=max_context_chars,
    )
    chat_history_text = build_chat_history_text(chat_history)

    available_sources = build_available_sources(chat_context)

    chain = build_report_chat_chain(llm)

    try:
        raw_output = chain.invoke(
            {
                "context_text": context_text,
                "available_sources_json": json.dumps(
                    available_sources,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "chat_history_text": chat_history_text,
                "question": question,
            }
        )

        parsed = extract_json_from_llm_output(raw_output)

        return clean_chat_answer(
            parsed=parsed,
            question=question,
            chat_context=chat_context,
            llm=llm,
            chat_history=chat_history,
        )

    except Exception as error:
        print(f"[WARN] 리포트 챗봇 답변 생성 실패. fallback answer를 사용합니다: {error}")

        fallback = build_fallback_answer(
            question=question,
            chat_context=chat_context,
            error_message=str(error),
        )
        fallback_metadata = fallback.get("metadata", {}) or {}
        fallback_metadata["chat_history_used"] = has_chat_history(chat_history)
        fallback_metadata["chat_history_count"] = len(normalize_chat_history(chat_history))
        fallback["metadata"] = fallback_metadata
        return fallback


# 호환용 alias
def chat_with_report(
    llm,
    question: str,
    chat_context: Dict[str, Any],
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    answer_report_question()의 alias 함수입니다.
    """

    return answer_report_question(
        llm=llm,
        question=question,
        chat_context=chat_context,
        chat_history=chat_history,
    )


# ---------------------------------------------------------------------
# 5. 단독 실행 테스트
# ---------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from src.ai.chat_context_builder import build_chat_context
        from src.ai.llm_client import get_llm
    except ModuleNotFoundError:
        from chat_context_builder import build_chat_context
        from llm_client import get_llm

    sample_ai_report_result = {
        "company_info": {
            "company_name": "삼성전자",
            "stock_code": "005930",
        },
        "industry_info": {
            "industry_group": "tech_equipment",
            "industry_group_name": "기술 및 장치 산업",
        },
        "analysis_year": 2023,
        "base_year": 2022,
        "signals": [
            {
                "year": 2023,
                "type": "negative",
                "severity": "HIGH",
                "signal": "영업이익 급감",
                "description": "전년 대비 영업이익이 -84.86% 감소했습니다.",
            }
        ],
        "detected_changes": [
            {
                "metric_key": "operating_income",
                "metric_label": "영업이익",
                "year": 2023,
                "base_year": 2022,
                "current_value": 6566976000000,
                "base_value": 43376630000000,
                "yoy_change_rate": -84.86,
                "severity": "high",
                "signal_type": "negative",
                "description": "전년 대비 영업이익이 -84.86% 감소했습니다.",
            }
        ],
        "report": {
            "executive_summary": "삼성전자는 2023년 영업이익이 크게 감소했습니다.",
            "financial_change_summary": "영업이익은 전년 대비 84.86% 감소했습니다.",
            "news_evidence_summary": "뉴스에서는 반도체 업황 부진이 관련 배경으로 언급됩니다.",
            "disclosure_evidence_summary": "공시에서는 수요 둔화와 가격 하락이 언급됩니다.",
            "possible_causes": "반도체 업황 부진과 수요 둔화가 가능한 배경입니다.",
            "interview_point": "반도체 부문 회복 전략을 질문할 수 있습니다.",
            "limitations": "추가 공시 확인이 필요합니다.",
        },
        "evidence_news": [
            {
                "metric_label": "영업이익",
                "title": "삼성전자 영업이익 급감",
                "url": "https://example.com/news",
                "evidence_summary": "반도체 업황 부진이 영업이익 감소 배경으로 보도되었습니다.",
            }
        ],
        "evidence_disclosures": [
            {
                "metric_label": "영업이익",
                "report_type": "사업보고서",
                "section": "사업의 내용",
                "source": "2023_삼성전자_사업보고서_mock",
                "page": 12,
                "evidence_summary": "메모리 수요 둔화와 가격 하락이 수익성 약화 배경으로 언급되었습니다.",
            }
        ],
    }

    llm = get_llm()
    context = build_chat_context(sample_ai_report_result)

    question = "삼성전자는 2023년에 영업이익이 왜 감소했어?"

    answer = answer_report_question(
        llm=llm,
        question=question,
        chat_context=context,
    )

    print("[Report Chat Chain Test]")
    print(json.dumps(answer, ensure_ascii=False, indent=2))
