# Vector DB Metadata Schema

## Overview

리포트 자동 생성 시스템의 검색 엔진 역할을 하는 Pinecone 벡터 데이터베이스의
데이터 저장 구조와 메타데이터 규격을 정의합니다.

---

## 1. 인덱스 구성

- **Index Name**: `finance-dot-news`
- **Dimension**: 1536 (OpenAI `text-embedding-3-small` 모델 기준)
- **Metric**: `cosine` (금융 문서 유사도 측정에 최적화)

---

## 2. Filtering Strategy

본 시스템은 namespace 분리 대신 metadata filtering 기반 검색 구조를 사용합니다.

지원 filtering 기준:

- `stock_code`
- `company_name`
- `year`
- `signal_type`
- `signal_code`
- `industry_group`
- `source`
- `source_url`
- `data_type`

---

## 3. 데이터 레코드 구조

각 공시/뉴스 문서는 아래와 같은 metadata와 함께 벡터화되어 저장됩니다.

```json
{
  "id": "{document_id}",
  "values": [0.0123, -0.0456, "..."],
  "metadata": {
    "company_name": "삼성전자",
    "stock_code": "005930",
    "year": 2023,
    "signal_type": "negative",
    "signal_code": "EARNINGS_DROP",
    "industry_group": "tech_equipment",
    "source": "cmpMgDecsn.json",
    "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20220105000457",
    "data_type": "disclosure"
  }
}
```

> ※ 실제 retriever 반환 시 본문은 metadata 내부가 아니라 최상위 `content` 필드로 반환됩니다.

---

## 4. 메타데이터 필드 상세

| 필드명 | 타입 | 설명 | 비고 |
|---|---|---|---|
| `company_name` | string | 대상 기업명 | 확인용 |
| `stock_code` | string | 종목코드 | filtering 기준 |
| `year` | int | 연도 정보 | filtering 기준 |
| `signal_type` | string | positive / negative | Signal 분류 |
| `signal_code` | string | Signal 코드 | detected_changes 연동 |
| `industry_group` | string | 산업 그룹 코드 | 산업별 filtering |
| `source` | string | 원본 파일명(json/csv 등) | metadata source |
| `source_url` | string | 원문 URL | 공시/뉴스 URL |
| `data_type` | string | disclosure / news | 데이터 유형 구분 |

---

## 5. Filtering Example

```python
build_metadata_filter(
    stock_code="005930",
    year=2023,
    signal_code="EARNINGS_DROP"
)
```

---

## 6. Retrieval Structure

```text
detected_changes
    ↓
query_hint 생성
    ↓
metadata filtering
    ↓
Vector DB retrieval
```

---

## 7. 데이터 무결성 및 검색 안정성

- 문서 단위 고유 ID 기반 Upsert 처리
- 동일 문서 재적재 시 중복 방지 처리 적용
- metadata 기반 filtering 지원
- 검색 단계에서는 `source_url` 기준 deduplication 적용
- 동일 문서가 반복 반환되지 않도록 검색 결과 중복 제거 수행
- retriever 반환 타입은 `list[dict]` 구조 사용