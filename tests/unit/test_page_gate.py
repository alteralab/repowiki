"""페이지 게이트의 단위 검사. 무엇을 거부하고 무엇을 통과시키는지 고정한다."""

from __future__ import annotations

from repowiki.gate.page import check_page
from repowiki.models import Diagram, Evidence, PageJob, PageOutput, PageType, Span


def _job(evidence: int = 3, diagram: str | None = None) -> PageJob:
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
        input_hash="h",
    )


def _page(body: str, description: str = "설명") -> PageOutput:
    return PageOutput(
        job_id="j1", title="모듈 a", description=description, body_markdown=body, citations=[]
    )


def test_page_with_enough_known_citations_passes() -> None:
    """근거 안의 인용이 셋이면 통과한다."""
    body = "책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E3]."
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
    body = f"책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E3].\n\n```mermaid\n{given}\n```\n"
    assert check_page(_job(diagram=given), _page(body)) == []


def test_citation_minimum_never_exceeds_available_evidence() -> None:
    """근거가 둘뿐인 페이지에 셋을 요구하지 않는다. 통과할 수 없는 요구는 게이트가 아니다."""
    body = "책임이다[^E1]. 계약이다[^E2]."
    assert check_page(_job(evidence=2), _page(body)) == []


def test_given_diagram_must_appear_in_the_body() -> None:
    """작업이 준 그림을 빼면 거부한다. 그림은 사실이고 페이지가 그것을 보여야 한다."""
    given = "flowchart LR\n  A --> B"
    body = "책임이다[^E1]. 계약이다[^E2]. 흐름이다[^E3]."
    rules = {v.rule for v in check_page(_job(diagram=given), _page(body))}
    assert "diagram-missing" in rules
