import sys
from pathlib import Path

from src.db.queries import (search_companies, search_origin_companies)
from rest_framework.decorators import api_view
from rest_framework.response import Response


# =========================
# src 경로 강제 등록
# =========================
CURRENT_FILE = Path(__file__).resolve()

PROJECT_ROOT = None

for parent in CURRENT_FILE.parents:
    if (parent / "src").exists():
        PROJECT_ROOT = parent
        break

if PROJECT_ROOT is None:
    raise RuntimeError("src 폴더를 찾을 수 없습니다. 프로젝트 구조를 확인해주세요.")

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


TEMP_COMPANY_DATA = [
    {"CORP_ID": "001", "CORP_NAME": "삼성전자", "TICKER": "005930"},
    {"CORP_ID": "002", "CORP_NAME": "SK하이닉스", "TICKER": "000660"},
    {"CORP_ID": "003", "CORP_NAME": "현대자동차", "TICKER": "005380"},
    {"CORP_ID": "004", "CORP_NAME": "LG화학", "TICKER": "051910"},
    {"CORP_ID": "005", "CORP_NAME": "카카오", "TICKER": "035720"},
]


def success_response(data=None, message="요청 성공"):
    return Response({
        "status": "success",
        "message": message,
        "data": data
    })


def fail_response(message="요청 실패", data=None):
    return Response({
        "status": "fail",
        "message": message,
        "data": data
    })


