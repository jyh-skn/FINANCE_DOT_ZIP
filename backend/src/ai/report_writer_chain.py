"""
report_writer_chain.py

재무 문맥, 뉴스 근거, 공시 근거, 산업별 분석 가이드를 바탕으로
최종 AI 재무 분석 리포트를 생성하는 Report Writer Chain 모듈입니다.

성능 개선 버전:
- LLM에 financial_context 전체 dict를 그대로 넣지 않고 핵심 필드만 압축해 전달합니다.
- evidence_news / evidence_disclosures는 최대 3개만 사용하고, 긴 본문 대신 summary 중심으로 전달합니다.
- JSON dump는 indent 없이 compact format으로 전달해 prompt 길이를 줄입니다.
- 최종 반환 JSON schema와 generate_report() 함수 시그니처는 기존과 동일하게 유지합니다.

주의:
- 투자 추천, 매수, 매도, 보유 판단을 하지 않습니다.
- 뉴스와 재무 변화의 관계를 단정적인 인과관계로 표현하지 않습니다.
- "가능한 요인", "관련 배경", "검토할 수 있다", "추가 확인이 필요하다" 중심으로 작성합니다.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

try:
    from src.ai.industry_analysis_rules import build_industry_analysis_instruction
except ModuleNotFoundError:
    from industry_analysis_rules import build_industry_analysis_instruction


# ---------------------------------------------------------------------
# 1. 공통 유틸
# ---------------------------------------------------------------------

def safe_text(value: Any) -> str:
    """
    None 또는 비문자열 값을 안전하게 문자열로 변환합니다.
    """

    if value is None:
        return ""

    return str(value)


def shorten_text(text: Any, max_length: int = 600) -> str:
    """
    LLM 입력이 너무 길어지지 않도록 텍스트를 자릅니다.
    """

    text = safe_text(text).strip()

    if not text:
        return ""

    if len(text) <= max_length:
        return text

    return text[:max_length] + "...(truncated)"


def compact_json(value: Any) -> str:
    """
    prompt 길이를 줄이기 위해 indent 없는 compact JSON 문자열로 변환합니다.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
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


def get_model_name(llm: Any) -> str:
    """
    ChatOpenAI 객체에서 모델명을 추출합니다.
    """

    return (
        getattr(llm, "model_name", None)
        or getattr(llm, "model", None)
        or "unknown"
    )


def get_company_name_from_context(financial_context: Dict[str, Any]) -> str:
    """
    financial_context에서 기업명을 추출합니다.
    """

    company_info = financial_context.get("company_info", {}) or {}

    return (
        company_info.get("company_name")
        or financial_context.get("company_name")
        or "기업"
    )


def resolve_industry_instruction(
    industry_info: Optional[Dict[str, Any]] = None,
    industry_analysis_instruction: Optional[str] = None,
) -> str:
    """
    Report Writer Chain에 전달할 산업별 분석 가이드를 결정합니다.
    """

    if industry_analysis_instruction:
        return industry_analysis_instruction

    if industry_info:
        return build_industry_analysis_instruction(industry_info)

    return """
산업별 분석 가이드:
- 별도의 업종 정보가 제공되지 않았습니다.
- 매출 성장성, 수익성, 안정성, 유동성, 현금흐름을 균형 있게 해석하세요.
- 입력 데이터와 근거 자료에 없는 요인은 임의로 추정하지 마세요.
- 투자 추천, 매수, 매도, 보유 판단은 작성하지 마세요.
""".strip()


def trim_industry_instruction(text: str, max_length: int = 1400) -> str:
    """
    산업별 분석 가이드가 너무 길어질 경우 핵심만 남깁니다.
    """

    return shorten_text(text, max_length=max_length)


# ---------------------------------------------------------------------
# 2. Prompt 입력 압축
# ---------------------------------------------------------------------

