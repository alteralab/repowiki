"""Mermaid 한도 게이트. 판정만 하고 고치지 않는다(PLAN §2.5, §6 2).

경계 계약: 입력은 컴파일된 다이어그램이고 출력은 위반 목록이다. 파서 통과 여부는
`adapters/node.py`가 실제 Mermaid로 재고, 이 모듈은 결정적으로 셀 수 있는 것만 본다.

사각: 문자 수와 블록 수는 GitLab 저장소 뷰의 실제 한도(리서치 05)를 재현하지만,
렌더 가독성(엣지 교차, 라벨 잘림)은 여기서 못 본다 — 사다리 측정이 본다(C-GATE-2).
"""

from __future__ import annotations

from pydantic import BaseModel

from repowiki.models import Diagram, DiagramLimit


class LimitViolation(BaseModel):
    """한도 위반 하나. `diagram_id`와 사유를 함께 낸다."""

    diagram_id: str
    rule: str
    detail: str


def check_limits(
    diagrams: list[Diagram], limits: dict[str, DiagramLimit], blocks_per_page: int
) -> list[LimitViolation]:
    """소스 문자 수, 노드 수, 페이지당 블록 수를 검사한다."""
    violations: list[LimitViolation] = []
    for diagram in diagrams:
        limit = limits.get(diagram.level)
        if limit is None:
            violations.append(
                LimitViolation(
                    diagram_id=diagram.id,
                    rule="unknown-level",
                    detail=f"한도 표에 없는 층 {diagram.level}",
                )
            )
            continue
        if len(diagram.source) > limit.max_source_chars:
            violations.append(
                LimitViolation(
                    diagram_id=diagram.id,
                    rule="source-chars",
                    detail=f"{len(diagram.source)}자 > 상한 {limit.max_source_chars}자",
                )
            )
        if diagram.node_count > limit.max_nodes:
            violations.append(
                LimitViolation(
                    diagram_id=diagram.id,
                    rule="node-count",
                    detail=f"{diagram.node_count}개 > 상한 {limit.max_nodes}개",
                )
            )
    first_limit = next(iter(limits.values()), None)
    if first_limit is not None and blocks_per_page > first_limit.max_blocks_per_page:
        violations.append(
            LimitViolation(
                diagram_id="page",
                rule="blocks-per-page",
                detail=f"{blocks_per_page}블록 > 상한 {first_limit.max_blocks_per_page}블록",
            )
        )
    return violations
