from src.db.connection import get_connection


def fetch_financials_by_stock_code(stock_code: str):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    stock_code,
                    year,
                    standard_account,
                    thstrm_amount
                FROM financials
                WHERE stock_code = %s
                ORDER BY year ASC
                """,
                (stock_code,)
            )
            return cursor.fetchall()

    finally:
        conn.close()


def fetch_company_info_by_stock_code(stock_code: str):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    stock_code,
                    corp_code,
                    company_name,
                    induty_code
                FROM companies
                WHERE stock_code = %s
                LIMIT 1
                """,
                (stock_code,)
            )
            return cursor.fetchone()

    finally:
        conn.close()


def search_companies(keyword: str, limit: int = 20):
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            like_keyword = f"%{keyword}%"
            cursor.execute(
                """
                SELECT
                    c.stock_code,
                    c.corp_code,
                    c.company_name,
                    c.induty_code
                FROM companies c
                WHERE EXISTS (
                    SELECT 1
                    FROM financials f
                    WHERE f.stock_code = c.stock_code
                )
                  AND (
                    c.company_name LIKE %s
                    OR c.stock_code LIKE %s
                  )
                ORDER BY c.company_name ASC
                LIMIT %s
                """,
                (like_keyword, like_keyword, limit)
            )
            rows = cursor.fetchall()

    finally:
        conn.close()

    return [
        {
            **row,
            "CORP_NAME": row.get("company_name", ""),
            "CORP_CODE": row.get("stock_code", ""),
            "TICKER": row.get("stock_code", ""),
        }
        for row in rows
    ]

def search_origin_companies():
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    c.stock_code,
                    c.company_name
                FROM companies c
                WHERE EXISTS (
                    SELECT 1
                    FROM financials f
                    WHERE f.stock_code = c.stock_code
                )
                ORDER BY c.company_name ASC
                """,
            )
            rows = cursor.fetchall()

    finally:
        conn.close()

    return [
        {
            **row,
            "CORP_NAME": row.get("company_name", ""),
            "CORP_CODE": row.get("stock_code", ""),
            "TICKER": row.get("stock_code", ""),
        }
        for row in rows
    ]