def to_bool(value, default=False):
    """
    request.data 또는 query_params에서 넘어온 값을 bool로 변환합니다.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}

    return bool(value)


def get_request_value(request, key, default=None):
    """
    GET query_params와 POST data 양쪽에서 값을 안전하게 가져옵니다.
    """

    if request.method == "GET":
        return request.query_params.get(key, default)

    return request.data.get(key, default)


def get_request_bool(request, key, default=False):
    """
    GET/POST 요청에서 bool 옵션 값을 읽습니다.
    """

    return to_bool(
        get_request_value(request, key, default),
        default=default,
    )


def inject_mock_disclosures_for_chat(ai_report_result, stock_code):
    """
    disclosure_retriever.py가 아직 구현되지 않은 상태에서
    테스트/발표용으로 sample_disclosure_data.py의 Mock 공시 근거를 주입합니다.

    실제 Vector DB 연결 후에는 이 함수 대신 disclosure_retriever.py 결과를
    evidence_disclosures로 연결하면 됩니다.
    """

    try:
        from src.ai.sample_disclosure_data import get_sample_evidence_disclosures
    except Exception:
        return ai_report_result

    evidence_disclosures = get_sample_evidence_disclosures(
        stock_code=stock_code,
        year=ai_report_result.get("analysis_year"),
        max_items=3,
    )

    ai_report_result["evidence_disclosures"] = evidence_disclosures

    disclosure_summary = " ".join(
        item.get("evidence_summary", "")
        for item in evidence_disclosures
        if item.get("evidence_summary")
    ).strip()

    report = ai_report_result.get("report", {}) or {}

    if disclosure_summary:
        report["disclosure_evidence_summary"] = disclosure_summary

    report_metadata = report.get("metadata", {}) or {}
    report_metadata["disclosure_evidence_count"] = len(evidence_disclosures)
    report["metadata"] = report_metadata
    ai_report_result["report"] = report

    metadata = ai_report_result.get("metadata", {}) or {}
    metadata["evidence_disclosure_count"] = len(evidence_disclosures)
    metadata["mock_disclosure_injected"] = True
    ai_report_result["metadata"] = metadata

    disclosure_result = ai_report_result.get("disclosure_result", {}) or {}
    disclosure_result["evidence_disclosures"] = evidence_disclosures
    disclosure_result["metadata"] = {
        **(disclosure_result.get("metadata", {}) or {}),
        "enabled": False,
        "source": "mock_disclosure",
        "evidence_disclosure_count": len(evidence_disclosures),
        "reason": "disclosure_retriever.py is not implemented. Mock disclosures are injected for API test.",
    }
    ai_report_result["disclosure_result"] = disclosure_result

    return ai_report_result


def build_ai_report_result_once(
    stock_code,
    use_mock_disclosures=False,
    include_searched_news=False,
    max_total_news_results=10,
):
    """
    AI 리포트 생성 체인을 1회 실행합니다.

    이 함수는 화면 최초 진입 또는 리포트 생성 버튼 클릭 시 한 번만 호출되는 것을 목표로 합니다.
    챗봇 질문마다 호출하면 응답 시간이 길어질 수 있습니다.
    """

    from src.services.report_service import build_report_response
    from src.ai.backend_payload_adapter import build_ai_input_from_backend_response
    from src.ai.comprehensive_report_service import create_ai_report

    report_response = build_report_response(stock_code)

    if report_response.get("status") == "fail":
        return report_response

    ai_input = build_ai_input_from_backend_response(report_response)

    ai_report_result = create_ai_report(
        ai_input=ai_input,
        vector_store=None,
        max_results_per_query=3,
        max_total_news_results=max_total_news_results,
        max_evidence_news=3,
        include_searched_news=include_searched_news,
    )

    # chat_context_builder.py가 정량 재무 데이터를 사용할 수 있도록 보강합니다.
    ai_report_result["finance_summary"] = ai_input.get("finance_summary", []) or []
    ai_report_result["financial_metrics"] = ai_input.get("financial_metrics", {}) or {}
    ai_report_result["signals"] = ai_input.get("signals", []) or ai_report_result.get("signals", [])
    ai_report_result["detected_changes"] = ai_input.get("detected_changes", []) or ai_report_result.get("detected_changes", [])
    ai_report_result["all_detected_changes"] = ai_input.get("all_detected_changes", []) or ai_report_result.get("all_detected_changes", [])

    if use_mock_disclosures:
        ai_report_result = inject_mock_disclosures_for_chat(
            ai_report_result=ai_report_result,
            stock_code=stock_code,
        )

    metadata = ai_report_result.get("metadata", {}) or {}
    metadata["generated_by_endpoint"] = "ai_comprehensive_report"
    metadata["use_mock_disclosures"] = use_mock_disclosures
    ai_report_result["metadata"] = metadata

    return {
        "status": "success",
        "message": "AI 종합 리포트 생성 성공",
        "data": ai_report_result,
    }


def get_ai_report_result_from_request(request):
    """
    프론트에서 전달한 이미 생성된 AI 리포트 JSON을 여러 key 이름으로 허용합니다.
    """

    candidates = [
        "ai_report_result",
        "aiReportResult",
        "report_result",
        "reportResult",
        "ai_report",
        "aiReport",
    ]

    for key in candidates:
        value = request.data.get(key)

        if isinstance(value, dict):
            return value

    return None


def get_chat_history_from_request(request):
    """
    프론트에서 전달한 이전 대화 기록을 여러 key 이름으로 허용합니다.

    권장 Request body 예시:
    {
        "question": "방금 답변에서 말한 두 번째 뉴스는 뭐야?",
        "ai_report_result": {...},
        "chat_history": [
            {"role": "user", "content": "파트론의 2021년 영업이익이 왜 증가했어?"},
            {"role": "assistant", "content": "파트론의 영업이익 증가는 ..."}
        ]
    }
    """

    candidates = [
        "chat_history",
        "chatHistory",
        "messages",
        "conversation_history",
        "conversationHistory",
    ]

    for key in candidates:
        value = request.data.get(key)

        if isinstance(value, list):
            return value

    return []


def get_report_data_from_request(request):
    """
    프론트가 별도로 넘긴 정량 리포트 데이터를 가져옵니다.

    기존 프론트 응답 구조를 고려해 reportData/report_data 둘 다 허용합니다.
    """

    candidates = [
        "report_data",
        "reportData",
        "backend_report_data",
        "backendReportData",
    ]

    for key in candidates:
        value = request.data.get(key)

        if isinstance(value, dict):
            return value

    return {}


def hydrate_ai_report_result_for_chat(
    ai_report_result,
    request,
    stock_code,
    use_mock_disclosures=False,
):
    """
    챗봇 context 생성을 위해 ai_report_result에 부족한 필드를 보강합니다.

    프론트가 ai_report_result와 별도로 finance_summary, signals, detected_changes,
    evidence_news, evidence_disclosures 등을 넘기는 경우 이를 합쳐줍니다.
    """

    ai_report_result = ai_report_result or {}
    report_data = get_report_data_from_request(request)

    finance_summary = (
        ai_report_result.get("finance_summary")
        or request.data.get("finance_summary")
        or report_data.get("finance_summary")
        or []
    )

    if finance_summary:
        ai_report_result["finance_summary"] = finance_summary

    financial_metrics = (
        ai_report_result.get("financial_metrics")
        or request.data.get("financial_metrics")
        or {}
    )

    if financial_metrics:
        ai_report_result["financial_metrics"] = financial_metrics

    company_info = (
        ai_report_result.get("company_info")
        or request.data.get("company_info")
        or report_data.get("company_info")
        or {}
    )

    if company_info:
        ai_report_result["company_info"] = company_info

    industry_info = (
        ai_report_result.get("industry_info")
        or request.data.get("industry_info")
        or report_data.get("industry_info")
        or {}
    )

    if industry_info:
        ai_report_result["industry_info"] = industry_info

    signals = (
        ai_report_result.get("signals")
        or request.data.get("signals")
        or report_data.get("signals")
        or []
    )

    if signals:
        ai_report_result["signals"] = signals

    detected_changes = (
        ai_report_result.get("detected_changes")
        or request.data.get("detected_changes")
        or report_data.get("detected_changes")
        or []
    )

    if detected_changes:
        ai_report_result["detected_changes"] = detected_changes

    all_detected_changes = (
        ai_report_result.get("all_detected_changes")
        or request.data.get("all_detected_changes")
        or request.data.get("allDetectedChanges")
        or detected_changes
        or []
    )

    if all_detected_changes:
        ai_report_result["all_detected_changes"] = all_detected_changes

    evidence_news = (
        ai_report_result.get("evidence_news")
        or request.data.get("evidence_news")
        or request.data.get("evidenceNews")
        or []
    )

    if evidence_news:
        ai_report_result["evidence_news"] = evidence_news

    evidence_disclosures = (
        ai_report_result.get("evidence_disclosures")
        or request.data.get("evidence_disclosures")
        or request.data.get("evidenceDisclosures")
        or []
    )

    if evidence_disclosures:
        ai_report_result["evidence_disclosures"] = evidence_disclosures

    if use_mock_disclosures and not ai_report_result.get("evidence_disclosures"):
        ai_report_result = inject_mock_disclosures_for_chat(
            ai_report_result=ai_report_result,
            stock_code=stock_code,
        )

    metadata = ai_report_result.get("metadata", {}) or {}
    metadata["hydrated_for_chat"] = True
    metadata["chat_finance_summary_count"] = len(ai_report_result.get("finance_summary", []) or [])
    metadata["chat_evidence_news_count"] = len(ai_report_result.get("evidence_news", []) or [])
    metadata["chat_evidence_disclosure_count"] = len(ai_report_result.get("evidence_disclosures", []) or [])
    ai_report_result["metadata"] = metadata

    return ai_report_result


@api_view(["GET", "POST"])
def test_api(request):
    return success_response(
        data={
            "method": request.method
        },
        message=f"DRF {request.method} 연결 성공"
    )


@api_view(["GET", "POST"])
def init_data(request):
    """ 프론트 화면 초기화 시 가져와야 하는 초기 정보 세팅
        1. 자동완성에 필요한 관리 기업 정보
    """
    result = search_origin_companies()
    # print(len(result))
    return success_response(
        data=result,
        message="초기 기업 데이터 조회 성공"
    )

@api_view(["GET", "POST"])
def search_company(request):
    # keyword(기업명/종목명에서 종목코드로 변경)
    if request.method == "GET":
        stock_code = request.query_params.get("corp_code", "").strip()
    else:
        stock_code = str(request.data.get("corp_code", "")).strip()

    if not stock_code:
        return fail_response(message="자동완성에서 종목코드를 선택해주세요.", data=[])

    # DB에서 검색 결과 가져오기
    # result = search_companies(keyword)

    # if not result:
    #     return fail_response(message="검색 결과가 없습니다.", data=[])

    # 주석처리
    # if len(result) > 1:
    #     return fail_response(message="검색 결과가 여러 개입니다. 더 구체적으로 검색해주세요.", data=result)
    
    # matched = resultstock_code = matched["TICKER"][0]  

    try:
        from src.services.report_service import build_report_response
        # report_result = build_report_response(stock_code)

        # 기존 report_result를 ai_report에서 포함하고 있어, 주석처리 후 ai_report 변수 생성
        ai_report_result = build_ai_report_result_once(
            stock_code=stock_code,
        )
        
    except Exception as e:
        return fail_response(message=f"리포트 생성 오류: {str(e)}")

    if ai_report_result.get("status") == "fail":
        return fail_response(message=ai_report_result.get("message", "리포트 조회 실패"))

    # ai_report_result에서 data 추출
    report_data = ai_report_result.get("data", {})

    # newsData에서 사용하는 ai_data 변수 추출
    ai_data = ai_report_result.get("data", {}) if ai_report_result.get("status") == "success" else {}

    news_data = {
        "detected_changes": report_data.get("detected_changes", []) or [],
        "evidence_news": ai_data.get("evidence_news", []),
        "signals": report_data.get("signals", []) or [],
        "company_info": report_data.get("company_info", {}),
    }

    return success_response(
        data={
            "reportData": report_data,
            "newsData": news_data,
            "disclosureData": {"company_info": report_data.get("company_info", {})},
        },
        message="기업 검색 성공"
    )


@api_view(["GET"])
def comprehensive_report(request, stock_code):
    print("\n===== [1] comprehensive_report 호출됨 =====")
    print("[2] stock_code:", stock_code)

    if not stock_code:
        print("[ERROR] stock_code 없음")
        return fail_response(
            message="stock_code가 필요합니다.",
            data=None
        )

    try:
        print("[3] build_report_response import 직전")
        from src.services.report_service import build_report_response

        print("[4] build_report_response 실행 직전")
        result = build_report_response(stock_code)

        print("[5] build_report_response 실행 완료")
        print("[6] result:", result)

    except Exception as e:
        print("[ERROR] build_report_response 내부 오류 발생")
        print(type(e).__name__, str(e))

        return fail_response(
            message=f"리포트 생성 중 오류 발생: {str(e)}",
            data=None
        )

    if result.get("status") == "fail":
        print("[7] result status = fail")
        print("[8] message:", result.get("message"))

        return fail_response(
            message=result.get("message", "리포트 조회 실패"),
            data=result.get("data")
        )

    print("[9] 최종 응답 반환")

    return success_response(
        data=result.get("data"),
        message="종합 재무 리포트 조회 성공"
    )


@api_view(["GET", "POST"])
def ai_comprehensive_report(request, stock_code):
    """
    AI 종합 리포트 1회 생성 API입니다.

    Endpoint:
    GET  /api/v1/report/comprehensive/{stock_code}/ai
    POST /api/v1/report/comprehensive/{stock_code}/ai

    Query 또는 Body 옵션:
    {
        "use_mock_disclosures": true,
        "include_searched_news": false
    }

    이 API는 화면 진입 시 또는 리포트 생성 버튼 클릭 시 1회 호출하는 용도입니다.
    챗봇 질문마다 호출하지 않습니다.
    """

    print("\n===== [1] ai_comprehensive_report 호출됨 =====")
    print("[2] stock_code:", stock_code)

    if not stock_code:
        return fail_response(
            message="stock_code가 필요합니다.",
            data=None
        )

    use_mock_disclosures = get_request_bool(
        request,
        "use_mock_disclosures",
        default=False,
    )
    include_searched_news = get_request_bool(
        request,
        "include_searched_news",
        default=False,
    )

    try:
        result = build_ai_report_result_once(
            stock_code=stock_code,
            use_mock_disclosures=use_mock_disclosures,
            include_searched_news=include_searched_news,
            max_total_news_results=10,
        )
    except Exception as e:
        print("[ERROR] ai_comprehensive_report 내부 오류 발생")
        print(type(e).__name__, str(e))

        return fail_response(
            message=f"AI 리포트 생성 중 오류 발생: {str(e)}",
            data=None
        )

    if result.get("status") == "fail":
        return fail_response(
            message=result.get("message", "AI 리포트 생성 실패"),
            data=result.get("data")
        )

    return success_response(
        data=result.get("data"),
        message="AI 종합 리포트 생성 성공"
    )


@api_view(["POST"])
def report_chat(request, stock_code):
    """
    이미 생성된 AI 리포트 기반 Q&A 챗봇 API입니다.

    Endpoint:
    POST /api/v1/report/comprehensive/{stock_code}/chat

    권장 Request body:
    {
        "question": "삼성전자는 2023년에 영업이익이 왜 감소했어?",
        "ai_report_result": {...},
        "chat_history": [
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답변"}
        ],
        "use_mock_disclosures": false
    }

    중요:
    - 기본 동작은 ai_report_result를 받아서 답변만 생성합니다.
    - 따라서 챗봇 질문마다 create_ai_report()를 다시 실행하지 않습니다.
    - chat_history가 있으면 "방금 답변", "두 번째 뉴스" 같은 후속 질문 처리에 사용합니다.
    - 테스트/비상용으로 allow_generate_report=true를 보내면 내부에서 리포트를 생성합니다.
    """

    print("\n===== [1] report_chat 호출됨 =====")
    print("[2] stock_code:", stock_code)

    if not stock_code:
        return fail_response(
            message="stock_code가 필요합니다.",
            data=None
        )

    question = str(request.data.get("question", "")).strip()

    if not question:
        return fail_response(
            message="question이 필요합니다.",
            data=None
        )

    try:
        from src.ai.chat_safety_filter import check_chat_safety, build_safety_block_response

        safety_result = check_chat_safety(question)

        if safety_result.get("blocked"):
            blocked_answer = build_safety_block_response(
                question=question,
                safety_result=safety_result,
            )
            response_data = {
                "company_info": {},
                "industry_info": {},
                "analysis_year": None,
                "base_year": None,
                "question": question,
                "answer": blocked_answer.get("answer", ""),
                "used_sources": blocked_answer.get("used_sources", []),
                "limitations": blocked_answer.get("limitations", ""),
                "metadata": {
                    **(blocked_answer.get("metadata", {}) or {}),
                    "received_ai_report_result": False,
                    "generated_ai_report_inside_chat": False,
                },
            }
            return success_response(
                data=response_data,
                message="부적절한 표현이 감지되어 챗봇 답변을 차단했습니다.",
            )
    except Exception as e:
        print("[WARN] chat_safety_filter 실행 실패", type(e).__name__, str(e))

    try:
        from src.ai.financial_term_glossary import (
            detect_financial_term_question,
            build_financial_term_response,
        )

        term_result = detect_financial_term_question(question)

        if term_result.get("matched"):
            term_answer = build_financial_term_response(
                question=question,
                term_result=term_result,
            )
            response_data = {
                "company_info": {},
                "industry_info": {},
                "analysis_year": None,
                "base_year": None,
                "question": question,
                "answer": term_answer.get("answer", ""),
                "used_sources": term_answer.get("used_sources", []),
                "limitations": term_answer.get("limitations", ""),
                "metadata": {
                    **(term_answer.get("metadata", {}) or {}),
                    "received_ai_report_result": False,
                    "generated_ai_report_inside_chat": False,
                },
            }
            return success_response(
                data=response_data,
                message="경제·재무 용어 설명 답변 생성 성공",
            )
    except Exception as e:
        print("[WARN] financial_term_glossary 실행 실패", type(e).__name__, str(e))

    chat_history = get_chat_history_from_request(request)

    use_mock_disclosures = to_bool(
        request.data.get("use_mock_disclosures"),
        default=False,
    )
    allow_generate_report = to_bool(
        request.data.get("allow_generate_report"),
        default=False,
    )

    received_ai_report_result = False
    generated_ai_report_inside_chat = False

    try:
        from src.ai.chat_context_builder import build_chat_context
        from src.ai.llm_client import get_llm
        from src.ai.report_chat_chain import answer_report_question

        ai_report_result = get_ai_report_result_from_request(request)

        if ai_report_result:
            received_ai_report_result = True
            print("[3] 요청 body의 ai_report_result 사용")
        elif allow_generate_report:
            generated_ai_report_inside_chat = True
            print("[3] allow_generate_report=True이므로 내부에서 AI 리포트 생성")
            result = build_ai_report_result_once(
                stock_code=stock_code,
                use_mock_disclosures=use_mock_disclosures,
                include_searched_news=False,
                max_total_news_results=20,
            )

            if result.get("status") == "fail":
                return fail_response(
                    message=result.get("message", "AI 리포트 생성 실패"),
                    data=result.get("data")
                )

            ai_report_result = result.get("data")
        else:
            return fail_response(
                message=(
                    "ai_report_result가 필요합니다. "
                    "먼저 /api/v1/report/comprehensive/{stock_code}/ai 에서 AI 리포트를 생성한 뒤, "
                    "그 결과를 챗봇 API에 전달하세요. "
                    "테스트용으로 기존 방식이 필요하면 allow_generate_report=true를 보내세요."
                ),
                data={
                    "required_body_example": {
                        "question": "삼성전자는 2023년에 영업이익이 왜 감소했어?",
                        "ai_report_result": "{...}",
                        "chat_history": [],
                        "use_mock_disclosures": False,
                    }
                }
            )

        ai_report_result = hydrate_ai_report_result_for_chat(
            ai_report_result=ai_report_result,
            request=request,
            stock_code=stock_code,
            use_mock_disclosures=use_mock_disclosures,
        )

        print("[4] chat_context_builder 실행")
        chat_context = build_chat_context(ai_report_result)

        print("[5] report_chat_chain 실행")
        llm = get_llm()
        chat_answer = answer_report_question(
            llm=llm,
            question=question,
            chat_context=chat_context,
            chat_history=chat_history,
        )

    except Exception as e:
        print("[ERROR] report_chat 내부 오류 발생")
        print(type(e).__name__, str(e))

        return fail_response(
            message=f"챗봇 답변 생성 중 오류 발생: {str(e)}",
            data=None
        )

    company_info = ai_report_result.get("company_info", {}) or {}
    industry_info = ai_report_result.get("industry_info", {}) or {}

    response_data = {
        "company_info": company_info,
        "industry_info": industry_info,
        "analysis_year": ai_report_result.get("analysis_year"),
        "base_year": ai_report_result.get("base_year"),
        "question": question,
        "answer": chat_answer.get("answer", ""),
        "used_sources": chat_answer.get("used_sources", []),
        "limitations": chat_answer.get("limitations", ""),
        "metadata": {
            **(chat_answer.get("metadata", {}) or {}),
            "chat_context": chat_context.get("metadata", {}),
            "ai_report": ai_report_result.get("metadata", {}),
            "use_mock_disclosures": use_mock_disclosures,
            "received_ai_report_result": received_ai_report_result,
            "generated_ai_report_inside_chat": generated_ai_report_inside_chat,
            "request_chat_history_count": len(chat_history or []),
        },
    }

    return success_response(
        data=response_data,
        message="리포트 챗봇 답변 생성 성공"
    )

