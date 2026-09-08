"""근거 게이트. 사실마다 인용 span이 실재하는지 본다(PLAN §1 목표 3, §6 2).

경계 계약: 입력은 사실 묶음과 파일 줄 수 조회이고, 출력은 위반 목록이다. 판정만 하고
사실을 고치지 않는다. 근거가 없는 항목은 페이지가 아니라 보고서로 간다.

사각: 줄 번호가 파일 안에 있는지만 본다. 그 줄이 정말 그 사실을 말하는지는 사람과
Phase 3의 표본 판정이 본다(C-GATE-2).
"""

from __future__ import annotations

from pydantic import BaseModel

from repowiki.models import RepoFacts, Span


class EvidenceViolation(BaseModel):
    """근거 위반 하나. 무엇의 어떤 근거가 왜 못 쓰는지 적는다."""

    subject: str
    rule: str
    detail: str


def _check_span(subject: str, span: Span, line_counts: dict[str, int]) -> EvidenceViolation | None:
    if span.path not in line_counts:
        return EvidenceViolation(
            subject=subject, rule="path-missing", detail=f"없는 경로 {span.path}"
        )
    total = line_counts[span.path]
    if span.start_line > total or span.end_line > total:
        return EvidenceViolation(
            subject=subject,
            rule="line-out-of-range",
            detail=f"{span.cite()} 가 파일 줄 수 {total}을 넘는다",
        )
    if span.end_line < span.start_line:
        return EvidenceViolation(
            subject=subject, rule="line-reversed", detail=f"{span.cite()} 의 끝이 시작보다 앞이다"
        )
    return None


def _spans_of(facts: RepoFacts) -> list[tuple[str, Span]]:
    """검사 대상 (주체, span) 쌍 전부. 종류가 늘면 여기 한 줄이 는다(C-BRANCH-1)."""
    pairs: list[tuple[str, Span]] = []
    pairs += [(f"symbol {s.name}", s.span) for s in facts.symbols]
    pairs += [(f"type-edge {e.src}->{e.dst}", e.span) for e in facts.type_edges]
    pairs += [(f"entry-point {e.name}", e.span) for e in facts.entry_points]
    pairs += [
        (f"module-edge {edge.src}->{edge.dst}", span)
        for edge in facts.module_edges
        for span in edge.evidence
    ]
    pairs += [
        (f"flow {flow.id} hop {hop.symbol}", hop.span)
        for flow in facts.flows
        for hop in flow.hops
    ]
    return pairs


def _missing_evidence(facts: RepoFacts) -> list[EvidenceViolation]:
    """근거 자체가 없는 항목. span이 틀린 것과 없는 것은 다른 위반이다."""
    violations = [
        EvidenceViolation(
            subject=f"module-edge {edge.src}->{edge.dst}",
            rule="no-evidence",
            detail="뒷받침하는 import span이 없다",
        )
        for edge in facts.module_edges
        if not edge.evidence
    ]
    violations += [
        EvidenceViolation(subject=f"flow {flow.id}", rule="no-hops", detail="홉이 없는 흐름이다")
        for flow in facts.flows
        if not flow.hops
    ]
    return violations


def check_evidence(facts: RepoFacts, line_counts: dict[str, int]) -> list[EvidenceViolation]:
    """모든 사실의 근거 span이 실재하는지 본다."""
    violations = _missing_evidence(facts)
    for subject, span in _spans_of(facts):
        found = _check_span(subject, span, line_counts)
        if found is not None:
            violations.append(found)
    return violations
