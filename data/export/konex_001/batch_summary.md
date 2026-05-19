# Batch Summary: konex_001

## 실행 결과
- years: 2021-2025
- reprt_code: 11011
- fs_div: CFS
- fs_div fallback: CFS no_data 시 OFS를 추가 조회합니다.
- write policy: limit/skip-existing 없이 전체 실행하면 이번 실행 결과로 CSV를 덮어씁니다.
- success: 60
- failed: 0
- no_data: 1005
- rate_limited: 0
- skipped: 0
- skipped 정책: collection_log.csv에는 회사/연도별 최신 최종 상태만 보존하고, 이미 성공한 건의 skip은 이번 실행 summary에만 표시합니다.

## PR 체크리스트
- [ ] 내 batch 폴더만 수정했습니다.
- [ ] CSV 헤더를 변경하지 않았습니다.
- [ ] collection_log.csv에 실패/스킵 사유를 기록했습니다.
- [ ] API 키 또는 .env 값을 커밋하지 않았습니다.
