"""
test_tavily.py

Tavily API 연결 및 한국어/국내 뉴스 검색 결과 확인용 테스트 파일입니다.
"""

import json
import os
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from tavily import TavilyClient


load_dotenv()


KOREAN_NEWS_DOMAINS = [
    "yna.co.kr",
    "newsis.com",
    "hankyung.com",
    "mk.co.kr",
    "sedaily.com",
    "edaily.co.kr",
    "etnews.com",
    "zdnet.co.kr",
    "biz.chosun.com",
    "thelec.kr",
    "ddaily.co.kr",
    "fnnews.com",
    "joongang.co.kr",
    "chosun.com",
    "donga.com",
]


def get_tavily_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY가 설정되어 있지 않습니다. "
            ".env 파일 또는 환경 변수에 TAVILY_API_KEY를 추가해주세요."
        )

    return TavilyClient(api_key=api_key)


def contains_korean(text: str) -> bool:
    """
    문자열에 한글이 포함되어 있는지 확인합니다.
    """

    if not text:
        return False

    return bool(re.search(r"[가-힣]", text))


def is_korean_result(item: Dict[str, Any]) -> bool:
    """
    title 또는 content에 한글이 포함되어 있는 결과만 통과시킵니다.
    """

    title = item.get("title", "")
    content = item.get("content", "")

    return contains_korean(title) or contains_korean(content)


def normalize_tavily_results(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = response.get("results", []) or []
    normalized_results = []

    for item in results:
        if not is_korean_result(item):
            continue

        normalized_results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "published_date": item.get("published_date", ""),
                "score": item.get("score"),
            }
        )

    return normalized_results


def search_korean_news(client: TavilyClient, query: str) -> Dict[str, Any]:
    """
    국내/한국어 결과 우선 검색.

    1차: topic="news" + include_domains
    2차: 결과가 부족하면 topic="general" + country="south korea"로 재검색
    """

    enriched_query = f"{query} 국내 뉴스 한국어 기사"

    print("[DEBUG] 1차 검색: topic='news' + include_domains")

    response = client.search(
        query=enriched_query,
        topic="news",
        search_depth="basic",
        max_results=10,
        include_domains=KOREAN_NEWS_DOMAINS,
        include_answer=False,
        include_raw_content=False,
        include_images=False,
    )

    normalized_results = normalize_tavily_results(response)

    if normalized_results:
        return {
            "search_mode": "news_with_include_domains",
            "response": response,
            "normalized_results": normalized_results,
        }

    print("[DEBUG] 1차 결과 부족. 2차 검색: topic='general' + country='south korea'")

    response = client.search(
        query=enriched_query,
        topic="general",
        country="south korea",
        search_depth="basic",
        max_results=10,
        include_domains=KOREAN_NEWS_DOMAINS,
        include_answer=False,
        include_raw_content=False,
        include_images=False,
    )

    normalized_results = normalize_tavily_results(response)

    return {
        "search_mode": "general_with_country_and_domains",
        "response": response,
        "normalized_results": normalized_results,
    }


def run_tavily_connection_test() -> None:
    client = get_tavily_client()

    query = "삼성전자 2023 영업이익 감소 원인"

    result = search_korean_news(
        client=client,
        query=query,
    )

    response = result["response"]
    normalized_results = result["normalized_results"]

    print("[Tavily Korean Search Test]")
    print("query:", query)
    print("search_mode:", result["search_mode"])
    print("result_count:", len(normalized_results))

    print("\n[Raw Response Keys]")
    print(list(response.keys()))

    print("\n[Normalized Korean Results]")
    print(json.dumps(normalized_results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_tavily_connection_test()