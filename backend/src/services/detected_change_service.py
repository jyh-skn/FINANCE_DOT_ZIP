"""
AI 연동용 detected_changes 생성 모듈

역할:
- signal_service.py에서 생성된 signals를 AI 파트가 사용하기 쉬운 구조로 변환
- signal_code 기반으로 안정적으로 매핑
- Tavily / Vector DB 검색에 사용할 query_hint, search_keywords 포함
"""


SIGNAL_TO_CHANGE_RULES = {
    "REVENUE_DROP_50": {
        "metric_key": "revenue",
        "metric_label": "매출액",
        "change_type": "sharp_decrease",
        "direction": "decrease",
        "search_keywords": ["매출 급감", "수요 둔화", "실적 부진", "업황 악화"],
    },
    "OPERATING_LOSS_3Y": {
        "metric_key": "operating_income",
        "metric_label": "영업이익",
        "change_type": "continuous_loss",
        "direction": "decrease",
        "search_keywords": ["영업손실 지속", "수익성 악화", "구조적 적자"],
    },
    "INTEREST_COVERAGE_3Y_LOW": {
        "metric_key": "interest_coverage_ratio",
        "metric_label": "이자보상배율",
        "change_type": "low_level",
        "direction": "decrease",
        "search_keywords": ["이자보상배율 하락", "금융비용 부담", "한계기업"],
    },
    "CASH_FLOW_NEGATIVE_3Y": {
        "metric_key": "operating_cash_flow",
        "metric_label": "영업활동현금흐름",
        "change_type": "continuous_negative",
        "direction": "decrease",
        "search_keywords": ["영업현금흐름 적자", "현금흐름 악화", "유동성 우려"],
    },
    "CASH_LESS_THAN_SHORT_BORROWINGS": {
        "metric_key": "cash",
        "metric_label": "현금성자산",
        "change_type": "liquidity_shortage",
        "direction": "decrease",
        "search_keywords": ["현금 부족", "단기차입금 부담", "유동성 위험"],
    },
    "DEBT_RATIO_OVER_400": {
        "metric_key": "debt_ratio",
        "metric_label": "부채비율",
        "change_type": "high_level",
        "direction": "increase",
        "search_keywords": ["부채비율 과다", "재무 부담", "차입금 증가", "재무구조 악화"],
    },
    "CAPITAL_IMPAIRMENT_PARTIAL": {
        "metric_key": "total_equity",
        "metric_label": "자본총계",
        "change_type": "capital_impairment",
        "direction": "decrease",
        "search_keywords": ["부분자본잠식", "자본잠식", "재무구조 악화"],
    },
    "CAPITAL_IMPAIRMENT_FULL": {
        "metric_key": "total_equity",
        "metric_label": "자본총계",
        "change_type": "full_capital_impairment",
        "direction": "decrease",
        "search_keywords": ["완전자본잠식", "자본잠식", "상장폐지 위험"],
    },
    "REVENUE_JUMP": {
        "metric_key": "revenue",
        "metric_label": "매출액",
        "change_type": "sharp_increase",
        "direction": "increase",
        "search_keywords": ["매출 성장", "수요 증가", "신사업 성장", "실적 개선"],
    },
    "EARNINGS_SURPRISE": {
        "metric_key": "operating_income",
        "metric_label": "영업이익",
        "change_type": "sharp_increase",
        "direction": "increase",
        "search_keywords": ["어닝 서프라이즈", "영업이익 증가", "실적 개선"],
    },
    "OPERATING_INCOME_TURN_TO_PROFIT": {
        "metric_key": "operating_income",
        "metric_label": "영업이익",
        "change_type": "turnaround",
        "direction": "increase",
        "search_keywords": ["흑자 전환", "턴어라운드", "수익성 개선"],
    },
    "ASSET_EFFICIENCY_UP": {
        "metric_key": "asset_turnover",
        "metric_label": "자산회전율",
        "change_type": "improve",
        "direction": "increase",
        "search_keywords": ["자산 효율성 개선", "자산회전율 상승", "운영 효율화"],
    },
    "CAPACITY_EXPANSION": {
        "metric_key": "total_assets",
        "metric_label": "자산 규모",
        "change_type": "capacity_expansion",
        "direction": "increase",
        "search_keywords": ["설비 투자", "CAPEX", "생산능력 확대", "투자 확대"],
    },
    "DEBT_RATIO_DOWN": {
        "metric_key": "debt_ratio",
        "metric_label": "부채비율",
        "change_type": "improve",
        "direction": "decrease",
        "search_keywords": ["부채비율 감소", "재무구조 개선", "디레버리징"],
    },
    "CASH_FLOW_STRONG": {
        "metric_key": "operating_cash_flow",
        "metric_label": "영업활동현금흐름",
        "change_type": "improve",
        "direction": "increase",
        "search_keywords": ["영업현금흐름 개선", "현금 창출력", "현금흐름 개선"],
    },
    "TECH_LOSS_WIDENING_3Y": {
        "metric_key": "operating_income",
        "metric_label": "영업이익",
        "change_type": "industry_loss_widening",
        "direction": "decrease",
        "search_keywords": ["기술 기업 적자 확대", "R&D 비용 부담", "현금 소진"],
    },
    "TECH_CAPA_EXPANSION_CASH_RISK": {
        "metric_key": "operating_cash_flow",
        "metric_label": "영업활동현금흐름",
        "change_type": "investment_cash_risk",
        "direction": "decrease",
        "search_keywords": ["투자 부담", "현금흐름 악화", "설비투자 리스크"],
    },
    "MANUFACTURING_MARGIN_DROP_INTEREST_RISK": {
        "metric_key": "operating_margin",
        "metric_label": "영업이익률",
        "change_type": "profitability_drop",
        "direction": "decrease",
        "search_keywords": ["제조업 수익성 악화", "이자 부담", "고정비 부담"],
    },
    "MANUFACTURING_INVENTORY_LIQUIDITY_RISK": {
        "metric_key": "inventory_turnover",
        "metric_label": "재고자산회전율",
        "change_type": "inventory_liquidity_risk",
        "direction": "decrease",
        "search_keywords": ["재고 부담", "재고 적체", "유동성 위험"],
    },
    "DISTRIBUTION_LOW_MARGIN_REVENUE_DROP": {
        "metric_key": "operating_margin",
        "metric_label": "영업이익률",
        "change_type": "low_margin_revenue_drop",
        "direction": "decrease",
        "search_keywords": ["저마진", "매출 감소", "유통업 수익성 악화"],
    },
    "DISTRIBUTION_COLLECTION_LIQUIDITY_RISK": {
        "metric_key": "receivables_turnover",
        "metric_label": "매출채권회전율",
        "change_type": "collection_liquidity_risk",
        "direction": "decrease",
        "search_keywords": ["매출채권 회수 지연", "현금 회전 악화", "유동성 위험"],
    },
    "CONSTRUCTION_CASH_FLOW_SHORT_BORROWING_RISK": {
        "metric_key": "operating_cash_flow",
        "metric_label": "영업활동현금흐름",
        "change_type": "cash_flow_borrowing_risk",
        "direction": "decrease",
        "search_keywords": ["건설 현금흐름 악화", "단기차입금 증가", "수주형 리스크"],
    },
    "CONSTRUCTION_CASH_FLOW_RISK": {
        "metric_key": "operating_cash_flow",
        "metric_label": "영업활동현금흐름",
        "change_type": "cash_flow_risk",
        "direction": "decrease",
        "search_keywords": ["수주형 현금흐름 악화", "미청구공사", "공사대금 회수 지연"],
    },
    "FACILITY_SERVICE_INTEREST_BURDEN": {
        "metric_key": "interest_expense",
        "metric_label": "이자비용",
        "change_type": "interest_burden",
        "direction": "increase",
        "search_keywords": ["장치형 서비스 금융비용", "이자비용 부담", "고정비 부담"],
    },
}


SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFO": "info",
}


def get_year_item_map(finance_summary):
    return {
        item.get("year"): item
        for item in finance_summary
        if item.get("year") is not None
    }


def get_base_year(year, finance_summary):
    if year is None:
        return None

    years = sorted([
        item.get("year")
        for item in finance_summary
        if item.get("year") is not None
    ])

    previous_years = [
        target_year
        for target_year in years
        if target_year < year
    ]

    if previous_years:
        return previous_years[-1]

    return None


def get_metric_value(item, metric_key):
    if not item:
        return None

    if metric_key == "asset_turnover":
        revenue = item.get("revenue")
        total_assets = item.get("total_assets")

        if revenue is None or total_assets in (None, 0):
            return None

        return round(revenue / total_assets, 4)

    return item.get(metric_key)


def get_metric_yoy(item, metric_key):
    if not item:
        return None

    yoy_key_map = {
        "revenue": "revenue_yoy",
        "operating_income": "operating_income_yoy",
        "net_income": "net_income_yoy",
        "debt_ratio": "debt_ratio_change",
        "equity_ratio": "equity_ratio_change",
        "receivables_turnover": "receivables_turnover_yoy",
        "inventory_turnover": "inventory_turnover_yoy",
        "asset_turnover": "asset_turnover_yoy",
        "interest_coverage_ratio": "interest_coverage_ratio_change",
        "borrowings_dependency": "borrowings_dependency_change",
        "net_margin": "net_margin_change",
    }

    yoy_key = yoy_key_map.get(metric_key)

    if not yoy_key:
        return None

    return item.get(yoy_key)


def build_detected_change(
    signal,
    finance_summary,
    company_name="",
    stock_code="",
    industry_group="unknown",
):
    signal_code = signal.get("signal_code")
    rule = SIGNAL_TO_CHANGE_RULES.get(signal_code)

    if not rule:
        return None

    year = signal.get("year")
    base_year = get_base_year(year, finance_summary)

    year_item_map = get_year_item_map(finance_summary)
    current_item = year_item_map.get(year)

    metric_key = signal.get("metric_key") or rule["metric_key"]
    current_value = get_metric_value(current_item, metric_key)
    yoy_change_rate = get_metric_yoy(current_item, metric_key)

    source_signal = signal.get("signal", "")
    signal_type = signal.get("type", "unknown")

    query_hint = f"{company_name} {source_signal} 원인".strip()

    return {
        "metric_key": metric_key,
        "metric_label": rule["metric_label"],
        "year": year,
        "base_year": base_year,
        "change_type": rule["change_type"],
        "direction": rule["direction"],
        "severity": SEVERITY_MAP.get(signal.get("severity"), "medium"),
        "signal_type": signal_type,
        "signal_code": signal_code,
        "company_name": company_name,
        "stock_code": stock_code,
        "industry_group": industry_group,
        "current_value": current_value,
        "yoy_change_rate": yoy_change_rate,
        "description": signal.get("description", ""),
        "source_signal": source_signal,
        "query_hint": query_hint,
        "search_keywords": rule["search_keywords"],
    }


def build_detected_changes(
    finance_summary,
    signals,
    company_name="",
    stock_code="",
    industry_group="unknown",
):
    detected_changes = []

    if not signals:
        return detected_changes

    for signal in signals:
        change = build_detected_change(
            signal,
            finance_summary,
            company_name=company_name,
            stock_code=stock_code,
            industry_group=industry_group,
        )

        if change:
            detected_changes.append(change)

    return detected_changes
