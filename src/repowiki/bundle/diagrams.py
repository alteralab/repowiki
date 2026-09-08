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
    CrossModuleFlow,
    Diagram,
    DiagramLimit,
    Module,
    ModuleEdge,
    Span,
    Subsystem,
    TypeEdge,
    TypeEdgeKind,
)

# ast-grep-ignore: regex-on-structure — 어휘: Mermaid 식별자에 허용되는 문자집합 판정이다. 구조가 아니라 문자 하나씩의 치환이라 정규 언어다.
_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


class _Plan(BaseModel):
    """그릴 것의 계획. 노드는 우선순위 순서이고 엣지는 노드 이름을 가리킨다."""

    header: str
    directive: str = ""
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
    lines = [plan.header] if not plan.directive else [plan.directive, plan.header]
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
    if limit.layout != "dagre":
        plan = plan.model_copy(
            update={"directive": f'%%{{init: {{"layout": "{limit.layout}"}}}}%%'}
        )
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
    if len(source) > limit.max_source_chars:
        # 노드 하나로도 상한을 못 맞추는 경우다. 상한을 넘는 다이어그램을 내보내면
        # 게이트가 그다음에 잡을 뿐이라, 여기서 표로 강등한다(사다리 마지막 단).
        source, edge_count = _render(plan, []), 0
        source = source[0] if isinstance(source, tuple) else source
        reasons.append(
            f"노드 하나의 라벨만으로도 {limit.max_source_chars}자를 넘어 다이어그램을 비웠다"
        )
        shown = []
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


def _identity(declaration: Span | None, path: str | None, name: str) -> str:
    """노드의 정체. 선언 위치가 있으면 그것이고, 없으면 경로, 그것도 없으면 이름이다.

    한 파일에 같은 이름의 중첩 선언이 여럿일 수 있어 경로만으로는 부족하다.
    """
    if declaration is not None:
        return f"{declaration.path}#{declaration.start_line}"
    return path or f"name:{name}"


_EDGE_ARROW = {
    TypeEdgeKind.EXTENDS: "<|--",
    TypeEdgeKind.IMPLEMENTS: "<|..",
    TypeEdgeKind.FIELD_TYPE: "..>",
    TypeEdgeKind.PARAM_TYPE: "..>",
}


_MAX_HOPS = 12


def entity_diagram(entities: list[dict], relations: list[dict], limit: DiagramLimit) -> Diagram | None:
    """데이터 모델을 erDiagram으로 그린다.

    엔티티는 저장소가 스스로 테이블이라고 적어 둔 타입이고, 관계는 외래 키와 관계
    애노테이션이다. 엔티티가 없으면 그리지 않는다 — 없는 모델을 지어내지 않는다.
    """
    if not entities:
        return None
    ordered = sorted(entities, key=lambda e: (-len(e.get("attributes", [])), e["table"]))
    shown = ordered[: limit.max_nodes]
    visible = {e["table"] for e in shown}
    by_type = {e["type_name"]: e["table"] for e in shown}

    lines = ["erDiagram"]
    kept = 0
    for relation in relations:
        source = by_type.get(relation["src"])
        target = relation["dst_table"]
        if source is None or target not in visible or source == target:
            continue
        lines.append(f'  {_ID_SAFE.sub("_", target)} ||--o{{ {_ID_SAFE.sub("_", source)} : "{relation["kind"]}"')
        kept += 1
    for entity in shown:
        name = _ID_SAFE.sub("_", entity["table"])
        lines.append(f"  {name} {{")
        for attribute in entity.get("attributes", [])[:8]:
            lines.append(f'    field {_ID_SAFE.sub("_", attribute["name"])}')
        lines.append("  }")

    source_text = "\n".join(lines)
    reasons = []
    if len(entities) > limit.max_nodes:
        reasons.append(f"엔티티 {len(entities)}개가 상한 {limit.max_nodes}개를 넘어 속성이 많은 순으로 그렸다")
    while len(source_text) > limit.max_source_chars and len(shown) > 1:
        shown = shown[:-1]
        return entity_diagram(shown, relations, limit)
    return Diagram(
        id="ER-entities",
        level="ER",
        source=source_text,
        node_count=len(shown),
        edge_count=kept,
        degraded_reason="; ".join(reasons) or None,
    )
_MAX_PERIODS = 12


