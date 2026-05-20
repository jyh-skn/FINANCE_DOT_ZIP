"""
financial_context_builder.py

AI 리포트 생성을 위한 재무 context를 구성하는 모듈입니다.

성능 개선 버전:
- LLM을 호출하지 않습니다.
- ai_input에 이미 포함된 finance_summary, financial_metrics, signals, detected_changes를
  rule-based 방식으로 정리합니다.
- 기존 comprehensive_report_service.py의 호출 형태를 유지하기 위해
  build_financial_context(llm, ai_input) 시그니처를 그대로 사용합니다.

기존 병목:
- financial_context_builder에서 LLM 호출 시 10~40초 이상 소요될 수 있었습니다.

개선 방향:
- 재무 수치와 detected_changes는 이미 백엔드/API에서 계산된 구조화 데이터이므로
  LLM으로 다시 요약하지 않고, report_writer_chain에 전달할 context만 정리합니다.
"""

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------
# 1. 공통 유틸
# ---------------------------------------------------------------------

def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except Exception:
        return None


def safe_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None

    try:
        return int(float(value))
    except Exception:
        return None


def format_number(value: Any) -> str:
    """
    숫자를 사람이 읽기 좋은 형태로 변환합니다.
    """

    if value is None:
        return "N/A"

    number = safe_float(value)

    if number is None:
        return safe_text(value)

    abs_number = abs(number)

    # 원 단위 금액이 큰 경우 조/억 단위로 축약
    if abs_number >= 1_0000_0000_0000:
        return f"{number / 1_0000_0000_0000:.2f}조"
    if abs_number >= 1_0000_0000:
        return f"{number / 1_0000_0000:.2f}억"

    if abs_number >= 1000:
        return f"{number:,.0f}"

    return f"{number:.2f}"


def format_rate(value: Any) -> str:
    number = safe_float(value)

    if number is None:
        return "N/A"

    return f"{number:.2f}%"


def build_change_value_text(metric_key: str, value: Any) -> str:
    number = safe_float(value)

    if number is None:
        return "계산 불가"

    if metric_key == "interest_coverage_ratio":
        return f"{number:.2f}배"

    return f"{number:.2f}%"


def normalize_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def get_company_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    return ai_input.get("company_info", {}) or {}


def get_industry_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    return ai_input.get("industry_info", {}) or {}


