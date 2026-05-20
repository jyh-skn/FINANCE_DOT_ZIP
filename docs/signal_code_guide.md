# Signal Code Guide

## Overview

Warning Signal 코드 정의 문서

---

# Signal Codes

## EARNINGS_SURPRISE

| Field | Value |
|---|---|
| type | positive |
| severity | HIGH |
| metric_key | operating_income |

설명: 전년 대비 영업이익 급증

---

## REVENUE_JUMP

| Field | Value |
|---|---|
| type | positive |
| severity | HIGH |
| metric_key | revenue |

설명: 전년 대비 매출 급증

---

## CASH_FLOW_STRONG

| Field | Value |
|---|---|
| type | positive |
| severity | LOW |
| metric_key | operating_cash_flow |

설명: 현금흐름 개선

---

# detected_changes 연동

signal_code 기반으로:

- query_hint 생성
- search_keywords 생성
- Vector DB 검색 수행