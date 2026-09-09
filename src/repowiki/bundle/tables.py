"""사실 표를 Markdown으로 낸다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 `FactTable`이고 출력은 문자열이다. 이 함수 하나가 표의 정본 표기라,
계획 층과 게이트가 같은 문자열을 본다. 두 자리가 각자 렌더하면 게이트는 자기가 만든
문자열과 남의 문자열을 비교하게 되고 그 비교는 언제나 실패한다.

사각: 셀 안의 파이프 문자는 이스케이프하지만 줄바꿈은 다루지 않는다. 표에 넣는 값은
한 줄짜리라는 것이 계획 층의 계약이다.
"""

from __future__ import annotations

from repowiki.models import FactTable


def _cell(value: str) -> str:
    """셀 하나. 파이프는 표 문법을 깨므로 escape 한다."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render(table: FactTable) -> str:
    """표 하나를 Markdown 블록으로 만든다. 제목과 각주까지 한 덩어리다."""
    lines = [f"**{table.title}**", ""]
    lines.append("| " + " | ".join(_cell(c) for c in table.columns) + " |")
    lines.append("|" + "|".join(" --- " for _ in table.columns) + "|")
    for row in table.rows:
        padded = list(row) + [""] * (len(table.columns) - len(row))
        lines.append("| " + " | ".join(_cell(c) for c in padded[: len(table.columns)]) + " |")
    if table.note:
        lines += ["", table.note]
    return "\n".join(lines)


def _cells(line: str) -> list[str]:
    """표 줄의 칸. 앞뒤 파이프는 있어도 없어도 된다 — CommonMark는 둘 다 표다."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_delimiter(line: str) -> bool:
    """구분 줄인가. `| --- | :---: |` 모양이라야 표다.

    구분 줄을 요구하지 않으면 파이프로 시작하는 산문 한 줄도 표가 된다. 그러면 게이트가
    정상 문장을 "작업이 주지 않은 표"로 거절한다.
    """
    cells = _cells(line)
    if len(cells) < 2:
        return False
    return all(cell and set(cell) <= set("-: ") and "-" in cell for cell in cells)


def _looks_like_row(line: str) -> bool:
    """표의 줄인가. 파이프가 있고 코드나 인용이 아니면 표의 줄로 본다."""
    return "|" in line and len(_cells(line)) >= 2


def _strip_quote(line: str) -> str:
    """인용문 표시를 벗긴다. `> | a | b |`도 렌더러에게는 표다."""
    stripped = line.strip()
    while stripped.startswith(">"):
        stripped = stripped[1:].strip()
    return stripped


def _skipped(lines: list[str]) -> list[bool]:
    """표를 찾지 않을 줄. 코드 울타리와 들여쓴 코드와 HTML 주석 안쪽이다."""
    in_fence = False
    in_comment = False
    found: list[bool] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            found.append(True)
            continue
        if "<!--" in line:
            in_comment = True
        skip = in_fence or in_comment or line.startswith("    ")
        if "-->" in line:
            in_comment = False
        found.append(skip)
    return found


def blocks_in(body: str) -> list[str]:
    """본문에 있는 Markdown 표의 본체만 꺼낸다.

    표로 세는 조건은 머리 줄 바로 뒤에 구분 줄이 오는 것이다. 앞뒤 파이프가 없는 형태도
    표이고, 인용문 안의 표도 렌더러가 표로 그리므로 함께 센다 — 게이트가 못 보는 자리에
    숫자를 숨길 수 있으면 게이트가 아니다.

    코드 울타리와 들여쓴 코드와 HTML 주석 안쪽은 렌더되지 않으므로 세지 않는다.
    """
    raw = body.splitlines()
    skipped = _skipped(raw)
    lines = [_strip_quote(line) for line in raw]

    found: list[str] = []
    position = 0
    while position < len(lines) - 1:
        if (
            skipped[position]
            or not _looks_like_row(lines[position])
            or not _is_delimiter(lines[position + 1])
        ):
            position += 1
            continue
        block = [lines[position], lines[position + 1]]
        cursor = position + 2
        while cursor < len(lines) and _looks_like_row(lines[cursor]) and not skipped[cursor]:
            block.append(lines[cursor])
            cursor += 1
        found.append("\n".join(block))
        position = cursor
    return found


def html_tables_in(body: str) -> int:
    """본문의 HTML 표 개수. 주석 안쪽은 렌더되지 않으므로 세지 않는다."""
    lines = body.splitlines()
    skipped = _skipped(lines)
    return sum(
        line.lower().count("<table")
        for line, skip in zip(lines, skipped, strict=True)
        if not skip
    )


def body_of(table: FactTable) -> str:
    """표의 본체(제목과 각주를 뺀 파이프 줄)만. 게이트의 비교 단위다."""
    return "\n".join(
        line for line in render(table).splitlines() if line.strip().startswith("|")
    )
