"""
backend_payload_adapter.py

백엔드 종합 리포트 API 응답을 AI 파이프라인 입력 형식(ai_input)으로 변환하는 Adapter 모듈입니다.

중요:
- 백엔드 API의 detected_changes는 여러 연도/여러 signal을 모두 포함할 수 있습니다.
- AI 뉴스 검색과 최종 리포트는 기본적으로 analysis_year의 핵심 변동만 사용하는 것이 안정적입니다.
- 따라서 all_detected_changes에는 원본 전체를 보존하고,
  detected_changes에는 analysis_year 기준의 high/medium 또는 negative 중심 핵심 변동만 남깁니다.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------
# 1. 재무 지표 정의
# ---------------------------------------------------------------------

METRIC_CONFIG = {
    "revenue": {"label": "매출액", "unit": "KRW", "change_field": "revenue_yoy"},
    "operating_income": {"label": "영업이익", "unit": "KRW", "change_field": "operating_income_yoy"},
    "net_income": {"label": "당기순이익", "unit": "KRW", "change_field": "net_income_yoy"},
    "total_assets": {"label": "총자산", "unit": "KRW", "change_field": None},
    "total_liabilities": {"label": "총부채", "unit": "KRW", "change_field": None},
    "total_equity": {"label": "자본총계", "unit": "KRW", "change_field": None},
    "current_assets": {"label": "유동자산", "unit": "KRW", "change_field": None},
    "current_liabilities": {"label": "유동부채", "unit": "KRW", "change_field": None},
    "inventory": {"label": "재고자산", "unit": "KRW", "change_field": None},
    "receivables": {"label": "매출채권", "unit": "KRW", "change_field": None},
    "cash": {"label": "현금및현금성자산", "unit": "KRW", "change_field": None},
    "short_term_borrowings": {"label": "단기차입금", "unit": "KRW", "change_field": None},
    "long_term_borrowings": {"label": "장기차입금", "unit": "KRW", "change_field": None},
    "bonds": {"label": "사채", "unit": "KRW", "change_field": None},
    "interest_expense": {"label": "이자비용", "unit": "KRW", "change_field": None},
    "operating_margin": {"label": "영업이익률", "unit": "%", "change_field": None},
    "net_margin": {"label": "순이익률", "unit": "%", "change_field": "net_margin_change"},
    "debt_ratio": {"label": "부채비율", "unit": "%", "change_field": "debt_ratio_change"},
    "equity_ratio": {"label": "자기자본비율", "unit": "%", "change_field": "equity_ratio_change"},
    "roe": {"label": "ROE", "unit": "%", "change_field": None},
    "roa": {"label": "ROA", "unit": "%", "change_field": None},
    "current_ratio": {"label": "유동비율", "unit": "%", "change_field": None},
    "quick_ratio": {"label": "당좌비율", "unit": "%", "change_field": None},
    "borrowings_dependency": {"label": "차입금의존도", "unit": "%", "change_field": "borrowings_dependency_change"},
    "interest_coverage_ratio": {"label": "이자보상배율", "unit": "배", "change_field": "interest_coverage_ratio_change"},
    "receivables_turnover": {"label": "매출채권회전율", "unit": "회", "change_field": "receivables_turnover_yoy"},
    "inventory_turnover": {"label": "재고자산회전율", "unit": "회", "change_field": "inventory_turnover_yoy"},
    "asset_turnover": {"label": "자산회전율", "unit": "회", "change_field": "asset_turnover_yoy"},
    "operating_cash_flow": {"label": "영업활동현금흐름", "unit": "KRW", "change_field": None},
}


# ---------------------------------------------------------------------
# 2. 공통 유틸 함수
# ---------------------------------------------------------------------

def unwrap_backend_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    백엔드 API 응답에서 data 영역을 추출합니다.
    이미 data 내부만 전달된 경우에도 그대로 사용할 수 있도록 처리합니다.
    """

    if not isinstance(payload, dict):
        raise TypeError("payload는 dict여야 합니다.")

    data = payload.get("data")

    if isinstance(data, dict):
        return data

    return payload


