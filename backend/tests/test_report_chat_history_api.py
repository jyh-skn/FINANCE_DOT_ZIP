"""
test_report_chat_history_api.py

챗봇 API가 chat_history를 활용해 후속 질문에 답변할 수 있는지 확인하는 테스트입니다.

테스트 흐름:
1. /ai API로 AI 리포트를 먼저 생성합니다.
2. /chat API에 첫 번째 질문을 보냅니다.
3. 첫 번째 답변을 chat_history에 저장합니다.
4. "방금 답변에서", "두 번째 뉴스"처럼 이전 답변을 참조하는 후속 질문을 보냅니다.
5. 챗봇이 기존 ai_report_result와 chat_history를 함께 참고하는지 확인합니다.

실행 전제:
- Django 서버 실행 필요
- report_chat API가 request.data["chat_history"]를 받아 report_chat_chain까지 전달해야 합니다.

실행:
cd backend
python -m tests.test_report_chat_history_api
"""

import json
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def unwrap_response(response: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(response.get("data"), dict):
        return response["data"]

    return response


def request_json(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 240,
) -> Dict[str, Any]:
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
            f"HTTPError {error.code} while requesting {url}\n{body_text}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"URL 요청 실패: {url}\n"
            "Django 서버가 실행 중인지 확인하세요."
        ) from error


def get_ai_report(stock_code: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/api/v1/report/comprehensive/{stock_code}/ai"
    response = request_json(url=url, method="GET")
    return unwrap_response(response)


def post_report_chat(
    stock_code: str,
    question: str,
    ai_report_result: Dict[str, Any],
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    url = f"{BASE_URL}/api/v1/report/comprehensive/{stock_code}/chat"

    payload = {
        "question": question,
        "ai_report_result": ai_report_result,
        "chat_history": chat_history or [],
    }

    response = request_json(
        url=url,
        method="POST",
        payload=payload,
        timeout=180,
    )

    return unwrap_response(response)


def print_chat_turn(
    question: str,
    response: Dict[str, Any],
) -> None:
    used_sources = response.get("used_sources", []) or []
    metadata = response.get("metadata", {}) or {}

    print("\n[Question]")
    print(question)

    print("\n[Answer]")
    print(response.get("answer"))

    print("\n[Metadata]")
    print("used_source_count:", len(used_sources))
    print("received_ai_report_result:", metadata.get("received_ai_report_result"))
    print("generated_ai_report_inside_chat:", metadata.get("generated_ai_report_inside_chat"))
    print("chat_history_used:", metadata.get("chat_history_used"))
    print("chat_history_count:", metadata.get("chat_history_count"))
    print("prompt_compaction_applied:", metadata.get("prompt_compaction_applied"))

    print("\n[Used Sources]")
    for idx, source in enumerate(used_sources, start=1):
        print(f"- source_{idx}:")
        print("  source_type:", source.get("source_type"))
        print("  title:", source.get("title") or source.get("source"))
        print("  metric:", source.get("metric_label"))
        print("  url:", source.get("url") or source.get("source_url"))

    print("\n[Limitations]")
    print(response.get("limitations"))


def validate_chat_response(response: Dict[str, Any]) -> None:
    if not response.get("answer"):
        raise AssertionError("answer가 비어 있습니다.")

    if not isinstance(response.get("used_sources", []), list):
        raise AssertionError("used_sources는 list여야 합니다.")


def main() -> None:
    stock_code = "091700"

    print_section("[Chat History API Test] 파트론 / 091700")

    ai_report_result = get_ai_report(stock_code)

    print("[AI Report]")
    print("company:", (ai_report_result.get("company_info", {}) or {}).get("company_name"))
    print("stock_code:", (ai_report_result.get("company_info", {}) or {}).get("stock_code"))
    print("evidence_news_count:", len(ai_report_result.get("evidence_news", []) or []))
    print("evidence_disclosure_count:", len(ai_report_result.get("evidence_disclosures", []) or []))

    chat_history: List[Dict[str, str]] = []

    questions = [
        "파트론의 2021년 영업이익이 왜 증가했어?",
        "방금 답변에서 말한 뉴스 근거를 조금 더 자세히 설명해줘.",
        "그럼 두 번째 뉴스는 어떤 의미가 있어?",
        "공시 근거는 영업이익 증가와 직접 관련이 있다고 볼 수 있어?",
    ]

    for question in questions:
        start_time = time.perf_counter()

        response = post_report_chat(
            stock_code=stock_code,
            question=question,
            ai_report_result=ai_report_result,
            chat_history=chat_history,
        )

        elapsed = time.perf_counter() - start_time
        print(f"\n[CHAT_API_TIME] {elapsed:.2f}s")

        validate_chat_response(response)
        print_chat_turn(question, response)

        chat_history.append(
            {
                "role": "user",
                "content": question,
            }
        )
        chat_history.append(
            {
                "role": "assistant",
                "content": response.get("answer", ""),
            }
        )

    print("\n[Chat History API Test Passed]")
    print("stock_code:", stock_code)
    print("turn_count:", len(questions))


if __name__ == "__main__":
    main()
