"""
disclosure_retriever.py

Vector DB에서 공시/사업보고서 chunk를 검색하고,
report_writer_chain.py가 사용할 evidence_disclosures 형식으로 변환하는 모듈입니다.

역할:
1. ai_input["detected_changes"]를 기준으로 Vector DB 검색을 수행합니다.
2. data_type="disclosure" metadata filter를 사용합니다.
3. 검색 결과를 evidence_disclosures 형식으로 변환합니다.
4. comprehensive_report_service.py에서 report_writer_chain에 전달할 수 있는 구조로 반환합니다.

반환 형식:
{
    "evidence_disclosures": [...],
    "disclosure_context": "...",
    "metadata": {...}
}
"""

import json
from typing import Any, Dict, List

from src.ai.vector_evidence_retriever import (
    retrieve_evidence_by_data_type,
    safe_text,
)


def build_disclosure_context_text(evidence_disclosures: List[Dict[str, Any]]) -> str:
    """
    evidence_disclosures를 LLM context에 넣을 수 있는 텍스트로 변환합니다.
    """

    if not evidence_disclosures:
        return "검색된 공시/사업보고서 근거가 없습니다."

    lines = []

    for idx, item in enumerate(evidence_disclosures, start=1):
        lines.append(
            f"[공시 근거 {idx}]\n"
            f"- 기업: {item.get('company_name')}\n"
            f"- 종목코드: {item.get('stock_code')}\n"
            f"- 연도: {item.get('year')}\n"
            f"- 지표: {item.get('metric_label')} ({item.get('metric_key')})\n"
            f"- 출처: {item.get('source')}\n"
            f"- URL: {item.get('source_url')}\n"
            f"- 유사도: {item.get('relevance_score')}\n"
            f"- 내용: {safe_text(item.get('chunk_text'))[:1000]}"
        )

    return "\n\n".join(lines)


def retrieve_disclosure_context(
    ai_input: Dict[str, Any],
    vector_store: Any = None,
    top_k_per_change: int = 5,
    max_total_results: int = 5,
) -> Dict[str, Any]:
    """
    Vector DB에서 공시/사업보고서 근거를 검색합니다.

    Args:
        ai_input: backend_payload_adapter.py가 만든 AI 입력 데이터
        vector_store: 현재 retriever 함수 내부에서 Pinecone 연결을 처리하므로 사용하지 않습니다.
        top_k_per_change: detected_change 하나당 검색할 최대 개수
        max_total_results: 최종 evidence_disclosures 최대 개수

    Returns:
        {
            "evidence_disclosures": [...],
            "disclosure_context": "...",
            "metadata": {...}
        }
    """

    evidence_disclosures = retrieve_evidence_by_data_type(
        ai_input=ai_input,
        data_type="disclosure",
        top_k_per_change=2,
        max_total_results=3,
        max_changes=2,
    )

    disclosure_context = build_disclosure_context_text(evidence_disclosures)

    return {
        "evidence_disclosures": evidence_disclosures,
        "disclosure_context": disclosure_context,
        "metadata": {
            "enabled": True,
            "source": "vector_db",
            "data_type": "disclosure",
            "evidence_disclosure_count": len(evidence_disclosures),
            "top_k_per_change": top_k_per_change,
            "max_total_results": max_total_results,
        },
    }


# 호환용 alias
def retrieve_disclosures(
    ai_input: Dict[str, Any],
    vector_store: Any = None,
    top_k_per_change: int = 5,
    max_total_results: int = 5,
) -> Dict[str, Any]:
    """
    retrieve_disclosure_context()의 alias입니다.
    """

    return retrieve_disclosure_context(
        ai_input=ai_input,
        vector_store=vector_store,
        top_k_per_change=top_k_per_change,
        max_total_results=max_total_results,
    )


if __name__ == "__main__":
    try:
        from src.ai.backend_payload_adapter import build_ai_input_from_backend_response
        from src.services.report_service import build_report_response
    except ModuleNotFoundError:
        print("이 파일은 backend 루트에서 python -m src.ai.disclosure_retriever 로 실행하세요.")
        raise

    stock_code = "091700"

    backend_response = build_report_response(stock_code)
    ai_input = build_ai_input_from_backend_response(backend_response)

    result = retrieve_disclosure_context(
        ai_input=ai_input,
        top_k_per_change=3,
        max_total_results=5,
    )

    print("[Disclosure Retriever Test]")
    print("evidence_disclosure_count:", result["metadata"]["evidence_disclosure_count"])
    print(json.dumps(result["evidence_disclosures"], ensure_ascii=False, indent=2))
