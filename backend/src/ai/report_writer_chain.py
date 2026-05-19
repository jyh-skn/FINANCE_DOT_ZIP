"""
report_writer_chain.py

재무 문맥, 뉴스 근거, 공시 근거, 산업별 분석 가이드를 바탕으로
최종 AI 재무 분석 리포트를 생성하는 Report Writer Chain 모듈입니다.

역할:
1. financial_context_builder.py의 financial_context를 입력받습니다.
2. news_evidence_filter.py의 evidence_news를 입력받습니다.
3. 추후 disclosure_retriever.py의 evidence_disclosures를 함께 입력받을 수 있도록 구조를 열어둡니다.
4. industry_analysis_rules.py의 industry_analysis_instruction을 받아 업종별 해석 기준을 반영합니다.
5. 공통 LLM 객체를 사용해 최종 분석 리포트를 JSON 형태로 생성합니다.

주의:
- disclosure_retriever.py는 아직 구현되지 않았으므로 evidence_disclosures는 빈 리스트일 수 있습니다.
- 투자 추천, 매수, 매도, 보유 판단을 하지 않습니다.
- 뉴스와 재무 변화의 관계를 단정적인 인과관계로 표현하지 않습니다.
- "가능한 요인", "관련 배경", "추정된다", "추가 확인이 필요하다" 중심으로 작성합니다.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

try:
    from src.ai.industry_analysis_rules import build_industry_analysis_instruction
except ModuleNotFoundError:
    from industry_analysis_rules import build_industry_analysis_instruction


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


def safe_text(value: Any) -> str:
    """
    None 또는 비문자열 값을 안전하게 문자열로 변환합니다.
    """

    if value is None:
        return ""

    return str(value)


def shorten_text(text: str, max_length: int = 1500) -> str:
    """
    LLM 입력이 너무 길어지지 않도록 텍스트를 자릅니다.
    """

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


def prepare_evidence_news_for_prompt(
    evidence_news: List[Dict[str, Any]],
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    """
    LLM 프롬프트에 넣을 뉴스 근거를 간결하게 정리합니다.
    """

    prepared = []

    for item in evidence_news[:max_items]:
        prepared.append(
            {
                "metric_key": item.get("metric_key"),
                "metric_label": item.get("metric_label"),
                "year": item.get("year"),
                "base_year": item.get("base_year"),
                "change_type": item.get("change_type"),
                "direction": item.get("direction"),
                "severity": item.get("severity"),
                "yoy_change_rate": item.get("yoy_change_rate"),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": shorten_text(
                    safe_text(item.get("content")),
                    max_length=800,
                ),
                "published_date": item.get("published_date", ""),
                "evidence_summary": item.get("evidence_summary", ""),
                "relevance_score": item.get("relevance_score"),
                "reason": item.get("reason", ""),
                "source": item.get("source", ""),
            }
        )

    return prepared


def prepare_evidence_disclosures_for_prompt(
    evidence_disclosures: Optional[List[Dict[str, Any]]] = None,
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    """
    LLM 프롬프트에 넣을 공시 근거를 간결하게 정리합니다.
    """

    if not evidence_disclosures:
        return []

    prepared = []

    for item in evidence_disclosures[:max_items]:
        prepared.append(
            {
                "metric_key": item.get("metric_key"),
                "metric_label": item.get("metric_label"),
                "year": item.get("year"),
                "source_type": item.get("source_type", "disclosure"),
                "source": item.get("source", ""),
                "report_type": item.get("report_type", ""),
                "page": item.get("page", ""),
                "section": item.get("section", ""),
                "chunk_text": shorten_text(
                    safe_text(item.get("chunk_text")),
                    max_length=900,
                ),
                "evidence_summary": item.get("evidence_summary", ""),
                "relevance_score": item.get("relevance_score"),
            }
        )

    return prepared


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

    detected_change_summary = financial_context.get("detected_change_summary", "")
    metric_summary = financial_context.get("metric_summary", "")

    if isinstance(metric_summary, dict):
        metric_summary_text = "\n".join(
            f"- {key}: {value}"
            for key, value in metric_summary.items()
        )
    else:
        metric_summary_text = safe_text(metric_summary)

    news_lines = []

    for item in evidence_news[:5]:
        metric_label = item.get("metric_label", "재무 지표")
        title = item.get("title", "")
        summary = item.get("evidence_summary", "")

        news_lines.append(
            f"- [{metric_label}] {title}: {summary}"
        )

    if not news_lines:
        news_summary = "현재 리포트 작성에 사용할 선별 뉴스 근거가 없습니다."
    else:
        news_summary = "\n".join(news_lines)

    disclosure_count = len(evidence_disclosures or [])

    if disclosure_count == 0:
        disclosure_summary = (
            "현재 공시/사업보고서 기반 RAG 근거는 연결되지 않았습니다. "
            "Vector DB 연결 후 공시 근거가 추가될 수 있습니다."
        )
    else:
        disclosure_lines = []

        for item in (evidence_disclosures or [])[:5]:
            metric_label = item.get("metric_label", "재무 지표")
            source = item.get("source", "")
            summary = item.get("evidence_summary", "")

            disclosure_lines.append(
                f"- [{metric_label}] {source}: {summary}"
            )

        disclosure_summary = "\n".join(disclosure_lines)

    industry_group_name = ""

    if industry_info:
        industry_group_name = industry_info.get("industry_group_name", "")

    industry_phrase = (
        f" 또한 {industry_group_name} 특성을 고려한 해석이 필요합니다."
        if industry_group_name
        else ""
    )

    return {
        "executive_summary": (
            f"{company_name}의 {analysis_year}년 재무 지표에서는 "
            f"{detected_change_summary or '일부 주요 변동이 확인되었습니다.'} "
            "다만 현재 리포트는 제공된 재무 수치와 선별된 근거를 기반으로 한 요약이며, "
            "단정적인 인과관계 판단은 제한됩니다."
            f"{industry_phrase}"
        ),
        "financial_change_summary": metric_summary_text,
        "news_evidence_summary": news_summary,
        "disclosure_evidence_summary": disclosure_summary,
        "possible_causes": (
            "선별된 뉴스 및 공시 근거를 종합하면, 업황 변화, 수요 둔화, 수익성 악화 등이 "
            "재무 변화와 관련된 가능한 배경 요인으로 검토될 수 있습니다. "
            "다만 이는 직접적인 원인으로 단정할 수 없으며 추가 검증이 필요합니다."
        ),
        "interview_point": (
            "발표 또는 질의응답에서는 재무 수치 변화와 뉴스/공시 근거를 연결하되, "
            "외부 요인을 원인으로 단정하지 않고 관련 배경으로 해석했다는 점을 강조하면 좋습니다."
        ),
        "limitations": (
            "본 리포트는 제공된 재무 데이터와 선별 근거를 기반으로 생성되었습니다. "
            "공시 RAG 근거가 부족하거나 연결되지 않은 경우, 최종 분석에서는 실제 공시 문서와 "
            "뉴스 전처리 결과를 함께 검토해야 합니다."
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


REPORT_WRITER_SYSTEM_PROMPT = """
당신은 재무 분석 리포트를 작성하는 전문가입니다.

