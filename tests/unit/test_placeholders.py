"""자리표시자 확장의 단위 검사.

여기서 고정하는 것은 "작업이 준 것만 편다"이다. 없는 이름을 조용히 남기면 사람이 읽는 글에
중괄호가 실리고, 없는 이름을 빈 문자열로 바꾸면 게이트가 그 쪽을 통과시킨다.
"""

from __future__ import annotations

import pytest

from repowiki.bundle.placeholders import PlaceholderError, expand, names
from repowiki.bundle.tables import render
from repowiki.models import Diagram, FactTable

DIAGRAM = Diagram(
    id="TYPE-Option", level="TYPE", source="classDiagram\n  class Option", node_count=1, edge_count=0
)
TABLE = FactTable(
    id="lang-versions", title="언어 버전", columns=["언어", "버전"], rows=[["Java", "1.8"]]
)


def test_a_diagram_placeholder_becomes_a_fenced_block() -> None:
    body = expand("앞\n\n{{diagram:TYPE-Option}}\n\n뒤", [DIAGRAM], [])
    assert body == f"앞\n\n```mermaid\n{DIAGRAM.source}\n```\n\n뒤"


def test_a_table_placeholder_becomes_the_rendered_table() -> None:
    body = expand("{{table:lang-versions}}", [], [TABLE])
    assert body == render(TABLE)


def test_an_unknown_name_is_refused_rather_than_left_in_the_page() -> None:
    with pytest.raises(PlaceholderError):
        expand("{{diagram:없는것}}", [DIAGRAM], [])
    with pytest.raises(PlaceholderError):
        expand("{{table:없는것}}", [], [TABLE])


def test_a_body_without_placeholders_is_unchanged() -> None:
    assert expand("그냥 글이다. 중괄호 하나 {만 있다.", [DIAGRAM], [TABLE]) == (
        "그냥 글이다. 중괄호 하나 {만 있다."
    )


def test_names_lists_exactly_what_the_job_gave() -> None:
    assert names([DIAGRAM], [TABLE]) == ["{{diagram:TYPE-Option}}", "{{table:lang-versions}}"]


def test_the_expanded_body_is_what_the_gate_compares() -> None:
    """편 결과가 게이트가 보는 형태와 같아야 한다. 다르면 통과할 수 없는 요구가 된다."""
    from repowiki.bundle.tables import blocks_in, body_of

    assert body_of(TABLE) in blocks_in(expand("{{table:lang-versions}}", [], [TABLE]))
