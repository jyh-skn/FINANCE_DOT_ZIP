"""
test_report_chat_api_vector_rag.py

프론트 흐름 기준으로 AI 리포트 생성 후 챗봇 API가
Vector DB 뉴스/공시 근거를 활용해 답변하는지 확인하는 테스트입니다.

테스트 흐름:
1. GET /api/v1/report/comprehensive/{stock_code}/ai
   - AI 리포트 생성
   - evidence_news / evidence_disclosures 포함 여부 확인

2. POST /api/v1/report/comprehensive/{stock_code}/chat
   - question + ai_report_result 전달
   - 챗봇이 리포트를 재생성하지 않고 기존 ai_report_result 기반으로 답변하는지 확인
   - used_sources에 ai_report/news/disclosure가 포함되는지 확인

실행 전제:
- Django 서버가 실행 중이어야 합니다.
- 기본 주소: http://127.0.0.1:8000

실행:
cd backend
python -m tests.test_report_chat_api_vector_rag
"""

import json
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"


def print_section(title: str) -> None:
    print("\\n" + "=" * 80)
    print(title)
    print("=" * 80)


def unwrap_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    API 응답이 {"status": "...", "data": {...}} 형태이거나
    바로 data 형태로 오는 경우를 모두 처리합니다.
    """

    if isinstance(response.get("data"), dict):
        return response["data"]

    return response


def request_json(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 240,
) -> Dict[str, Any]:
    """
    JSON API 요청 공통 함수입니다.
    """

    body = None

    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = Request(
        url=url,
        data=body,
        method=method,
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
        body_text = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTPError {error.code} while requesting {url}\\n{body_text}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"URL 요청 실패: {url}\\n"
            "Django 서버가 실행 중인지 확인하세요."
        ) from error


def get_ai_report(stock_code: str) -> Dict[str, Any]:
    """
    AI 리포트 API를 호출합니다.
    """

    url = f"{BASE_URL}/api/v1/report/comprehensive/{stock_code}/ai"
    response = request_json(url=url, method="GET")
    return unwrap_response(response)


def post_report_chat(
    stock_code: str,
    question: str,
    ai_report_result: Dict[str, Any],
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    챗봇 API를 호출합니다.
    """

    url = f"{BASE_URL}/api/v1/report/comprehensive/{stock_code}/chat"

    payload = {
        "question": question,
        "ai_report_result": ai_report_result,
    }

    if chat_history is not None:
        payload["chat_history"] = chat_history

    response = request_json(
        url=url,
        method="POST",
        payload=payload,
        timeout=180,
    )

    return unwrap_response(response)


def summarize_ai_report(ai_report_result: Dict[str, Any]) -> None:
    """
    AI 리포트 응답 요약을 출력합니다.
    """

    company_info = ai_report_result.get("company_info", {}) or {}
    metadata = ai_report_result.get("metadata", {}) or {}

    evidence_news = ai_report_result.get("evidence_news", []) or []
    evidence_disclosures = ai_report_result.get("evidence_disclosures", []) or []

    print("[AI Report Result]")
    print("company:", company_info.get("company_name"))
    print("stock_code:", company_info.get("stock_code"))
    print("analysis_year:", ai_report_result.get("analysis_year"))
    print("base_year:", ai_report_result.get("base_year"))
    print("evidence_news_count:", len(evidence_news))
    print("evidence_disclosure_count:", len(evidence_disclosures))
    print("news_vector_enabled:", metadata.get("news_vector_enabled"))
    print("news_evidence_source:", metadata.get("news_evidence_source"))
    print("disclosure_enabled:", metadata.get("disclosure_enabled"))


def summarize_chat_response(question: str, chat_response: Dict[str, Any]) -> None:
    """
    챗봇 응답 요약을 출력합니다.
    """

    used_sources = chat_response.get("used_sources", []) or []
    metadata = chat_response.get("metadata", {}) or {}

    print("\\n[Question]")
    print(question)

    print("\\n[Answer]")
    print(chat_response.get("answer"))

    print("\\n[Chat Metadata]")
    print("used_source_count:", len(used_sources))
    print("generated_ai_report_inside_chat:", metadata.get("generated_ai_report_inside_chat"))
    print("received_ai_report_result:", metadata.get("received_ai_report_result"))
    print("source:", metadata.get("source"))

    print("\\n[Used Sources]")
    for idx, source in enumerate(used_sources, start=1):
        print(f"- source_{idx}:")
        print("  source_type:", source.get("source_type"))
        print("  title:", source.get("title") or source.get("source"))
        print("  url:", source.get("url") or source.get("source_url"))
        print("  metric:", source.get("metric_label"))
        print("  summary:", (source.get("summary") or source.get("reason") or "")[:300])

    print("\\n[Limitations]")
    print(chat_response.get("limitations"))


def validate_chat_response(chat_response: Dict[str, Any]) -> None:
    """
    챗봇 응답 필수 필드를 검증합니다.
    """

    required_keys = [
        "answer",
        "used_sources",
        "limitations",
        "metadata",
    ]

    missing_keys = [
        key for key in required_keys
        if key not in chat_response
    ]

    if missing_keys:
        raise AssertionError(f"챗봇 응답 필수 key 누락: {missing_keys}")

    if not chat_response.get("answer"):
        raise AssertionError("챗봇 answer가 비어 있습니다.")

    if not isinstance(chat_response.get("used_sources"), list):
        raise AssertionError("used_sources는 list여야 합니다.")


def run_chat_api_vector_rag_test(stock_code: str, label: str, questions: List[str]) -> None:
    """
    특정 종목 기준으로 AI 리포트 생성 후 챗봇 질문 테스트를 실행합니다.
    """

    print_section(f"[Report Chat API Vector RAG Test] {label} / {stock_code}")

    ai_report_result = get_ai_report(stock_code)
    summarize_ai_report(ai_report_result)

    chat_history: List[Dict[str, str]] = []

    for question in questions:
        chat_response = post_report_chat(
            stock_code=stock_code,
            question=question,
            ai_report_result=ai_report_result,
            chat_history=chat_history,
        )

        validate_chat_response(chat_response)
        summarize_chat_response(question, chat_response)

        chat_history.append(
            {
                "role": "user",
                "content": question,
            }
        )
        chat_history.append(
            {
                "role": "assistant",
                "content": chat_response.get("answer", ""),
            }
        )

    print("\\n[Report Chat API Vector RAG Test Passed]")
    print("stock_code:", stock_code)
    print("question_count:", len(questions))


def main() -> None:
    """
    뉴스와 공시가 모두 나오는 파트론 기준으로 챗봇 API를 우선 검증합니다.
    삼성전자는 공시 chunk가 없으므로 뉴스 RAG 기반 챗봇 확인용으로만 사용합니다.
    """

    run_chat_api_vector_rag_test(
        stock_code="091700",
        label="뉴스/공시 RAG 확인용 파트론",
        questions=[
            "파트론의 2021년 영업이익이 왜 증가했어?",
            "뉴스 근거와 공시 근거를 나눠서 설명해줘.",
            "공시 근거는 영업이익 증가와 직접 관련이 있어?",
        ],
    )

    run_chat_api_vector_rag_test(
        stock_code="005930",
        label="뉴스 RAG 확인용 삼성전자",
        questions=[
            "삼성전자의 주요 재무 변화는 뭐야?",
            "뉴스 근거를 중심으로 설명해줘.",
        ],
    )


if __name__ == "__main__":
    main()
