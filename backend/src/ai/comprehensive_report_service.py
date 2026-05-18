"""
comprehensive_report_service.py

AI 재무 분석 리포트 파이프라인을 하나로 연결하는 상위 서비스 모듈입니다.

v6 Vector DB RAG + News Quality Filter 버전:
1. Backend/Data 파트에서 ai_input을 받습니다.
2. 공통 LLM 객체를 가져옵니다.
3. financial_context_builder.py로 재무 문맥을 생성합니다.
4. industry_analysis_rules.py로 업종별 분석 가이드를 생성합니다.
5. news_query_builder.py로 뉴스 검색 query_groups를 생성합니다.
   - detected_changes가 있으면 signal 기반 query 생성
   - detected_changes가 없으면 기업 일반 동향 query 생성
6. Tavily 뉴스 후보를 수집합니다.
   - news_search_cache_service.py를 통해 동일 조건 반복 검색은 캐시를 사용합니다.
7. Tavily 뉴스 후보를 Vector DB에 실시간 적재합니다.
8. Vector DB에서 공시 근거를 검색합니다.
9. Vector DB에서 뉴스 근거를 검색합니다.
10. Vector DB 뉴스 근거에 rule-based 품질 필터를 적용합니다.
    - 기업명 미포함 기사 제거
    - 지표 관련성 확인
    - 분석연도 관련성 확인
    - 개인 투자자/증시 일반/명품주 등 오프토픽 기사 감점
11. 품질 필터를 통과한 Vector DB 뉴스 근거가 있으면 우선 사용합니다.
12. 품질 필터 통과 뉴스가 없으면 기존 Tavily LLM evidence filtering 결과를 fallback으로 사용합니다.
13. report_writer_chain.py로 최종 리포트 JSON을 생성합니다.

주의:
- 일반 DB companies 테이블에 존재하는 기업이라고 해서 Vector DB disclosure/news chunk가 반드시 존재하는 것은 아닙니다.
- 삼성전자처럼 일반 DB에는 있고 뉴스 chunk는 있으나 disclosure chunk는 없는 케이스가 가능합니다.
- 뉴스 Vector DB가 실시간 적재 후 비워지는 구조라면, 뉴스 upsert를 생략하면 안 됩니다.
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.ai.financial_context_builder import build_financial_context
from src.ai.industry_analysis_rules import build_industry_analysis_instruction
from src.ai.llm_client import get_llm
from src.ai.news_evidence_filter import filter_evidence
from src.ai.news_evidence_quality_filter import (
    filter_news_evidence_quality,
    summarize_quality_filter_result,
)
from src.ai.news_query_builder import build_news_queries
from src.ai.news_search_cache_service import search_news_by_query_groups_cached
from src.ai.report_writer_chain import generate_report


# ---------------------------------------------------------------------
# 1. 공통 유틸 함수
# ---------------------------------------------------------------------

def get_model_name(llm: Any) -> str:
    """
    ChatOpenAI 객체에서 모델명을 추출합니다.
    """

    return (
        getattr(llm, "model_name", None)
        or getattr(llm, "model", None)
        or "unknown"
    )


def get_company_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    ai_input에서 기업 정보를 추출합니다.
    """

    company_info = ai_input.get("company_info", {}) or {}

    return {
        "stock_code": company_info.get("stock_code", ""),
        "company_name": company_info.get("company_name", ""),
        "induty_code": company_info.get("induty_code", ""),
    }


def get_industry_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    ai_input에서 업종 정보를 추출합니다.
    """

    return ai_input.get("industry_info", {}) or {}


def get_detected_changes(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    ai_input에서 AI 리포트 생성용 detected_changes를 추출합니다.
    """

    return ai_input.get("detected_changes", []) or []


