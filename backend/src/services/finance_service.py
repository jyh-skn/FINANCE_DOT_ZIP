from src.db.queries import fetch_financials_by_stock_code


def safe_divide(numerator, denominator, percent=True):
    if numerator is None or denominator in (None, 0):
        return None

    result = numerator / denominator

    if percent:
        result *= 100

    return round(result, 2)


def calculate_yoy(current, previous):
    if current is None or previous in (None, 0):
        return None

    return round(((current - previous) / previous) * 100, 2)


def group_by_year(rows):
    result = {}

    for row in rows:
        year = row["year"]
        account = row["standard_account"]
        amount = row["thstrm_amount"]

        if year not in result:
            result[year] = {}

        result[year][account] = amount

    return result


def get_account(data, candidates):
    for name in candidates:
        value = data.get(name)
        if value is not None:
            return value
    return None


ACCOUNT_MAP = {
    "revenue": ["매출액", "수익(매출액)", "영업수익"],
    "operating_income": ["영업이익", "영업이익(손실)"],
    "net_income": ["당기순이익", "당기순이익(손실)", "연결당기순이익"],
    "total_assets": ["자산총계"],
    "total_liabilities": ["부채총계"],
    "total_equity": ["자본총계"],

    "current_assets": ["유동자산"],
    "current_liabilities": ["유동부채"],
    "inventory": ["재고자산", "재고자산합계"],
    "receivables": ["매출채권", "매출채권 및 기타채권", "매출채권및기타채권", "매출채권및기타유동채권"],
    "cash": ["현금및현금성자산", "현금 및 현금성자산"],

    "short_term_borrowings": ["단기차입금", "유동성차입금", "유동차입금"],
    "long_term_borrowings": ["장기차입금", "비유동차입금"],
    "bonds": ["사채", "유동성사채", "비유동사채"],

    "interest_expense": ["이자비용", "금융비용", "이자비용(금융원가)"],
    "operating_cash_flow": ["영업활동현금흐름", "영업활동으로 인한 현금흐름", "영업활동 현금흐름"],
}


