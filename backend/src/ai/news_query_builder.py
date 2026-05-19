"""
news_query_builder.py

재무 변동(detected_changes)을 기반으로 뉴스 검색 query_groups를 생성하는 모듈입니다.

v2 개선 방향:
- 기존 LLM 기반 뉴스 쿼리 생성 방식은 속도가 느릴 수 있습니다.
- 현재 detected_changes 안에 metric_label, year, direction, severity, search_keywords가 이미 들어오므로
  LLM 호출 없이 template 기반으로 Tavily 검색 쿼리를 생성합니다.
- 이를 통해 news_query_builder 단계의 실행 시간을 크게 줄입니다.

주의:
- build_news_queries(ai_input, llm=None) 시그니처는 기존 호출부 호환을 위해 유지합니다.
- llm 인자는 더 이상 사용하지 않습니다.
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

        if not item:
            continue

        if item in seen:
            continue

        seen.add(item)
        result.append(item)

    return result


def get_company_name(ai_input: Dict[str, Any]) -> str:
    company_info = ai_input.get("company_info", {}) or {}

    return (
        company_info.get("company_name")
        or ai_input.get("company_name")
        or ""
    )


def get_stock_code(ai_input: Dict[str, Any]) -> str:
    company_info = ai_input.get("company_info", {}) or {}

    return (
        company_info.get("stock_code")
        or ai_input.get("stock_code")
        or ""
    )


def get_industry_group(ai_input: Dict[str, Any]) -> str:
    industry_info = ai_input.get("industry_info", {}) or {}
    return industry_info.get("industry_group", "")


def get_detected_changes(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    changes = ai_input.get("detected_changes", []) or []

    if not isinstance(changes, list):
        return []

    return changes



RISK_INCREASE_METRICS = {
    "debt_ratio",
    "total_liabilities",
    "liabilities",
    "borrowings",
    "borrowings_dependency",
    "interest_bearing_debt",
    "debt_to_equity",
}

RISK_DECREASE_METRICS = {
    "revenue",
    "operating_income",
    "net_income",
    "operating_margin",
    "net_margin",
    "current_ratio",
    "quick_ratio",
    "interest_coverage_ratio",
    "operating_cash_flow",
    "free_cash_flow",
    "total_equity",
    "asset_turnover",
    "receivables_turnover",
    "inventory_turnover",
}

NEGATIVE_CHANGE_TYPES = {
    "decrease",
    "sharp_decrease",
    "turn_to_loss",
    "loss_increase",
    "deficit",
    "negative_turn",
    "deterioration",
}

POSITIVE_CHANGE_TYPES = {
    "increase",
    "sharp_increase",
    "turn_to_profit",
    "improvement",
    "recovery",
}

NEGATIVE_SIGNAL_TYPES = {
    "negative",
    "warning",
    "risk",
    "danger",
    "bad",
}

POSITIVE_SIGNAL_TYPES = {
    "positive",
    "good",
    "favorable",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def classify_change_sentiment(change: Dict[str, Any]) -> str:
    """
    detected_change가 뉴스 검색 관점에서 부정/긍정/중립 중 어디에 가까운지 분류합니다.

    주의:
    - direction="increase"가 항상 긍정은 아닙니다.
    - 부채비율, 총부채, 차입금의존도 증가는 위험 신호입니다.
    - 매출, 영업이익, 순이익, 유동비율, 현금흐름 감소는 부정 신호입니다.
    """

    metric_key = safe_text(change.get("metric_key")).lower()
    change_type = safe_text(change.get("change_type")).lower()
    direction = safe_text(change.get("direction")).lower()
    signal_type = safe_text(change.get("signal_type")).lower()

    if signal_type in NEGATIVE_SIGNAL_TYPES:
        return "negative"

    if signal_type in POSITIVE_SIGNAL_TYPES:
        return "positive"

    if change_type in {"turn_to_loss", "sharp_decrease"}:
        return "negative"

    if change_type == "turn_to_profit":
        return "positive"

    if metric_key in RISK_INCREASE_METRICS:
        if direction == "increase":
            return "negative"
        if direction == "decrease":
            return "positive"

    if metric_key in RISK_DECREASE_METRICS:
        if direction == "decrease":
            return "negative"
        if direction == "increase":
            return "positive"

    if change_type in NEGATIVE_CHANGE_TYPES:
        return "negative"

    if change_type in POSITIVE_CHANGE_TYPES:
        return "positive"

    return "neutral"


def get_news_query_priority(change: Dict[str, Any]) -> tuple:
    """
    뉴스 검색 query_group 정렬 우선순위를 반환합니다.

    정렬 기준:
    1. 부정 이슈를 긍정 이슈보다 먼저 검색
    2. severity가 높은 이슈를 먼저 검색
    3. yoy 변화율 절댓값이 큰 이슈를 먼저 검색
    """

    sentiment = classify_change_sentiment(change)
    severity = safe_text(change.get("severity")).lower()
    abs_yoy = abs(safe_float(change.get("yoy_change_rate"), default=0.0))

    sentiment_rank = {
        "negative": 0,
        "positive": 1,
        "neutral": 2,
    }

    severity_rank = {
        "high": 0,
        "medium": 1,
        "low": 2,
        "": 3,
    }

    return (
        sentiment_rank.get(sentiment, 2),
        severity_rank.get(severity, 3),
        -abs_yoy,
    )


def sort_detected_changes_by_priority(
    detected_changes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    부정적인 재무 변동을 우선 검색하도록 detected_changes를 정렬합니다.
    """

    return sorted(
        detected_changes,
        key=get_news_query_priority,
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
        "yoy_change_rate": change.get("yoy_change_rate"),
        "description": change.get("description"),
        "source_signal": change.get("source_signal"),
        "change_sentiment": classify_change_sentiment(change),
        "query_priority": get_news_query_priority(change),
        "queries": queries,

        # 기존 news_search_service.py 호환용
        "query": queries[0] if queries else "",
    }