def get_all_detected_changes(ai_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    ai_input에서 원본 전체 detected_changes를 추출합니다.
    """

    return ai_input.get("all_detected_changes", []) or get_detected_changes(ai_input)


def log_step_time(step_name: str, start_time: float, extra: str = "") -> None:
    """
    AI 파이프라인 단계별 실행 시간을 출력합니다.
    """

    elapsed = time.perf_counter() - start_time
    suffix = f" | {extra}" if extra else ""
    print(f"[AI_PIPELINE_TIME] {step_name}: {elapsed:.2f}s{suffix}")


# ---------------------------------------------------------------------
# 2. 공시/뉴스 Vector DB Retriever 연결
# ---------------------------------------------------------------------

def build_empty_disclosure_result() -> Dict[str, Any]:
    """
    공시 검색 실패 또는 결과 없음 fallback 결과입니다.
    """

    return {
        "evidence_disclosures": [],
        "disclosure_context": "검색된 공시/사업보고서 근거가 없습니다.",
        "metadata": {
            "enabled": False,
            "source": "empty",
            "reason": "No disclosure evidence retrieved.",
            "evidence_disclosure_count": 0,
        },
    }


def build_empty_news_result() -> Dict[str, Any]:
    """
    뉴스 Vector DB 검색 실패 또는 결과 없음 fallback 결과입니다.
    """

    return {
        "evidence_news": [],
        "news_context": "검색된 뉴스 근거가 없습니다.",
        "metadata": {
            "enabled": False,
            "source": "empty",
            "reason": "No news evidence retrieved from Vector DB.",
            "evidence_news_count": 0,
        },
    }


def build_empty_news_ingest_result() -> Dict[str, Any]:
    """
    뉴스 Vector DB 적재 실패 또는 적재 대상 없음 fallback 결과입니다.
    """

    return {
        "source": "news_vector_ingest_service",
        "enabled": False,
        "searched_news_count": 0,
        "chunk_count": 0,
        "upserted_count": 0,
        "reason": "No news ingested.",
    }


def build_empty_news_quality_filter_result() -> Dict[str, Any]:
    """
    뉴스 품질 필터 미적용 또는 대상 없음 fallback 결과입니다.
    """

    return {
        "source": "news_evidence_quality_filter",
        "applied": False,
        "before_count": 0,
        "after_count": 0,
        "removed_count": 0,
        "quality_scores": [],
        "reason": "No quality filter applied.",
    }


def try_upsert_news_to_vector_db(
    searched_news: List[Dict[str, Any]],
    ai_input: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Tavily 검색 결과를 Vector DB에 실시간 적재합니다.

    실패해도 전체 리포트 생성을 중단하지 않고 fallback 결과를 반환합니다.
    """

    if not searched_news:
        result = build_empty_news_ingest_result()
        result["reason"] = "searched_news is empty."
        return result

    try:
        from src.ai.news_vector_ingest_service import upsert_searched_news_to_vector_db

        result = upsert_searched_news_to_vector_db(
            searched_news=searched_news,
            ai_input=ai_input,
        )

        return {
            **result,
            "enabled": bool(result.get("upserted_count", 0)),
        }

    except Exception as error:
        print(f"[WARN] 뉴스 Vector DB 적재 실패: {error}")

        result = build_empty_news_ingest_result()
        result["error"] = str(error)
        return result


def try_retrieve_disclosure_context(
    ai_input: Dict[str, Any],
    vector_store: Optional[Any] = None,
    top_k_per_change: int = 3,
    max_total_results: int = 5,
) -> Dict[str, Any]:
    """
    Vector DB에서 공시/사업보고서 근거를 검색합니다.
    """

    try:
        from src.ai.disclosure_retriever import retrieve_disclosure_context

        return retrieve_disclosure_context(
            ai_input=ai_input,
            vector_store=vector_store,
            top_k_per_change=top_k_per_change,
            max_total_results=max_total_results,
        )

    except Exception as error:
        print(f"[WARN] disclosure_retriever 실행 실패: {error}")

        result = build_empty_disclosure_result()
        result["metadata"]["error"] = str(error)
        return result


def try_retrieve_news_context(
    ai_input: Dict[str, Any],
    vector_store: Optional[Any] = None,
    top_k_per_change: int = 3,
    max_total_results: int = 5,
) -> Dict[str, Any]:
    """
    Vector DB에서 뉴스 근거를 검색합니다.
    """

    try:
        from src.ai.news_retriever import retrieve_news_context

        return retrieve_news_context(
            ai_input=ai_input,
            vector_store=vector_store,
            top_k_per_change=top_k_per_change,
            max_total_results=max_total_results,
        )

    except Exception as error:
        print(f"[WARN] news_retriever 실행 실패: {error}")

        result = build_empty_news_result()
        result["metadata"]["error"] = str(error)
        return result


def apply_news_quality_filter(
    evidence_news: List[Dict[str, Any]],
    ai_input: Dict[str, Any],
    max_items: int = 3,
    min_quality_score: float = 3.0,
    require_company_mention: bool = True,
) -> Dict[str, Any]:
    """
    Vector DB 또는 fallback 뉴스 evidence에 품질 필터를 적용합니다.

    Returns:
        {
            "filtered_news": [...],
            "metadata": {...}
        }
    """

    before_news = evidence_news or []

    if not before_news:
        metadata = build_empty_news_quality_filter_result()
        metadata["reason"] = "evidence_news is empty."
        return {
            "filtered_news": [],
            "metadata": metadata,
        }

    filtered_news = filter_news_evidence_quality(
        evidence_news=before_news,
        ai_input=ai_input,
        min_quality_score=min_quality_score,
        max_items=max_items,
        require_company_mention=require_company_mention,
    )

    metadata = summarize_quality_filter_result(
        before_news=before_news,
        after_news=filtered_news,
    )
    metadata["applied"] = True
    metadata["min_quality_score"] = min_quality_score
    metadata["require_company_mention"] = require_company_mention

    return {
        "filtered_news": filtered_news,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------
# 3. 최종 JSON 조립
# ---------------------------------------------------------------------

def build_final_report_json(
    ai_input: Dict[str, Any],
    financial_context: Dict[str, Any],
    query_groups: List[Dict[str, Any]],
    searched_news: List[Dict[str, Any]],
    evidence: Dict[str, Any],
    report: Dict[str, Any],
    disclosure_result: Optional[Dict[str, Any]] = None,
    news_result: Optional[Dict[str, Any]] = None,
    news_ingest_result: Optional[Dict[str, Any]] = None,
    news_quality_filter_result: Optional[Dict[str, Any]] = None,
    model_name: str = "unknown",
    include_searched_news: bool = True,
    industry_analysis_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    각 Chain의 결과를 백엔드/프론트에서 사용하기 좋은 최종 JSON으로 조립합니다.
    """

    disclosure_result = disclosure_result or build_empty_disclosure_result()
    news_result = news_result or build_empty_news_result()
    news_ingest_result = news_ingest_result or build_empty_news_ingest_result()
    news_quality_filter_result = news_quality_filter_result or build_empty_news_quality_filter_result()

    evidence_news = evidence.get("evidence_news", []) or []
    evidence_disclosures = evidence.get("evidence_disclosures", []) or []

    searched_news_for_output = searched_news if include_searched_news else []
    industry_info = get_industry_info(ai_input)
    evidence_metadata = evidence.get("metadata", {}) or {}
    news_result_metadata = news_result.get("metadata", {}) or {}

    final_news_source = (
        evidence_metadata.get("news_source")
        or evidence_metadata.get("source")
        or (
            news_result_metadata.get("source")
            if news_result.get("evidence_news")
            else "unknown"
        )
    )

    final_news_vector_used = final_news_source in {
        "vector_db",
        "vector_db_quality_filtered",
    }

    return {
        "company_info": get_company_info(ai_input),
        "industry_info": industry_info,
        "analysis_year": ai_input.get("analysis_year"),
        "base_year": ai_input.get("base_year"),

        "signals": ai_input.get("signals", []) or [],
        "detected_changes": get_detected_changes(ai_input),
        "all_detected_changes": get_all_detected_changes(ai_input),

        "financial_context": financial_context,
        "query_groups": query_groups,
        "industry_analysis_instruction": industry_analysis_instruction or "",

        "searched_news": searched_news_for_output,

        "evidence_news": evidence_news,
        "evidence_disclosures": evidence_disclosures,

        "report": report,

        "disclosure_result": disclosure_result,
        "news_result": news_result,
        "news_ingest_result": news_ingest_result,
        "news_quality_filter_result": news_quality_filter_result,

        "metadata": {
            "model": model_name,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "analysis_year": ai_input.get("analysis_year"),
            "base_year": ai_input.get("base_year"),
            "industry_group": industry_info.get("industry_group"),
            "industry_group_name": industry_info.get("industry_group_name"),
            "industry_instruction_applied": bool(industry_analysis_instruction),
            "detected_change_count": len(get_detected_changes(ai_input)),
            "all_detected_change_count": len(get_all_detected_changes(ai_input)),
            "query_group_count": len(query_groups),
            "searched_news_count": len(searched_news),
            "searched_news_included": include_searched_news,
            "evidence_news_count": len(evidence_news),
            "evidence_disclosure_count": len(evidence_disclosures),
            "financial_context_source": financial_context.get("source"),
            "evidence_source": evidence_metadata.get("source"),
            "report_source": report.get("source"),
            "disclosure_attempted": bool(
                (disclosure_result.get("metadata", {}) or {}).get("enabled")
            ),
            "disclosure_enabled": bool(disclosure_result.get("evidence_disclosures")),

            "news_vector_attempted": bool(
                news_result_metadata.get("enabled")
            ),
            "news_vector_retrieved_count": len(news_result.get("evidence_news", []) or []),
            "news_vector_enabled": bool(final_news_vector_used and evidence_news),
            "news_evidence_source": final_news_source,
            "news_vector_ingest_enabled": bool(news_ingest_result.get("enabled")),
            "news_vector_upserted_count": news_ingest_result.get("upserted_count", 0),
            "news_vector_chunk_count": news_ingest_result.get("chunk_count", 0),

            "news_quality_filter_applied": bool(news_quality_filter_result.get("applied")),
            "news_quality_filter_before_count": news_quality_filter_result.get("before_count", 0),
            "news_quality_filter_after_count": news_quality_filter_result.get("after_count", 0),
            "news_quality_filter_removed_count": news_quality_filter_result.get("removed_count", 0),
            "news_quality_scores": news_quality_filter_result.get("quality_scores", []),

            "adapter_metadata": ai_input.get("adapter_metadata", {}),
        },
    }


# ---------------------------------------------------------------------
# 4. 대표 실행 함수
# ---------------------------------------------------------------------

def create_ai_report(
    ai_input: Dict[str, Any],
    vector_store: Optional[Any] = None,
    max_results_per_query: int = 3,
    max_total_news_results: int = 10,
    max_evidence_news: int = 3,
    include_searched_news: bool = True,
) -> Dict[str, Any]:
    """
    전체 AI 리포트 파이프라인을 실행합니다.
    """

    pipeline_start = time.perf_counter()

    step_start = time.perf_counter()
    llm = get_llm()
    model_name = get_model_name(llm)
    log_step_time("get_llm", step_start, f"model={model_name}")

    industry_info = get_industry_info(ai_input)
    industry_analysis_instruction = build_industry_analysis_instruction(industry_info)

    # 1. 재무 문맥 생성
    step_start = time.perf_counter()
    financial_context = build_financial_context(
        llm=llm,
        ai_input=ai_input,
    )
    log_step_time("financial_context_builder", step_start)

    financial_context["industry_info"] = industry_info
    financial_context["industry_analysis_instruction"] = industry_analysis_instruction

    # 2. 뉴스 검색 query 생성
    step_start = time.perf_counter()
    query_groups = build_news_queries(
        ai_input=ai_input,
        llm=llm,
    )
    query_groups = query_groups[:2]
    log_step_time("news_query_builder", step_start, f"query_group_count={len(query_groups)}")

    # 3. Tavily 뉴스 후보 수집
    step_start = time.perf_counter()
    searched_news = search_news_by_query_groups_cached(
        query_groups=query_groups,
        ai_input=ai_input,
        max_results_per_query=max_results_per_query,
        max_total_results=max_total_news_results,
        cache_enabled=True,
    )
    log_step_time("news_search_service", step_start, f"searched_news_count={len(searched_news)}")

    # 4. 뉴스 Vector DB 실시간 적재
    step_start = time.perf_counter()
    news_ingest_result = try_upsert_news_to_vector_db(
        searched_news=searched_news,
        ai_input=ai_input,
    )
    log_step_time(
        "news_vector_ingest",
        step_start,
        f"upserted_count={news_ingest_result.get('upserted_count', 0)}"
    )

    # Pinecone upsert 직후 검색 반영 지연 대응
    time.sleep(3)

    # 5. 공시 Vector DB 검색
    step_start = time.perf_counter()
    disclosure_result = try_retrieve_disclosure_context(
        ai_input=ai_input,
        vector_store=vector_store,
        top_k_per_change=3,
        max_total_results=5,
    )
    log_step_time(
        "disclosure_retriever",
        step_start,
        f"evidence_disclosure_count={len(disclosure_result.get('evidence_disclosures', []))}"
    )

    # 6. 뉴스 Vector DB 검색
    step_start = time.perf_counter()
    news_result = try_retrieve_news_context(
        ai_input=ai_input,
        vector_store=vector_store,
        top_k_per_change=3,
        max_total_results=max(max_evidence_news * 2, 5),
    )
    vector_evidence_news = news_result.get("evidence_news", []) or []
    log_step_time(
        "news_vector_retriever",
        step_start,
        f"evidence_news_count={len(vector_evidence_news)}"
    )

    # 7. 뉴스 품질 필터 적용
    # Vector DB 유사도 검색 결과가 있어도 기업명/지표/연도 관련성이 낮으면 제거합니다.
    step_start = time.perf_counter()
    vector_quality_filter = apply_news_quality_filter(
        evidence_news=vector_evidence_news,
        ai_input=ai_input,
        max_items=max_evidence_news,
        min_quality_score=5.0,
        require_company_mention=True,
    )
    quality_filtered_vector_news = vector_quality_filter.get("filtered_news", []) or []
    news_quality_filter_result = vector_quality_filter.get("metadata", {}) or build_empty_news_quality_filter_result()

    log_step_time(
        "news_quality_filter",
        step_start,
        (
            f"before={news_quality_filter_result.get('before_count', 0)} "
            f"after={news_quality_filter_result.get('after_count', 0)} "
            f"removed={news_quality_filter_result.get('removed_count', 0)}"
        )
    )

    # 8. 뉴스 evidence 결정
    # 품질 필터를 통과한 Vector DB 뉴스가 있으면 우선 사용하고,
    # 없으면 기존 Tavily LLM evidence filter를 fallback으로 사용합니다.
    if quality_filtered_vector_news:
        evidence = {
            "evidence_news": quality_filtered_vector_news[:max_evidence_news],
            "evidence_disclosures": disclosure_result.get("evidence_disclosures", []) or [],
            "metadata": {
                "source": "vector_db_quality_filtered",
                "news_source": "vector_db_quality_filtered",
                "disclosure_source": (
                    (disclosure_result.get("metadata", {}) or {}).get("source")
                ),
                "evidence_news_count": len(quality_filtered_vector_news[:max_evidence_news]),
                "evidence_disclosure_count": len(disclosure_result.get("evidence_disclosures", []) or []),
                "news_quality_filter": news_quality_filter_result,
            },
        }
        log_step_time(
            "news_evidence_filter",
            time.perf_counter(),
            "skipped=quality_filtered_vector_db_news_used"
        )
    else:
        # Vector DB 결과가 없거나 품질 필터를 모두 통과하지 못하면 Tavily 후보 기반 LLM 필터로 fallback
        step_start = time.perf_counter()
        evidence = filter_evidence(
            llm=llm,
            ai_input=ai_input,
            financial_context=financial_context,
            searched_news=searched_news,
            disclosure_context=disclosure_result.get("disclosure_context"),
            max_evidence=max_evidence_news,
        )
        log_step_time(
            "news_evidence_filter",
            step_start,
            f"evidence_news_count={len(evidence.get('evidence_news', []))}"
        )

        # fallback 결과에도 동일 품질 필터를 한 번 더 적용하되,
        # 전부 제거되는 경우에는 기존 fallback 결과를 유지하여 리포트 생성이 비지 않도록 합니다.
        fallback_news = evidence.get("evidence_news", []) or []
        fallback_quality_filter = apply_news_quality_filter(
            evidence_news=fallback_news,
            ai_input=ai_input,
            max_items=max_evidence_news,
            min_quality_score=4.5,
            require_company_mention=True,
        )
        quality_filtered_fallback_news = fallback_quality_filter.get("filtered_news", []) or []

        if quality_filtered_fallback_news:
            evidence["evidence_news"] = quality_filtered_fallback_news
            news_quality_filter_result = fallback_quality_filter.get("metadata", {}) or news_quality_filter_result
            fallback_news_source = "tavily_fallback_quality_filtered"
        else:
            # 중요:
            # LLM 기반 fallback이 관련 없는 기사를 골랐는데 rule-based 품질 필터를 모두 통과하지 못한 경우,
            # 품질이 낮은 fallback 결과를 억지로 유지하지 않습니다.
            # 이 경우 리포트에는 "신뢰할 수 있는 뉴스 근거 부족"으로 반영되게 둡니다.
            evidence["evidence_news"] = []
            news_quality_filter_result = fallback_quality_filter.get("metadata", {}) or news_quality_filter_result
            fallback_news_source = "tavily_fallback_quality_filtered_empty"

        evidence["metadata"] = {
            **(evidence.get("metadata", {}) or {}),
            "source": fallback_news_source,
            "news_source": fallback_news_source,
            "disclosure_source": (
                (disclosure_result.get("metadata", {}) or {}).get("source")
            ),
            "news_quality_filter": news_quality_filter_result,
        }

    # 공시는 Vector DB 검색 결과를 사용합니다.
    evidence["evidence_disclosures"] = disclosure_result.get("evidence_disclosures", []) or []

    # 9. 최종 리포트 생성
    step_start = time.perf_counter()
    report = generate_report(
        llm=llm,
        financial_context=financial_context,
        evidence_news=evidence.get("evidence_news", []),
        evidence_disclosures=evidence.get("evidence_disclosures", []),
        industry_info=industry_info,
        industry_analysis_instruction=industry_analysis_instruction,
    )
    log_step_time("report_writer_chain", step_start)

    # 10. 최종 JSON 조립
    step_start = time.perf_counter()
    final_json = build_final_report_json(
        ai_input=ai_input,
        financial_context=financial_context,
        query_groups=query_groups,
        searched_news=searched_news,
        evidence=evidence,
        report=report,
        disclosure_result=disclosure_result,
        news_result=news_result,
        news_ingest_result=news_ingest_result,
        news_quality_filter_result=news_quality_filter_result,
        model_name=model_name,
        include_searched_news=include_searched_news,
        industry_analysis_instruction=industry_analysis_instruction,
    )
    log_step_time("build_final_report_json", step_start)

    log_step_time("TOTAL_create_ai_report", pipeline_start)

    return final_json


def run_ai_report_pipeline(
    ai_input: Dict[str, Any],
    vector_store: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    create_ai_report()의 alias 함수입니다.
    """

    return create_ai_report(
        ai_input=ai_input,
        vector_store=vector_store,
    )


# ---------------------------------------------------------------------
# 5. 단독 실행 테스트
# ---------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from src.ai.sample_report_data import get_sample_ai_input
    except ModuleNotFoundError:
        from sample_report_data import get_sample_ai_input

    sample_ai_input = get_sample_ai_input(case="warning")

    sample_ai_input["company_info"]["company_name"] = "삼성전자"
    sample_ai_input["company_info"]["stock_code"] = "005930"
    sample_ai_input["industry_info"] = {
        "industry_group": "tech_equipment",
        "industry_group_name": "기술 및 장치 산업",
    }
    sample_ai_input["analysis_year"] = 2023
    sample_ai_input["base_year"] = 2022

    for change in sample_ai_input.get("detected_changes", []):
        change["year"] = 2023
        change["base_year"] = 2022

    result = create_ai_report(
        ai_input=sample_ai_input,
        vector_store=None,
        max_results_per_query=3,
        max_total_news_results=10,
        max_evidence_news=3,
        include_searched_news=False,
    )

    print("[Comprehensive Report Service Vector RAG + News Quality Filter Test]")
    print("company:", result.get("company_info", {}).get("company_name"))
    print("industry_group:", result.get("industry_info", {}).get("industry_group"))
    print("analysis_year:", result.get("analysis_year"))
    print("detected_change_count:", result.get("metadata", {}).get("detected_change_count"))
    print("searched_news_count:", result.get("metadata", {}).get("searched_news_count"))
    print("evidence_news_count:", result.get("metadata", {}).get("evidence_news_count"))
    print("evidence_disclosure_count:", result.get("metadata", {}).get("evidence_disclosure_count"))
    print("news_evidence_source:", result.get("metadata", {}).get("news_evidence_source"))
    print("news_vector_enabled:", result.get("metadata", {}).get("news_vector_enabled"))
    print("news_quality_filter_applied:", result.get("metadata", {}).get("news_quality_filter_applied"))
    print("news_quality_filter_before_count:", result.get("metadata", {}).get("news_quality_filter_before_count"))
    print("news_quality_filter_after_count:", result.get("metadata", {}).get("news_quality_filter_after_count"))
    print("news_quality_filter_removed_count:", result.get("metadata", {}).get("news_quality_filter_removed_count"))
    print("disclosure_enabled:", result.get("metadata", {}).get("disclosure_enabled"))

    print("\n[Final AI Report JSON]")
    print(json.dumps(result, ensure_ascii=False, indent=2))
