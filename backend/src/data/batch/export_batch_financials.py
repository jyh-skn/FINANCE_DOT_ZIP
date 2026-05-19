"""
batch companies.csv를 기준으로 OpenDART 전체 재무제표 CSV export를 생성합니다.

이 스크립트는 data/export/<batch_id>/companies.csv를 입력으로 사용합니다.
각 회사와 연도에 대해 fnlttSinglAcntAll.json을 호출할 수 있도록 설계되어 있으며,
실행 시에는 반드시 --limit 3처럼 작은 범위로 먼저 검증한 뒤 확대해야 합니다.
DB 저장, 재무비율 계산, Signal 계산 로직은 실행하지 않습니다.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


BACKEND_SRC_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = BACKEND_SRC_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.data.batch.create_batch_templates import CSV_HEADERS, EXPORT_ROOT  # noqa: E402
from src.data.process_single_all_accounts import build_signal_account_availability  # noqa: E402
from src.services.financial_processor import (  # noqa: E402
    build_single_all_account_availability,
    build_single_all_standard_financials,
)


load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")
DART_API_KEY = os.getenv("DART_API_KEY", "")
DART_API_BASE = "https://opendart.fss.or.kr/api"
SOURCE_API = "fnlttSinglAcntAll.json"


def latest_available_business_year(run_date: date | None = None) -> int:
    """Return the latest business year whose annual report is usually available."""
    run_date = run_date or date.today()
    if run_date.month >= 4:
        return run_date.year - 1
    return run_date.year - 2


def recent_business_years(count: int = 5, run_date: date | None = None) -> list[int]:
    """Return recent business years for annual-report based collection."""
    if count <= 0:
        raise ValueError("year count must be greater than 0.")

    end_year = latest_available_business_year(run_date)
    start_year = end_year - count + 1
    return list(range(start_year, end_year + 1))


def parse_years(years_value: str) -> list[int]:
    """Parse year input such as recent5, 2021-2025, or 2021,2022."""
    value = (years_value or "").strip().lower()
    if value in {"", "recent", "latest", "recent5", "last5"}:
        return recent_business_years(5)
    if value in {"recent3", "last3"}:
        return recent_business_years(3)
    if value in {"recent4", "last4"}:
        return recent_business_years(4)

    if "-" in value:
        start_text, end_text = value.split("-", 1)
        start_year = int(start_text)
        end_year = int(end_text)
        if start_year > end_year:
            raise ValueError("--years 시작 연도는 종료 연도보다 작거나 같아야 합니다.")
        return list(range(start_year, end_year + 1))
    return [int(year.strip()) for year in value.split(",") if year.strip()]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """CSV 파일을 dict row 목록으로 읽습니다."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """CSV 파일을 헤더와 함께 덮어씁니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def append_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """기존 CSV의 행 뒤에 새 row를 추가합니다."""
    existing_rows = read_csv_rows(path)
    existing_rows.extend(rows)
    write_csv_rows(path, fieldnames, existing_rows)


def row_key(row: dict[str, Any], fields: list[str]) -> tuple[str, ...]:
    """중복 방지에 사용할 key tuple을 만듭니다."""
    return tuple(str(row.get(field, "")) for field in fields)


def sanitize_error_message(message: str) -> str:
    """오류 메시지에 API 키가 포함되지 않도록 인증 파라미터를 마스킹합니다."""
    return re.sub(r"(crtfc_key=)[^&\s)]+", r"\1***", message or "")


def merge_csv_rows(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
    key_fields: list[str],
) -> None:
    """key 기준으로 기존 행을 새 행으로 갱신해 중복 append를 방지합니다."""
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    ordered_keys: list[tuple[str, ...]] = []

    for row in read_csv_rows(path):
        key = row_key(row, key_fields)
        merged[key] = row
        ordered_keys.append(key)

    for row in rows:
        key = row_key(row, key_fields)
        if key not in merged:
            ordered_keys.append(key)
        merged[key] = row

    unique_ordered_keys = []
    seen = set()
    for key in ordered_keys:
        if key in seen:
            continue
        seen.add(key)
        unique_ordered_keys.append(key)

    write_csv_rows(path, fieldnames, [merged[key] for key in unique_ordered_keys])