def prepare_financial_context_for_prompt(
    financial_context: Dict[str, Any],
    max_changes: int = 3,
    max_finance_years: int = 3,
    max_signals: int = 5,
) -> Dict[str, Any]:
    """
    LLM prompt에 넣을 financial_context를 핵심 필드 중심으로 압축합니다.
    """

    company_info = financial_context.get("company_info", {}) or {}
    industry_info = financial_context.get("industry_info", {}) or {}

    metric_highlights = financial_context.get("metric_highlights", []) or []
    detected_changes = financial_context.get("detected_changes", []) or []
    signals = financial_context.get("signals", []) or []
    finance_summary = financial_context.get("finance_summary", []) or []

    if not metric_highlights:
        metric_highlights = detected_changes

    prepared_changes = []

    for item in (metric_highlights or [])[:max_changes]:
        if not isinstance(item, dict):
            continue

        prepared_changes.append(
            {
                "metric_key": item.get("metric_key"),
                "metric_label": item.get("metric_label"),
                "year": item.get("year"),
                "base_year": item.get("base_year"),
                "current_value": item.get("current_value"),
                "base_value": item.get("base_value"),
                "yoy_change_rate": item.get("yoy_change_rate"),
                "change_type": item.get("change_type"),
                "direction": item.get("direction"),
                "severity": item.get("severity"),
                "signal_type": item.get("signal_type"),
                "description": shorten_text(item.get("description"), max_length=220),
            }
        )

    prepared_finance_summary = []

    for row in (finance_summary or [])[:max_finance_years]:
        if not isinstance(row, dict):
            continue

        prepared_finance_summary.append(
            {
                "year": row.get("year"),
                "revenue": row.get("revenue"),
                "operating_income": row.get("operating_income"),
                "net_income": row.get("net_income"),
                "total_assets": row.get("total_assets"),
                "total_liabilities": row.get("total_liabilities"),
                "total_equity": row.get("total_equity"),
                "debt_ratio": row.get("debt_ratio"),
                "current_ratio": row.get("current_ratio"),
                "operating_cash_flow": row.get("operating_cash_flow"),
            }
        )

    prepared_signals = []

    for item in (signals or [])[:max_signals]:
        if not isinstance(item, dict):
            continue

        prepared_signals.append(
            {
                "year": item.get("year"),
                "type": item.get("type") or item.get("signal_type"),
                "severity": item.get("severity"),
                "signal": item.get("signal") or item.get("signal_code"),
                "description": shorten_text(item.get("description"), max_length=180),
            }
        )

    return {
        "company_info": {
            "company_name": company_info.get("company_name"),
            "stock_code": company_info.get("stock_code"),
        },
        "industry_info": {
            "industry_group": industry_info.get("industry_group"),
            "industry_group_name": industry_info.get("industry_group_name"),
        },
        "analysis_year": financial_context.get("analysis_year"),
        "base_year": financial_context.get("base_year"),
        "summary": shorten_text(
            financial_context.get("summary")
            or financial_context.get("overall_summary")
            or financial_context.get("financial_summary"),
            max_length=450,
        ),
        "financial_change_summary": shorten_text(
            financial_context.get("financial_change_summary")
            or financial_context.get("detected_change_summary"),
            max_length=900,
        ),
        "yearly_finance_summary": shorten_text(
            financial_context.get("yearly_finance_summary"),
            max_length=900,
        ),
        "metric_highlights": prepared_changes,
        "finance_summary": prepared_finance_summary,
        "signals": prepared_signals,
    }


def prepare_evidence_news_for_prompt(
    evidence_news: List[Dict[str, Any]],
    max_items: int = 3,
) -> List[Dict[str, Any]]:
    """
    LLM 프롬프트에 넣을 뉴스 근거를 간결하게 정리합니다.
    """

    prepared = []

    for item in evidence_news[:max_items]:
        summary = (
            item.get("evidence_summary")
            or item.get("summary")
            or item.get("content")
            or item.get("reason")
            or ""
        )

        prepared.append(
            {
                "metric_key": item.get("metric_key"),
                "metric_label": item.get("metric_label"),
                "year": item.get("year"),
                "change_type": item.get("change_type"),
                "direction": item.get("direction"),
                "severity": item.get("severity"),
                "yoy_change_rate": item.get("yoy_change_rate"),
                "title": item.get("title", ""),
                "url": item.get("url") or item.get("source_url") or "",
                "published_date": item.get("published_date", ""),
                "evidence_summary": shorten_text(summary, max_length=450),
                "relevance_score": item.get("relevance_score"),
            }
        )

    return prepared


