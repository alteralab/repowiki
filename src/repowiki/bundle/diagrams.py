"""Mermaid 다이어그램 컴파일러. 결정적 사실만 그린다(PLAN §2.5).

경계 계약: 입력은 사실 자료형이고 출력은 `Diagram`이다. LLM은 이 소스를 만들지 않고
라벨만 제안한다. 노드 수나 소스 문자 수가 한도를 넘으면 우선순위가 낮은 노드부터
줄이고 그 사유를 `degraded_reason`에 남긴다 — 조용히 자르지 않는다(C-REPORT-2).

사각: 이 컴파일러는 문법만 만든다. 실제 렌더 가독성(엣지 교차, 라벨 잘림)은
`gate/mermaid.py`의 한도 게이트와 Phase 1의 사다리 측정이 판정한다(C-GATE-2).
"""

from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel

from repowiki.models import (
    Diagram,
    DiagramLimit,
    Module,
    ModuleEdge,
    Subsystem,
    TypeEdge,
    TypeEdgeKind,
)

# ast-grep-ignore: regex-on-structure — 어휘: Mermaid 식별자에 허용되는 문자집합 판정이다. 구조가 아니라 문자 하나씩의 치환이라 정규 언어다.
_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


class _Plan(BaseModel):
    """그릴 것의 계획. 노드는 우선순위 순서이고 엣지는 노드 이름을 가리킨다."""

    header: str
    nodes: list[str]
    node_lines: dict[str, str]
    edges: list[tuple[str, str, str]]


def _node_id(prefix: str, raw: str) -> str:
    """Mermaid 노드 id. 문자와 숫자와 밑줄만 남긴다."""
    return f"{prefix}_{_ID_SAFE.sub('_', raw) or 'root'}"


def _label(raw: str) -> str:
    """라벨. 파서가 거부하는 문자를 지운다."""
    cleaned = raw.replace('"', "").replace("[", "(").replace("]", ")")
    return cleaned or "."


def _render(plan: _Plan, shown: list[str]) -> tuple[str, int]:
    visible = set(shown)
    lines = [plan.header]
    for name in shown:
        lines.append(plan.node_lines[name])
    kept = 0
    for src, dst, edge_line in plan.edges:
        if src in visible and dst in visible:
            lines.append(edge_line)
            kept += 1
    return "\n".join(lines), kept


def _compile(plan: _Plan, limit: DiagramLimit, diagram_id: str, level: str) -> Diagram:
    """노드 상한과 소스 문자 상한을 함께 만족할 때까지 노드를 줄인다."""
    total = len(plan.nodes)
    shown = plan.nodes[: limit.max_nodes]
    reasons: list[str] = []
    if total > limit.max_nodes:
        reasons.append(f"노드 {total}개가 상한 {limit.max_nodes}개를 넘어 상위만 그렸다")
    source, edge_count = _render(plan, shown)
    while len(source) > limit.max_source_chars and len(shown) > 1:
        shown = shown[:-1]
        source, edge_count = _render(plan, shown)
    if len(shown) < min(total, limit.max_nodes):
        reasons.append(
            f"소스 {limit.max_source_chars}자 상한을 맞추려고 노드를 {len(shown)}개로 줄였다"
        )
    return Diagram(
        id=diagram_id,
        level=level,
        source=source,
        node_count=len(shown),
        edge_count=edge_count,
        degraded_reason="; ".join(reasons) or None,
    )


def subsystem_diagram(
    subsystems: list[Subsystem], edges: list[ModuleEdge], limit: DiagramLimit
) -> Diagram:
    """L0. 서브시스템을 노드로, 서브시스템 사이 import 합계를 엣지로 그린다."""
    owner = {module: sub.id for sub in subsystems for module in sub.modules}
    weights: Counter[tuple[str, str]] = Counter()
    for edge in edges:
        src, dst = owner.get(edge.src), owner.get(edge.dst)
        if src is None or dst is None or src == dst:
            continue
        weights[(src, dst)] += edge.weight
    degree: Counter[str] = Counter()
    for (src, dst), weight in weights.items():
        degree[src] += weight
        degree[dst] += weight
    ordered = sorted((s.id for s in subsystems), key=lambda name: (-degree[name], name))
    plan = _Plan(
        header="flowchart LR",
        nodes=ordered,
        node_lines={name: f'  {_node_id("S", name)}["{_label(name)}"]' for name in ordered},
        edges=[
            (src, dst, f'  {_node_id("S", src)} -->|{weight}| {_node_id("S", dst)}')
            for (src, dst), weight in weights.most_common()
        ],
    )
    return _compile(plan, limit, "L0-subsystems", "L0")


def module_diagram(
    subsystem: Subsystem, modules: list[Module], edges: list[ModuleEdge], limit: DiagramLimit
) -> Diagram:
    """L1. 한 서브시스템 안의 모듈과 그 사이 엣지를 그린다."""
    members = set(subsystem.modules)
    sizes = {m.id: m.main_file_count for m in modules if m.id in members}
    ordered = [name for name, _ in sorted(sizes.items(), key=lambda item: (-item[1], item[0]))]
    plan = _Plan(
        header="flowchart LR",
        nodes=ordered,
        node_lines={name: f'  {_node_id("M", name)}["{_label(name)}"]' for name in ordered},
        edges=[
            (e.src, e.dst, f'  {_node_id("M", e.src)} -->|{e.weight}| {_node_id("M", e.dst)}')
            for e in sorted(edges, key=lambda e: -e.weight)
            if e.src in members and e.dst in members
        ],
    )
    return _compile(plan, limit, f"L1-{subsystem.id}", "L1")


_EDGE_ARROW = {
    TypeEdgeKind.EXTENDS: "<|--",
    TypeEdgeKind.IMPLEMENTS: "<|..",
    TypeEdgeKind.FIELD_TYPE: "..>",
    TypeEdgeKind.PARAM_TYPE: "..>",
}


def type_diagram(
    module_id: str, edges: list[TypeEdge], limit: DiagramLimit
) -> Diagram | None:
    """L2. 한 모듈 안 핵심 타입의 관계를 classDiagram으로 그린다.

    엣지가 하나도 없으면 만들지 않는다 — 빈 그림은 사실을 늘리지 않는다(C-SPEC-1).
    """
    in_module = [e for e in edges if e.src_module == module_id]
    if not in_module:
        return None
    fan_in: Counter[str] = Counter()
    for edge in in_module:
        fan_in[edge.dst] += 1
        fan_in.setdefault(edge.src, 0)
    ordered = [name for name, _ in fan_in.most_common()]
    seen: set[tuple[str, str, TypeEdgeKind]] = set()
    edge_lines: list[tuple[str, str, str]] = []
    for edge in in_module:
        key = (edge.src, edge.dst, edge.kind)
        if key in seen:
            continue
        seen.add(key)
        arrow = _EDGE_ARROW.get(edge.kind, "..>")
        src, dst = _ID_SAFE.sub("_", edge.src), _ID_SAFE.sub("_", edge.dst)
        edge_lines.append((edge.src, edge.dst, f"  {dst} {arrow} {src}"))
    plan = _Plan(
        header="classDiagram",
        nodes=ordered,
        node_lines={name: f"  class {_ID_SAFE.sub('_', name)}" for name in ordered},
        edges=edge_lines,
    )
    label = module_id if module_id not in ("", ".") else "root"
    return _compile(plan, limit, f"L2-{label}", "L2")
