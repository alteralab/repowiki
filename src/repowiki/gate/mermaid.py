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
    diagrams: list[Diagram], limits: dict[str, DiagramLimit]
) -> list[LimitViolation]:
    """도식 하나하나의 소스 문자 수와 노드 수를 검사한다.

    쪽당 블록 수는 여기서 보지 않는다. 이 함수가 보는 것은 사실 전체이고, 사실 전체는 한
    쪽이 아니다. 그 검사는 쪽이 정해진 뒤에 `check_page_blocks`가 한다.
    """
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
    return violations


def check_page_blocks(
    page_id: str, diagrams: list[Diagram], limits: dict[str, DiagramLimit]
) -> list[LimitViolation]:
    """한 쪽이 실은 블록 수를 검사한다. 상한은 그 쪽이 실은 층 중 가장 낮은 값이다."""
    if not diagrams:
        return []
    caps = [
        limits[diagram.level].max_blocks_per_page
        for diagram in diagrams
        if diagram.level in limits
    ]
    if not caps or len(diagrams) <= min(caps):
        return []
    return [
        LimitViolation(
            diagram_id=page_id,
            rule="blocks-per-page",
            detail=f"{len(diagrams)}블록 > 상한 {min(caps)}블록",
        )
    ]
