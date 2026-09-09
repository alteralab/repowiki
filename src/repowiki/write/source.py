"""근거 자리의 원문을 브리핑에 실을 수 있는 크기로 잘라 낸다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 파일 내용과 자리이고 출력은 문자열이다. 파일을 여는 것은 호출자의 일이다.

왜 자르는가. 한 페이지의 근거가 예순 자리이고 그중에는 천 줄짜리 클래스가 있다. 전부 실으면
브리핑이 저장소가 되고, 쓰는 층은 무엇이 중요한지 다시 판단해야 한다. 자르는 규칙은 하나다 —
선언의 머리는 그 선언이 무엇인지 말하므로 앞쪽을 남긴다.

사각: 잘린 뒤쪽에 있는 것은 쓰는 층이 보지 못한다. 잘랐다는 사실을 본문에 표시해 두어,
쓰는 층이 "여기까지만 보았다"를 알 수 있게 한다.
"""

from __future__ import annotations

MAX_LINES_PER_SPAN = 60
MAX_LINES_PER_PAGE = 1200


def excerpt(text: str, start_line: int, end_line: int, budget: int = MAX_LINES_PER_SPAN) -> str:
    """자리 하나의 원문. 예산을 넘으면 앞쪽을 남기고 잘랐다고 적는다."""
    lines = text.splitlines()
    first = max(1, start_line)
    last = min(len(lines), max(first, end_line))
    if first > len(lines):
        return ""
    chosen = lines[first - 1 : last]
    if len(chosen) <= budget:
        return "\n".join(chosen)
    kept = chosen[:budget]
    return "\n".join([*kept, f"... ({len(chosen) - budget}줄 더 있다)"])


def fill(evidence: list, texts: dict[str, str], page_budget: int = MAX_LINES_PER_PAGE) -> int:
    """근거 목록에 원문을 채운다. 채운 줄 수를 낸다.

    페이지 예산을 다 쓰면 뒤쪽 근거는 원문 없이 남는다. 자리와 설명은 그대로 있으므로 여전히
    인용할 수 있다 — 다만 그 자리를 읽지 않고 쓰는 것은 쓰는 층의 판단이다.
    """
    used = 0
    for item in evidence:
        if used >= page_budget:
            break
        text = texts.get(item.span.path)
        if text is None:
            continue
        remaining = min(MAX_LINES_PER_SPAN, page_budget - used)
        body = excerpt(text, item.span.start_line, item.span.end_line, remaining)
        if not body:
            continue
        item.text = body
        used += len(body.splitlines())
    return used
