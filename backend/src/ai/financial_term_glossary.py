"""
financial_term_glossary.py

챗봇에서 경제/재무 용어 질문을 빠르게 처리하기 위한 간단한 rule-based 용어 사전입니다.
LLM 호출 전에 용어 질문을 감지하면 즉시 답변을 반환할 수 있습니다.
"""

from datetime import datetime
from typing import Any, Dict, List


TERM_GLOSSARY: Dict[str, Dict[str, str]] = {
    "상장": {
        "title": "상장",
        "definition": "상장은 기업의 주식이 한국거래소 같은 증권시장에 등록되어 투자자들이 공개적으로 사고팔 수 있게 되는 것을 의미합니다.",
        "example": "예를 들어 기업이 코스피나 코스닥에 상장되면 일반 투자자도 해당 기업의 주식을 거래할 수 있습니다.",
    },
    "ipo": {
        "title": "IPO",
        "definition": "IPO는 Initial Public Offering의 약자로, 기업이 처음으로 주식을 일반 투자자에게 공개하고 증권시장에 상장하는 절차를 의미합니다.",
        "example": "IPO를 통해 기업은 자금을 조달하고, 투자자는 새로 상장되는 기업의 주식을 살 기회를 얻습니다.",
    },
    "코스피": {
        "title": "코스피",
        "definition": "코스피는 한국거래소 유가증권시장에 상장된 기업들의 주식 시장을 의미합니다. 일반적으로 규모가 크고 안정적인 기업들이 많이 포함됩니다.",
        "example": "삼성전자, 현대자동차 같은 대형 기업은 코스피 시장에 상장되어 있습니다.",
    },
    "코스닥": {
        "title": "코스닥",
        "definition": "코스닥은 성장성이 높은 중소·벤처기업 중심의 주식 시장을 의미합니다.",
        "example": "기술 기반 성장 기업이나 바이오 기업이 코스닥에 상장되는 경우가 많습니다.",
    },
    "매출액": {
        "title": "매출액",
        "definition": "매출액은 기업이 제품이나 서비스를 판매해서 벌어들인 총 수익을 의미합니다.",
        "example": "매출액이 증가했다면 판매 규모가 커졌을 가능성이 있지만, 이익이 함께 늘었는지는 별도로 확인해야 합니다.",
    },
    "영업이익": {
        "title": "영업이익",
        "definition": "영업이익은 기업의 본업에서 벌어들인 이익을 의미합니다. 매출액에서 매출원가와 판매관리비 등을 뺀 값입니다.",
        "example": "영업이익이 감소했다면 본업의 수익성이 약해졌을 가능성이 있습니다.",
    },
    "당기순이익": {
        "title": "당기순이익",
        "definition": "당기순이익은 일정 기간 동안 기업이 최종적으로 벌어들인 순이익을 의미합니다. 영업외손익과 세금까지 반영한 최종 이익입니다.",
        "example": "영업이익은 좋지만 당기순이익이 낮다면 이자비용, 환율 손실, 세금 등의 영향을 받았을 수 있습니다.",
    },
    "부채비율": {
        "title": "부채비율",
        "definition": "부채비율은 자기자본 대비 부채가 얼마나 많은지를 보여주는 재무 안정성 지표입니다.",
        "example": "부채비율이 높아지면 차입 부담이나 재무 위험이 커졌는지 확인할 필요가 있습니다.",
    },
    "유동비율": {
        "title": "유동비율",
        "definition": "유동비율은 유동부채 대비 유동자산의 비율로, 단기 지급능력을 보여주는 지표입니다.",
        "example": "유동비율이 100% 미만이면 단기 부채를 갚을 유동자산이 부족할 가능성을 점검해야 합니다.",
    },
    "per": {
        "title": "PER",
        "definition": "PER은 주가수익비율로, 주가가 기업의 주당순이익에 비해 몇 배 수준인지 보여주는 지표입니다.",
        "example": "PER이 높으면 시장이 기업의 성장성을 높게 평가하고 있을 수 있지만, 고평가 가능성도 함께 검토해야 합니다.",
    },
    "pbr": {
        "title": "PBR",
        "definition": "PBR은 주가순자산비율로, 주가가 기업의 주당순자산에 비해 몇 배 수준인지 보여주는 지표입니다.",
        "example": "PBR이 1보다 낮으면 장부상 순자산보다 낮은 가격에 거래된다는 의미일 수 있습니다.",
    },
    "roe": {
        "title": "ROE",
        "definition": "ROE는 자기자본이익률로, 기업이 자기자본을 활용해 얼마나 효율적으로 이익을 냈는지 보여주는 지표입니다.",
        "example": "ROE가 높으면 자기자본 대비 이익 창출력이 높다고 해석할 수 있습니다.",
    },
    "roa": {
        "title": "ROA",
        "definition": "ROA는 총자산이익률로, 기업이 보유한 자산을 활용해 얼마나 이익을 냈는지 보여주는 지표입니다.",
        "example": "ROA가 높으면 자산을 효율적으로 운용하고 있을 가능성이 있습니다.",
    },
    "eps": {
        "title": "EPS",
        "definition": "EPS는 주당순이익으로, 기업의 순이익을 발행주식 수로 나눈 값입니다.",
        "example": "EPS가 증가하면 주식 한 주당 벌어들이는 이익이 늘었다고 볼 수 있습니다.",
    },
    "ebitda": {
        "title": "EBITDA",
        "definition": "EBITDA는 이자, 세금, 감가상각비 등을 차감하기 전 이익으로, 기업의 현금 창출력을 대략적으로 보는 데 사용됩니다.",
        "example": "설비투자가 많은 기업은 EBITDA와 영업이익을 함께 보면 수익성을 더 입체적으로 볼 수 있습니다.",
    },
    "현금흐름": {
        "title": "현금흐름",
        "definition": "현금흐름은 기업에 실제로 현금이 들어오고 나가는 흐름을 의미합니다.",
        "example": "이익이 나더라도 현금흐름이 나쁘면 대금 회수 지연이나 재고 부담이 있을 수 있습니다.",
    },
    "영업활동현금흐름": {
        "title": "영업활동현금흐름",
        "definition": "영업활동현금흐름은 기업의 본업 활동에서 실제로 벌어들인 현금 흐름을 의미합니다.",
        "example": "영업이익은 좋은데 영업활동현금흐름이 나쁘다면 매출채권 증가나 재고 부담을 점검해야 합니다.",
    },
    "자산회전율": {
        "title": "자산회전율",
        "definition": "자산회전율은 기업이 보유한 자산을 활용해 얼마나 많은 매출을 만들었는지 보여주는 효율성 지표입니다.",
        "example": "자산회전율이 높아지면 같은 자산으로 더 많은 매출을 냈다는 의미일 수 있습니다.",
    },
    "재고자산회전율": {
        "title": "재고자산회전율",
        "definition": "재고자산회전율은 재고가 얼마나 빠르게 판매되거나 소진되는지 보여주는 지표입니다.",
        "example": "재고자산회전율이 낮아지면 재고 부담이나 수요 둔화를 의심해볼 수 있습니다.",
    },
    "공시": {
        "title": "공시",
        "definition": "공시는 기업이 투자자와 시장에 중요한 경영·재무 정보를 공식적으로 공개하는 것을 의미합니다.",
        "example": "사업보고서, 분기보고서, 주요사항보고서 등이 공시에 포함됩니다.",
    },
    "사업보고서": {
        "title": "사업보고서",
        "definition": "사업보고서는 기업의 사업 내용, 재무 상태, 경영 성과 등을 정기적으로 정리해 공시하는 문서입니다.",
        "example": "사업보고서를 보면 매출 구조, 주요 위험, 재무제표 등을 확인할 수 있습니다.",
    },
}

