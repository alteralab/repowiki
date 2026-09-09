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

    예산을 앞에서부터 다 쓰지 않는다. 그렇게 하면 앞쪽의 큰 클래스 몇이 예산을 먹고 뒤쪽
    근거가 통째로 원문 없이 남는다. 실측(kafka, 2026-09-10): 근거 4664자리 가운데 739개
    (16%)가 원문이 없었고, 어떤 쪽은 예순 중 서른여섯이 비어 있었다. 쓰는 층은 그 자리를
    읽지 못한 채 인용만 하게 된다.

    두 벌로 나눠 준다. 먼저 자리마다 같은 몫까지 채우고, 남은 예산을 앞에서부터 더 준다.
    작은 선언은 첫 벌에서 통째로 들어오고, 큰 클래스는 둘째 벌에서 더 받는다.

    사각: 예산이 근거 수보다 작으면 여전히 뒤쪽이 빈다. 자리와 설명은 그대로 있으므로
    인용은 되지만, 그 자리를 읽지 않고 쓰는 것은 쓰는 층의 판단이다.
    """
    filled = [item for item in evidence if texts.get(item.span.path) is not None]
    if not filled:
        return 0

    share = max(1, min(MAX_LINES_PER_SPAN, page_budget // len(filled)))
    used = 0
    for item in filled:
        body = excerpt(
            texts[item.span.path], item.span.start_line, item.span.end_line, share
        )
        if not body:
            continue
        item.text = body
        used += len(body.splitlines())

    # 남은 예산을 앞에서부터 더 준다. 순서가 곧 중요도다.
    for item in filled:
        if used >= page_budget:
            break
        already = len(item.text.splitlines()) if item.text else 0
        if already >= MAX_LINES_PER_SPAN:
            continue
        want = min(MAX_LINES_PER_SPAN, already + (page_budget - used))
        body = excerpt(
            texts[item.span.path], item.span.start_line, item.span.end_line, want
        )
        if not body:
            continue
        item.text = body
        used += len(body.splitlines()) - already
    return used