def history_diagram(periods: list[dict], limit: DiagramLimit) -> Diagram | None:
    """이력을 timeline으로 그린다.

    분기마다 커밋 수와 그 분기에 가장 많이 바뀐 파일 이름을 적는다. 사람은 이 그림에서
    "최근에 어디가 움직였는가"를 먼저 본다. 기간이 없으면 그리지 않는다.
    """
    if not periods:
        return None
    shown = periods[-_MAX_PERIODS:]
    lines = ["timeline", "  title 분기별 변경"]
    for period in shown:
        name = period.get("top_path", "").split("/")[-1]
        detail = f"커밋 {period['commits']}건"
        if name:
            detail += f" : 최다 {_label(name)} {period['top_revisions']}회"
        lines.append(f"  {period['label']} : {detail}")
    source = "\n".join(lines)
    reasons = []
    if len(periods) > _MAX_PERIODS:
        reasons.append(f"기간 {len(periods)}개가 상한 {_MAX_PERIODS}개를 넘어 최근만 그렸다")
    while len(source) > limit.max_source_chars and len(lines) > 3:
        lines.pop(2)
        source = "\n".join(lines)
        reasons.append("소스 상한을 맞추려고 앞 기간을 줄였다")
    return Diagram(
        id="TIME-history",
        level="TIME",
        source=source,
        node_count=len(shown),
        edge_count=0,
        degraded_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def flow_diagram(flow: CrossModuleFlow, limit: DiagramLimit) -> Diagram | None:
    """흐름 하나를 sequenceDiagram으로 그린다.

    참가자는 모듈이고 메시지는 홉이다. 홉의 라벨은 지나가는 타입과 관계 종류이며,
    사람은 이 그림에서 "요청이 어느 모듈을 거치는가"를 먼저 본다.

    홉이 없거나 모듈이 하나뿐인 흐름은 그리지 않는다. 보여 줄 경계가 없기 때문이다.
    """
    if not flow.hops or len(flow.modules) < 2:
        return None
    participants = list(dict.fromkeys(flow.modules))[: limit.max_nodes]
    visible = set(participants)
    short = {name: f"P{position}" for position, name in enumerate(participants)}
    lines = ["sequenceDiagram"]
    for name in participants:
        lines.append(f'  participant {short[name]} as {_label(name)}')
    lines.append(f'  Note over {short[participants[0]]}: {_label(flow.entry.kind.value)} {_label(flow.entry.name)[:30]}')
    kept = 0
    for hop in flow.hops[:_MAX_HOPS]:
        if hop.src_module not in visible or hop.dst_module not in visible:
            continue
        arrow = "->>" if hop.src_module != hop.dst_module else "-->>"
        lines.append(
            f"  {short[hop.src_module]}{arrow}{short[hop.dst_module]}:"
            f" {_label(hop.symbol)} ({hop.kind.value})"
        )
        kept += 1
    if kept == 0:
        return None
    source = "\n".join(lines)
    reasons = []
    if len(flow.hops) > _MAX_HOPS:
        reasons.append(f"홉 {len(flow.hops)}개가 상한 {_MAX_HOPS}개를 넘어 앞쪽만 그렸다")
    if len(flow.modules) > limit.max_nodes:
        reasons.append(f"모듈 {len(flow.modules)}개가 상한 {limit.max_nodes}개를 넘었다")
    while len(source) > limit.max_source_chars and len(lines) > 3:
        lines.pop()
        source = "\n".join(lines)
        reasons.append("소스 상한을 맞추려고 홉을 줄였다")
    return Diagram(
        id=f"FLOW-{flow.id}",
        level="FLOW",
        source=source,
        node_count=len(participants),
        edge_count=kept,
        degraded_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def type_diagram(
    module_id: str, edges: list[TypeEdge], limit: DiagramLimit
) -> Diagram | None:
    """L2. 한 모듈 안 핵심 타입의 관계를 classDiagram으로 그린다.

    엣지가 하나도 없으면 만들지 않는다 — 빈 그림은 사실을 늘리지 않는다(C-SPEC-1).
    """
    in_module = [e for e in edges if e.src_module == module_id]
    if not in_module:
        return None
    # 노드의 정체는 선언 파일이고 이름은 라벨이다. 같은 이름의 다른 타입을 한 노드로
    # 합치면 다이어그램이 없는 관계를 그린다.
    label_of: dict[str, str] = {}
    fan_in: Counter[str] = Counter()
    for edge in in_module:
        src_key = _identity(edge.src_declaration, edge.src_path, edge.src)
        dst_key = _identity(edge.dst_declaration, edge.dst_path, edge.dst)
        label_of.setdefault(src_key, edge.src)
        label_of.setdefault(dst_key, edge.dst)
        fan_in[dst_key] += 1
        fan_in.setdefault(src_key, 0)
    ordered = [key for key, _ in fan_in.most_common()]
    # 노드 id는 짧은 자리 번호다. 경로를 id로 쓰면 소스 문자 예산을 다 먹는다.
    # 순서는 결정적이므로 같은 입력에서 같은 번호가 붙는다.
    short = {key: f"T{position}" for position, key in enumerate(ordered)}
    seen: set[tuple[str, str, TypeEdgeKind]] = set()
    edge_lines: list[tuple[str, str, str]] = []
    for edge in in_module:
        src_key = _identity(edge.src_declaration, edge.src_path, edge.src)
        dst_key = _identity(edge.dst_declaration, edge.dst_path, edge.dst)
        key = (src_key, dst_key, edge.kind)
        if key in seen:
            continue
        seen.add(key)
        arrow = _EDGE_ARROW.get(edge.kind, "..>")
        edge_lines.append((src_key, dst_key, f"  {short[dst_key]} {arrow} {short[src_key]}"))
    plan = _Plan(
        header="classDiagram",
        nodes=ordered,
        node_lines={
            key: f'  class {short[key]}["{_label(label_of[key])}"]' for key in ordered
        },
        edges=edge_lines,
    )
    label = module_id if module_id not in ("", ".") else "root"
    return _compile(plan, limit, f"L2-{label}", "L2")
