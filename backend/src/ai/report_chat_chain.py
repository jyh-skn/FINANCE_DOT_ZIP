"""
report_chat_chain.py

AI 리포트 기반 Q&A 챗봇 Chain 모듈입니다.

성능 개선 버전:
- LLM에 전달하는 chat_context를 압축합니다.
- 기존 context_text 전체 + available_sources_json 전체를 모두 넣던 구조를 줄입니다.
- source 목록은 LLM이 source_id를 고를 수 있을 정도로만 짧게 제공합니다.
- answer 후처리에서는 기존 available_sources를 사용하므로 used_sources 상세 정보는 유지됩니다.
- chat_history는 최근 대화만 짧게 넣습니다.
"""

import ast
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
    if value is None:
        return ""
    return str(value)


def shorten_text(text: Any, max_length: int = 800) -> str:
    text = safe_text(text).strip()
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "...(truncated)"


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )


def get_model_name(llm: Any) -> str:
    return (
        getattr(llm, "model_name", None)
        or getattr(llm, "model", None)
        or "unknown"
    )


def extract_json_from_llm_output(output: str) -> Dict[str, Any]:
    cleaned = output.strip()
    fence = "`" * 3

    if cleaned.startswith(f"{fence}json"):
        cleaned = cleaned.replace(f"{fence}json", "", 1).strip()
    if cleaned.startswith(fence):
        cleaned = cleaned.replace(fence, "", 1).strip()
    if cleaned.endswith(fence):
        cleaned = cleaned[:-3].strip()

    return json.loads(cleaned)


def looks_like_object_string(text: str) -> bool:
    text = safe_text(text).strip()
    if not text:
        return False
    return (
        (text.startswith("{") and text.endswith("}"))
        or (text.startswith("[") and text.endswith("]"))
    )


def convert_object_answer_to_text(answer: str) -> str:
    answer = safe_text(answer).strip()

    if not looks_like_object_string(answer):
        return answer

    try:
        parsed = ast.literal_eval(answer)
    except Exception:
        try:
            parsed = json.loads(answer)
        except Exception:
            return answer

    if not isinstance(parsed, dict):
        return answer

    lines = []
    news_items = parsed.get("news_evidence") or parsed.get("news") or []
    disclosure_items = parsed.get("disclosure_evidence") or parsed.get("disclosures") or []

    if news_items:
        lines.append("뉴스 근거에서는 다음 내용이 언급됩니다.")
        for idx, item in enumerate(news_items, start=1):
            if not isinstance(item, dict):
                continue
            source_id = item.get("source_id", f"news_{idx}")
            summary = item.get("summary", "")
            lines.append(f"- {source_id}: {summary}")

    if disclosure_items:
        if lines:
            lines.append("")
        lines.append("공시 근거에서는 다음 내용이 언급됩니다.")
        for idx, item in enumerate(disclosure_items, start=1):
            if not isinstance(item, dict):
                continue
            source_id = item.get("source_id", f"disclosure_{idx}")
            summary = item.get("summary", "")
            lines.append(f"- {source_id}: {summary}")

    if lines:
        return "\n".join(lines).strip()

    return answer


# ---------------------------------------------------------------------
# 2. source 정리
# ---------------------------------------------------------------------

def build_available_sources(chat_context: Dict[str, Any]) -> List[Dict[str, Any]]:
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


def build_compact_sources_for_prompt(
    available_sources: List[Dict[str, Any]],
    max_summary_chars: int = 220,
) -> List[Dict[str, Any]]:
    compact_sources = []

    for source in available_sources:
        compact_sources.append(
            {
                "source_id": source.get("source_id"),
                "source_type": source.get("source_type"),
                "title": source.get("title") or source.get("source"),
                "metric_label": source.get("metric_label"),
                "year": source.get("year"),
                "summary": shorten_text(source.get("summary", ""), max_length=max_summary_chars),
            }
        )

    return compact_sources


