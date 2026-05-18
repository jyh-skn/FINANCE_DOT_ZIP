"""
news_evidence_quality_filter.py

뉴스 evidence 품질 필터 v3입니다.

목적:
- Vector DB similarity만으로 관련 없는 기사(명품주, 개인 투자자 단타, 시장 일반 기사 등)가
  evidence_news로 채택되는 문제를 줄입니다.
- "삼성전자" 분석에서 "삼성SDS", "삼성전기" 등 다른 삼성 계열사 기사가 통과하는 문제를 줄입니다.
- 단, 한국 기사 제목에서 "삼성·SK하이닉스"처럼 삼성전자를 줄여 쓰는 반도체 기사까지
  과도하게 제거하지 않도록 허용합니다.

핵심:
1. 제목/본문에 실제 target 기업명 또는 종목코드가 있는지 확인합니다.
2. 제목이 다른 계열사 중심이면 hard reject합니다.
3. 제목이 명품주/단타/개미/매매 회전율 등 오프토픽이면 hard reject합니다.
4. 삼성전자에 한해 "삼성·SK하이닉스", "삼성ㆍSK하이닉스", "삼성·하이닉스" 형태의
   반도체/재고/실적 기사 제목은 삼성전자 축약 표현으로 허용합니다.
5. 필터 통과 결과에는 quality_score, quality_reasons, hard_reject_reason을 붙입니다.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------
# 1. 기본 유틸
# ---------------------------------------------------------------------

def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def normalize_space(text: Any) -> str:
    return " ".join(safe_text(text).split())


def count_keyword_hits(text: str, keywords: List[str]) -> int:
    lowered = safe_text(text).lower()
    return sum(1 for keyword in keywords if keyword and keyword.lower() in lowered)


def contains_any(text: str, keywords: List[str]) -> bool:
    lowered = safe_text(text).lower()
    return any(keyword and keyword.lower() in lowered for keyword in keywords)


def get_company_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    return ai_input.get("company_info", {}) or {}


def get_company_name(ai_input: Dict[str, Any]) -> str:
    company_info = get_company_info(ai_input)
    return company_info.get("company_name") or ai_input.get("company_name") or ""


def get_stock_code(ai_input: Dict[str, Any]) -> str:
    company_info = get_company_info(ai_input)
    return company_info.get("stock_code") or ai_input.get("stock_code") or ""


def get_analysis_year(ai_input: Dict[str, Any]) -> Optional[int]:
    return safe_int(ai_input.get("analysis_year"))


def get_base_year(ai_input: Dict[str, Any]) -> Optional[int]:
    return safe_int(ai_input.get("base_year"))


# ---------------------------------------------------------------------
# 2. 사전
# ---------------------------------------------------------------------

COMPANY_ALIASES = {
    "삼성전자": ["삼성전자", "Samsung Electronics", "005930"],
    "SK하이닉스": ["SK하이닉스", "하이닉스", "000660"],
    "현대자동차": ["현대자동차", "현대차", "005380"],
    "기아": ["기아", "000270"],
    "LG화학": ["LG화학", "051910"],
    "카카오": ["카카오", "035720"],
    "NAVER": ["NAVER", "네이버", "035420"],
    "네이버": ["네이버", "NAVER", "035420"],
    "파트론": ["파트론", "091700"],
}

RELATED_COMPANY_EXCLUSION = {
    "삼성전자": [
        "삼성SDS",
        "삼성에스디에스",
        "삼성SDI",
        "삼성전기",
        "삼성물산",
        "삼성생명",
        "삼성화재",
        "삼성바이오로직스",
        "삼성중공업",
        "삼성엔지니어링",
        "제일기획",
        "에스원",
    ],
    "SK하이닉스": [
        "SK이노베이션",
        "SK텔레콤",
        "SK스퀘어",
        "SK바이오사이언스",
        "SKC",
    ],
    "LG화학": [
        "LG전자",
        "LG에너지솔루션",
        "LG생활건강",
        "LG이노텍",
        "LG유플러스",
    ],
}

METRIC_KEYWORDS = {
    "revenue": ["매출", "매출액", "sales", "revenue"],
    "operating_income": ["영업이익", "영업익", "영업손익", "영업손실", "수익성", "실적", "적자", "흑자"],
    "net_income": ["순이익", "당기순이익", "당기순손실", "net income", "적자", "흑자"],
    "debt_ratio": ["부채비율", "부채", "재무구조", "차입", "레버리지"],
    "current_ratio": ["유동비율", "유동성", "유동자산", "유동부채"],
    "operating_cash_flow": ["영업활동현금흐름", "현금흐름", "영업현금흐름", "cash flow"],
    "asset_turnover": ["자산회전율", "자산 효율", "자산 효율성"],
    "inventory_turnover": ["재고회전율", "재고자산회전율", "재고"],
    "total_assets": ["총자산", "자산"],
    "total_liabilities": ["총부채", "부채"],
    "total_equity": ["자본총계", "자기자본", "자본"],
}

GENERIC_FINANCIAL_KEYWORDS = [
    "매출",
    "영업이익",
    "영업익",
    "순이익",
    "실적",
    "수익성",
    "적자",
    "흑자",
    "영업손실",
    "재무",
    "현금흐름",
    "부채",
    "유동성",
    "재고",
    "수요",
    "가격",
    "업황",
    "반도체",
    "메모리",
    "낸드",
    "dram",
    "d램",
]

HARD_OFF_TOPIC_TITLE_KEYWORDS = [
    "단타",
    "개미",
    "개인 투자자",
    "매매 회전율",
    "수익률 꼴찌",
    "명품주",
    "명품株",
    "명품백",
    "테마주",
    "추천주",
    "종목 추천",
    "주식 투자",
    "투자 전략",
]

SOFT_OFF_TOPIC_KEYWORDS = [
    "단타",
    "개인 투자자",
    "매매 회전율",
    "명품주",
    "명품株",
    "테마주",
    "주식 투자",
    "투자 전략",
    "종목 추천",
    "거래대금",
]

# 삼성전자 기사가 제목에서 "삼성전자" 대신 "삼성·SK하이닉스"처럼 줄어드는 경우 허용
SAMSUNG_ELECTRONICS_SHORTHAND_PATTERNS = [
    "삼성·sk하이닉스",
    "삼성ㆍsk하이닉스",
    "삼성·하이닉스",
    "삼성ㆍ하이닉스",
    "삼성-sk하이닉스",
    "삼성 sk하이닉스",
]

SAMSUNG_ELECTRONICS_CONTEXT_KEYWORDS = [
    "반도체",
    "메모리",
    "재고",
    "가동률",
    "d램",
    "dram",
    "낸드",
    "영업이익",
    "실적",
    "업황",
]


# ---------------------------------------------------------------------
# 3. 정보 추출
# ---------------------------------------------------------------------

def build_company_aliases(company_name: str, stock_code: str = "") -> List[str]:
    company_name = safe_text(company_name).strip()
    stock_code = safe_text(stock_code).strip()

    aliases = []

    if company_name:
        aliases.append(company_name)

    if stock_code:
        aliases.append(stock_code)

    aliases.extend(COMPANY_ALIASES.get(company_name, []))

    result = []
    seen = set()

    for alias in aliases:
        alias = safe_text(alias).strip()
        key = alias.lower()

        if alias and key not in seen:
            result.append(alias)
            seen.add(key)

    return result


def get_metric_keywords(item: Dict[str, Any]) -> List[str]:
    metric_key = safe_text(item.get("metric_key")).strip()
    metric_label = safe_text(item.get("metric_label")).strip()

    metadata = item.get("metadata", {}) or {}
    metadata_metric_key = safe_text(metadata.get("metric_key")).strip()
    metadata_metric_label = safe_text(metadata.get("metric_label")).strip()

    keywords = []

    for label in [metric_label, metadata_metric_label]:
        if label:
            keywords.append(label)

    for key_value in [metric_key, metadata_metric_key]:
        if key_value:
            keywords.extend(METRIC_KEYWORDS.get(key_value, []))

        normalized_key = key_value.lower()

        for key, values in METRIC_KEYWORDS.items():
            if key in normalized_key:
                keywords.extend(values)

    result = []
    seen = set()

    for keyword in keywords:
        keyword = safe_text(keyword).strip()
        key = keyword.lower()

        if keyword and key not in seen:
            result.append(keyword)
            seen.add(key)

    return result


def get_title(item: Dict[str, Any]) -> str:
    return normalize_space(
        item.get("title")
        or item.get("source")
        or (item.get("metadata", {}) or {}).get("title")
        or (item.get("metadata", {}) or {}).get("source")
    )


def get_url(item: Dict[str, Any]) -> str:
    return safe_text(
        item.get("url")
        or item.get("source_url")
        or (item.get("metadata", {}) or {}).get("source_url")
    ).strip()


def get_news_text(item: Dict[str, Any]) -> str:
    parts = [
        get_title(item),
        item.get("content"),
        item.get("evidence_summary"),
        item.get("summary"),
        item.get("reason"),
        item.get("source"),
        (item.get("metadata", {}) or {}).get("source"),
    ]

    return "\n".join(safe_text(part) for part in parts if safe_text(part).strip())


def extract_year_from_text(text: str) -> Optional[int]:
    matches = re.findall(r"(20\d{2})", safe_text(text))

    if not matches:
        return None

    try:
        return int(matches[0])
    except Exception:
        return None


def is_samsung_electronics_shorthand_title(title: str) -> bool:
    lowered = safe_text(title).lower()

    has_pattern = any(pattern in lowered for pattern in SAMSUNG_ELECTRONICS_SHORTHAND_PATTERNS)
    has_context = any(keyword.lower() in lowered for keyword in SAMSUNG_ELECTRONICS_CONTEXT_KEYWORDS)

    return has_pattern and has_context


# ---------------------------------------------------------------------
# 4. hard reject
# ---------------------------------------------------------------------

def get_hard_reject_reason(
    item: Dict[str, Any],
    ai_input: Dict[str, Any],
) -> Optional[str]:
    company_name = get_company_name(ai_input)
    stock_code = get_stock_code(ai_input)

    title = get_title(item)
    text = get_news_text(item)

    title_lower = title.lower()
    text_lower = text.lower()

    aliases = build_company_aliases(company_name, stock_code)

    exact_company_in_title = bool(company_name and company_name.lower() in title_lower)
    stock_code_in_title = bool(stock_code and stock_code in title)
    exact_company_in_text = bool(company_name and company_name.lower() in text_lower)
    stock_code_in_text = bool(stock_code and stock_code in text)

    shorthand_title_match = (
        company_name == "삼성전자"
        and is_samsung_electronics_shorthand_title(title)
    )

    if contains_any(title, HARD_OFF_TOPIC_TITLE_KEYWORDS):
        return "hard_reject: title contains off-topic investment/market keyword"

    for other_company in RELATED_COMPANY_EXCLUSION.get(company_name, []):
        if other_company.lower() in title_lower:
            if not exact_company_in_title and not stock_code_in_title:
                return f"hard_reject: title is about another related company({other_company})"

    if not (
        exact_company_in_title
        or stock_code_in_title
        or exact_company_in_text
        or stock_code_in_text
        or shorthand_title_match
    ):
        return "hard_reject: target company/stock_code not found"

    target_hit_count = count_keyword_hits(text, aliases)

    # 제목이 target 기업도 아니고, 약칭 패턴도 아니며, 본문에 한 번만 스친 경우 제거
    if (
        not exact_company_in_title
        and not stock_code_in_title
        and not shorthand_title_match
        and target_hit_count <= 1
    ):
        return "hard_reject: target company only mentioned incidentally"

    return None


# ---------------------------------------------------------------------
# 5. 점수 계산
# ---------------------------------------------------------------------

def score_news_evidence_item(
    item: Dict[str, Any],
    ai_input: Dict[str, Any],
) -> Tuple[float, List[str], Optional[str]]:
    company_name = get_company_name(ai_input)
    stock_code = get_stock_code(ai_input)
    analysis_year = get_analysis_year(ai_input)
    base_year = get_base_year(ai_input)

    title = get_title(item)
    text = get_news_text(item)
    title_lower = title.lower()
    lowered = text.lower()

    company_aliases = build_company_aliases(company_name, stock_code)
    metric_keywords = get_metric_keywords(item)

    score = 0.0
    reasons = []

    hard_reject_reason = get_hard_reject_reason(
        item=item,
        ai_input=ai_input,
    )

    exact_company_in_title = bool(company_name and company_name.lower() in title_lower)
    stock_code_in_title = bool(stock_code and stock_code in title)
    shorthand_title_match = (
        company_name == "삼성전자"
        and is_samsung_electronics_shorthand_title(title)
    )

    if exact_company_in_title:
        score += 5.0
        reasons.append("제목에 정확한 기업명 있음")
    elif stock_code_in_title:
        score += 4.5
        reasons.append("제목에 종목코드 있음")
    elif shorthand_title_match:
        score += 3.8
        reasons.append("제목에 삼성전자 축약형 반도체 문맥 있음")
    else:
        reasons.append("제목에 정확한 기업명/종목코드 없음")

    company_hit_count = count_keyword_hits(text, company_aliases)

    if company_hit_count >= 2:
        score += 2.5
        reasons.append(f"본문/요약에 기업명 또는 종목코드 반복 언급({company_hit_count})")
    elif company_hit_count == 1:
        score += 0.8
        reasons.append("본문/요약에 기업명 또는 종목코드 1회 언급")
    elif shorthand_title_match:
        score += 0.5
        reasons.append("본문 기업명 반복은 약하지만 제목 약칭 문맥 인정")
    else:
        score -= 5.0
        reasons.append("본문/요약에 기업명 또는 종목코드 없음")

    metric_hit_count = count_keyword_hits(text, metric_keywords)

    if metric_hit_count > 0:
        score += min(2.5, 1.0 + metric_hit_count * 0.4)
        reasons.append(f"지표 키워드 언급 있음({metric_hit_count})")
    else:
        score -= 0.5
        reasons.append("지표 키워드 직접 언급 부족")

    financial_hit_count = count_keyword_hits(text, GENERIC_FINANCIAL_KEYWORDS)

    if financial_hit_count > 0:
        score += min(2.0, financial_hit_count * 0.3)
        reasons.append(f"재무/실적 관련 키워드 있음({financial_hit_count})")

    item_year = safe_int(item.get("year"))
    text_year = extract_year_from_text(text)
    effective_year = item_year or text_year

    valid_years = {
        year
        for year in [analysis_year, base_year]
        if year is not None
    }

    if effective_year and valid_years:
        if effective_year in valid_years:
            score += 1.0
            reasons.append(f"분석/기준 연도와 일치({effective_year})")
        elif min(abs(effective_year - year) for year in valid_years) <= 1:
            score += 0.3
            reasons.append(f"분석연도와 인접({effective_year})")
        else:
            score -= 1.0
            reasons.append(f"분석연도와 거리가 있음({effective_year})")

    relevance_score = safe_float(item.get("relevance_score"), default=0.0)

    if relevance_score > 0:
        score += min(0.8, relevance_score * 1.2)
        reasons.append(f"vector relevance_score 반영({relevance_score:.3f})")

    soft_off_topic_hits = [
        keyword
        for keyword in SOFT_OFF_TOPIC_KEYWORDS
        if keyword.lower() in lowered
    ]

    if soft_off_topic_hits:
        penalty = min(3.0, len(soft_off_topic_hits) * 1.2)
        score -= penalty
        reasons.append(f"오프토픽 키워드 감점({', '.join(soft_off_topic_hits[:3])})")

    if len(text.strip()) < 80:
        score -= 0.8
        reasons.append("본문/요약이 너무 짧음")

    if hard_reject_reason:
        reasons.append(hard_reject_reason)

    return score, reasons, hard_reject_reason


# ---------------------------------------------------------------------
# 6. 대표 필터
# ---------------------------------------------------------------------

def filter_news_evidence_quality(
    evidence_news: List[Dict[str, Any]],
    ai_input: Dict[str, Any],
    min_quality_score: float = 5.0,
    max_items: int = 3,
    require_company_mention: bool = True,
) -> List[Dict[str, Any]]:
    if not evidence_news:
        return []

    scored_items = []

    for item in evidence_news:
        if not isinstance(item, dict):
            continue

        quality_score, quality_reasons, hard_reject_reason = score_news_evidence_item(
            item=item,
            ai_input=ai_input,
        )

        passed = hard_reject_reason is None and quality_score >= min_quality_score

        enriched = {
            **item,
            "quality_score": round(quality_score, 4),
            "quality_reasons": quality_reasons,
            "quality_filter_passed": passed,
            "hard_reject_reason": hard_reject_reason,
        }

        if passed:
            scored_items.append(enriched)

    scored_items.sort(
        key=lambda item: (
            safe_float(item.get("quality_score")),
            safe_float(item.get("relevance_score")),
        ),
        reverse=True,
    )

    deduped = []
    seen = set()

    for item in scored_items:
        key = (
            get_url(item)
            or get_title(item)
        ).lower()

        if key and key in seen:
            continue

        if key:
            seen.add(key)

        deduped.append(item)

        if len(deduped) >= max_items:
            break

    return deduped


def summarize_quality_filter_result(
    before_news: List[Dict[str, Any]],
    after_news: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "source": "news_evidence_quality_filter_v3",
        "before_count": len(before_news or []),
        "after_count": len(after_news or []),
        "removed_count": max(0, len(before_news or []) - len(after_news or [])),
        "quality_scores": [
            item.get("quality_score")
            for item in after_news
        ],
    }


if __name__ == "__main__":
    sample_ai_input = {
        "company_info": {
            "company_name": "삼성전자",
            "stock_code": "005930",
        },
        "analysis_year": 2022,
        "base_year": 2021,
    }

    sample_news = [
        {
            "title": "메모리 수요부진 직격탄…삼성·SK하이닉스 '재고 회전율'도 뚝",
            "metric_key": "asset_turnover",
            "metric_label": "자산회전율",
            "year": 2022,
            "evidence_summary": "삼성전자가 가동률을 높이고 있다는 내용과 재고자산 규모 변화가 언급됩니다.",
            "relevance_score": 0.50,
            "url": "https://example.com/1",
        },
        {
            "title": "삼성SDS 2023년 1분기 실적발표 컨퍼런스콜 전문",
            "metric_key": "revenue",
            "metric_label": "매출액",
            "year": 2023,
            "evidence_summary": "삼성SDS의 매출과 영업이익이 언급되며, 본문에 삼성전자 등 제조 관계사가 한 번 언급됩니다.",
            "relevance_score": 0.39,
            "url": "https://example.com/2",
        },
        {
            "title": "명품백 없어 못사면 명품株로 눈길 돌려라",
            "metric_key": "asset_turnover",
            "metric_label": "자산회전율",
            "year": 2022,
            "evidence_summary": "명품 기업들의 재고자산회전율 상승이 언급됩니다.",
            "relevance_score": 0.43,
            "url": "https://example.com/3",
        },
        {
            "title": "샀다 팔았다 '단타 개미' 김부장, 수익률 꼴찌",
            "metric_key": "asset_turnover",
            "metric_label": "자산회전율",
            "year": 2022,
            "evidence_summary": "개인 투자자들의 매매 회전율이 언급됩니다.",
            "relevance_score": 0.43,
            "url": "https://example.com/4",
        },
    ]

    filtered = filter_news_evidence_quality(
        evidence_news=sample_news,
        ai_input=sample_ai_input,
    )

    print("[News Evidence Quality Filter v3 Test]")
    print("before:", len(sample_news))
    print("after:", len(filtered))

    import json
    print(json.dumps(filtered, ensure_ascii=False, indent=2))