def get_finance_summary(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    finance_summary = ai_input.get("finance_summary", []) or []

    if not isinstance(finance_summary, list):
        return []

    return finance_summary


def get_financial_metrics(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    financial_metrics = ai_input.get("financial_metrics", {}) or {}

    if not isinstance(financial_metrics, dict):
        return {}

    return financial_metrics


def get_detected_changes(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    detected_changes = ai_input.get("detected_changes", []) or []

    if not isinstance(detected_changes, list):
        return []

    return detected_changes


def get_all_detected_changes(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    all_changes = ai_input.get("all_detected_changes", []) or []

    if isinstance(all_changes, list) and all_changes:
        return all_changes

    return get_detected_changes(ai_input)


def get_signals(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    signals = ai_input.get("signals", []) or []

    if not isinstance(signals, list):
        return []

    return signals


# ---------------------------------------------------------------------
# 2. 정렬 및 요약
# ---------------------------------------------------------------------

def sort_finance_summary(finance_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        finance_summary,
        key=lambda row: safe_int(row.get("year")) or 0,
        reverse=True,
    )


def sort_changes_by_priority(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    severity_score = {
        "high": 3,
        "HIGH": 3,
        "medium": 2,
        "MEDIUM": 2,
        "low": 1,
        "LOW": 1,
    }

    signal_score = {
        "negative": 3,
        "warning": 3,
        "positive": 2,
        "neutral": 1,
    }

    def score(change: Dict[str, Any]) -> tuple:
        severity = change.get("severity")
        signal_type = change.get("signal_type") or change.get("type")
        yoy = safe_float(change.get("yoy_change_rate"))

        return (
            severity_score.get(severity, 0),
            signal_score.get(signal_type, 0),
            abs(yoy or 0),
        )

    return sorted(changes, key=score, reverse=True)


def build_yearly_finance_summary_text(
    finance_summary: List[Dict[str, Any]],
    max_years: int = 5,
) -> str:
    if not finance_summary:
        return "연도별 재무지표 정보가 제공되지 않았습니다."

    rows = sort_finance_summary(finance_summary)[:max_years]
    lines = []

    for row in rows:
        year = row.get("year", "N/A")

        lines.append(
            "- "
            f"{year}년: "
            f"매출액={format_number(row.get('revenue'))}, "
            f"영업이익={format_number(row.get('operating_income'))}, "
            f"당기순이익={format_number(row.get('net_income'))}, "
            f"총자산={format_number(row.get('total_assets'))}, "
            f"총부채={format_number(row.get('total_liabilities'))}, "
            f"자본총계={format_number(row.get('total_equity'))}, "
            f"부채비율={format_rate(row.get('debt_ratio'))}, "
            f"유동비율={format_rate(row.get('current_ratio'))}, "
            f"영업활동현금흐름={format_number(row.get('operating_cash_flow'))}"
        )

    return "\n".join(lines)


def build_detected_change_summary_text(
    detected_changes: List[Dict[str, Any]],
    max_items: int = 5,
) -> str:
    if not detected_changes:
        return "주요 재무 변동 signal이 제공되지 않았습니다."

    sorted_changes = sort_changes_by_priority(detected_changes)[:max_items]
    lines = []

    for item in sorted_changes:
        metric_key = item.get("metric_key")
        metric_label = item.get("metric_label") or item.get("metric_key")
        year = item.get("year")
        base_year = item.get("base_year")
        yoy_change_rate = item.get("yoy_change_rate")
        current_value = item.get("current_value")
        base_value = item.get("base_value")
        direction = item.get("direction")
        description = item.get("description") or item.get("source_signal") or ""

        if direction == "increase":
            direction_text = "증가"
        elif direction == "decrease":
            direction_text = "감소"
        else:
            direction_text = "변동"

        lines.append(
            "- "
            f"{year}년 {metric_label}: "
            f"전년/기준연도({base_year}) 대비 변화값={build_change_value_text(metric_key, yoy_change_rate)}, "
            f"현재값={format_number(current_value)}, "
            f"기준값={format_number(base_value)}, "
            f"{direction_text} 흐름입니다. "
            f"{description}"
        )

    return "\n".join(lines)


def build_signal_summary_text(
    signals: List[Dict[str, Any]],
    max_items: int = 10,
) -> str:
    if not signals:
        return "signals 정보가 제공되지 않았습니다."

    lines = []

    for item in signals[:max_items]:
        lines.append(
            "- "
            f"{item.get('year')}년 / "
            f"{item.get('type') or item.get('signal_type')} / "
            f"{item.get('severity')} / "
            f"{item.get('signal') or item.get('signal_code')}: "
            f"{item.get('description')}"
        )

    return "\n".join(lines)


def build_metric_highlights(
    detected_changes: List[Dict[str, Any]],
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    """
    report_writer_chain이 핵심 지표를 쉽게 사용할 수 있도록 주요 변화만 정리합니다.
    """

    highlights = []

    for item in sort_changes_by_priority(detected_changes)[:max_items]:
        highlights.append(
            {
                "metric_key": item.get("metric_key"),
                "metric_label": item.get("metric_label"),
                "year": item.get("year"),
                "base_year": item.get("base_year"),
                "current_value": item.get("current_value"),
                "base_value": item.get("base_value"),
                "yoy_change_rate": item.get("yoy_change_rate"),
                "change_type": item.get("change_type"),
                "direction": item.get("direction"),
                "severity": item.get("severity"),
                "signal_type": item.get("signal_type"),
                "description": item.get("description") or item.get("source_signal"),
                "search_keywords": item.get("search_keywords", []),
            }
        )

    return highlights


def build_overall_financial_summary(
    ai_input: Dict[str, Any],
    detected_changes: List[Dict[str, Any]],
) -> str:
    """
    LLM 없이 간단한 전체 요약 문장을 생성합니다.
    """

    company_info = get_company_info(ai_input)
    company_name = company_info.get("company_name") or "해당 기업"
    analysis_year = ai_input.get("analysis_year")
    base_year = ai_input.get("base_year")

    if not detected_changes:
        return (
            f"{company_name}의 {analysis_year}년 재무 데이터에서 "
            "뚜렷한 주요 변동 signal이 제공되지 않았습니다. "
            "연도별 재무지표와 뉴스/공시 근거를 함께 확인해야 합니다."
        )

    highlights = sort_changes_by_priority(detected_changes)[:3]
    parts = []

    for item in highlights:
        metric_label = item.get("metric_label") or item.get("metric_key")
        yoy = item.get("yoy_change_rate")
        direction = item.get("direction")

        if direction == "increase":
            direction_text = "증가"
        elif direction == "decrease":
            direction_text = "감소"
        else:
            direction_text = "변동"

        parts.append(
            f"{metric_label}이 기준연도({base_year}) 대비 {format_rate(yoy)} {direction_text}"
        )

    return (
        f"{company_name}의 {analysis_year}년 주요 재무 변화는 "
        + ", ".join(parts)
        + "입니다. 해당 변화는 뉴스 및 공시 근거와 함께 해석해야 합니다."
    )


# ---------------------------------------------------------------------
# 3. 대표 함수
# ---------------------------------------------------------------------

def build_financial_context(
    llm: Any,
    ai_input: Dict[str, Any],
    max_finance_years: int = 5,
    max_changes: int = 5,
    max_signals: int = 10,
) -> Dict[str, Any]:
    """
    AI 리포트 생성용 재무 context를 구성합니다.

    Args:
        llm: 호환성을 위해 받지만 사용하지 않습니다.
        ai_input: backend_payload_adapter.py가 생성한 AI 입력 데이터

    Returns:
        report_writer_chain이 사용할 수 있는 재무 context dict
    """

    company_info = get_company_info(ai_input)
    industry_info = get_industry_info(ai_input)
    finance_summary = get_finance_summary(ai_input)
    financial_metrics = get_financial_metrics(ai_input)
    detected_changes = get_detected_changes(ai_input)
    all_detected_changes = get_all_detected_changes(ai_input)
    signals = get_signals(ai_input)

    sorted_finance_summary = sort_finance_summary(finance_summary)
    sorted_detected_changes = sort_changes_by_priority(detected_changes)
    sorted_all_detected_changes = sort_changes_by_priority(all_detected_changes)

    yearly_finance_summary_text = build_yearly_finance_summary_text(
        finance_summary=sorted_finance_summary,
        max_years=max_finance_years,
    )
    detected_change_summary_text = build_detected_change_summary_text(
        detected_changes=sorted_detected_changes,
        max_items=max_changes,
    )
    signal_summary_text = build_signal_summary_text(
        signals=signals,
        max_items=max_signals,
    )
    overall_summary = build_overall_financial_summary(
        ai_input=ai_input,
        detected_changes=sorted_detected_changes,
    )
    metric_highlights = build_metric_highlights(
        detected_changes=sorted_detected_changes,
        max_items=max_changes,
    )

    context_text = "\n\n".join(
        [
            "[기업 정보]",
            f"기업명: {company_info.get('company_name')}",
            f"종목코드: {company_info.get('stock_code')}",
            f"업종: {industry_info.get('industry_group_name')} ({industry_info.get('industry_group')})",
            f"분석 연도: {ai_input.get('analysis_year')}",
            f"비교 기준 연도: {ai_input.get('base_year')}",
            "",
            "[재무 요약]",
            overall_summary,
            "",
            "[연도별 재무지표]",
            yearly_finance_summary_text,
            "",
            "[핵심 detected_changes]",
            detected_change_summary_text,
            "",
            "[signals]",
            signal_summary_text,
        ]
    ).strip()

    return {
        "source": "rule_based",
        "company_info": company_info,
        "industry_info": industry_info,
        "analysis_year": ai_input.get("analysis_year"),
        "base_year": ai_input.get("base_year"),
        "finance_summary": sorted_finance_summary[:max_finance_years],
        "financial_metrics": financial_metrics,
        "signals": signals[:max_signals],
        "detected_changes": sorted_detected_changes[:max_changes],
        "all_detected_changes": sorted_all_detected_changes,
        "metric_highlights": metric_highlights,

        # report_writer_chain 호환용 여러 이름 제공
        "summary": overall_summary,
        "overall_summary": overall_summary,
        "financial_summary": overall_summary,
        "financial_change_summary": detected_change_summary_text,
        "yearly_finance_summary": yearly_finance_summary_text,
        "detected_change_summary": detected_change_summary_text,
        "signal_summary": signal_summary_text,
        "context_text": context_text,

        "metadata": {
            "source": "rule_based",
            "llm_used": False,
            "finance_summary_count": len(finance_summary),
            "financial_metric_count": len(financial_metrics),
            "detected_change_count": len(detected_changes),
            "all_detected_change_count": len(all_detected_changes),
            "signal_count": len(signals),
        },
    }


# 기존 코드 호환용 alias
def build_context(
    llm: Any,
    ai_input: Dict[str, Any],
) -> Dict[str, Any]:
    return build_financial_context(
        llm=llm,
        ai_input=ai_input,
    )


if __name__ == "__main__":
    sample_ai_input = {
        "company_info": {
            "company_name": "파트론",
            "stock_code": "091700",
        },
        "industry_info": {
            "industry_group": "tech_equipment",
            "industry_group_name": "기술 및 장치 산업",
        },
        "analysis_year": 2021,
        "base_year": 2020,
        "finance_summary": [
            {
                "year": 2021,
                "revenue": 1310000000000,
                "operating_income": 78708841559,
                "net_income": 65000000000,
                "debt_ratio": 45.2,
                "current_ratio": 180.3,
                "operating_cash_flow": 92000000000,
            },
            {
                "year": 2020,
                "revenue": 1180000000000,
                "operating_income": 41900000000,
                "net_income": 30000000000,
                "debt_ratio": 55.1,
                "current_ratio": 160.2,
                "operating_cash_flow": 70000000000,
            },
        ],
        "detected_changes": [
            {
                "metric_key": "operating_income",
                "metric_label": "영업이익",
                "year": 2021,
                "base_year": 2020,
                "current_value": 78708841559,
                "base_value": 41900000000,
                "yoy_change_rate": 87.66,
                "change_type": "sharp_increase",
                "direction": "increase",
                "severity": "high",
                "signal_type": "positive",
                "description": "영업이익이 전년 대비 크게 증가했습니다.",
            }
        ],
        "signals": [
            {
                "year": 2021,
                "type": "positive",
                "severity": "HIGH",
                "signal": "영업이익 급증",
                "description": "전년 대비 영업이익이 87.66% 증가했습니다.",
            }
        ],
    }

    result = build_financial_context(
        llm=None,
        ai_input=sample_ai_input,
    )

    import json
    print("[Fast Financial Context Builder Test]")
    print(json.dumps(result, ensure_ascii=False, indent=2))