def sort_finance_summary(finance_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    finance_summary를 연도 오름차순으로 정렬합니다.
    """

    return sorted(finance_summary or [], key=lambda item: item.get("year", 0))


def get_year_row(
    finance_summary: List[Dict[str, Any]],
    year: Optional[int],
) -> Optional[Dict[str, Any]]:
    """
    finance_summary에서 특정 연도의 row를 찾습니다.
    """

    if year is None:
        return None

    for row in finance_summary:
        if row.get("year") == year:
            return row

    return None


def get_available_years(finance_summary: List[Dict[str, Any]]) -> List[int]:
    """
    finance_summary에 존재하는 연도 목록을 반환합니다.
    """

    years = []

    for row in finance_summary or []:
        year = row.get("year")

        if isinstance(year, int):
            years.append(year)

    return sorted(set(years))


def choose_analysis_year(
    finance_summary: List[Dict[str, Any]],
    detected_changes: List[Dict[str, Any]],
) -> Optional[int]:
    """
    분석 대상 연도를 결정합니다.

    우선순위:
    1. detected_changes 중 severity가 high인 항목의 최신 연도
    2. detected_changes 전체의 최신 연도
    3. finance_summary의 최신 연도
    """

    high_years = []

    for change in detected_changes or []:
        severity = str(change.get("severity", "")).lower()
        year = change.get("year")

        if severity == "high" and isinstance(year, int):
            high_years.append(year)

    if high_years:
        return max(high_years)

    change_years = [
        change.get("year")
        for change in detected_changes or []
        if isinstance(change.get("year"), int)
    ]

    if change_years:
        return max(change_years)

    years = get_available_years(finance_summary)

    if years:
        return max(years)

    return None


def choose_base_year(
    finance_summary: List[Dict[str, Any]],
    analysis_year: Optional[int],
) -> Optional[int]:
    """
    비교 기준 연도를 결정합니다.
    """

    if analysis_year is None:
        return None

    years = get_available_years(finance_summary)
    preferred_base_year = analysis_year - 1

    if preferred_base_year in years:
        return preferred_base_year

    previous_years = [year for year in years if year < analysis_year]

    if previous_years:
        return max(previous_years)

    return preferred_base_year


def build_signal_type_map(signals: List[Dict[str, Any]]) -> Dict[Tuple[Optional[int], str], str]:
    """
    signals 목록에서 (year, signal명) 기준으로 type을 찾을 수 있는 map을 생성합니다.
    """

    result = {}

    for signal in signals or []:
        year = signal.get("year")
        signal_name = signal.get("signal")

        if not signal_name:
            continue

        result[(year, signal_name)] = signal.get("type", "")

    return result


def safe_get_change_value(
    current_row: Optional[Dict[str, Any]],
    metric_key: str,
) -> Optional[float]:
    """
    metric_key에 대응하는 yoy/change 값을 current_row에서 가져옵니다.
    """

    if not current_row:
        return None

    config = METRIC_CONFIG.get(metric_key, {})
    change_field = config.get("change_field")

    if not change_field:
        return None

    return current_row.get(change_field)


def get_metric_label(metric_key: str) -> str:
    """
    metric_key에 대응하는 한글 라벨을 반환합니다.
    """

    config = METRIC_CONFIG.get(metric_key, {})
    return config.get("label", metric_key)


# ---------------------------------------------------------------------
# 3. financial_metrics 생성
# ---------------------------------------------------------------------

def build_financial_metrics(
    finance_summary: List[Dict[str, Any]],
    analysis_year: Optional[int],
    base_year: Optional[int],
) -> Dict[str, Dict[str, Any]]:
    """
    finance_summary에서 AI 파이프라인용 financial_metrics를 생성합니다.
    계산을 새로 수행하기보다는 API가 제공한 current/base 값과 yoy/change 필드를 정리합니다.
    """

    current_row = get_year_row(finance_summary, analysis_year)
    base_row = get_year_row(finance_summary, base_year)

    financial_metrics = {}

    if not current_row:
        return financial_metrics

    for metric_key, config in METRIC_CONFIG.items():
        if metric_key not in current_row:
            continue

        current_value = current_row.get(metric_key)
        base_value = base_row.get(metric_key) if base_row else None
        yoy_change_rate = safe_get_change_value(current_row=current_row, metric_key=metric_key)

        financial_metrics[metric_key] = {
            "label": config.get("label", metric_key),
            "current_year": analysis_year,
            "base_year": base_year,
            "current_value": current_value,
            "base_value": base_value,
            "yoy_change_rate": yoy_change_rate,
            "unit": config.get("unit", ""),
        }

    return financial_metrics


# ---------------------------------------------------------------------
# 4. detected_changes 보강 및 필터링
# ---------------------------------------------------------------------

def enrich_detected_changes(
    detected_changes: List[Dict[str, Any]],
    finance_summary: List[Dict[str, Any]],
    base_year: Optional[int],
    signals: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    detected_changes에 AI 파이프라인에서 쓰기 좋은 필드를 보강합니다.

    보강 필드:
    - base_year
    - base_value
    - metric_label fallback
    - signal_type
    """

    enriched_changes = []
    signal_type_map = build_signal_type_map(signals or [])

    for change in detected_changes or []:
        enriched = deepcopy(change)

        metric_key = enriched.get("metric_key")
        year = enriched.get("year")

        if "base_year" not in enriched or enriched.get("base_year") is None:
            enriched["base_year"] = base_year if base_year is not None else (year - 1 if isinstance(year, int) else None)

        if "metric_label" not in enriched or not enriched.get("metric_label"):
            enriched["metric_label"] = get_metric_label(metric_key)

        if "base_value" not in enriched or enriched.get("base_value") is None:
            base_row = get_year_row(finance_summary, enriched.get("base_year"))
            enriched["base_value"] = base_row.get(metric_key) if base_row and metric_key else None

        if "current_value" not in enriched or enriched.get("current_value") is None:
            current_row = get_year_row(finance_summary, year)
            enriched["current_value"] = current_row.get(metric_key) if current_row and metric_key else None

        if "yoy_change_rate" not in enriched or enriched.get("yoy_change_rate") is None:
            current_row = get_year_row(finance_summary, year)
            enriched["yoy_change_rate"] = safe_get_change_value(current_row=current_row, metric_key=metric_key)

        source_signal = enriched.get("source_signal")
        if source_signal:
            enriched["signal_type"] = signal_type_map.get((year, source_signal), enriched.get("signal_type", ""))
        else:
            enriched["signal_type"] = enriched.get("signal_type", "")

        enriched_changes.append(enriched)

    return enriched_changes


def is_primary_detected_change(
    change: Dict[str, Any],
    analysis_year: Optional[int],
) -> bool:
    """
    AI 뉴스 검색/리포트 생성에 우선 사용할 핵심 변동인지 판단합니다.

    기본 기준:
    - analysis_year에 해당하는 변동만 사용
    - severity가 high/medium이면 사용
    - signal_type이 negative이면 사용
    - change_type에 sharp, drop, decrease, risk 등이 들어가면 사용

    low severity positive signal은 전체 데이터에는 보존하지만,
    뉴스 검색 대상으로는 기본 제외합니다.
    """

    if analysis_year is not None and change.get("year") != analysis_year:
        return False

    severity = str(change.get("severity", "")).lower()
    signal_type = str(change.get("signal_type", "")).lower()
    change_type = str(change.get("change_type", "")).lower()
    direction = str(change.get("direction", "")).lower()

    if severity in {"high", "medium"}:
        return True

    if signal_type == "negative":
        return True

    if direction == "decrease" and severity != "low":
        return True

    important_tokens = [
        "sharp",
        "drop",
        "decrease",
        "risk",
        "loss",
        "turn",
        "deterioration",
        "profitability",
    ]

    return any(token in change_type for token in important_tokens)


def filter_primary_detected_changes(
    enriched_changes: List[Dict[str, Any]],
    analysis_year: Optional[int],
) -> List[Dict[str, Any]]:
    """
    전체 detected_changes 중 AI 뉴스 검색/리포트 생성에 사용할 핵심 변동만 필터링합니다.

    필터링 결과가 비어 있으면 analysis_year의 모든 변동을 fallback으로 사용합니다.
    그래도 비어 있으면 전체 enriched_changes를 반환합니다.
    """

    primary_changes = [
        change
        for change in enriched_changes
        if is_primary_detected_change(change, analysis_year)
    ]

    if primary_changes:
        return primary_changes

    same_year_changes = [
        change
        for change in enriched_changes
        if analysis_year is not None and change.get("year") == analysis_year
    ]

    if same_year_changes:
        return same_year_changes

    return enriched_changes


# ---------------------------------------------------------------------
# 5. 대표 변환 함수
# ---------------------------------------------------------------------

def build_ai_input_from_backend_response(
    payload: Dict[str, Any],
    filter_to_primary_changes: bool = True,
) -> Dict[str, Any]:
    """
    백엔드 종합 리포트 API 응답을 create_ai_report() 입력용 ai_input으로 변환합니다.

    Args:
        payload: 백엔드 API 전체 응답 또는 data 내부 dict
        filter_to_primary_changes:
            True이면 ai_input["detected_changes"]에 분석연도 핵심 변동만 넣고,
            전체 변동은 ai_input["all_detected_changes"]에 보존합니다.

    Returns:
        create_ai_report()에 전달 가능한 ai_input dict
    """

    data = unwrap_backend_response(payload)

    company_info = deepcopy(data.get("company_info", {}) or {})
    industry_info = deepcopy(data.get("industry_info", {}) or {})
    finance_summary = sort_finance_summary(deepcopy(data.get("finance_summary", []) or []))
    signals = deepcopy(data.get("signals", []) or [])
    detected_changes = deepcopy(data.get("detected_changes", []) or [])

    analysis_year = choose_analysis_year(finance_summary=finance_summary, detected_changes=detected_changes)
    base_year = choose_base_year(finance_summary=finance_summary, analysis_year=analysis_year)

    financial_metrics = build_financial_metrics(
        finance_summary=finance_summary,
        analysis_year=analysis_year,
        base_year=base_year,
    )

    enriched_detected_changes = enrich_detected_changes(
        detected_changes=detected_changes,
        finance_summary=finance_summary,
        base_year=base_year,
        signals=signals,
    )

    if filter_to_primary_changes:
        ai_detected_changes = filter_primary_detected_changes(
            enriched_changes=enriched_detected_changes,
            analysis_year=analysis_year,
        )
    else:
        ai_detected_changes = enriched_detected_changes

    return {
        "company_info": company_info,
        "industry_info": industry_info,
        "analysis_year": analysis_year,
        "base_year": base_year,
        "finance_summary": finance_summary,
        "financial_metrics": financial_metrics,
        "signals": signals,

        # AI 뉴스 검색/리포트 생성용 핵심 변동
        "detected_changes": ai_detected_changes,

        # 원본 전체 변동 보존용
        "all_detected_changes": enriched_detected_changes,

        "source": "backend_api",
        "adapter_metadata": {
            "original_detected_change_count": len(enriched_detected_changes),
            "selected_detected_change_count": len(ai_detected_changes),
            "filter_to_primary_changes": filter_to_primary_changes,
        },
    }


def build_ai_input_from_backend_data(
    data: Dict[str, Any],
    filter_to_primary_changes: bool = True,
) -> Dict[str, Any]:
    """
    data 내부 dict만 받은 경우 사용할 수 있는 alias 함수입니다.
    """

    return build_ai_input_from_backend_response(
        payload=data,
        filter_to_primary_changes=filter_to_primary_changes,
    )


# ---------------------------------------------------------------------
# 6. 단독 실행용 예시
# ---------------------------------------------------------------------

if __name__ == "__main__":
    print("backend_payload_adapter.py loaded successfully.")
