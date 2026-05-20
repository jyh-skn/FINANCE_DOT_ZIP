# Vector DB Guide

## Overview

본 시스템은 Vector DB 기반 공시/뉴스 검색 구조를 사용한다.

- **Embedding Model**: `text-embedding-3-small`

---

## Metadata Schema

| Field | Description |
|---|---|
| `stock_code` | 종목코드 |
| `company_name` | 기업명 |
| `year` | 연도 |
| `signal_type` | positive / negative |
| `signal_code` | Signal 코드 |
| `industry_group` | 산업 그룹 |
| `source` | 원본 파일명 |
| `source_url` | 원문 URL |
| `data_type` | disclosure / news |

---

## Metadata Filtering

지원 필터링:

- `stock_code`
- `company_name`
- `year`
- `signal_code`
- `signal_type`
- `industry_group`
- `source`
- `source_url`
- `data_type`

---

## Retriever Functions

### `search_similar_documents()`

metadata filtering 기반 검색 함수

```python
search_similar_documents(
    query="삼성전자 영업이익 감소 원인",
    stock_code="005930",
    data_type="disclosure"
)
```

### `search_by_detected_change()`

detected_changes 기반 검색 함수

```python
search_by_detected_change(
    detected_change
)
```

---

## Test Result

| TEST | 결과 |
|---|---|
| TEST 1 | disclosure 전체 검색 성공 |
| TEST 2 | stock_code filtering 성공 |
| TEST 3 | 존재하지 않는 stock_code → 결과 없음 |

---

## Actual Retriever Output Structure

현재 retriever 실제 반환 구조 기준:

- 본문 위치: `item["content"]`
- metadata 위치: `item["metadata"]`
- `metadata["text"]` 사용 안 함
- 날짜 필드: `year`
- URL 필드: `source_url`
- `source`는 원본 파일명 의미
- 반환 타입: `list[dict]`