def clean_used_sources(
    used_sources: Any,
    available_sources: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
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
        merged = {**base, **item}
        cleaned.append(merged)

    return cleaned


def infer_used_sources_from_question(
    question: str,
    available_sources: List[Dict[str, Any]],
    max_per_type: int = 3,
) -> List[Dict[str, Any]]:
    question = safe_text(question)
    inferred = []

    wants_news = "뉴스" in question
    wants_disclosure = ("공시" in question) or ("사업보고서" in question) or ("문서" in question)
    wants_report = (
        ("리포트" in question)
        or ("요약" in question)
        or ("왜" in question)
        or ("원인" in question)
        or ("주요" in question)
    )

    if wants_report:
        inferred.extend(
            source
            for source in available_sources
            if source.get("source_type") == "ai_report"
        )

    if wants_news:
        inferred.extend(
            source
            for source in available_sources
            if source.get("source_type") == "news"
        )

    if wants_disclosure:
        inferred.extend(
            source
            for source in available_sources
            if source.get("source_type") in {"disclosure", "business_report"}
        )

    if ("두 번째" in question or "2번째" in question) and "뉴스" in question:
        inferred.extend(
            source
            for source in available_sources
            if source.get("source_type") == "news"
        )

    if not inferred:
        inferred.extend(
            source
            for source in available_sources
            if source.get("source_type") in {"ai_report", "news"}
        )

    result = []
    seen = set()
    type_counts = {}

    for source in inferred:
        source_id = source.get("source_id")
        if not source_id or source_id in seen:
            continue

        source_type = source.get("source_type")
        type_counts[source_type] = type_counts.get(source_type, 0) + 1

        if source_type != "ai_report" and type_counts[source_type] > max_per_type:
            continue

        result.append(source)
        seen.add(source_id)

    return result


def normalize_limitations(
    limitations: str,
    chat_context: Dict[str, Any],
) -> str:
    limitations = safe_text(limitations).strip()
    disclosure_count = len(chat_context.get("evidence_disclosures", []) or [])

    if disclosure_count > 0:
        bad_phrases = [
            "공시 근거는 없습니다",
            "공시 근거가 없습니다",
            "공시 근거는 없으며",
            "공시 근거가 전혀 없는",
        ]

        if any(phrase in limitations for phrase in bad_phrases):
            limitations = (
                "본 답변은 제공된 AI 리포트, 재무 데이터, 뉴스 근거, 공시 근거에 한정됩니다. "
                "공시 내용이 재무 변화의 직접 원인을 의미하는지는 추가 확인이 필요합니다."
            )

    if not limitations:
        limitations = "본 답변은 제공된 AI 리포트, 재무 데이터, 뉴스 근거, 공시 근거에 한정됩니다."

    return limitations


# ---------------------------------------------------------------------
# 3. context 압축
# ---------------------------------------------------------------------

def build_compact_context_text(
    chat_context: Dict[str, Any],
    max_news_items: int = 3,
    max_disclosure_items: int = 3,
    max_detected_changes: int = 4,
) -> str:
    company = chat_context.get("company", {}) or {}
    report = chat_context.get("report", {}) or {}
    detected_changes = chat_context.get("detected_changes", []) or []
    evidence_news = chat_context.get("evidence_news", []) or []
    evidence_disclosures = chat_context.get("evidence_disclosures", []) or []

    lines = [
        "[기업 정보]",
        f"기업명: {company.get('company_name')}",
        f"종목코드: {company.get('stock_code')}",
        f"업종: {company.get('industry_group_name')} ({company.get('industry_group')})",
        f"분석 연도: {company.get('analysis_year')}",
        f"비교 기준 연도: {company.get('base_year')}",
        "",
        "[AI 리포트 요약]",
        f"요약: {shorten_text(report.get('executive_summary'), 450)}",
        f"재무 변화: {shorten_text(report.get('financial_change_summary'), 650)}",
        f"뉴스 근거 요약: {shorten_text(report.get('news_evidence_summary'), 550)}",
        f"공시 근거 요약: {shorten_text(report.get('disclosure_evidence_summary'), 550)}",
        f"가능한 배경: {shorten_text(report.get('possible_causes'), 450)}",
        f"한계: {shorten_text(report.get('limitations'), 350)}",
        "",
        "[핵심 재무 변화]",
    ]

    if detected_changes:
        for item in detected_changes[:max_detected_changes]:
            lines.append(
                "- "
                f"{item.get('year')}년 {item.get('metric_label')} "
                f"변화율={item.get('yoy_change_rate')}, "
                f"severity={item.get('severity')}, "
                f"signal_type={item.get('signal_type')}, "
                f"설명={shorten_text(item.get('description'), 180)}"
            )
    else:
        lines.append("핵심 재무 변동 정보가 제공되지 않았습니다.")

    lines.extend(["", "[뉴스 근거]"])

    if evidence_news:
        for idx, item in enumerate(evidence_news[:max_news_items], start=1):
            lines.append(
                f"[뉴스 {idx}] "
                f"title={item.get('title')}, "
                f"metric={item.get('metric_label')}, "
                f"summary={shorten_text(item.get('evidence_summary') or item.get('content'), 420)}, "
                f"url={item.get('url')}"
            )
    else:
        lines.append("리포트 근거로 선별된 뉴스가 없습니다.")

    lines.extend(["", "[공시 근거]"])

    if evidence_disclosures:
        for idx, item in enumerate(evidence_disclosures[:max_disclosure_items], start=1):
            lines.append(
                f"[공시 {idx}] "
                f"source={item.get('source')}, "
                f"metric={item.get('metric_label')}, "
                f"summary={shorten_text(item.get('evidence_summary') or item.get('chunk_text'), 420)}"
            )
    else:
        lines.append("리포트 근거로 선별된 공시/사업보고서 근거가 없습니다.")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------
# 4. fallback 답변
# ---------------------------------------------------------------------

def build_fallback_answer(
    question: str,
    chat_context: Dict[str, Any],
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
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
# 5. Report Chat Chain
# ---------------------------------------------------------------------

REPORT_CHAT_SYSTEM_PROMPT = """
당신은 특정 기업의 재무 분석 리포트에 대해 질의응답을 수행하는 AI 챗봇입니다.
반드시 JSON만 반환하세요. 마크다운, 코드블록, 추가 설명 문장은 출력하지 마세요.

원칙:
- 제공된 리포트 context, 이전 대화, 사용 가능한 근거 목록 안에서만 답변하세요.
- context에 없는 사실은 만들지 마세요.
- 뉴스 발행일이 명확하지 않거나 1월 1일처럼 기본값으로 보이는 경우, 답변에서 날짜를 확정적으로 언급하지 마세요.
- 뉴스나 공시를 재무 변화의 직접 원인으로 단정하지 마세요.
- "가능한 배경", "관련 요인", "검토할 수 있다", "추가 확인이 필요하다"처럼 신중하게 표현하세요.
- 투자 추천, 매수/매도/보유, 목표주가 판단은 절대 하지 마세요.
- 현재 질문이 "방금 답변", "그 내용", "두 번째 뉴스", "앞에서 말한 공시"처럼 이전 대화를 가리키면 [이전 대화]를 참고하세요.
- 단, 최종 근거는 반드시 제공된 AI 리포트, 뉴스 근거, 공시 근거 안에서만 사용하세요.
- used_sources에는 실제 답변에 사용한 source_id만 넣으세요.
- answer는 자연스러운 한국어 문장으로 작성하세요.

반환 JSON:
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
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", REPORT_CHAT_SYSTEM_PROMPT),
            (
                "human",
                """
[리포트 Context]
{context_text}

{chat_history_text}

[사용 가능한 근거 목록]
{available_sources_json}

[현재 질문]
{question}

위 정보만 근거로 답변 JSON을 생성하세요.
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
    available_sources = build_available_sources(chat_context)
    normalized_chat_history = normalize_chat_history(chat_history)

    answer = safe_text(parsed.get("answer", "")).strip()
    answer = convert_object_answer_to_text(answer)

    limitations = normalize_limitations(
        limitations=parsed.get("limitations", ""),
        chat_context=chat_context,
    )

    if not answer:
        answer = "제공된 리포트 context만으로는 해당 질문에 답변하기 어렵습니다."

    used_sources = clean_used_sources(
        used_sources=parsed.get("used_sources", []),
        available_sources=available_sources,
    )

    if not used_sources:
        used_sources = infer_used_sources_from_question(
            question=question,
            available_sources=available_sources,
        )

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
            "chat_history_count": len(normalized_chat_history),
            "prompt_compaction_applied": True,
        },
    }