def load_companies(batch_id: str, limit: int | None) -> list[dict[str, str]]:
    """batch companies.csv에서 처리 대상 회사를 읽습니다."""
    companies_path = EXPORT_ROOT / batch_id / "companies.csv"
    rows = [row for row in read_csv_rows(companies_path) if row.get("corp_code") and row.get("stock_code")]
    if limit is not None and limit > 0:
        return rows[:limit]
    return rows


def load_success_keys(batch_id: str) -> set[tuple[str, str, str, str]]:
    """collection_log.csv에서 이미 성공한 회사/연도/보고서/재무제표 구분 조합을 읽습니다."""
    log_path = EXPORT_ROOT / batch_id / "collection_log.csv"
    keys: set[tuple[str, str, str, str]] = set()
    for row in read_csv_rows(log_path):
        if row.get("status") != "success":
            continue
        keys.add((
            row.get("stock_code", ""),
            row.get("bsns_year", ""),
            row.get("reprt_code", ""),
            row.get("fs_div", ""),
        ))
    return keys


def fetch_single_company_all_accounts(
    corp_code: str,
    bsns_year: int,
    reprt_code: str,
    fs_div: str,
    timeout: int = 20,
) -> dict[str, Any]:
    """OpenDART 전체 재무제표 API 응답을 성공/실패와 관계없이 반환합니다."""
    url = f"{DART_API_BASE}/{SOURCE_API}"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": fs_div,
    }
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def build_raw_rows(
    batch_id: str,
    company: dict[str, str],
    year: int,
    reprt_code: str,
    fs_div: str,
    items: list[dict[str, Any]],
    collected_at: str,
) -> list[dict[str, Any]]:
    """OpenDART 원본 계정 행을 financial_accounts_raw.csv 형식으로 변환합니다."""
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append({
            "batch_id": batch_id,
            "corp_code": company.get("corp_code", ""),
            "stock_code": company.get("stock_code", ""),
            "corp_name": company.get("corp_name", ""),
            "bsns_year": item.get("bsns_year") or year,
            "reprt_code": item.get("reprt_code") or reprt_code,
            "fs_div": item.get("fs_div") or fs_div,
            "fs_nm": item.get("fs_nm", ""),
            "sj_div": item.get("sj_div", ""),
            "sj_nm": item.get("sj_nm", ""),
            "account_id": item.get("account_id", ""),
            "account_nm": item.get("account_nm", ""),
            "account_detail": item.get("account_detail", ""),
            "thstrm_nm": item.get("thstrm_nm", ""),
            "thstrm_amount": item.get("thstrm_amount", ""),
            "frmtrm_nm": item.get("frmtrm_nm", ""),
            "frmtrm_amount": item.get("frmtrm_amount", ""),
            "bfefrmtrm_nm": item.get("bfefrmtrm_nm", ""),
            "bfefrmtrm_amount": item.get("bfefrmtrm_amount", ""),
            "ord": item.get("ord", ""),
            "currency": item.get("currency", ""),
            "rcept_no": item.get("rcept_no", ""),
            "source_api": SOURCE_API,
            "collected_at": collected_at,
        })
    return rows


def build_standard_rows(
    batch_id: str,
    company: dict[str, str],
    raw_data: dict[str, Any],
    collected_at: str,
    default_fs_div: str,
) -> list[dict[str, Any]]:
    """표준 계정 매핑 결과를 financial_accounts_standard.csv 형식으로 변환합니다."""
    rows: list[dict[str, Any]] = []
    for row in build_single_all_standard_financials(raw_data):
        rows.append({
            "batch_id": batch_id,
            "corp_code": company.get("corp_code", ""),
            "stock_code": company.get("stock_code", ""),
            "corp_name": company.get("corp_name", ""),
            "bsns_year": row.get("year", ""),
            "reprt_code": row.get("reprt_code", ""),
            "fs_div": row.get("fs_div") or default_fs_div,
            "sj_div": row.get("sj_div", ""),
            "standard_account": row.get("standard_account", ""),
            "account_nm": row.get("account_nm", ""),
            "account_id": row.get("account_id", ""),
            "amount": row.get("thstrm_amount", ""),
            "currency": row.get("currency", ""),
            "mapping_status": row.get("match_type", ""),
            "is_proxy": "false",
            "proxy_reason": "",
            "rcept_no": row.get("rcept_no", ""),
            "collected_at": collected_at,
        })
    return rows


