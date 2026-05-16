"""
news_search_cache_service.py

Tavily 뉴스 검색 결과를 로컬 파일 캐시로 재사용하는 서비스입니다.

목적:
- 같은 기업/연도/query_group에 대해 반복 테스트할 때 Tavily를 매번 호출하지 않도록 합니다.
- news_search_service 시간이 20~30초 이상 걸리는 병목을 줄입니다.
- 기존 news_search_service.search_news_by_query_groups()를 감싸는 wrapper입니다.

사용 위치:
- comprehensive_report_service.py에서 기존 search_news_by_query_groups() 대신
  search_news_by_query_groups_cached()를 호출하면 됩니다.

캐시 기준:
- company_name
- stock_code
- analysis_year
- query_groups 내용
- max_results_per_query
- max_total_results

기본 캐시 TTL:
- 24시간

주의:
- 캐시는 개발/시연 속도 개선용입니다.
- 최신 뉴스가 반드시 필요한 경우 cache_enabled=False로 호출하면 됩니다.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24시간


# ---------------------------------------------------------------------
# 1. 경로 및 유틸
# ---------------------------------------------------------------------

def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def get_backend_root() -> Path:
    """
    현재 파일 위치를 기준으로 backend 루트를 찾습니다.
    """

    current_file = Path(__file__).resolve()

    for parent in current_file.parents:
        if (parent / "src").exists():
            return parent

    # fallback
    return current_file.parents[2]


def get_cache_dir() -> Path:
    """
    뉴스 검색 캐시 저장 디렉터리를 반환합니다.
    """

    env_cache_dir = os.getenv("NEWS_SEARCH_CACHE_DIR")

    if env_cache_dir:
        cache_dir = Path(env_cache_dir)
    else:
        cache_dir = get_backend_root() / ".cache" / "news_search"

    cache_dir.mkdir(parents=True, exist_ok=True)

    return cache_dir


def normalize_for_hash(value: Any) -> Any:
    """
    dict/list를 안정적인 hash 대상으로 만들기 위해 정규화합니다.
    """

    if isinstance(value, dict):
        return {
            key: normalize_for_hash(value[key])
            for key in sorted(value.keys())
            if key not in {"created_at", "generated_at"}
        }

    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]

    return value


def build_cache_key(
    query_groups: List[Dict[str, Any]],
    ai_input: Optional[Dict[str, Any]] = None,
    max_results_per_query: int = 3,
    max_total_results: int = 10,
) -> str:
    """
    뉴스 검색 캐시 key를 생성합니다.
    """

    ai_input = ai_input or {}
    company_info = ai_input.get("company_info", {}) or {}

    payload = {
        "stock_code": company_info.get("stock_code") or ai_input.get("stock_code"),
        "company_name": company_info.get("company_name") or ai_input.get("company_name"),
        "analysis_year": ai_input.get("analysis_year"),
        "base_year": ai_input.get("base_year"),
        "query_groups": query_groups,
        "max_results_per_query": max_results_per_query,
        "max_total_results": max_total_results,
    }

    normalized = normalize_for_hash(payload)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)

    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get_cache_path(cache_key: str) -> Path:
    return get_cache_dir() / f"{cache_key}.json"


def read_cache(cache_path: Path, ttl_seconds: int) -> Optional[List[Dict[str, Any]]]:
    """
    캐시 파일을 읽습니다. TTL이 지나면 None을 반환합니다.
    """

    if not cache_path.exists():
        return None

    try:
        with cache_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return None

    cached_at = payload.get("cached_at", 0)

    try:
        age = time.time() - float(cached_at)
    except Exception:
        return None

    if ttl_seconds >= 0 and age > ttl_seconds:
        return None

    searched_news = payload.get("searched_news", [])

    if not isinstance(searched_news, list):
        return None

    return searched_news


def write_cache(
    cache_path: Path,
    searched_news: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    검색 결과를 캐시에 저장합니다.
    """

    payload = {
        "cached_at": time.time(),
        "cached_at_readable": time.strftime("%Y-%m-%d %H:%M:%S"),
        "metadata": metadata or {},
        "searched_news": searched_news,
    }

    with cache_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------
# 2. 대표 wrapper
# ---------------------------------------------------------------------

def search_news_by_query_groups_cached(
    query_groups: List[Dict[str, Any]],
    ai_input: Optional[Dict[str, Any]] = None,
    max_results_per_query: int = 3,
    max_total_results: int = 10,
    cache_enabled: bool = True,
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
) -> List[Dict[str, Any]]:
    """
    news_search_service.search_news_by_query_groups()에 캐시를 추가한 wrapper입니다.

    Args:
        query_groups: news_query_builder.py가 생성한 query_groups
        ai_input: 캐시 key 생성을 위한 기업/연도 정보
        max_results_per_query: query 하나당 최대 뉴스 수
        max_total_results: 최종 뉴스 최대 수
        cache_enabled: 캐시 사용 여부
        cache_ttl_seconds: 캐시 유효 시간. -1이면 만료 없음.

    Returns:
        searched_news list
    """

    from src.ai.news_search_service import search_news_by_query_groups

    if not cache_enabled:
        print("[NEWS_SEARCH_CACHE] disabled")
        return search_news_by_query_groups(
            query_groups=query_groups,
            max_results_per_query=max_results_per_query,
            max_total_results=max_total_results,
        )

    cache_key = build_cache_key(
        query_groups=query_groups,
        ai_input=ai_input,
        max_results_per_query=max_results_per_query,
        max_total_results=max_total_results,
    )
    cache_path = get_cache_path(cache_key)

    cached_news = read_cache(
        cache_path=cache_path,
        ttl_seconds=cache_ttl_seconds,
    )

    if cached_news is not None:
        print(
            "[NEWS_SEARCH_CACHE] hit "
            f"| count={len(cached_news)} "
            f"| path={cache_path}"
        )
        return cached_news

    print(
        "[NEWS_SEARCH_CACHE] miss "
        f"| key={cache_key}"
    )

    searched_news = search_news_by_query_groups(
        query_groups=query_groups,
        max_results_per_query=max_results_per_query,
        max_total_results=max_total_results,
    )

    write_cache(
        cache_path=cache_path,
        searched_news=searched_news,
        metadata={
            "query_group_count": len(query_groups),
            "max_results_per_query": max_results_per_query,
            "max_total_results": max_total_results,
            "cache_key": cache_key,
        },
    )

    print(
        "[NEWS_SEARCH_CACHE] saved "
        f"| count={len(searched_news)} "
        f"| path={cache_path}"
    )

    return searched_news


def clear_news_search_cache() -> int:
    """
    뉴스 검색 캐시 파일을 모두 삭제합니다.

    Returns:
        삭제된 파일 수
    """

    cache_dir = get_cache_dir()
    count = 0

    for path in cache_dir.glob("*.json"):
        try:
            path.unlink()
            count += 1
        except Exception:
            pass

    return count


if __name__ == "__main__":
    print("[News Search Cache Service]")
    print("cache_dir:", get_cache_dir())
    print("cache_file_count:", len(list(get_cache_dir().glob("*.json"))))