def build_news_queries(
    ai_input: Dict[str, Any],
    llm: Any = None,
    max_changes: int = 2,
    max_queries_per_change: int = 3,
) -> List[Dict[str, Any]]:
    """
    ai_input의 detected_changes를 기반으로 뉴스 검색 query_groups를 생성합니다.
    """

    company_name = get_company_name(ai_input)
    stock_code = get_stock_code(ai_input)
    industry_group = get_industry_group(ai_input)
    detected_changes = get_detected_changes(ai_input)

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

    sample_ai_input = {
        "company_info": {
            "company_name": "삼성전자",
            "stock_code": "005930",
        },
        "industry_info": {
            "industry_group": "tech_equipment",
            "industry_group_name": "기술 및 장치 산업",
        },
        "detected_changes": [
            {
                "metric_key": "operating_income",
                "metric_label": "영업이익",
                "year": 2023,
                "base_year": 2022,
                "change_type": "sharp_decrease",
                "direction": "decrease",
                "severity": "high",
                "signal_type": "negative",
                "yoy_change_rate": -84.86,
                "description": "전년 대비 영업이익이 -84.86% 감소했습니다.",
                "search_keywords": ["영업이익 감소", "수익성 악화", "실적 부진"],
                "source_signal": "영업이익 급감",
            },
            {
                "metric_key": "net_income",
                "metric_label": "당기순이익",
                "year": 2023,
                "base_year": 2022,
                "change_type": "decrease",
                "direction": "decrease",
                "severity": "medium",
                "signal_type": "negative",
                "yoy_change_rate": -72.17,
                "description": "전년 대비 당기순이익이 -72.17% 감소했습니다.",
                "search_keywords": ["순이익 감소", "실적 악화"],
                "source_signal": "순이익 감소",
            },
        ],
    }

    result = build_news_queries(sample_ai_input)

    print("[News Query Builder Template Test]")
    print("query_group_count:", len(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
