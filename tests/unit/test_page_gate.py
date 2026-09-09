"""페이지 게이트의 단위 검사. 무엇을 거부하고 무엇을 통과시키는지 고정한다."""

from __future__ import annotations

from repowiki.gate.page import check_page
from repowiki.bundle.tables import render
from repowiki.models import (
    Diagram,
    Evidence,
    FactTable,
    PageJob,
    PageOutput,
    PageType,
    Span,
)


TABLE = FactTable(
    id="t1", title="언어 버전", columns=["언어", "버전"], rows=[["Java", "1.8"]]
)


def _job(
    evidence: int = 3, diagram: str | None = None, tables: list[FactTable] | None = None
) -> PageJob:
    return PageJob(
        id="j1",
        path="modules/a.md",
        type=PageType.MODULE,
        title="모듈 a",
        purpose="시험",
        facts={},
        evidence=[
            Evidence(id=f"E{i}", span=Span(path="a/A.java", start_line=i, end_line=i), note="선언")
            for i in range(1, evidence + 1)
        ],
        diagrams=(
            [Diagram(id="L2-a", level="L2", source=diagram, node_count=1, edge_count=0)]
            if diagram
            else []
        ),
        tables=tables or [],
        input_hash="h",
    )


def _long(body: str) -> str:
    """분량 하한을 넘기는 본문. 하한이 가려서 보려는 규칙을 못 보게 하지 않는다."""
    filler = " ".join(["이 모듈은 경계면 계약을 지킨다."] * 90)
    return f"{body}\n\n{filler}"


def _page(body: str, description: str = "설명") -> PageOutput:
    return PageOutput(
        job_id="j1", title="모듈 a", description=description, body_markdown=body, citations=[]
    )


def test_page_with_enough_known_citations_passes() -> None:
    """근거 안의 인용이 셋이면 통과한다."""
    body = _long("책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E3].")
    assert check_page(_job(), _page(body)) == []


def test_citation_outside_the_given_evidence_is_rejected() -> None:
    """작업이 주지 않은 근거 id는 거부한다. 사실 밖을 쓴 것이다."""
    body = "책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E9]."
    rules = {v.rule for v in check_page(_job(), _page(body))}
    assert "citation-out-of-range" in rules


def test_too_few_citations_is_rejected() -> None:
    """근거가 있는 페이지는 인용 세 건 이상이어야 한다."""
    rules = {v.rule for v in check_page(_job(), _page("책임이다[^E1]."))}
    assert "too-few-citations" in rules


def test_forbidden_prose_marks_are_rejected_outside_code() -> None:
    """엠대시와 이중 피동은 본문에서 거부한다."""
    body = "책임이다[^E1]. 계약이다[^E2]. 흐름이 만들어지게 된다[^E3]."
    rules = {v.rule for v in check_page(_job(), _page(body))}
    assert "double-passive" in rules


def test_diagram_must_come_from_the_facts() -> None:
    """LLM이 그림을 새로 그리면 거부한다."""
    given = "flowchart LR\n  A --> B"
    body = "책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E3].\n\n```mermaid\nflowchart LR\n  X --> Y\n```\n"
    rules = {v.rule for v in check_page(_job(diagram=given), _page(body))}
    assert "diagram-not-from-facts" in rules


def test_given_diagram_passes_unchanged() -> None:
    """작업이 준 그림을 그대로 넣으면 통과한다."""
    given = "flowchart LR\n  A --> B"
    body = _long(f"책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E3].\n\n```mermaid\n{given}\n```")
    assert check_page(_job(diagram=given), _page(body)) == []


def test_citation_minimum_never_exceeds_available_evidence() -> None:
    """근거가 둘뿐인 페이지에 셋을 요구하지 않는다. 통과할 수 없는 요구는 게이트가 아니다."""
    body = _long("책임이다[^E1]. 계약이다[^E2].")
    assert check_page(_job(evidence=2), _page(body)) == []


def test_given_diagram_must_appear_in_the_body() -> None:
    """작업이 준 그림을 빼면 거부한다. 그림은 사실이고 페이지가 그것을 보여야 한다."""
    given = "flowchart LR\n  A --> B"
    body = "책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E3]."
    rules = {v.rule for v in check_page(_job(diagram=given), _page(body))}
    assert "diagram-missing" in rules


def _passing_body(extra: str = "") -> str:
    """분량 하한과 인용 하한을 함께 넘는 본문."""
    cited = " ".join(f"근거가 있다[^E{i}]." for i in (1, 2, 3))
    return f"{_long(cited)}\n\n{extra}"


def test_a_table_the_job_gave_must_appear_verbatim() -> None:
    job = _job(tables=[TABLE])
    missing = check_page(job, PageOutput(job_id="j1", title="t", description="d",
                                         body_markdown=_passing_body()))
    assert [v.rule for v in missing] == ["table-missing"]

    present = check_page(
        job,
        PageOutput(
            job_id="j1", title="t", description="d",
            body_markdown=_passing_body(render(TABLE)),
        ),
    )
    assert present == []


def test_a_table_the_job_did_not_give_is_rejected() -> None:
    fabricated = "| 언어 | 버전 |\n| --- | --- |\n| Java | 999 |"
    violations = check_page(
        _job(),
        PageOutput(job_id="j1", title="t", description="d",
                   body_markdown=_passing_body(fabricated)),
    )
    assert [v.rule for v in violations] == ["table-not-from-facts"]


def test_the_same_table_twice_is_not_the_same_as_once() -> None:
    body = _passing_body(render(TABLE) + "\n\n" + render(TABLE))
    violations = check_page(
        _job(tables=[TABLE]),
        PageOutput(job_id="j1", title="t", description="d", body_markdown=body),
    )
    assert [v.rule for v in violations] == ["table-not-from-facts"]


def test_prose_that_begins_with_a_pipe_is_not_treated_as_a_table() -> None:
    body = _passing_body("| 이것은 표가 아니라 산문이다\n계속되는 문장이다.")
    assert check_page(_job(), PageOutput(job_id="j1", title="t", description="d",
                                         body_markdown=body)) == []


def test_an_html_table_is_rejected() -> None:
    body = _passing_body("<table><tr><td>999</td></tr></table>")
    violations = check_page(_job(), PageOutput(job_id="j1", title="t", description="d",
                                               body_markdown=body))
    assert [v.rule for v in violations] == ["html-table"]
