"""
vector_evidence_retriever.py

Vector DB 검색 결과를 AI 리포트/챗봇에서 사용하는 evidence 형식으로 변환하는 공통 모듈입니다.

역할:
1. src.vector_db.retriever의 search_by_detected_change(), search_similar_documents()를 호출합니다.
2. Vector DB 반환값(list[dict])을 표준화합니다.
3. data_type="disclosure" 검색 결과를 evidence_disclosures 형식으로 변환합니다.
4. data_type="news" 검색 결과를 evidence_news 형식으로 변환합니다.
5. source_url 기준 중복 제거를 수행합니다.

Vector DB retriever 반환 구조:
[
    {
        "content": "...본문...",
        "metadata": {
            "data_type": "disclosure" 또는 "news",
            "stock_code": "005930",
            "company_name": "삼성전자",
            "year": 2023.0,
            "signal_type": "negative",
            "signal_code": "EARNINGS_DROP",
            "industry_group": "tech_equipment",
            "source": "원본 파일명 또는 출처",
            "source_url": "https://..."
        },
        "score": 0.4676
    }
]

주의:
- metadata["text"]는 사용하지 않습니다.
- 본문은 item["content"]를 사용합니다.
- URL은 metadata["source_url"]을 우선 사용합니다.
- source_url이 없으면 metadata["source"]를 dedupe key로 사용합니다.
"""

from typing import Any, Dict, List, Optional


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


def shorten_text(text: Any, max_length: int = 500) -> str:
    """
    evidence_summary에 넣을 수 있도록 긴 텍스트를 자릅니다.
    """

    text = safe_text(text).strip()

    if len(text) <= max_length:
        return text

    return text[:max_length] + "...(truncated)"


def normalize_year(value: Any, fallback: Optional[int] = None) -> Optional[int]:
    """
    Vector DB metadata의 year가 2023.0처럼 float로 오는 경우 int로 정리합니다.
    """

    if value is None or value == "":
        return fallback

    try:
        return int(float(value))
    except Exception:
        return fallback


def normalize_score(value: Any) -> float:
    """
    score 값을 float로 변환합니다.
    """

    try:
        return float(value)
    except Exception:
        return 0.0


def get_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Vector DB 반환 item에서 metadata를 안전하게 가져옵니다.
    """

    metadata = item.get("metadata", {}) or {}

    if not isinstance(metadata, dict):
        return {}

    return metadata


def get_content(item: Dict[str, Any]) -> str:
    """
    Vector DB 반환 item에서 본문 content를 안전하게 가져옵니다.
    """

    return safe_text(item.get("content", "")).strip()


def get_source_url(metadata: Dict[str, Any]) -> str:
    """
    metadata에서 URL을 가져옵니다.
    """

    return (
        safe_text(metadata.get("source_url")).strip()
        or safe_text(metadata.get("url")).strip()
        or ""
    )


def get_source_name(metadata: Dict[str, Any]) -> str:
    """
    metadata에서 원본 파일명/출처명을 가져옵니다.
    """

    return (
        safe_text(metadata.get("source")).strip()
        or safe_text(metadata.get("source_name")).strip()
        or safe_text(metadata.get("report_name")).strip()
        or ""
    )


def dedupe_results_by_source_url(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    source_url 기준으로 중복 결과를 제거합니다.
    source_url이 없는 경우 source + content 앞부분을 기준으로 중복 제거합니다.
    """

    deduped = []
    seen = set()

    for item in results:
        metadata = get_metadata(item)
        content = get_content(item)

        source_url = get_source_url(metadata)
        source = get_source_name(metadata)

        key = source_url or f"{source}:{content[:100]}"

        if key in seen:
            continue

        seen.add(key)
        deduped.append(item)

    return deduped