def answer_report_question(
    llm,
    question: str,
    chat_context: Dict[str, Any],
    chat_history: Optional[List[Dict[str, Any]]] = None,
    max_context_chars: int = 6500,
) -> Dict[str, Any]:
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
        build_compact_context_text(chat_context),
        max_length=max_context_chars,
    )

    available_sources = build_available_sources(chat_context)
    compact_sources = build_compact_sources_for_prompt(
        available_sources=available_sources,
        max_summary_chars=220,
    )
    chat_history_text = build_chat_history_text(
        chat_history,
        max_messages=6,
        max_chars_per_message=450,
    )

    chain = build_report_chat_chain(llm)

    try:
        raw_output = chain.invoke(
            {
                "context_text": context_text,
                "chat_history_text": chat_history_text,
                "available_sources_json": compact_json(compact_sources),
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
        fallback["metadata"]["chat_history_used"] = has_chat_history(chat_history)
        fallback["metadata"]["chat_history_count"] = len(normalize_chat_history(chat_history))
        fallback["metadata"]["prompt_compaction_applied"] = True

        return fallback


def chat_with_report(
    llm,
    question: str,
    chat_context: Dict[str, Any],
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return answer_report_question(
        llm=llm,
        question=question,
        chat_context=chat_context,
        chat_history=chat_history,
    )


# ---------------------------------------------------------------------
# 6. 단독 실행 테스트
# ---------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from src.ai.chat_context_builder import build_chat_context
        from src.ai.llm_client import get_llm
    except ModuleNotFoundError:
        from chat_context_builder import build_chat_context
        from llm_client import get_llm

    sample_ai_report_result = {
        "company_info": {"company_name": "삼성전자", "stock_code": "005930"},
        "industry_info": {
            "industry_group": "tech_equipment",
            "industry_group_name": "기술 및 장치 산업",
        },
        "analysis_year": 2023,
        "base_year": 2022,
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
                "year": 2023,
                "title": "삼성전자 영업이익 급감",
                "url": "https://example.com/news",
                "evidence_summary": "반도체 업황 부진이 영업이익 감소 배경으로 보도되었습니다.",
            }
        ],
        "evidence_disclosures": [
            {
                "metric_label": "영업이익",
                "year": 2023,
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
    questions = [
        "삼성전자는 2023년에 영업이익이 왜 감소했어?",
        "뉴스 근거와 공시 근거를 나눠서 설명해줘.",
        "그럼 첫 번째 뉴스는 어떤 의미야?",
    ]
    history: List[Dict[str, str]] = []

    print("[Fast Report Chat Chain Test]")

    for question in questions:
        answer = answer_report_question(
            llm=llm,
            question=question,
            chat_context=context,
            chat_history=history,
        )

        print("\nQuestion:", question)
        print(json.dumps(answer, ensure_ascii=False, indent=2))

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer.get("answer", "")})
