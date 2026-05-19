"""
test_report_chat_debug_response.py

챗봇 테스트에서 answer가 비어 있다고 나올 때 실제 응답 wrapper를 확인하는 임시 디버그 스크립트입니다.
"""

import json
import time
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8000"
STOCK_CODE = "091700"


def request_json(url, method="GET", payload=None, timeout=180):
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = Request(
        url=url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    ai_url = f"{BASE_URL}/api/v1/report/comprehensive/{STOCK_CODE}/ai"
    ai_response = request_json(ai_url)
    print("[AI RESPONSE]")
    print("status:", ai_response.get("status"))
    print("message:", ai_response.get("message"))
    ai_report_result = ai_response.get("data")

    chat_url = f"{BASE_URL}/api/v1/report/comprehensive/{STOCK_CODE}/chat"
    payload = {
        "question": "파트론의 2021년 영업이익이 왜 증가했어?",
        "ai_report_result": ai_report_result,
        "chat_history": [],
    }

    start = time.perf_counter()
    chat_response = request_json(chat_url, method="POST", payload=payload)
    elapsed = time.perf_counter() - start

    print("\\n[CHAT RESPONSE]")
    print("elapsed:", round(elapsed, 2))
    print("status:", chat_response.get("status"))
    print("message:", chat_response.get("message"))
    print("top_keys:", list(chat_response.keys()))

    data = chat_response.get("data")
    print("data_type:", type(data).__name__)

    if isinstance(data, dict):
        print("data_keys:", list(data.keys()))
        print("answer:", repr(data.get("answer")))
        print("metadata:", json.dumps(data.get("metadata", {}), ensure_ascii=False, indent=2))
    else:
        print("data:", data)

    print("\\n[FULL CHAT RESPONSE]")
    print(json.dumps(chat_response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
