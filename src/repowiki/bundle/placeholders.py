"""쓰는 층이 도식과 표를 자리표시자로 두게 한다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 본문과 작업이 준 도식·표이고 출력은 확장된 본문이다.

왜 필요한가. 게이트는 작업이 준 도식과 표가 본문에 **글자 그대로** 있어야 통과시킨다.
그 요구는 옳다 — 값이 한 칸이라도 바뀌면 그 쪽은 근거 없는 숫자를 실은 것이다. 그런데 쓰는
층에게 표 서른 줄을 손으로 옮겨 적으라고 하면, 옮겨 적다가 틀리는 일이 규칙 위반과 구별되지
않는다. 자리표시자를 두면 옮겨 적을 일이 없어지고, 게이트의 요구는 그대로 남는다.

문법은 둘이다. `{{diagram:TYPE-Option}}`과 `{{table:members-Option}}`이다. 작업에 없는
이름을 쓰면 확장하지 않고 예외로 올린다 — 자리표시자가 본문에 그대로 남으면 사람이 읽는
글에 중괄호가 실린다(C-REPORT-2).
"""

from __future__ import annotations

import re

from repowiki.bundle.tables import render
from repowiki.models import Diagram, FactTable

# ast-grep-ignore: regex-on-structure — 어휘: 자리표시자는 `{{종류:이름}}` 고정 형식이다.
_PLACEHOLDER = re.compile(r"\{\{(diagram|table):([^}]+)\}\}")


class PlaceholderError(ValueError):
    """작업이 주지 않은 이름을 자리표시자가 가리켰다."""


def expand(body: str, diagrams: list[Diagram], tables: list[FactTable]) -> str:
    """본문의 자리표시자를 작업이 준 소스로 바꾼다.

    도식은 Mermaid 울타리로 감싸고, 표는 렌더된 Markdown으로 바꾼다. 둘 다 게이트가 보는
    형태와 같은 문자열이라, 확장한 본문은 그 자리에서 게이트를 지난다.
    """
    by_diagram = {diagram.id: diagram for diagram in diagrams}
    by_table = {table.id: table for table in tables}

    def _replace(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2).strip()
        if kind == "diagram":
            diagram = by_diagram.get(name)
            if diagram is None:
                raise PlaceholderError(
                    f"이 작업에 없는 도식이다: {name}. 있는 것은 {sorted(by_diagram)}"
                )
            return f"```mermaid\n{diagram.source}\n```"
        table = by_table.get(name)
        if table is None:
            raise PlaceholderError(f"이 작업에 없는 표다: {name}. 있는 것은 {sorted(by_table)}")
        return render(table)

    return _PLACEHOLDER.sub(_replace, body)


def names(diagrams: list[Diagram], tables: list[FactTable]) -> list[str]:
    """이 작업에서 쓸 수 있는 자리표시자 전부. 지시문에 그대로 싣는다."""
    return [f"{{{{diagram:{d.id}}}}}" for d in diagrams] + [
        f"{{{{table:{t.id}}}}}" for t in tables
    ]