def build_report_rows(
    batch_id: str,
    company: dict[str, str],
    year: int,
    reprt_code: str,
    fs_div: str,
    items: list[dict[str, Any]],
    collected_at: str,
) -> list[dict[str, Any]]:
    """보고서 단위 메타 정보를 reports.csv 형식으로 변환합니다."""
    rcept_numbers = sorted({item.get("rcept_no", "") for item in items if item.get("rcept_no")})
    if not rcept_numbers:
        rcept_numbers = [""]
    return [
        {
            "batch_id": batch_id,
            "rcept_no": rcept_no,
            "corp_code": company.get("corp_code", ""),
            "stock_code": company.get("stock_code", ""),
            "corp_name": company.get("corp_name", ""),
            "bsns_year": year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
            "report_name": "",
            "source_api": SOURCE_API,
            "collected_at": collected_at,
        }
        for rcept_no in rcept_numbers
    ]


def add_company_fields(
    rows: list[dict[str, Any]],
    batch_id: str,
    company: dict[str, str],
) -> list[dict[str, Any]]:
    """availability row에 batch와 회사 식별 컬럼을 추가합니다."""
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        enriched = {
            "batch_id": batch_id,
            "corp_code": company.get("corp_code", ""),
            "stock_code": company.get("stock_code", ""),
            "corp_name": company.get("corp_name", ""),
        }
        enriched.update(row)
        enriched_rows.append(enriched)
    return enriched_rows


