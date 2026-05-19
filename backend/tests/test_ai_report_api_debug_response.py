"""
test_ai_report_api_debug_response.py

AI 리포트 API 테스트에서 "필수 top-level key 누락"이 발생할 때,
실제 응답 status/message/data 타입을 확인하기 위한 임시 디버그 스크립트입니다.
"""

import json
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8000"


def main():
    url = f"{BASE_URL}/api/v1/report/comprehensive/005930/ai"
    request = Request(
        url=url,
        method="GET",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=180) as response:
        raw = response.read().decode("utf-8")
        payload = json.loads(raw)

    print("[AI Report API Debug Response]")
    print("status:", payload.get("status"))
    print("message:", payload.get("message"))
    print("data_type:", type(payload.get("data")).__name__)
    print("top_level_keys:", list(payload.keys()))

    data = payload.get("data")
    if isinstance(data, dict):
        print("data_keys:", list(data.keys())[:30])
    else:
        print("data:", data)


if __name__ == "__main__":
    main()