def build_query_from_detected_change(
    detected_change: Dict[str, Any],
    company_name: str = "",
) -> str:
    """
    detected_change에서 Vector DB 검색용 query를 생성합니다.
    """

    query_hint = safe_text(detected_change.get("query_hint")).strip()

    if query_hint:
        return query_hint

    company = (
        company_name
        or safe_text(detected_change.get("company_name")).strip()
        or safe_text(detected_change.get("stock_code")).strip()
    )
    year = safe_text(detected_change.get("year")).strip()
    metric_label = safe_text(detected_change.get("metric_label")).strip()
    description = safe_text(detected_change.get("description")).strip()
    source_signal = safe_text(detected_change.get("source_signal")).strip()

    keywords = detected_change.get("search_keywords", [])
    keyword_text = ""

    if isinstance(keywords, list):
        keyword_text = " ".join(safe_text(keyword) for keyword in keywords[:3])
    elif isinstance(keywords, str):
        keyword_text = keywords

    parts = [
        company,
        year,
        metric_label,
        source_signal,
        description,
        keyword_text,
    ]

    query = " ".join(
        part
        for part in parts
        if safe_text(part).strip()
    ).strip()

    return query or "재무 변동 관련 공시 뉴스"


def enrich_detected_change(
    detected_change: Dict[str, Any],
    ai_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    detected_change에 company_info, industry_info, stock_code 등을 보강합니다.
    search_by_detected_change()가 metadata filter를 잘 사용할 수 있도록 돕습니다.
    """

    ai_input = ai_input or {}

    company_info = ai_input.get("company_info", {}) or {}
    industry_info = ai_input.get("industry_info", {}) or {}

    enriched = dict(detected_change)

    enriched.setdefault("stock_code", company_info.get("stock_code"))
    enriched.setdefault("company_name", company_info.get("company_name"))
    enriched.setdefault("industry_group", industry_info.get("industry_group"))

    return enriched


def get_stock_code_from_context(
    detected_change: Dict[str, Any],
    ai_input: Optional[Dict[str, Any]] = None,
) -> str:
    """
    detected_change 또는 ai_input에서 stock_code를 가져옵니다.
    """

    ai_input = ai_input or {}
    company_info = ai_input.get("company_info", {}) or {}

    return (
        safe_text(detected_change.get("stock_code")).strip()
        or safe_text(company_info.get("stock_code")).strip()
        or ""
    )


def get_company_name_from_context(
    detected_change: Dict[str, Any],
    ai_input: Optional[Dict[str, Any]] = None,
) -> str:
    """
    detected_change 또는 ai_input에서 company_name을 가져옵니다.
    """

    ai_input = ai_input or {}
    company_info = ai_input.get("company_info", {}) or {}

    return (
        safe_text(detected_change.get("company_name")).strip()
        or safe_text(company_info.get("company_name")).strip()
        or ""
    )


# ---------------------------------------------------------------------
# 2. Vector DB 검색 호출
# ---------------------------------------------------------------------

def search_with_fallback_query(
    detected_change: Dict[str, Any],
    ai_input: Optional[Dict[str, Any]] = None,
    data_type: str = "disclosure",
    top_k: int = 5,
    with_score: bool = True,
) -> List[Dict[str, Any]]:
    """
    search_similar_documents()를 사용해 더 느슨한 조건으로 fallback 검색합니다.

    search_by_detected_change()는 signal_code/year 등 강한 filter 때문에
    0개가 나올 수 있으므로, fallback에서는 query + stock_code + data_type 기준으로 검색합니다.
    """

    from src.vector_db.retriever import search_similar_documents

    ai_input = ai_input or {}

    stock_code = get_stock_code_from_context(
        detected_change=detected_change,
        ai_input=ai_input,
    )
    company_name = get_company_name_from_context(
        detected_change=detected_change,
        ai_input=ai_input,
    )

    query = build_query_from_detected_change(
        detected_change=detected_change,
        company_name=company_name,
    )

    results = search_similar_documents(
        query=query,
        stock_code=stock_code,
        data_type=data_type,
        top_k=top_k,
        with_score=with_score,
    )

    return dedupe_results_by_source_url(results or [])


def retrieve_vector_results_for_change(
    detected_change: Dict[str, Any],
    ai_input: Optional[Dict[str, Any]] = None,
    data_type: str = "disclosure",
    top_k: int = 5,
    with_score: bool = True,
) -> List[Dict[str, Any]]:
    """
    detected_change 하나에 대해 Vector DB 검색을 수행합니다.

    1차:
    - search_by_detected_change()

    2차 fallback:
    - 1차에서 에러가 나거나 빈 결과가 나오면 search_similar_documents()
    - query + stock_code + data_type 기준의 더 느슨한 검색
    """

    from src.vector_db.retriever import search_by_detected_change

    ai_input = ai_input or {}

    enriched_change = enrich_detected_change(
        detected_change=detected_change,
        ai_input=ai_input,
    )

    try:
        results = search_by_detected_change(
            detected_change=enriched_change,
            top_k=top_k,
            data_type=data_type,
            with_score=with_score,
        )

        results = dedupe_results_by_source_url(results or [])

        if results:
            return results

        print(
            "[INFO] search_by_detected_change 결과가 0개입니다. "
            "search_similar_documents로 fallback합니다."
        )

        return search_with_fallback_query(
            detected_change=enriched_change,
            ai_input=ai_input,
            data_type=data_type,
            top_k=top_k,
            with_score=with_score,
        )

    except Exception as first_error:
        print(
            "[WARN] search_by_detected_change 실패. "
            f"search_similar_documents로 fallback합니다. error={first_error}"
        )

        return search_with_fallback_query(
            detected_change=enriched_change,
            ai_input=ai_input,
            data_type=data_type,
            top_k=top_k,
            with_score=with_score,
        )


def retrieve_vector_results(
    ai_input: Dict[str, Any],
    data_type: str = "disclosure",
    top_k_per_change: int = 5,
    max_total_results: int = 10,
) -> List[Dict[str, Any]]:
    """
    ai_input의 detected_changes 전체에 대해 Vector DB 검색을 수행합니다.
    """

    detected_changes = ai_input.get("detected_changes", []) or []

    if not isinstance(detected_changes, list):
        return []

    all_results = []

    for detected_change in detected_changes:
        results = retrieve_vector_results_for_change(
            detected_change=detected_change,
            ai_input=ai_input,
            data_type=data_type,
            top_k=top_k_per_change,
            with_score=True,
        )
        all_results.extend(results)

    deduped = dedupe_results_by_source_url(all_results)

    return deduped[:max_total_results]


# ---------------------------------------------------------------------
# 3. Evidence 변환
# ---------------------------------------------------------------------

def build_common_evidence_fields(
    item: Dict[str, Any],
    detected_change: Optional[Dict[str, Any]] = None,
    ai_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    news/disclosure evidence 공통 필드를 생성합니다.
    """

    detected_change = detected_change or {}
    ai_input = ai_input or {}

    metadata = get_metadata(item)
    content = get_content(item)

    company_info = ai_input.get("company_info", {}) or {}

    year = normalize_year(
        metadata.get("year"),
        fallback=normalize_year(detected_change.get("year")),
    )
    base_year = normalize_year(detected_change.get("base_year"))

    return {
        "stock_code": (
            metadata.get("stock_code")
            or detected_change.get("stock_code")
            or company_info.get("stock_code")
        ),
        "company_name": (
            metadata.get("company_name")
            or metadata.get("company")
            or detected_change.get("company_name")
            or company_info.get("company_name")
        ),
        "year": year,
        "base_year": base_year,
        "source_type": metadata.get("data_type", ""),
        "signal_type": metadata.get("signal_type") or detected_change.get("signal_type"),
        "signal_code": metadata.get("signal_code") or detected_change.get("signal_code"),
        "industry_group": metadata.get("industry_group"),
        "metric_key": detected_change.get("metric_key"),
        "metric_label": detected_change.get("metric_label"),
        "change_type": detected_change.get("change_type"),
        "direction": detected_change.get("direction"),
        "severity": detected_change.get("severity"),
        "yoy_change_rate": detected_change.get("yoy_change_rate"),
        "source": get_source_name(metadata),
        "source_url": get_source_url(metadata),
        "relevance_score": normalize_score(item.get("score")),
        "metadata": metadata,
        "_content": content,
    }


def vector_item_to_evidence_disclosure(
    item: Dict[str, Any],
    detected_change: Optional[Dict[str, Any]] = None,
    ai_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Vector DB 검색 결과 하나를 evidence_disclosures item으로 변환합니다.
    """

    common = build_common_evidence_fields(
        item=item,
        detected_change=detected_change,
        ai_input=ai_input,
    )

    content = common.pop("_content", "")
    metadata = common.get("metadata", {}) or {}

    source = common.get("source", "")
    source_url = common.get("source_url", "")

    evidence = {
        **common,
        "source_type": "disclosure",
        "report_type": metadata.get("report_type") or "공시",
        "section": metadata.get("section") or "Vector DB 검색 결과",
        "page": metadata.get("page", ""),
        "chunk_id": metadata.get("chunk_id") or source or source_url,
        "chunk_text": content,
        "evidence_summary": shorten_text(content, max_length=500),
        "retrieval_reason": (
            f"{common.get('company_name', '')} "
            f"{common.get('year', '')}년 "
            f"{common.get('metric_label') or ''} 관련 공시 근거로 검색되었습니다."
        ).strip(),
    }

    return evidence


def vector_item_to_evidence_news(
    item: Dict[str, Any],
    detected_change: Optional[Dict[str, Any]] = None,
    ai_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Vector DB 검색 결과 하나를 evidence_news item으로 변환합니다.
    """

    common = build_common_evidence_fields(
        item=item,
        detected_change=detected_change,
        ai_input=ai_input,
    )

    content = common.pop("_content", "")
    metadata = common.get("metadata", {}) or {}

    source = common.get("source", "")
    source_url = common.get("source_url", "")

    evidence = {
        **common,
        "source_type": "news",
        "title": metadata.get("title") or source or "뉴스",
        "url": source_url,
        "published_date": metadata.get("published_date") or metadata.get("date") or "",
        "content": content,
        "evidence_summary": shorten_text(content, max_length=500),
        "reason": (
            f"{common.get('company_name', '')} "
            f"{common.get('year', '')}년 "
            f"{common.get('metric_label') or ''} 관련 뉴스 근거로 검색되었습니다."
        ).strip(),
    }

    return evidence


def convert_results_to_evidence(
    results: List[Dict[str, Any]],
    data_type: str,
    detected_change: Optional[Dict[str, Any]] = None,
    ai_input: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Vector DB 검색 결과 리스트를 evidence_news 또는 evidence_disclosures로 변환합니다.
    """

    evidence_items = []

    for item in results:
        if data_type == "news":
            evidence = vector_item_to_evidence_news(
                item=item,
                detected_change=detected_change,
                ai_input=ai_input,
            )
        else:
            evidence = vector_item_to_evidence_disclosure(
                item=item,
                detected_change=detected_change,
                ai_input=ai_input,
            )

        evidence_items.append(evidence)

    return evidence_items


def retrieve_evidence_by_data_type(
    ai_input: Dict[str, Any],
    data_type: str,
    top_k_per_change: int = 3,
    max_total_results: int = 5,
    max_changes: int = 2,
) -> List[Dict[str, Any]]:
    detected_changes = ai_input.get("detected_changes", []) or []

    if not isinstance(detected_changes, list):
        return []

    selected_changes = detected_changes[:max_changes]

    evidence_items = []

    for detected_change in selected_changes:
        results = retrieve_vector_results_for_change(
            detected_change=detected_change,
            ai_input=ai_input,
            data_type=data_type,
            top_k=top_k_per_change,
            with_score=True,
        )

        converted = convert_results_to_evidence(
            results=results,
            data_type=data_type,
            detected_change=detected_change,
            ai_input=ai_input,
        )

        evidence_items.extend(converted)

    deduped = []
    seen = set()

    for evidence in evidence_items:
        key = (
            evidence.get("source_url")
            or evidence.get("url")
            or evidence.get("source")
            or evidence.get("chunk_id")
            or safe_text(evidence.get("content"))[:100]
            or safe_text(evidence.get("chunk_text"))[:100]
        )

        if key in seen:
            continue

        seen.add(key)
        deduped.append(evidence)

    return deduped[:max_total_results]


if __name__ == "__main__":
    print(
        "vector_evidence_retriever.py는 공통 모듈입니다.\n"
        "실제 테스트는 disclosure_retriever.py 또는 news_retriever.py에서 실행하세요."
    )