def build_log_row(
    batch_id: str,
    company: dict[str, str],
    year: int,
    reprt_code: str,
    fs_div: str,
    status: str,
    started_at: str,
    finished_at: str,
    error_code: str = "",
    error_message: str = "",
    retry_count: int = 0,
) -> dict[str, Any]:
    """collection_log.csv 한 행을 만듭니다."""
    return {
        "batch_id": batch_id,
        "market": company.get("market", ""),
        "stock_code": company.get("stock_code", ""),
        "corp_code": company.get("corp_code", ""),
        "corp_name": company.get("corp_name", ""),
        "bsns_year": year,
        "reprt_code": reprt_code,
        "fs_div": fs_div,
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "retry_count": retry_count,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def classify_api_failure(response: dict[str, Any] | None) -> tuple[str, str, str]:
    """OpenDART 응답 실패를 collection_log 상태로 분류합니다."""
    if not response:
        return "failed", "exception", "empty response"

    status_code = str(response.get("status", "")).strip()
    message = str(response.get("message", "")).strip()
    if status_code in {"013", "014"} or "조회된 데이타가 없습니다" in message or "조회된 데이터가 없습니다" in message:
        return "no_data", status_code, message
    if status_code in {"020", "800"} or "요청 제한" in message or "rate" in message.lower():
        return "rate_limited", status_code, message
    return "failed", status_code, message


def build_fs_div_attempts(fs_div: str) -> list[str]:
    """Return financial statement divisions to try for one company/year.

    The default collection target is CFS, but some listed companies only expose
    OFS data. In that case, try OFS after CFS returns no_data.
    """
    requested_fs_div = (fs_div or "").strip().upper() or "CFS"
    attempts = [requested_fs_div]
    if requested_fs_div == "CFS":
        attempts.append("OFS")
    return attempts


def collect_batch_financials(
    batch_id: str,
    years: list[int],
    reprt_code: str,
    fs_div: str,
    limit: int | None,
    skip_existing: bool,
    sleep_interval: float,
) -> dict[str, int]:
    """지정 batch의 회사 목록을 순회하며 재무제표 CSV export를 생성합니다."""
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY가 설정되지 않았습니다.")

    batch_dir = EXPORT_ROOT / batch_id
    companies = load_companies(batch_id, limit)
    success_keys = load_success_keys(batch_id) if skip_existing else set()

    raw_rows: list[dict[str, Any]] = []
    standard_rows: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    account_rows: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    counters = {"success": 0, "failed": 0, "no_data": 0, "rate_limited": 0, "skipped": 0}

    print(
        f"[start] batch_id={batch_id}, companies={len(companies)}, "
        f"years={years[0]}-{years[-1] if years else ''}",
        flush=True,
    )

    for company_index, company in enumerate(companies, start=1):
        print(
            f"[current] {company_index}/{len(companies)} "
            f"stock_code={company.get('stock_code', '')} corp_name={company.get('corp_name', '')}",
            flush=True,
        )

        company_raw_data: dict[str, Any] = {"data": {}}

        for year in years:
            fs_div_attempts = build_fs_div_attempts(fs_div)
            if any((company.get("stock_code", ""), str(year), reprt_code, attempt_fs_div) in success_keys for attempt_fs_div in fs_div_attempts):
                counters["skipped"] += 1
                continue

            for attempt_index, attempt_fs_div in enumerate(fs_div_attempts):
                started_at = datetime.now().isoformat(timespec="seconds")
                response: dict[str, Any] | None = None
                exception_message = ""
                try:
                    response = fetch_single_company_all_accounts(
                        corp_code=company.get("corp_code", ""),
                        bsns_year=year,
                        reprt_code=reprt_code,
                        fs_div=attempt_fs_div,
                    )
                except requests.RequestException as exc:
                    exception_message = sanitize_error_message(str(exc))
                finished_at = datetime.now().isoformat(timespec="seconds")
                collected_at = finished_at

                if response and response.get("status") == "000":
                    items = [
                        {**item, "fs_div": item.get("fs_div") or attempt_fs_div}
                        for item in response.get("list", [])
                    ]
                    if items:
                        company_raw_data["data"][str(year)] = items
                        raw_rows.extend(build_raw_rows(batch_id, company, year, reprt_code, attempt_fs_div, items, collected_at))
                        report_rows.extend(build_report_rows(batch_id, company, year, reprt_code, attempt_fs_div, items, collected_at))
                        log_rows.append(build_log_row(batch_id, company, year, reprt_code, attempt_fs_div, "success", started_at, finished_at))
                        counters["success"] += 1
                    else:
                        log_rows.append(build_log_row(batch_id, company, year, reprt_code, attempt_fs_div, "no_data", started_at, finished_at))
                        counters["no_data"] += 1
                    break

                if exception_message:
                    status, error_code, error_message = "failed", "exception", exception_message
                else:
                    status, error_code, error_message = classify_api_failure(response)
                log_rows.append(
                    build_log_row(
                        batch_id,
                        company,
                        year,
                        reprt_code,
                        attempt_fs_div,
                        status,
                        started_at,
                        finished_at,
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
                counters[status] = counters.get(status, 0) + 1

                should_try_ofs = (
                    status == "no_data"
                    and attempt_fs_div == "CFS"
                    and attempt_index + 1 < len(fs_div_attempts)
                )
                if not should_try_ofs:
                    break

                if sleep_interval > 0:
                    time.sleep(sleep_interval)

            print(
                "[progress] "
                f"success={counters['success']}, failed={counters['failed']}, "
                f"no_data={counters['no_data']}, rate_limited={counters['rate_limited']}, "
                f"skipped={counters['skipped']}",
                flush=True,
            )

            if sleep_interval > 0:
                time.sleep(sleep_interval)

        if company_raw_data["data"]:
            standard_rows.extend(build_standard_rows(
                batch_id,
                company,
                company_raw_data,
                datetime.now().isoformat(timespec="seconds"),
                default_fs_div=fs_div,
            ))
            account_rows.extend(add_company_fields(
                build_single_all_account_availability(company_raw_data),
                batch_id,
                company,
            ))
            signal_rows.extend(add_company_fields(
                build_signal_account_availability(company_raw_data),
                batch_id,
                company,
            ))

    def persist_csv_rows(
        path: Path,
        fieldnames: list[str],
        rows: list[dict[str, Any]],
        key_fields: list[str],
    ) -> None:
        if limit is None and not skip_existing:
            write_csv_rows(path, fieldnames, rows)
            return

        merge_csv_rows(path, fieldnames, rows, key_fields)

    persist_csv_rows(
        batch_dir / "reports.csv",
        CSV_HEADERS["reports.csv"],
        report_rows,
        ["batch_id", "stock_code", "bsns_year", "reprt_code", "fs_div", "rcept_no"],
    )
    persist_csv_rows(
        batch_dir / "financial_accounts_raw.csv",
        CSV_HEADERS["financial_accounts_raw.csv"],
        raw_rows,
        ["batch_id", "stock_code", "bsns_year", "reprt_code", "fs_div", "sj_div", "account_id", "account_nm", "ord"],
    )
    persist_csv_rows(
        batch_dir / "financial_accounts_standard.csv",
        CSV_HEADERS["financial_accounts_standard.csv"],
        standard_rows,
        ["batch_id", "stock_code", "bsns_year", "reprt_code", "fs_div", "sj_div", "standard_account", "account_id", "account_nm"],
    )
    persist_csv_rows(
        batch_dir / "account_availability.csv",
        CSV_HEADERS["account_availability.csv"],
        account_rows,
        ["batch_id", "stock_code", "standard_account"],
    )
    persist_csv_rows(
        batch_dir / "signal_account_availability.csv",
        CSV_HEADERS["signal_account_availability.csv"],
        signal_rows,
        ["batch_id", "stock_code", "signal_name", "required_account"],
    )
    persist_csv_rows(
        batch_dir / "collection_log.csv",
        CSV_HEADERS["collection_log.csv"],
        log_rows,
        ["batch_id", "stock_code", "bsns_year", "reprt_code", "fs_div"],
    )
    update_batch_summary(batch_dir / "batch_summary.md", batch_id, counters, years, reprt_code, fs_div)

    print("[done] batch export finished", flush=True)
    return counters


def update_batch_summary(
    summary_path: Path,
    batch_id: str,
    counters: dict[str, int],
    years: list[int],
    reprt_code: str,
    fs_div: str,
) -> None:
    """batch_summary.md에 실행 결과 요약을 덮어씁니다."""
    lines = [
        f"# Batch Summary: {batch_id}",
        "",
        "## 실행 결과",
        f"- years: {years[0]}-{years[-1] if years else ''}",
        f"- reprt_code: {reprt_code}",
        f"- fs_div: {fs_div}",
        "- fs_div fallback: CFS no_data 시 OFS를 추가 조회합니다.",
        "- write policy: limit/skip-existing 없이 전체 실행하면 이번 실행 결과로 CSV를 덮어씁니다.",
        f"- success: {counters.get('success', 0)}",
        f"- failed: {counters.get('failed', 0)}",
        f"- no_data: {counters.get('no_data', 0)}",
        f"- rate_limited: {counters.get('rate_limited', 0)}",
        f"- skipped: {counters.get('skipped', 0)}",
        "- skipped 정책: collection_log.csv에는 회사/연도별 최신 최종 상태만 보존하고, 이미 성공한 건의 skip은 이번 실행 summary에만 표시합니다.",
        "",
        "## PR 체크리스트",
        "- [ ] 내 batch 폴더만 수정했습니다.",
        "- [ ] CSV 헤더를 변경하지 않았습니다.",
        "- [ ] collection_log.csv에 실패/스킵 사유를 기록했습니다.",
        "- [ ] API 키 또는 .env 값을 커밋하지 않았습니다.",
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """명령행 옵션을 파싱합니다."""
    parser = argparse.ArgumentParser(
        description="Export OpenDART fnlttSinglAcntAll.json results into one batch folder."
    )
    parser.add_argument("--batch-id", required=True, help="처리할 batch_id입니다. 예: kospi_001")
    parser.add_argument("--years", default="recent5", help="Collection years. Use recent5/recent4/recent3, 2021-2025, or 2021,2022.")
    parser.add_argument("--reprt-code", default="11011", help="보고서 코드입니다. 기본값은 사업보고서 11011입니다.")
    parser.add_argument("--fs-div", default="CFS", help="재무제표 구분입니다. 기본값은 CFS입니다.")
    parser.add_argument("--limit", type=int, default=None, help="처리할 회사 수 제한입니다.")
    parser.add_argument("--skip-existing", action="store_true", help="collection_log.csv의 success 조합은 건너뜁니다.")
    parser.add_argument("--sleep-interval", type=float, default=1.0, help="API 호출 간 대기 시간입니다.")
    return parser.parse_args()


def main() -> int:
    """CLI 진입점입니다."""
    args = parse_args()
    years = parse_years(args.years)
    collect_batch_financials(
        batch_id=args.batch_id,
        years=years,
        reprt_code=args.reprt_code,
        fs_div=args.fs_div,
        limit=args.limit,
        skip_existing=args.skip_existing,
        sleep_interval=args.sleep_interval,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