QUESTION_HINTS = [
    "무슨 뜻",
    "무슨의미",
    "무슨 의미",
    "뜻이 뭐",
    "뜻은 뭐",
    "뭐야",
    "뭔데",
    "설명",
    "정의",
    "뜻",
    "이란",
    "란 무엇",
    "알려줘",
]

# 회사 리포트 분석 질문을 용어 질문으로 오분류하지 않기 위한 단서입니다.
# 예: "파트론의 2021년 영업이익이 왜 증가했어?"는 영업이익이라는 용어를 포함하지만
# 용어 설명 질문이 아니라 리포트 분석 질문입니다.
ANALYSIS_INTENT_HINTS = [
    "왜",
    "원인",
    "이유",
    "증가",
    "감소",
    "상승",
    "하락",
    "급증",
    "급감",
    "개선",
    "악화",
    "변동",
    "변화",
    "관련",
    "영향",
    "직접",
    "근거",
    "뉴스",
    "공시",
    "보고서",
    "리포트",
]

# 연도/기업명이 섞인 질문은 대부분 특정 리포트 분석 질문입니다.
YEAR_PATTERN = r"20\d{2}"


def normalize_text(value: Any) -> str:
    return str(value or "").lower().replace(" ", "")


def detect_financial_term_question(question: str) -> Dict[str, Any]:
    """
    경제/재무 용어 설명 질문인지 판별합니다.

    v2 정책:
    - "상장이 무슨 뜻이야?", "PER 설명해줘"처럼 명확한 정의 요청만 matched=True
    - "PER", "상장"처럼 용어만 단독으로 입력한 경우도 matched=True
    - "파트론의 2021년 영업이익이 왜 증가했어?"처럼 특정 기업/연도/증감 분석 질문은 matched=False
    """

    import re

    raw_question = str(question or "").strip()
    normalized = normalize_text(raw_question)

    if not normalized:
        return {"matched": False}

    matched_terms: List[str] = []

    for term in TERM_GLOSSARY:
        term_normalized = normalize_text(term)
        if term_normalized and term_normalized in normalized:
            matched_terms.append(term)

    if not matched_terms:
        return {"matched": False}

    has_question_hint = any(hint.replace(" ", "") in normalized for hint in QUESTION_HINTS)
    has_analysis_hint = any(hint.replace(" ", "") in normalized for hint in ANALYSIS_INTENT_HINTS)
    has_year = bool(re.search(YEAR_PATTERN, raw_question))

    # PER / PBR / ROE 처럼 용어만 입력한 경우 허용
    # 단, "파트론 영업이익"처럼 문장이 길거나 회사명이 섞인 느낌이면 용어 질문으로 보지 않습니다.
    only_term_like = normalized in {normalize_text(term) for term in TERM_GLOSSARY}

    if only_term_like:
        primary = matched_terms[0]
        return {
            "matched": True,
            "term_key": primary,
            "term": TERM_GLOSSARY[primary],
            "matched_terms": matched_terms,
            "reason": "term_only",
        }

    # 분석 의도나 연도가 섞였는데 명확한 정의 요청이 아니면 리포트 Q&A로 넘깁니다.
    if (has_analysis_hint or has_year) and not has_question_hint:
        return {"matched": False}

    # 명확한 정의/설명 요청일 때만 용어 질문으로 처리합니다.
    if has_question_hint:
        primary = matched_terms[0]
        return {
            "matched": True,
            "term_key": primary,
            "term": TERM_GLOSSARY[primary],
            "matched_terms": matched_terms,
            "reason": "definition_hint",
        }

    return {"matched": False}


def build_financial_term_response(
    question: str,
    term_result: Dict[str, Any],
) -> Dict[str, Any]:
    term = term_result.get("term", {}) or {}
    title = term.get("title", "해당 용어")
    definition = term.get("definition", "해당 용어에 대한 설명을 찾지 못했습니다.")
    example = term.get("example", "")

    answer = definition

    if example:
        answer += f" {example}"

    answer += " 다만 이 설명은 일반적인 용어 설명이며, 특정 기업에 대한 투자 판단은 아닙니다."

    return {
        "answer": answer,
        "used_sources": [
            {
                "source_id": "financial_term_glossary",
                "source_type": "glossary",
                "title": f"재무/경제 용어 사전 - {title}",
                "reason": "사용자 질문이 경제·재무 용어 설명 요청으로 분류되었습니다.",
            }
        ],
        "limitations": "일반적인 용어 설명이며, 특정 기업의 재무 상태나 투자 판단을 의미하지 않습니다.",
        "metadata": {
            "source": "financial_term_glossary",
            "intent": "term_definition",
            "term": title,
            "question": question,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "llm_used": False,
        },
    }