def prepare_evidence_disclosures_for_prompt(
    evidence_disclosures: Optional[List[Dict[str, Any]]] = None,
    max_items: int = 3,
) -> List[Dict[str, Any]]:
    """
    LLM 프롬프트에 넣을 공시 근거를 간결하게 정리합니다.
    """

    if not evidence_disclosures:
        return []

    prepared = []

    for item in evidence_disclosures[:max_items]:
        summary = (
            item.get("evidence_summary")
            or item.get("summary")
            or item.get("chunk_text")
            or ""
        )

        prepared.append(
            {
                "metric_key": item.get("metric_key"),
                "metric_label": item.get("metric_label"),
                "year": item.get("year"),
                "source_type": item.get("source_type", "disclosure"),
                "source": item.get("source", ""),
                "source_url": item.get("source_url", ""),
                "report_type": item.get("report_type", ""),
                "page": item.get("page", ""),
                "section": item.get("section", ""),
                "evidence_summary": shorten_text(summary, max_length=500),
                "relevance_score": item.get("relevance_score"),
            }
        )

    return prepared


# ---------------------------------------------------------------------
# 3. fallback
# ---------------------------------------------------------------------

def build_fallback_report(
    financial_context: Dict[str, Any],
    evidence_news: List[Dict[str, Any]],
    evidence_disclosures: Optional[List[Dict[str, Any]]] = None,
    industry_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    LLM 기반 리포트 생성 실패 시 사용할 fallback 리포트를 생성합니다.
    """

    company_name = get_company_name_from_context(financial_context)
    analysis_year = financial_context.get("analysis_year")
    base_year = financial_context.get("base_year")

    detected_change_summary = (
        financial_context.get("detected_change_summary")
        or financial_context.get("financial_change_summary")
        or ""
    )
    metric_summary_text = (
        financial_context.get("summary")
        or financial_context.get("overall_summary")
        or financial_context.get("financial_summary")
        or detected_change_summary
        or "주요 재무 변동이 확인되었습니다."
    )

    news_lines = []

    for item in evidence_news[:3]:
        metric_label = item.get("metric_label", "재무 지표")
        title = item.get("title", "")
        summary = item.get("evidence_summary", "") or item.get("summary", "")

        news_lines.append(
            f"- [{metric_label}] {title}: {shorten_text(summary, max_length=250)}"
        )

    news_summary = (
        "\n".join(news_lines)
        if news_lines
        else "현재 리포트 작성에 사용할 선별 뉴스 근거가 없습니다."
    )

    disclosure_count = len(evidence_disclosures or [])

    if disclosure_count == 0:
        disclosure_summary = "현재 공시/사업보고서 근거는 확인되지 않았습니다."
    else:
        disclosure_lines = []

        for item in (evidence_disclosures or [])[:3]:
            metric_label = item.get("metric_label", "재무 지표")
            source = item.get("source", "")
            summary = item.get("evidence_summary", "") or item.get("summary", "")

            disclosure_lines.append(
                f"- [{metric_label}] {source}: {shorten_text(summary, max_length=250)}"
            )

        disclosure_summary = "\n".join(disclosure_lines)

    industry_group_name = ""

    if industry_info:
        industry_group_name = industry_info.get("industry_group_name", "")

    industry_phrase = (
        f" {industry_group_name} 특성을 함께 고려해야 합니다."
        if industry_group_name
        else ""
    )

    return {
        "executive_summary": (
            f"{company_name}의 {analysis_year}년 재무 지표에서는 "
            f"{metric_summary_text} "
            "다만 제공된 재무 수치와 선별 근거를 기반으로 한 요약이므로 "
            f"단정적인 인과관계 판단은 제한됩니다.{industry_phrase}"
        ),
        "financial_change_summary": safe_text(detected_change_summary or metric_summary_text),
        "news_evidence_summary": news_summary,
        "disclosure_evidence_summary": disclosure_summary,
        "possible_causes": (
            "선별된 뉴스 및 공시 근거를 종합하면, 업황 변화, 수요 변화, 제품/사업 전략 등이 "
            "재무 변화와 관련된 가능한 배경 요인으로 검토될 수 있습니다. "
            "다만 직접적인 원인으로 단정할 수 없으며 추가 검증이 필요합니다."
        ),
        "interview_point": (
            "발표 또는 질의응답에서는 재무 수치 변화와 뉴스/공시 근거를 연결하되, "
            "외부 요인을 원인으로 단정하지 않고 관련 배경으로 해석했다는 점을 강조하면 좋습니다."
        ),
        "limitations": (
            "본 리포트는 제공된 재무 데이터와 선별 근거를 기반으로 생성되었습니다. "
            "뉴스 또는 공시 근거가 제한적일 수 있으며, 실제 공시 문서와 추가 자료 확인이 필요합니다."
        ),
        "source": "fallback",
        "metadata": {
            "company_name": company_name,
            "analysis_year": analysis_year,
            "base_year": base_year,
            "industry_group": (industry_info or {}).get("industry_group"),
            "industry_group_name": (industry_info or {}).get("industry_group_name"),
            "news_evidence_count": len(evidence_news),
            "disclosure_evidence_count": disclosure_count,
        },
    }


# ---------------------------------------------------------------------
# 4. Prompt / Chain
# ---------------------------------------------------------------------

REPORT_WRITER_SYSTEM_PROMPT = """
당신은 재무 분석 리포트를 작성하는 AI입니다.
반드시 JSON만 반환하세요. 마크다운, 코드블록, 설명 문장은 금지입니다.

원칙:
- 제공된 재무 문맥, 뉴스 근거, 공시 근거, 산업 가이드 안의 정보만 사용하세요.
- 재무 수치를 새로 계산하지 마세요.
- 뉴스/공시와 재무 변화의 관계를 직접 인과로 단정하지 마세요.
- "가능한 배경", "관련 요인", "검토할 수 있다", "추가 확인이 필요하다"처럼 신중하게 표현하세요.
- 투자 추천, 매수, 매도, 보유, 목표주가 판단은 절대 작성하지 마세요.
- 공시 근거가 없으면 없다고 쓰고, 리포트 생성은 계속하세요.
- 산업 가이드에 언급된 지표가 입력에 없으면 "추가 확인 필요"라고 쓰세요.

JSON 형식:
{{
  "executive_summary": "",
  "financial_change_summary": "",
  "news_evidence_summary": "",
  "disclosure_evidence_summary": "",
  "possible_causes": "",
  "interview_point": "",
  "limitations": ""
}}
"""


def build_report_writer_chain(llm):
    """
    공통 LLM 객체에 Report Writer 전용 prompt를 연결한 Chain을 생성합니다.
    """

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", REPORT_WRITER_SYSTEM_PROMPT),
            (
                "human",
                """
아래 입력만 사용해 최종 재무 분석 리포트 JSON을 생성하세요.

[재무 문맥]
{financial_context_json}

[뉴스 근거]
{evidence_news_json}

[공시 근거]
{evidence_disclosures_json}

[산업 정보]
{industry_info_json}

[산업 가이드]
{industry_analysis_instruction}
""",
            ),
        ]
    )

    return prompt | llm | StrOutputParser()


def clean_report_output(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM이 반환한 report JSON을 최종 필드 기준으로 정리합니다.
    """

    required_fields = [
        "executive_summary",
        "financial_change_summary",
        "news_evidence_summary",
        "disclosure_evidence_summary",
        "possible_causes",
        "interview_point",
        "limitations",
    ]

    cleaned = {}

    for field in required_fields:
        cleaned[field] = safe_text(report.get(field, "")).strip()

    return cleaned


# ---------------------------------------------------------------------
# 5. 대표 함수
# ---------------------------------------------------------------------

def generate_report(
    llm,
    financial_context: Dict[str, Any],
    evidence_news: List[Dict[str, Any]],
    evidence_disclosures: Optional[List[Dict[str, Any]]] = None,
    industry_info: Optional[Dict[str, Any]] = None,
    industry_analysis_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    LLM Chain을 사용해 최종 재무 분석 리포트를 생성합니다.
    """

    evidence_disclosures = evidence_disclosures or []
    industry_info = industry_info or financial_context.get("industry_info", {}) or {}

    resolved_industry_instruction = resolve_industry_instruction(
        industry_info=industry_info,
        industry_analysis_instruction=industry_analysis_instruction,
    )

    compact_financial_context = prepare_financial_context_for_prompt(
        financial_context=financial_context,
        max_changes=3,
        max_finance_years=3,
        max_signals=5,
    )
    prepared_news = prepare_evidence_news_for_prompt(
        evidence_news=evidence_news,
        max_items=3,
    )
    prepared_disclosures = prepare_evidence_disclosures_for_prompt(
        evidence_disclosures=evidence_disclosures,
        max_items=3,
    )

    chain = build_report_writer_chain(llm)

    try:
        raw_output = chain.invoke(
            {
                "financial_context_json": compact_json(compact_financial_context),
                "evidence_news_json": compact_json(prepared_news),
                "evidence_disclosures_json": compact_json(prepared_disclosures),
                "industry_info_json": compact_json(industry_info),
                "industry_analysis_instruction": trim_industry_instruction(
                    resolved_industry_instruction,
                    max_length=1400,
                ),
            }
        )

        parsed = extract_json_from_llm_output(raw_output)
        report = clean_report_output(parsed)
        report["source"] = "llm"
        report["metadata"] = {
            "news_evidence_count": len(evidence_news),
            "disclosure_evidence_count": len(evidence_disclosures),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "model": get_model_name(llm),
            "industry_group": industry_info.get("industry_group"),
            "industry_group_name": industry_info.get("industry_group_name"),
            "industry_instruction_applied": bool(resolved_industry_instruction),
            "prompt_compaction_applied": True,
            "prompt_news_count": len(prepared_news),
            "prompt_disclosure_count": len(prepared_disclosures),
        }

        return report

    except Exception as error:
        print(f"[WARN] LLM 기반 리포트 생성 실패. fallback report를 사용합니다: {error}")

        fallback_report = build_fallback_report(
            financial_context=financial_context,
            evidence_news=evidence_news,
            evidence_disclosures=evidence_disclosures,
            industry_info=industry_info,
        )

        fallback_report["metadata"]["generated_at"] = datetime.now().isoformat(timespec="seconds")
        fallback_report["metadata"]["model"] = get_model_name(llm)
        fallback_report["metadata"]["industry_instruction_applied"] = bool(resolved_industry_instruction)
        fallback_report["metadata"]["prompt_compaction_applied"] = True

        return fallback_report


def write_report(
    llm,
    financial_context: Dict[str, Any],
    evidence_news: List[Dict[str, Any]],
    evidence_disclosures: Optional[List[Dict[str, Any]]] = None,
    industry_info: Optional[Dict[str, Any]] = None,
    industry_analysis_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    generate_report()의 alias 함수입니다.
    """

    return generate_report(
        llm=llm,
        financial_context=financial_context,
        evidence_news=evidence_news,
        evidence_disclosures=evidence_disclosures,
        industry_info=industry_info,
        industry_analysis_instruction=industry_analysis_instruction,
    )


# ---------------------------------------------------------------------
# 6. 단독 실행 테스트
# ---------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from src.ai.llm_client import get_llm
        from src.ai.sample_report_data import get_sample_ai_input
        from src.ai.financial_context_builder import build_financial_context
        from src.ai.news_query_builder import build_news_queries
        from src.ai.news_search_cache_service import search_news_by_query_groups_cached
        from src.ai.news_evidence_filter import filter_evidence
    except ModuleNotFoundError:
        from llm_client import get_llm
        from sample_report_data import get_sample_ai_input
        from financial_context_builder import build_financial_context
        from news_query_builder import build_news_queries
        from news_search_cache_service import search_news_by_query_groups_cached
        from news_evidence_filter import filter_evidence

    llm = get_llm()

    sample_ai_input = get_sample_ai_input(case="warning")

    sample_ai_input["company_info"]["company_name"] = "삼성전자"
    sample_ai_input["company_info"]["stock_code"] = "005930"
    sample_ai_input["industry_info"] = {
        "industry_group": "tech_equipment",
        "industry_group_name": "기술 및 장치 산업",
    }
    sample_ai_input["analysis_year"] = 2023
    sample_ai_input["base_year"] = 2022

    for change in sample_ai_input.get("detected_changes", []):
        change["year"] = 2023
        change["base_year"] = 2022

    financial_context = build_financial_context(
        llm=llm,
        ai_input=sample_ai_input,
    )

    financial_context["industry_info"] = sample_ai_input.get("industry_info", {})

    query_groups = build_news_queries(
        ai_input=sample_ai_input,
        llm=llm,
    )

    searched_news = search_news_by_query_groups_cached(
        query_groups=query_groups,
        ai_input=sample_ai_input,
        max_results_per_query=3,
        max_total_results=10,
    )

    evidence = filter_evidence(
        llm=llm,
        ai_input=sample_ai_input,
        financial_context=financial_context,
        searched_news=searched_news,
    )

    report = generate_report(
        llm=llm,
        financial_context=financial_context,
        evidence_news=evidence.get("evidence_news", []),
        evidence_disclosures=evidence.get("evidence_disclosures", []),
        industry_info=sample_ai_input.get("industry_info", {}),
    )

    print("[Fast Report Writer Chain Test]")
    print("evidence_news_count:", len(evidence.get("evidence_news", [])))
    print("evidence_disclosure_count:", len(evidence.get("evidence_disclosures", [])))
    print("prompt_compaction_applied:", report.get("metadata", {}).get("prompt_compaction_applied"))

    print("\n[Report]")
    print(json.dumps(report, ensure_ascii=False, indent=2))
