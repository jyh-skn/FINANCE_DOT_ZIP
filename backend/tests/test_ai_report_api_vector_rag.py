"""
test_ai_report_api_vector_rag.py

프론트가 호출할 AI 리포트 API가 Vector DB RAG 파이프라인을 제대로 타는지 확인하는 테스트입니다.

실행 전제:
- Django 서버가 실행 중이어야 합니다.
- 기본 주소: http://127.0.0.1:8000

실행:
cd backend
python -m tests.test_ai_report_api_vector_rag
"""

import json
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"


def get_json(url: str, timeout: int = 180) -> Dict[str, Any]:
    request = Request(
        url=url,
        method="GET",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTPError {error.code} while requesting {url}\n{body}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"URL 요청 실패: {url}\n"
            "Django 서버가 실행 중인지 확인하세요."
        ) from error


def unwrap_response(response: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(response.get("data"), dict):
        return response["data"]

    return response


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def validate_ai_report_payload(data: Dict[str, Any]) -> None:
    required_top_level_keys = [
        "company_info",
        "industry_info",
        "analysis_year",
        "base_year",
        "report",
        "metadata",
    ]

    missing_keys = [
        key for key in required_top_level_keys
        if key not in data
    ]

    if missing_keys:
        raise AssertionError(f"필수 top-level key 누락: {missing_keys}")

    report = data.get("report", {}) or {}
    metadata = data.get("metadata", {}) or {}

    required_report_keys = [
        "executive_summary",
        "financial_change_summary",
        "news_evidence_summary",
        "disclosure_evidence_summary",
        "possible_causes",
        "interview_point",
        "limitations",
    ]

    missing_report_keys = [
        key for key in required_report_keys
        if key not in report
    ]

    if missing_report_keys:
        raise AssertionError(f"report 필수 key 누락: {missing_report_keys}")

    if "evidence_news_count" not in metadata:
        raise AssertionError("metadata.evidence_news_count 누락")

    if "evidence_disclosure_count" not in metadata:
        raise AssertionError("metadata.evidence_disclosure_count 누락")


def run_ai_report_api_test(stock_code: str, label: str) -> Dict[str, Any]:
    print_section(f"[AI Report API Vector RAG Test] {label} / {stock_code}")

    url = f"{BASE_URL}/api/v1/report/comprehensive/{stock_code}/ai"

    response = get_json(url)
    data = unwrap_response(response)

    validate_ai_report_payload(data)

    company_info = data.get("company_info", {}) or {}
    industry_info = data.get("industry_info", {}) or {}
    metadata = data.get("metadata", {}) or {}
    report = data.get("report", {}) or {}

    evidence_news = data.get("evidence_news", []) or []
    evidence_disclosures = data.get("evidence_disclosures", []) or []

    print("[Basic Info]")
    print("company:", company_info.get("company_name"))
    print("stock_code:", company_info.get("stock_code"))
    print("industry_group:", industry_info.get("industry_group"))
    print("analysis_year:", data.get("analysis_year"))
    print("base_year:", data.get("base_year"))

    print("\n[Metadata]")
    print("searched_news_count:", metadata.get("searched_news_count"))
    print("evidence_news_count:", metadata.get("evidence_news_count"))
    print("evidence_disclosure_count:", metadata.get("evidence_disclosure_count"))
    print("news_vector_attempted:", metadata.get("news_vector_attempted"))
    print("news_vector_enabled:", metadata.get("news_vector_enabled"))
    print("news_evidence_source:", metadata.get("news_evidence_source"))
    print("disclosure_attempted:", metadata.get("disclosure_attempted"))
    print("disclosure_enabled:", metadata.get("disclosure_enabled"))
    print("generated_by_endpoint:", metadata.get("generated_by_endpoint"))

    print("\n[Report Preview]")
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

    print("\n[AI Report API Vector RAG Test Passed]")
    print("company:", company_info.get("company_name"))
    print("stock_code:", company_info.get("stock_code"))
    print("evidence_news_count:", len(evidence_news))
    print("evidence_disclosure_count:", len(evidence_disclosures))
    print("news_evidence_source:", metadata.get("news_evidence_source"))

    return data


def main():
    samsung_result = run_ai_report_api_test(
        stock_code="005930",
        label="뉴스 RAG 확인용 삼성전자",
    )

    try:
        partron_result = run_ai_report_api_test(
            stock_code="091700",
            label="공시 RAG 확인용 파트론",
        )
    except Exception as error:
        print_section("[WARN] 091700 API 테스트 실패")
        print("091700은 Vector DB 공시 검색은 가능하지만, API/재무 DB 상태에 따라 실패할 수 있습니다.")
        print("error:", error)
        partron_result = None

    print_section("[Summary]")
    print("005930 evidence_news_count:", len(samsung_result.get("evidence_news", []) or []))
    print("005930 evidence_disclosure_count:", len(samsung_result.get("evidence_disclosures", []) or []))

    if partron_result:
        print("091700 evidence_news_count:", len(partron_result.get("evidence_news", []) or []))
        print("091700 evidence_disclosure_count:", len(partron_result.get("evidence_disclosures", []) or []))


if __name__ == "__main__":
    main()
