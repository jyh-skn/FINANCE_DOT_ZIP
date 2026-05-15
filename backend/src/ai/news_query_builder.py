"""
news_query_builder.py

재무 변동(detected_changes)을 기반으로 뉴스 검색 query_groups를 생성하는 모듈입니다.

v3 개선 내용:
- detected_changes가 있으면 기존처럼 signal/metric 기반 뉴스 검색 query를 생성합니다.
- detected_changes가 없으면 기업명 기반 일반 동향/근황 query를 생성합니다.
- LLM 호출 없이 template 기반으로 동작합니다.

사용 목적:
1. 눈에 띄는 signal이 있는 기업
   → 해당 signal 원인 뉴스 검색

2. 눈에 띄는 signal이 없는 기업
   → 최근 기업 동향, 사업 전망, 실적 흐름 뉴스 검색
"""

from typing import Any, Dict, List, Optional


METRIC_DEFAULT_KEYWORDS = {
    "revenue": ["매출 감소", "실적 부진", "수요 둔화"],
    "operating_income": ["영업이익 감소", "수익성 악화", "실적 부진"],
    "net_income": ["순이익 감소", "당기순이익 감소", "실적 악화"],
    "operating_margin": ["영업이익률 하락", "수익성 악화", "마진 하락"],
    "net_margin": ["순이익률 하락", "수익성 악화", "마진 하락"],
    "debt_ratio": ["부채비율 상승", "재무 안정성 악화", "부채 부담"],
    "current_ratio": ["유동비율 하락", "유동성 악화", "단기 지급능력"],
    "quick_ratio": ["당좌비율 하락", "유동성 악화", "단기 지급능력"],
    "borrowings_dependency": ["차입금의존도 상승", "차입 부담", "재무 부담"],
    "interest_coverage_ratio": ["이자보상배율 하락", "이자 부담", "재무 위험"],
    "receivables_turnover": ["매출채권 회전율", "매출채권 증가", "대금 회수"],
    "inventory_turnover": ["재고자산 회전율", "재고 부담", "재고 증가"],
    "operating_cash_flow": ["영업활동현금흐름", "현금흐름 개선", "현금 창출력"],
}

DIRECTION_KEYWORDS = {
    "decrease": ["감소", "하락", "부진"],
    "increase": ["증가", "상승", "확대"],
    "negative": ["악화", "위험", "부진"],
    "positive": ["개선", "회복", "성장"],
}

SEVERITY_KEYWORDS = {
    "high": ["급감", "급락", "위기", "충격"],
    "medium": ["감소", "악화", "부진"],
    "low": ["변동", "변화"],
}

INDUSTRY_CONTEXT_KEYWORDS = {
    "tech_equipment": ["반도체 업황", "IT 수요", "메모리 가격"],
    "asset_service": ["가동률", "고정비", "영업 레버리지"],
    "retail_service": ["소비 둔화", "유통업", "마진"],
    "construction_order": ["수주", "매출채권", "현금흐름"],
}


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result = []

    for item in items:
        item = safe_text(item).strip()

        if not item or item in seen:
            continue

        seen.add(item)
        result.append(item)

    return result


def get_company_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    return ai_input.get("company_info", {}) or {}


def get_industry_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    return ai_input.get("industry_info", {}) or {}


def get_company_name(ai_input: Dict[str, Any]) -> str:
    company_info = get_company_info(ai_input)

    return (
        company_info.get("company_name")
        or ai_input.get("company_name")
        or ""
    )


def get_stock_code(ai_input: Dict[str, Any]) -> str:
    company_info = get_company_info(ai_input)

    return (
        company_info.get("stock_code")
        or ai_input.get("stock_code")
        or ""
    )


def get_industry_group(ai_input: Dict[str, Any]) -> str:
    industry_info = get_industry_info(ai_input)
    return industry_info.get("industry_group", "")


def get_analysis_year(ai_input: Dict[str, Any]) -> Optional[int]:
    year = ai_input.get("analysis_year")

    if year is None:
        return None

    try:
        return int(float(year))
    except Exception:
        return None