def calculate_finance_summary(stock_code: str):
    rows = fetch_financials_by_stock_code(stock_code)
    yearly_data = group_by_year(rows)

    summary = []
    previous_item = None

    for year in sorted(yearly_data.keys()):
        data = yearly_data[year]

        revenue = get_account(data, ACCOUNT_MAP["revenue"])
        operating_income = get_account(data, ACCOUNT_MAP["operating_income"])
        net_income = get_account(data, ACCOUNT_MAP["net_income"])
        total_assets = get_account(data, ACCOUNT_MAP["total_assets"])
        total_liabilities = get_account(data, ACCOUNT_MAP["total_liabilities"])
        total_equity = get_account(data, ACCOUNT_MAP["total_equity"])

        current_assets = get_account(data, ACCOUNT_MAP["current_assets"])
        current_liabilities = get_account(data, ACCOUNT_MAP["current_liabilities"])
        inventory = get_account(data, ACCOUNT_MAP["inventory"])
        receivables = get_account(data, ACCOUNT_MAP["receivables"])
        cash = get_account(data, ACCOUNT_MAP["cash"])

        short_term_borrowings = get_account(data, ACCOUNT_MAP["short_term_borrowings"])
        long_term_borrowings = get_account(data, ACCOUNT_MAP["long_term_borrowings"])
        bonds = get_account(data, ACCOUNT_MAP["bonds"])
        interest_expense = get_account(data, ACCOUNT_MAP["interest_expense"])
        operating_cash_flow = get_account(data, ACCOUNT_MAP["operating_cash_flow"])

        total_borrowings = (
            (short_term_borrowings or 0)
            + (long_term_borrowings or 0)
            + (bonds or 0)
        )

        operating_margin = safe_divide(operating_income, revenue)
        net_margin = safe_divide(net_income, revenue)

        debt_ratio = safe_divide(total_liabilities, total_equity)
        equity_ratio = safe_divide(total_equity, total_assets)

        roe = safe_divide(net_income, total_equity)
        roa = safe_divide(net_income, total_assets)

        current_ratio = safe_divide(current_assets, current_liabilities)

        quick_ratio = None
        if current_assets is not None and inventory is not None:
            quick_ratio = safe_divide(
                current_assets - inventory,
                current_liabilities
            )

        borrowings_dependency = None
        if total_borrowings > 0:
            borrowings_dependency = safe_divide(total_borrowings, total_assets)

        interest_coverage_ratio = safe_divide(
            operating_income,
            interest_expense,
            percent=False
        )

        receivables_turnover = safe_divide(
            revenue,
            receivables,
            percent=False
        )

        inventory_turnover = safe_divide(
            revenue,
            inventory,
            percent=False
        )

        asset_turnover = safe_divide(
            revenue,
            total_assets,
            percent=False
        )

        item = {
            "year": year,
            "revenue": revenue,
            "operating_income": operating_income,
            "net_income": net_income,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,

            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "inventory": inventory,
            "receivables": receivables,
            "cash": cash,
            "short_term_borrowings": short_term_borrowings,
            "long_term_borrowings": long_term_borrowings,
            "bonds": bonds,
            "interest_expense": interest_expense,

            "operating_margin": operating_margin,
            "net_margin": net_margin,
            "debt_ratio": debt_ratio,
            "equity_ratio": equity_ratio,
            "roe": roe,
            "roa": roa,

            "current_ratio": current_ratio,
            "quick_ratio": quick_ratio,
            "borrowings_dependency": borrowings_dependency,
            "interest_coverage_ratio": interest_coverage_ratio,
            "receivables_turnover": receivables_turnover,
            "inventory_turnover": inventory_turnover,
            "asset_turnover": asset_turnover,

            "operating_cash_flow": operating_cash_flow,

            "revenue_yoy": None,
            "operating_income_yoy": None,
            "net_income_yoy": None,
            "net_margin_change": None,
            "debt_ratio_change": None,
            "equity_ratio_change": None,
            "receivables_turnover_yoy": None,
            "inventory_turnover_yoy": None,
            "asset_turnover_yoy": None,
            "interest_coverage_ratio_change": None,
            "borrowings_dependency_change": None,
        }

        if previous_item:
            item["revenue_yoy"] = calculate_yoy(
                revenue,
                previous_item.get("revenue")
            )

            item["operating_income_yoy"] = calculate_yoy(
                operating_income,
                previous_item.get("operating_income")
            )

            item["net_income_yoy"] = calculate_yoy(
                net_income,
                previous_item.get("net_income")
            )

            if net_margin is not None and previous_item.get("net_margin") is not None:
                item["net_margin_change"] = round(
                    net_margin - previous_item["net_margin"],
                    2
                )

            if debt_ratio is not None and previous_item.get("debt_ratio") is not None:
                item["debt_ratio_change"] = round(
                    debt_ratio - previous_item["debt_ratio"],
                    2
                )

            if equity_ratio is not None and previous_item.get("equity_ratio") is not None:
                item["equity_ratio_change"] = round(
                    equity_ratio - previous_item["equity_ratio"],
                    2
                )

            item["receivables_turnover_yoy"] = calculate_yoy(
                receivables_turnover,
                previous_item.get("receivables_turnover")
            )

            item["inventory_turnover_yoy"] = calculate_yoy(
                inventory_turnover,
                previous_item.get("inventory_turnover")
            )

            item["asset_turnover_yoy"] = calculate_yoy(
                asset_turnover,
                previous_item.get("asset_turnover")
            )

            if (
                interest_coverage_ratio is not None
                and previous_item.get("interest_coverage_ratio") is not None
            ):
                item["interest_coverage_ratio_change"] = round(
                    interest_coverage_ratio - previous_item["interest_coverage_ratio"],
                    2
                )

            if (
                borrowings_dependency is not None
                and previous_item.get("borrowings_dependency") is not None
            ):
                item["borrowings_dependency_change"] = round(
                    borrowings_dependency - previous_item["borrowings_dependency"],
                    2
                )

        summary.append(item)
        previous_item = item

    return summary
