"""
chat_history_builder.py

챗봇 API에서 전달받은 chat_history를 LLM 프롬프트에 넣기 좋은 텍스트로 변환하는 유틸 모듈입니다.

목적:
- 사용자가 "방금 답변에서", "그 근거", "두 번째 뉴스"처럼 이전 대화를 참조할 때 대응할 수 있도록 합니다.
- 전체 대화를 무제한으로 넣지 않고 최근 N개 메시지만 사용합니다.
- 너무 긴 메시지는 잘라서 프롬프트 길이 증가를 방지합니다.

예상 입력:
[
    {"role": "user", "content": "파트론의 2021년 영업이익이 왜 증가했어?"},
    {"role": "assistant", "content": "파트론의 영업이익 증가는 ..."},
]

출력:
[이전 대화]
user: ...
assistant: ...
"""

from typing import Any, Dict, List, Optional


VALID_ROLES = {"user", "assistant", "system"}


def safe_text(value: Any) -> str:
    """
    None 또는 비문자열 값을 안전하게 문자열로 변환합니다.
    """

    if value is None:
        return ""

    return str(value)


def normalize_role(role: Any) -> str:
    """
    role 값을 user/assistant/system 중 하나로 정규화합니다.
    """

    role_text = safe_text(role).strip().lower()

    if role_text in VALID_ROLES:
        return role_text

    return "user"


def trim_message(content: Any, max_chars: int = 700) -> str:
    """
    메시지가 너무 길면 max_chars 기준으로 자릅니다.
    """

    text = safe_text(content).strip()

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "...(truncated)"


def normalize_chat_history(
    chat_history: Optional[List[Dict[str, Any]]],
    max_messages: int = 6,
    max_chars_per_message: int = 700,
) -> List[Dict[str, str]]:
    """
    chat_history를 안전한 list[dict] 형태로 정리합니다.

    Args:
        chat_history: 프론트에서 전달된 대화 기록
        max_messages: 최근 몇 개 메시지를 사용할지
        max_chars_per_message: 메시지 하나당 최대 문자 수

    Returns:
        [{"role": "...", "content": "..."}]
    """

    if not chat_history:
        return []

    if not isinstance(chat_history, list):
        return []

    normalized = []

    for item in chat_history:
        if not isinstance(item, dict):
            continue

        role = normalize_role(item.get("role"))
        content = trim_message(
            item.get("content"),
            max_chars=max_chars_per_message,
        )

        if not content:
            continue

        normalized.append(
            {
                "role": role,
                "content": content,
            }
        )

    if max_messages and len(normalized) > max_messages:
        normalized = normalized[-max_messages:]

    return normalized


def build_chat_history_text(
    chat_history: Optional[List[Dict[str, Any]]],
    max_messages: int = 6,
    max_chars_per_message: int = 700,
) -> str:
    """
    chat_history를 LLM context용 텍스트로 변환합니다.
    """

    normalized_history = normalize_chat_history(
        chat_history=chat_history,
        max_messages=max_messages,
        max_chars_per_message=max_chars_per_message,
    )

    if not normalized_history:
        return "[이전 대화]\n이전 대화 기록이 제공되지 않았습니다."

    lines = ["[이전 대화]"]

    for message in normalized_history:
        role = message.get("role", "user")
        content = message.get("content", "")
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


def has_chat_history(chat_history: Optional[List[Dict[str, Any]]]) -> bool:
    """
    유효한 chat_history가 있는지 확인합니다.
    """

    return bool(normalize_chat_history(chat_history))


if __name__ == "__main__":
    sample_history = [
        {
            "role": "user",
            "content": "파트론의 2021년 영업이익이 왜 증가했어?",
        },
        {
            "role": "assistant",
            "content": "뉴스에서는 카메라 모듈 공급 증가와 가격 상승이 언급되었습니다.",
        },
        {
            "role": "user",
            "content": "뉴스 근거와 공시 근거를 나눠서 설명해줘.",
        },
    ]

    print("[Chat History Builder Test]")
    print(build_chat_history_text(sample_history))