목표:
- 제공된 재무 문맥, 뉴스 근거, 공시 근거, 산업별 분석 가이드를 바탕으로 최종 재무 분석 리포트를 작성합니다.
- 리포트는 백엔드와 프론트엔드에서 바로 사용할 수 있는 JSON 형태로 반환합니다.

중요 원칙:
1. 반드시 JSON만 반환하세요.
2. 마크다운, 설명 문장, 코드블록은 출력하지 마세요.
3. 제공된 financial_context, evidence_news, evidence_disclosures, industry_analysis_instruction 안의 정보만 사용하세요.
4. 재무 수치를 새로 계산하지 마세요.
5. 뉴스와 공시, 재무 변화의 관계를 직접적인 인과관계로 단정하지 마세요.
6. "가능한 요인", "관련 배경", "추정된다", "검토할 수 있다", "추가 확인이 필요하다"와 같은 표현을 사용하세요.
7. 투자 추천, 매수, 매도, 보유, 목표주가 판단을 절대 작성하지 마세요.
8. 공시 근거가 없으면 없다고 명확히 쓰되, 리포트 생성을 중단하지 마세요.
9. 뉴스 근거가 부족하면 한계점에 명시하세요.
10. 과도하게 단정적이거나 과장된 표현을 피하세요.
11. 산업별 분석 가이드는 해석 우선순위로만 사용하세요.
12. 산업별 분석 가이드에 언급된 지표가 입력 데이터에 없으면 임의로 추정하지 말고 추가 확인이 필요하다고 작성하세요.
13. 수치 또는 변화율이 N/A, None, null인 경우 증가/감소로 단정하지 말고 "정확한 변화율은 제공되지 않았습니다"라고 작성하세요.

작성 형식:
- executive_summary: 전체 요약
- financial_change_summary: 주요 재무 변화 요약
- news_evidence_summary: 뉴스 근거 요약
- disclosure_evidence_summary: 공시 근거 요약
- possible_causes: 가능한 배경 요인
- interview_point: 발표나 질의응답에서 강조할 포인트
- limitations: 한계 및 주의사항

반환 JSON 형식:
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
다음 정보를 바탕으로 최종 재무 분석 리포트 JSON을 생성하세요.

재무 문맥:
{financial_context_json}

뉴스 근거:
{evidence_news_json}

공시 근거:
{evidence_disclosures_json}

산업 정보:
{industry_info_json}

산업별 분석 가이드:
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
        cleaned[field] = safe_text(report.get(field, ""))

    return cleaned


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

    prepared_news = prepare_evidence_news_for_prompt(
        evidence_news=evidence_news,
        max_items=5,
    )

    prepared_disclosures = prepare_evidence_disclosures_for_prompt(
        evidence_disclosures=evidence_disclosures,
        max_items=5,
    )

    chain = build_report_writer_chain(llm)

    try:
        raw_output = chain.invoke(
            {
                "financial_context_json": json.dumps(
                    financial_context,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "evidence_news_json": json.dumps(
                    prepared_news,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "evidence_disclosures_json": json.dumps(
                    prepared_disclosures,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "industry_info_json": json.dumps(
                    industry_info,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "industry_analysis_instruction": resolved_industry_instruction,
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


if __name__ == "__main__":
    try:
        from src.ai.llm_client import get_llm
        from src.ai.sample_report_data import get_sample_ai_input
        from src.ai.financial_context_builder import build_financial_context
        from src.ai.news_query_builder import build_news_queries
        from src.ai.news_search_service import search_news_by_query_groups
        from src.ai.news_evidence_filter import filter_evidence
    except ModuleNotFoundError:
        from llm_client import get_llm
        from sample_report_data import get_sample_ai_input
        from financial_context_builder import build_financial_context
        from news_query_builder import build_news_queries
        from news_search_service import search_news_by_query_groups
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

    searched_news = search_news_by_query_groups(
        query_groups=query_groups,
        max_results_per_query=5,
        max_total_results=20,
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

    print("[Report Writer Chain Test]")
    print("evidence_news_count:", len(evidence.get("evidence_news", [])))
    print("evidence_disclosure_count:", len(evidence.get("evidence_disclosures", [])))

    print("\n[Report]")
    print(json.dumps(report, ensure_ascii=False, indent=2))
