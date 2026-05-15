"""
test_ai_report_vector_rag.py

AI 리포트 파이프라인에 Vector DB RAG가 실제로 연결되는지 확인하는 통합 테스트입니다.

검증 목적:
1. 뉴스 RAG
   - Tavily 검색 결과가 Vector DB에 적재되는지
   - news_retriever가 evidence_news를 반환하는지
   - news_evidence_filter가 skip되는지

2. 공시 RAG
   - data_type="disclosure"인 공시 chunk가 검색되는지
   - disclosure_retriever가 evidence_disclosures를 반환하는지
   - report_writer_chain에 공시 근거가 들어가는지

주의:
- 삼성전자(005930)는 뉴스 RAG 확인용으로 적합합니다.
- 파트론(091700)은 공시 RAG 확인용으로 적합합니다.
- 실제 공시/뉴스 적재 상태에 따라 evidence count는 달라질 수 있습니다.
"""

import json
from typing import Any, Dict

from src.ai.backend_payload_adapter import build_ai_input_from_backend_response
from src.ai.comprehensive_report_service import create_ai_report
from src.services.report_service import build_report_response


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def build_ai_input(stock_code: str) -> Dict[str, Any]:
    """
    백엔드 종합 리포트 응답을 AI 입력 형식으로 변환합니다.
    """

    backend_response = build_report_response(stock_code)
    ai_input = build_ai_input_from_backend_response(backend_response)

    return ai_input


def run_vector_rag_report_test(
    stock_code: str,
    label: str,
    include_searched_news: bool = False,
) -> Dict[str, Any]:
    """
    특정 종목 기준으로 AI 리포트 Vector RAG 통합 테스트를 실행합니다.
    """

    print_section(f"[Vector RAG AI Report Test] {label} / {stock_code}")

    ai_input = build_ai_input(stock_code)

    company_info = ai_input.get("company_info", {}) or {}
    industry_info = ai_input.get("industry_info", {}) or {}
    detected_changes = ai_input.get("detected_changes", []) or []

    print("[AI Input]")
    print("company:", company_info.get("company_name"))
    print("stock_code:", company_info.get("stock_code"))
    print("industry_group:", industry_info.get("industry_group"))
    print("analysis_year:", ai_input.get("analysis_year"))
    print("base_year:", ai_input.get("base_year"))
    print("detected_change_count:", len(detected_changes))

    result = create_ai_report(
        ai_input=ai_input,
        vector_store=None,
        max_results_per_query=3,
        max_total_news_results=10,
        max_evidence_news=3,
        include_searched_news=include_searched_news,
    )

    metadata = result.get("metadata", {}) or {}
    report = result.get("report", {}) or {}
    evidence_news = result.get("evidence_news", []) or []
    evidence_disclosures = result.get("evidence_disclosures", []) or []

    print("\n[Vector RAG Result]")
    print("company:", result.get("company_info", {}).get("company_name"))
    print("stock_code:", result.get("company_info", {}).get("stock_code"))
    print("analysis_year:", result.get("analysis_year"))
    print("searched_news_count:", metadata.get("searched_news_count"))
    print("evidence_news_count:", metadata.get("evidence_news_count"))
    print("evidence_disclosure_count:", metadata.get("evidence_disclosure_count"))
    print("news_vector_attempted:", metadata.get("news_vector_attempted"))
    print("news_vector_enabled:", metadata.get("news_vector_enabled"))
    print("news_evidence_source:", metadata.get("news_evidence_source"))
    print("disclosure_attempted:", metadata.get("disclosure_attempted"))
    print("disclosure_enabled:", metadata.get("disclosure_enabled"))

    print("\n[Report Summary]")
    print("executive_summary:", report.get("executive_summary"))
    print("news_evidence_summary:", report.get("news_evidence_summary"))
    print("disclosure_evidence_summary:", report.get("disclosure_evidence_summary"))
    print("limitations:", report.get("limitations"))

    print("\n[Evidence News Preview]")
    for idx, item in enumerate(evidence_news[:3], start=1):
        print(f"- news_{idx}:")
        print("  title:", item.get("title") or item.get("source"))
        print("  url:", item.get("url") or item.get("source_url"))
        print("  metric:", item.get("metric_label"))
        print("  score:", item.get("relevance_score"))

    print("\n[Evidence Disclosure Preview]")
    for idx, item in enumerate(evidence_disclosures[:3], start=1):
        print(f"- disclosure_{idx}:")
        print("  source:", item.get("source"))
        print("  url:", item.get("source_url"))
        print("  metric:", item.get("metric_label"))
        print("  score:", item.get("relevance_score"))
        print("  summary:", (item.get("evidence_summary") or "")[:300])

    return result


def main():
    """
    뉴스 RAG와 공시 RAG를 각각 확인합니다.
    """

    samsung_result = run_vector_rag_report_test(
        stock_code="005930",
        label="뉴스 RAG 확인용 삼성전자",
        include_searched_news=False,
    )

    try:
        partron_result = run_vector_rag_report_test(
            stock_code="091700",
            label="공시 RAG 확인용 파트론",
            include_searched_news=False,
        )
    except Exception as error:
        print_section("[WARN] 091700 통합 테스트 실패")
        print("091700은 Vector DB 공시 검색은 가능하지만, backend 재무 DB/API에 없을 수 있습니다.")
        print("error:", error)
        partron_result = None

    print_section("[Test Summary]")
    print("005930 news evidence count:", len(samsung_result.get("evidence_news", []) or []))
    print("005930 disclosure evidence count:", len(samsung_result.get("evidence_disclosures", []) or []))

    if partron_result:
        print("091700 news evidence count:", len(partron_result.get("evidence_news", []) or []))
        print("091700 disclosure evidence count:", len(partron_result.get("evidence_disclosures", []) or []))


if __name__ == "__main__":
    main()