def get_detected_changes(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    changes = ai_input.get("detected_changes", []) or []

    if not isinstance(changes, list):
        return []

    return changes


def sort_detected_changes_by_priority(
    detected_changes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    severity_score = {
        "high": 3,
        "medium": 2,
        "low": 1,
    }

    signal_score = {
        "negative": 3,
        "positive": 2,
        "neutral": 1,
    }

    def score(change: Dict[str, Any]) -> tuple:
        severity = safe_text(change.get("severity")).lower()
        signal_type = safe_text(change.get("signal_type")).lower()
        yoy = change.get("yoy_change_rate")

        try:
            abs_yoy = abs(float(yoy))
        except Exception:
            abs_yoy = 0.0

        return (
            severity_score.get(severity, 0),
            signal_score.get(signal_type, 0),
            abs_yoy,
        )

    return sorted(
        detected_changes,
        key=score,
        reverse=True,
    )


def normalize_search_keywords(
    change: Dict[str, Any],
    industry_group: str = "",
) -> List[str]:
    metric_key = safe_text(change.get("metric_key"))
    metric_label = safe_text(change.get("metric_label"))
    direction = safe_text(change.get("direction")).lower()
    severity = safe_text(change.get("severity")).lower()
    signal_type = safe_text(change.get("signal_type")).lower()
    source_signal = safe_text(change.get("source_signal"))

    keywords = []

    raw_keywords = change.get("search_keywords", [])

    if isinstance(raw_keywords, list):
        keywords.extend(safe_text(item) for item in raw_keywords)
    elif isinstance(raw_keywords, str):
        keywords.append(raw_keywords)

    if metric_label:
        keywords.append(metric_label)

    if source_signal:
        keywords.append(source_signal)

    keywords.extend(METRIC_DEFAULT_KEYWORDS.get(metric_key, []))
    keywords.extend(DIRECTION_KEYWORDS.get(direction, []))
    keywords.extend(DIRECTION_KEYWORDS.get(signal_type, []))
    keywords.extend(SEVERITY_KEYWORDS.get(severity, []))
    keywords.extend(INDUSTRY_CONTEXT_KEYWORDS.get(industry_group, []))

    return unique_keep_order(keywords)


def build_single_query(
    company_name: str,
    year: Optional[int],
    metric_label: str,
    keyword: str,
) -> str:
    parts = [
        company_name,
        safe_text(year),
        metric_label,
        keyword,
    ]

    return " ".join(
        part
        for part in parts
        if safe_text(part).strip()
    ).strip()


def build_queries_for_change(
    change: Dict[str, Any],
    company_name: str,
    industry_group: str = "",
    max_queries_per_change: int = 3,
) -> List[str]:
    year = change.get("year")
    metric_label = safe_text(change.get("metric_label"))
    keywords = normalize_search_keywords(
        change=change,
        industry_group=industry_group,
    )

    queries = []

    for keyword in keywords:
        query = build_single_query(
            company_name=company_name,
            year=year,
            metric_label=metric_label,
            keyword=keyword,
        )

        if query:
            queries.append(query)

        if len(queries) >= max_queries_per_change:
            break

    if not queries:
        fallback_query = build_single_query(
            company_name=company_name,
            year=year,
            metric_label=metric_label,
            keyword="실적 이슈",
        )
        queries.append(fallback_query)

    return unique_keep_order(queries)


def build_query_group(
    change: Dict[str, Any],
    company_name: str,
    stock_code: str = "",
    industry_group: str = "",
    max_queries_per_change: int = 3,
) -> Dict[str, Any]:
    queries = build_queries_for_change(
        change=change,
        company_name=company_name,
        industry_group=industry_group,
        max_queries_per_change=max_queries_per_change,
    )

    return {
        "company_name": company_name,
        "stock_code": stock_code,
        "metric_key": change.get("metric_key"),
        "metric_label": change.get("metric_label"),
        "year": change.get("year"),
        "base_year": change.get("base_year"),
        "change_type": change.get("change_type"),
        "direction": change.get("direction"),
        "severity": change.get("severity"),
        "signal_type": change.get("signal_type"),
        "signal_code": change.get("signal_code"),
        "yoy_change_rate": change.get("yoy_change_rate"),
        "description": change.get("description"),
        "source_signal": change.get("source_signal"),
        "queries": queries,

        # 기존 news_search_service.py 호환용
        "query": queries[0] if queries else "",
    }


def build_general_company_news_queries(
    ai_input: Dict[str, Any],
    max_queries: int = 3,
) -> List[Dict[str, Any]]:
    """
    detected_changes가 없을 때 기업 일반 동향/근황 검색용 query_group을 생성합니다.
    """

    company_name = get_company_name(ai_input)
    stock_code = get_stock_code(ai_input)
    industry_group = get_industry_group(ai_input)
    analysis_year = get_analysis_year(ai_input)

    if not company_name:
        company_name = stock_code

    industry_keywords = INDUSTRY_CONTEXT_KEYWORDS.get(industry_group, [])

    base_keywords = [
        "최근 실적 동향",
        "최근 뉴스",
        "사업 전망",
        "경영 현황",
        "투자 계획",
    ]

    if industry_keywords:
        base_keywords.extend(industry_keywords[:2])

    queries = []

    for keyword in unique_keep_order(base_keywords):
        query = build_single_query(
            company_name=company_name,
            year=analysis_year,
            metric_label="",
            keyword=keyword,
        )

        if query:
            queries.append(query)

        if len(queries) >= max_queries:
            break

    return [
        {
            "company_name": company_name,
            "stock_code": stock_code,
            "metric_key": "general_company_trend",
            "metric_label": "기업 일반 동향",
            "year": analysis_year,
            "base_year": ai_input.get("base_year"),
            "change_type": "general_trend",
            "direction": "neutral",
            "severity": "low",
            "signal_type": "neutral",
            "signal_code": "GENERAL_TREND",
            "yoy_change_rate": None,
            "description": "눈에 띄는 재무 signal이 없어 기업 일반 동향과 최근 근황을 검색합니다.",
            "source_signal": "기업 일반 동향",
            "queries": queries,
            "query": queries[0] if queries else f"{company_name} 최근 뉴스",
        }
    ]


def build_news_queries(
    ai_input: Dict[str, Any],
    llm: Any = None,
    max_changes: int = 2,
    max_queries_per_change: int = 3,
) -> List[Dict[str, Any]]:
    """
    ai_input의 detected_changes를 기반으로 뉴스 검색 query_groups를 생성합니다.

    detected_changes가 없으면 기업 일반 동향 query_group을 생성합니다.
    """

    company_name = get_company_name(ai_input)
    stock_code = get_stock_code(ai_input)
    industry_group = get_industry_group(ai_input)
    detected_changes = get_detected_changes(ai_input)

    if not detected_changes:
        return build_general_company_news_queries(
            ai_input=ai_input,
            max_queries=max_queries_per_change,
        )

    if not company_name:
        company_name = stock_code

    sorted_changes = sort_detected_changes_by_priority(detected_changes)
    selected_changes = sorted_changes[:max_changes]

    query_groups = []

    for change in selected_changes:
        query_group = build_query_group(
            change=change,
            company_name=company_name,
            stock_code=stock_code,
            industry_group=industry_group,
            max_queries_per_change=max_queries_per_change,
        )
        query_groups.append(query_group)

    return query_groups


def build_news_query_groups(
    ai_input: Dict[str, Any],
    llm: Any = None,
    max_changes: int = 2,
    max_queries_per_change: int = 3,
) -> List[Dict[str, Any]]:
    return build_news_queries(
        ai_input=ai_input,
        llm=llm,
        max_changes=max_changes,
        max_queries_per_change=max_queries_per_change,
    )


if __name__ == "__main__":
    import json

    sample_ai_input_without_signal = {
        "company_info": {
            "company_name": "삼성전자",
            "stock_code": "005930",
        },
        "industry_info": {
            "industry_group": "tech_equipment",
            "industry_group_name": "기술 및 장치 산업",
        },
        "analysis_year": 2023,
        "base_year": 2022,
        "detected_changes": [],
    }

    result = build_news_queries(sample_ai_input_without_signal)

    print("[News Query Builder General Fallback Test]")
    print("query_group_count:", len(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
