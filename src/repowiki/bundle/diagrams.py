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
    CallEdge,
    CrossModuleFlow,
    Diagram,
    DiagramLimit,
    Module,
    ModuleEdge,
    Span,
    Subsystem,
    Symbol,
    SymbolKind,
    TypeEdge,
    TypeEdgeKind,
)

# ast-grep-ignore: regex-on-structure — 어휘: Mermaid 식별자에 허용되는 문자집합 판정이다. 구조가 아니라 문자 하나씩의 치환이라 정규 언어다.
_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")

# 노드에 붙일 수 있는 역할. 여기 없는 이름을 붙이면 사이트가 색을 모른다.
# 색 자체는 이 층의 것이 아니다 — 소스에는 표식만 싣고, 색은 사이트가 테마에 맞춰
# 렌더 시점에 `classDef`로 주입한다. 그래야 다크와 라이트가 둘 다 맞고, 이 표식이
# 소스 문자 상한을 거의 먹지 않으며, classDef가 없는 GitHub에서도 그림이 깨지지 않는다
# (2026-09-09 Chrome 실측: `:::표식`만 있고 classDef가 없어도 정상 렌더).
_ROLES = frozenset({"rwFocus", "rwEntry", "rwTest"})


class _Plan(BaseModel):
    """그릴 것의 계획. 노드는 우선순위 순서이고 엣지는 노드 이름을 가리킨다."""

    header: str
    directive: str = ""
    nodes: list[str]
    node_lines: dict[str, str]
    edges: list[tuple[str, str, str]]
    node_roles: dict[str, str] = {}
    """노드 이름 -> 역할 표식. 색이 아니라 뜻이다(`_ROLES` 참조)."""


def _node_id(prefix: str, raw: str) -> str:
    """Mermaid 노드 id. 문자와 숫자와 밑줄만 남긴다."""
    return f"{prefix}_{_ID_SAFE.sub('_', raw) or 'root'}"


def _label(raw: str) -> str:
    """라벨. 파서가 거부하는 문자를 지운다."""
    cleaned = raw.replace('"', "").replace("[", "(").replace("]", ")")
    return cleaned or "."


# 라벨 글자 상한. 사이트 본문은 1440px 뷰포트에서 823px이고(2026-09-10 실측), 상자 하나의
# 폭은 노드 수가 아니라 가장 긴 라벨이 정한다. kafka의 타입 상세 50장을 재니 라벨을 24자로
# 자르면 전부 본문에 들고(최대 706px) 32자면 하나가 넘친다(826px). 전체 이름은 그 쪽의
# 표에 있다.
_MAX_LABEL = 24
# 1단 구성도 상자의 제목 상한. 제목은 한 줄이라 잎보다 길어도 된다(같은 실측, 최대 983px은
# 제목이 아니라 42자 잎 셋이 만든 폭이었다).
_MAX_AREA_TITLE = 40
# 시퀀스 참가자 이름을 접는 글자 수. 참가자 상자는 이름 폭이 아니라 아래 지시문의 `width`
# 로 고정되므로, 한 줄이 그보다 길면 글자가 상자 밖으로 나가 이웃과 겹친다. 한 줄 11자는
# 상자 100px 에 든다(kafka 60장 실측: 12자면 다섯 장이 넘치고 11자면 없다). 그래도 전체
# 1,324장에서는 `CommandSpec` 처럼 넓은 글자의 11자가 1px 넘쳤다. 열 자다. 낱말이 이보다
# 길면 낱말 안에서도 자른다.
_WRAP_AT = 10
# 시퀀스의 간격. Mermaid 기본(상자 150, 간격 50)으로는 참가자 넷이 918px이라 본문을 넘고,
# 이 값이면 여섯까지 든다(같은 실측: 최대 801px). 소스에 싣는 이유는 사이트와 GitHub 이
# 같은 그림을 보게 하려는 것이다.
_SEQUENCE_DIRECTIVE = (
    '%%{init: {"sequence": {"width": 100, "actorMargin": 16, "messageMargin": 20, '
    '"wrap": true, "mirrorActors": false}}}%%'
)
# ast-grep-ignore: regex-on-structure — 어휘: 낙타 표기 이름을 낱말로 가르는 문자 판정이다.
_WORD = re.compile(r"[A-Z][a-z0-9]*|[a-z0-9]+|[^A-Za-z0-9]+")


def _short(raw: str, limit: int = _MAX_LABEL) -> str:
    """상한 안의 라벨. 넘치면 말줄임표를 붙여 자른 것임을 보인다."""
    text = _label(raw)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _distinct(names: list[str], limit: int = _MAX_LABEL) -> dict[str, str]:
    """이름마다 그림 안에서 서로 다른 짧은 라벨. 순서가 곧 번호라 결정적이다.

    자른 라벨이 같아지면 화살표가 어느 타입을 뜻하는지 읽을 수 없다. 같은 접두어의 중첩
    타입이 그렇다(`InMemoryWindowStore.Inner…` 둘). 그때만 번호를 붙인다.
    """
    labels = {name: _short(name, limit) for name in names}
    seen: dict[str, int] = {}
    for name, label in labels.items():
        seen[label] = seen.get(label, 0) + 1
    counted: dict[str, int] = {}
    for name, label in labels.items():
        if seen[label] > 1:
            counted[label] = counted.get(label, 0) + 1
            labels[name] = f"{label} #{counted[label]}"
    return labels


def _wrap_name(raw: str) -> str:
    """참가자 이름을 접는다. 낱말 경계가 먼저이고, 낱말이 한 줄보다 길면 낱말 안에서도 자른다.

    줄바꿈은 Mermaid 가 아는 `<br/>`다. 그래서 이름에 든 `<`·`>`·`&` 는 다른 글자로 바꾼다.
    그대로 두면 삽입한 태그와 섞여 HTML 로 읽힌다.
    """
    text = _label(raw).replace("<", "‹").replace(">", "›").replace("&", "+")
    pieces: list[str] = []
    for word in _WORD.findall(text) or [text]:
        pieces += [word[i : i + _WRAP_AT] for i in range(0, len(word), _WRAP_AT)]
    lines = [""]
    for word in pieces:
        if lines[-1] and len(lines[-1]) + len(word) > _WRAP_AT:
            lines.append(word)
        else:
            lines[-1] += word
    return "<br/>".join(lines)


def _render(plan: _Plan, shown: list[str]) -> tuple[str, int]:
    visible = set(shown)
    lines = [plan.header] if not plan.directive else [plan.directive, plan.header]
    for name in shown:
        role = plan.node_roles.get(name)
        lines.append(plan.node_lines[name] + (f":::{role}" if role else ""))
    kept = 0
    for src, dst, edge_line in plan.edges:
        if src in visible and dst in visible:
            lines.append(edge_line)
            kept += 1
    return "\n".join(lines), kept


def _compile(plan: _Plan, limit: DiagramLimit, diagram_id: str, level: str) -> Diagram:
    """노드 상한과 소스 문자 상한을 함께 만족할 때까지 노드를 줄인다.

    그림이 스스로 밝히는 단과 그 그림을 깎을 때 쓴 한도는 같아야 한다. 다르면 통과할 수
    없는 그림이 만들어진다. 게이트가 밝힌 단으로 검사하기 때문이다. 실제로 그렇게 어긋나
    있었고(2026-09-09, COLLAB을 L1 한도로 깎아 kafka가 스무 건 위반으로 죽었다) 사람이
    그것을 게이트에서 뒤늦게 읽었다. 여기서 먼저 터뜨린다.
    """
    if limit.level != level:
        raise ValueError(
            f"{diagram_id}는 {level}단이라고 밝히면서 {limit.level}단 한도로 깎였다. "
            "게이트는 밝힌 단으로 검사하므로 이 그림은 통과할 수 없다"
        )
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


def _is_informative(nodes: list[str], edges: list) -> bool:
    """그릴 값이 있는가. 상자 하나에 화살표가 없으면 그림이 아니라 라벨이다.

    모듈이 하나인 저장소에서 서브시스템 그림과 모듈 그림은 상자 하나짜리가 된다. 그것을
    페이지에 실으면 읽는 사람은 무엇을 보라는 것인지 알 수 없다. 그리지 않는 쪽이 옳다.
    """
    return len(nodes) >= 2 or bool(edges)


def subsystem_diagram(
    subsystems: list[Subsystem],
    edges: list[ModuleEdge],
    limit: DiagramLimit,
    entry_modules: frozenset[str] = frozenset(),
) -> Diagram | None:
    """L0. 서브시스템을 노드로, 서브시스템 사이 import 합계를 엣지로 그린다.

    묶음이 하나뿐이고 그 사이 엣지가 없으면 그리지 않는다. `entry_modules`를 주면 그
    모듈을 품은 묶음에 진입점 표식을 붙인다 — 처음 보는 사람이 어디서부터 읽어야 하는지가
    그림에서 먼저 보여야 한다.
    """
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
    lines = [
        (src, dst, f'  {_node_id("S", src)} -->|{weight}| {_node_id("S", dst)}')
        for (src, dst), weight in weights.most_common()
    ]
    if not _is_informative(ordered, lines):
        return None
    entry_subsystems = {owner[m] for m in entry_modules if m in owner}
    # 세로다. 가로로 여섯을 늘어놓으면 kafka 가 1,119px 로 본문(823px)을 넘고, 세로면
    # 459px 이다(2026-09-10 실측).
    plan = _Plan(
        header="flowchart TB",
        nodes=ordered,
        node_lines={name: f'  {_node_id("S", name)}["{_label(name)}"]' for name in ordered},
        edges=lines,
        node_roles={name: "rwEntry" for name in ordered if name in entry_subsystems},
    )
    return _compile(plan, limit, "L0-subsystems", "L0")


def module_diagram(
    subsystem: Subsystem,
    modules: list[Module],
    edges: list[ModuleEdge],
    limit: DiagramLimit,
    root_name: str = "",
    entry_modules: frozenset[str] = frozenset(),
) -> Diagram | None:
    """L1. 한 서브시스템 안의 모듈과 그 사이 엣지를 그린다.

    모듈이 하나뿐이고 그 사이 엣지가 없으면 그리지 않는다. `root_name`을 주면 저장소 뿌리
    모듈의 라벨로 쓴다 — 뿌리 모듈의 id는 `.`이고 그 글자는 사람에게 아무 뜻이 없다.
    """
    members = set(subsystem.modules)
    sizes = {m.id: m.main_file_count for m in modules if m.id in members}
    ordered = [name for name, _ in sorted(sizes.items(), key=lambda item: (-item[1], item[0]))]
    lines = [
        (e.src, e.dst, f'  {_node_id("M", e.src)} -->|{e.weight}| {_node_id("M", e.dst)}')
        for e in sorted(edges, key=lambda e: -e.weight)
        if e.src in members and e.dst in members
    ]
    if not _is_informative(ordered, lines):
        return None
    plan = _Plan(
        header="flowchart LR",
        nodes=ordered,
        node_lines={
            name: f'  {_node_id("M", name)}["{_label(_module_label(name, root_name, subsystem.id))}"]'
            for name in ordered
        },
        edges=lines,
        node_roles={name: "rwEntry" for name in ordered if name in entry_modules},
    )
    return _compile(plan, limit, f"L1-{subsystem.id}", "L1")


def _module_label(module_id: str, root_name: str, subsystem_id: str = "") -> str:
    """모듈의 라벨. 저장소 뿌리는 id가 `.`이라 그대로 쓰면 점 하나가 그려진다.

    묶음 안의 그림에서 묶음 이름은 접두어일 뿐이다. `connect/basic-auth-extension` 아홉을
    그리면 그 접두어가 폭의 셋 중 하나를 먹어 1,221px 이 되고, 떼면 765px 이다
    (kafka 2026-09-10 실측). 쪽 제목이 그 묶음이므로 잃는 정보는 없다.
    """
    if module_id in ("", "."):
        return root_name or module_id
    prefix = f"{subsystem_id}/"
    return module_id[len(prefix) :] if subsystem_id and module_id.startswith(prefix) else module_id


def _identity(declaration: Span | None, path: str | None, name: str) -> str:
    """노드의 정체. 선언 위치가 있으면 그것이고, 없으면 경로, 그것도 없으면 이름이다.

    한 파일에 같은 이름의 중첩 선언이 여럿일 수 있어 경로만으로는 부족하다.
    """
    if declaration is not None:
        return f"{declaration.path}#{declaration.start_line}"
    return path or f"name:{name}"


# 관계 종류마다의 화살표와, 그 화살표를 적을 때의 (앞, 뒤) 순서. Mermaid 의 `A <|-- B` 는
# B 가 A 를 상속하고, `A ..> B` 는 A 가 B 에 기댄다(화살촉이 기대는 쪽을 가리킨다). 엣지의
# src 가 dst 를 상속하거나 dst 를 필드·인자로 쓰므로 상속은 `dst <|-- src`, 의존은
# `src ..> dst` 다. 의존을 `dst ..> src` 로 적으면 그림이 "설정이 Admin 에 기댄다"고
# 말한다 — 실제로 그렇게 적혀 있었다(kafka `TYPE-Admin`, 2026-09-10).
_EDGE_ARROW = {
    TypeEdgeKind.EXTENDS: ("<|--", "dst", "src"),
    TypeEdgeKind.IMPLEMENTS: ("<|..", "dst", "src"),
    TypeEdgeKind.FIELD_TYPE: ("..>", "src", "dst"),
    TypeEdgeKind.PARAM_TYPE: ("..>", "src", "dst"),
}
_DEFAULT_ARROW = ("..>", "src", "dst")
# 같은 관계를 반대편에서 적은 화살표. `A <|-- B` 와 `B --|> A` 는 같은 뜻이다.
_EDGE_ARROW_FLIPPED = {"<|--": "--|>", "<|..": "..|>", "..>": "<.."}


def _relation(edge: TypeEdge, src_id: str, dst_id: str) -> tuple[str, str, str]:
    """관계 한 줄의 (앞 노드, 화살표, 뒤 노드). 뜻이 맞는 순서다."""
    arrow, first, _ = _EDGE_ARROW.get(edge.kind, _DEFAULT_ARROW)
    ids = {"src": src_id, "dst": dst_id}
    return ids[first], arrow, ids["dst" if first == "src" else "src"]


_MAX_HOPS = 12
# 클래스 상자에 넣을 멤버 상한. 이보다 많으면 상자가 그림을 밀어낸다.
_MAX_MEMBERS = 14
# 1단 구성도의 한 상자에 넣을 대표 타입 수. 상자 안은 가로 한 줄이라 이 수가 곧 상자 폭이다.
# 다섯이면 상자 하나가 1,000px 을 넘고, 셋이면 본문에 든다(kafka 2026-09-10 실측).
_MAX_AREA_MEMBERS = 3


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
# 막대그래프의 크기. 폭은 본문(823px)보다 좁게 못 박는다. xychart 는 다른 그림과 달리
# 내용이 아니라 이 값이 폭을 정한다.
_CHART_WIDTH = 800
_CHART_HEIGHT = 320
# ast-grep-ignore: regex-on-structure — 어휘: xychart 문자열에 못 들어가는 문자의 판정이다.
_CHART_UNSAFE = re.compile(r'["\[\]\\\n\r]')


def _chart_text(raw: str) -> str:
    """xychart 의 따옴표 문자열. 따옴표·대괄호·역슬래시·줄바꿈이 있으면 문법이 깨진다."""
    return " ".join(_CHART_UNSAFE.sub(" ", raw).split()) or "."


def history_diagram(periods: list[dict], limit: DiagramLimit) -> Diagram | None:
    """이력을 분기별 커밋 수 막대그래프로 그린다.

    사람은 이 그림에서 "언제 많이 움직였는가"를 먼저 본다. 기간이 없으면 그리지 않는다.

    timeline 이 아니다. timeline 은 기간마다 한 칸을 가로로 늘어놓아 기간당 200px 이고,
    kafka 아홉 분기가 2,190px 로 본문의 2.7배였다(2026-09-10 실측). 본문에 드는 것은
    세 분기뿐이라 그림이 말할 것이 없다. 분기마다 가장 많이 바뀐 파일은 그림이 아니라
    이력 쪽의 표(`periods`)에 있다.
    """
    if not periods:
        return None
    shown = periods[-limit.max_nodes :]
    labels = ", ".join(f'"{_chart_text(str(period["label"]))}"' for period in shown)
    # 음수는 없는 값이다. 축은 0 에서 시작하고 위끝은 최소 1 이어야 한다 — 전부 0 이면
    # `0 --> 0` 이 되어 축이 무너진다.
    counts = [max(0, int(period["commits"])) for period in shown]
    lines = [
        f'%%{{init: {{"xyChart": {{"width": {_CHART_WIDTH}, "height": {_CHART_HEIGHT}}}}}}}%%',
        "xychart-beta",
        '  title "분기별 커밋"',
        f"  x-axis [{labels}]",
        f'  y-axis "커밋" 0 --> {max(counts, default=0) or 1}',
        f"  bar [{', '.join(str(count) for count in counts)}]",
    ]
    source = "\n".join(lines)
    reasons = []
    if len(periods) > limit.max_nodes:
        reasons.append(f"기간 {len(periods)}개가 상한 {limit.max_nodes}개를 넘어 최근만 그렸다")
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
    lines = [_SEQUENCE_DIRECTIVE, "sequenceDiagram"]
    for name in participants:
        lines.append(f'  participant {short[name]} as {_wrap_name(name)}')
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
        first, arrow, second = _relation(edge, short[src_key], short[dst_key])
        edge_lines.append((src_key, dst_key, f"  {first} {arrow} {second}"))
    # 왼쪽에서 오른쪽이다. 위에서 아래로 그리면 같은 층의 타입이 한 줄로 늘어서 노드 여덟에
    # 1,460px 이고, 가로 방향이면 스물에 791px 이다(kafka 2026-09-10 실측). 대신 키가
    # 자라므로 상한은 높이로 정했다(12에서 최대 1,574px).
    plan = _Plan(
        header="classDiagram\n  direction LR",
        nodes=ordered,
        node_lines={
            key: f'  class {short[key]}["{_label(label_of[key])}"]' for key in ordered
        },
        edges=edge_lines,
    )
    label = module_id if module_id not in ("", ".") else "root"
    return _compile(plan, limit, f"L2-{label}", "L2")


def _participants(type_name: str, edges: list[CallEdge]) -> list[str]:
    """시퀀스의 참가자. 처음 나오는 순서를 지킨다 — 그것이 소스의 순서다."""
    found = [type_name]
    for edge in edges:
        if edge.dst_type not in found:
            found.append(edge.dst_type)
    return found


def _fit(
    render, units: list, limit: DiagramLimit, reasons: list[str]
) -> tuple[str, int]:
    """단위를 줄여 가며 소스 상한에 맞춘다. 항상 완결된 소스를 낸다.

    줄 단위로 꼬리를 자르면 안 된다. 클래스 상자의 닫는 괄호가 잘려 문법이 깨지거나,
    메시지가 하나도 없는 시퀀스가 "엣지 1개"라고 주장하게 된다. 자르는 단위는 그림의
    의미 단위이고, 자른 뒤에는 다시 렌더한다.
    """
    kept = list(units)
    source = render(kept)
    while len(source) > limit.max_source_chars and kept:
        kept.pop()
        source = render(kept)
        reasons.append("소스 상한을 맞추려고 줄였다")
    return source, len(kept)


def member_sequence(
    type_name: str,
    member_name: str,
    call_edges: list[CallEdge],
    limit: DiagramLimit,
) -> Diagram | None:
    """멤버 하나가 부르는 것을 소스 순서대로 sequenceDiagram으로 그린다.

    사람이 "이 메서드가 무슨 일을 하는가"를 읽을 때 먼저 보는 것이 호출 순서다. 참가자는
    타입이고 메시지는 부르는 멤버 이름이며, 순서는 소스의 줄 순서다 — 실행 순서가 아니라
    적힌 순서라는 점이 이 그림의 한계이자 정확한 주장이다.

    부르는 것이 없거나 자기 자신만 부르면 그리지 않는다. 그림이 사실을 늘리지 않는다.
    """
    mine = sorted(
        (e for e in call_edges if e.src_type == type_name and e.src_member == member_name),
        key=lambda e: (e.span.start_line, e.dst_type, e.dst_member),
    )
    if not mine:
        return None
    participants = _participants(type_name, mine)
    if len(participants) < 2:
        return None
    participants = participants[: limit.max_nodes]
    visible = set(participants)
    short = {name: f"P{position}" for position, name in enumerate(participants)}

    messages = [edge for edge in mine[:_MAX_HOPS] if edge.dst_type in visible]
    if not messages:
        return None

    def render(kept: list[CallEdge]) -> str:
        lines = [_SEQUENCE_DIRECTIVE, "sequenceDiagram"]
        lines += [f"  participant {short[name]} as {_wrap_name(name)}" for name in participants]
        lines.append(f"  Note over {short[type_name]}: {_label(member_name)}")
        for edge in kept:
            arrow = "->>" if edge.dst_type != type_name else "-->>"
            lines.append(
                f"  {short[type_name]}{arrow}{short[edge.dst_type]}: {_label(edge.dst_member)}"
            )
        return "\n".join(lines)

    reasons: list[str] = []
    if len(mine) > _MAX_HOPS:
        reasons.append(f"호출 {len(mine)}건이 상한 {_MAX_HOPS}건을 넘어 앞쪽만 그렸다")
    source, kept = _fit(render, messages, limit, reasons)
    if kept == 0:
        return None
    return Diagram(
        id=f"SEQ-{type_name}.{member_name}",
        level="SEQ",
        source=source,
        node_count=len(participants),
        edge_count=kept,
        degraded_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def collaboration_diagram(
    type_name: str,
    call_edges: list[CallEdge],
    limit: DiagramLimit,
    test_types: frozenset[str] = frozenset(),
) -> Diagram | None:
    """한 타입이 어느 타입에 얼마나 기대는지 flowchart로 그린다.

    엣지의 굵기 대신 라벨에 호출 수를 적는다. Mermaid는 굵기를 소스로 정하지 못한다.
    """
    outgoing = [e for e in call_edges if e.src_type == type_name and e.dst_type != type_name]
    if not outgoing:
        return None
    weight: Counter[str] = Counter(e.dst_type for e in outgoing)
    ordered = [type_name] + [name for name, _ in weight.most_common()]
    short = {name: _node_id("C", name) for name in ordered}
    # 라벨은 자른다. 두 층뿐이라 폭은 중심과 가장 긴 이웃의 이름이 정하는데,
    # `MeteredTimestampedKeyValueStoreWithHeaders` 는 그것만으로 824px 이었다(2026-09-10).
    shown_label = _distinct(ordered)
    node_lines = {name: f'  {short[name]}["{shown_label[name]}"]' for name in ordered}
    edges = [
        (type_name, name, f"  {short[type_name]} -->|{count}| {short[name]}")
        for name, count in weight.most_common()
    ]
    roles = {type_name: "rwFocus"}
    roles.update({name: "rwTest" for name in ordered[1:] if name in test_types})
    plan = _Plan(
        header="flowchart LR",
        nodes=ordered,
        node_lines=node_lines,
        edges=edges,
        node_roles=roles,
    )
    return _compile(plan, limit, f"COLLAB-{type_name}", "COLLAB")


def _detail_edges(
    type_name: str,
    related: list[TypeEdge],
    limited: dict[str, str],
    short: dict[str, str],
) -> list[str]:
    """상세 그림의 관계 줄. 같은 줄은 한 번만 그린다.

    관계 종류가 달라도 화살표가 같으면 줄이 같아진다. 같은 줄을 두 번 그리면 사람은 관계가
    둘이라고 읽는다.

    줄마다 이웃이 먼저 온다. dagre 는 줄의 첫 노드를 앞 층에 두므로, 이웃을 늘 먼저 적으면
    이웃 전부가 중심 상자의 한쪽에 서고 그림은 두 층이다. 관계 방향에 따라 양쪽에 서게 두면
    세 층이 되어 같은 그림이 939px 로 본문을 넘겼다(kafka 2026-09-10 실측, 한쪽이면 706px).
    """
    drawn: list[str] = []
    centre = _safe_class(type_name)
    for edge in related:
        src_key = _identity(None, edge.src_path, edge.src)
        dst_key = _identity(None, edge.dst_path, edge.dst)
        other = dst_key if edge.src == type_name else src_key
        if other not in limited:
            continue
        first, arrow, second = _relation(
            edge,
            centre if edge.src == type_name else short[src_key],
            centre if edge.dst == type_name else short[dst_key],
        )
        if first == centre:
            first, arrow, second = second, _EDGE_ARROW_FLIPPED[arrow], first
        line = f"  {first} {arrow} {second}"
        if line not in drawn:
            drawn.append(line)
    return drawn


def type_detail_diagram(
    type_name: str,
    members: list[Symbol],
    edges: list[TypeEdge],
    limit: DiagramLimit,
    labels: dict[str, str] | None = None,
) -> Diagram | None:
    """한 타입의 멤버와 이웃을 classDiagram으로 그린다.

    빈 상자만 있는 클래스 다이어그램은 이름 목록과 다르지 않다. 멤버를 넣어야 사람이
    "이 타입이 무엇을 할 수 있는가"를 그림에서 읽는다.

    모양은 가로 두 층이다. 위에서 아래로 그리면 이웃이 한 줄로 늘어서 노드 25에 5,187px
    이 되고, 사이트는 그것을 본문 폭으로 줄여 글자가 21% 크기가 된다(kafka `Admin`,
    2026-09-10 실측). 이웃을 왼쪽 한 층에 세우고 라벨을 `_MAX_LABEL` 로 자르면 노드 16
    까지 전부 본문에 든다.

    이웃의 정체는 선언 파일이다. 이름만으로 묶으면 `Option.Builder`와 `TextStyle.Builder`가
    한 상자가 되고, 서로 다른 두 관계가 같은 화살표로 겹쳐 그려진다.
    """
    mine = [s for s in members if s.parent == type_name]
    related = [e for e in edges if e.src == type_name or e.dst == type_name]
    if not mine and not related:
        return None

    label_of = labels or {}
    neighbours: dict[str, str] = {}
    for edge in related:
        for name, path in ((edge.src, edge.src_path), (edge.dst, edge.dst_path)):
            if name == type_name:
                continue
            key = _identity(None, path, name)
            neighbours.setdefault(key, label_of.get(f"{path}#{name}", name))
    limited = dict(list(neighbours.items())[: max(0, limit.max_nodes - 1)])
    shown_label = _distinct(list(limited.values()))
    short = {key: f"N{position}" for position, key in enumerate(limited)}
    shown_members = list({(s.kind, s.name): s for s in mine}.values())
    drawn = _detail_edges(type_name, related, limited, short)

    def render(kept: list[str]) -> str:
        lines = ["classDiagram", "  direction LR", *_member_box(type_name, shown_members)]
        lines += [f'  class {short[key]}["{shown_label[label]}"]' for key, label in limited.items()]
        lines += kept
        return "\n".join(lines)

    reasons: list[str] = []
    if len(shown_members) > _MAX_MEMBERS:
        reasons.append(f"멤버 {len(shown_members)}개가 상한 {_MAX_MEMBERS}개를 넘어 앞쪽만 그렸다")
    if len(neighbours) > len(limited):
        reasons.append(f"이웃 {len(neighbours)}개가 상한 {limit.max_nodes - 1}개를 넘었다")
    source, kept = _fit(render, drawn, limit, reasons)
    return Diagram(
        id=f"TYPE-{type_name}",
        level="TYPE",
        source=source,
        node_count=1 + len(limited),
        edge_count=kept,
        degraded_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def _member_box(type_name: str, members: list[Symbol]) -> list[str]:
    """클래스 상자 하나. 필드는 `-`, 호출 가능한 것은 `+`로 적는다.

    같은 이름은 한 줄이다. 오버로드는 심볼이 여럿이지만 사람이 상자에서 읽는 것은 "무엇을
    할 수 있는가"이고, kafka `Admin`은 오버로드 때문에 14줄에 이름이 일곱뿐이었다(2026-09-10).
    """
    lines = [f"  class {_safe_class(type_name)} {{"]
    unique = {(s.kind, s.name): s for s in members}.values()
    for symbol in sorted(unique, key=lambda s: (s.kind.value, s.name))[:_MAX_MEMBERS]:
        marker = "-" if symbol.kind == SymbolKind.FIELD else "+"
        suffix = "" if symbol.kind == SymbolKind.FIELD else "()"
        lines.append(f"    {marker}{_short(symbol.name)}{suffix}")
    lines.append("  }")
    return lines


def _safe_class(raw: str) -> str:
    """classDiagram의 클래스 이름. 이 문법은 따옴표 라벨을 클래스 본문과 함께 쓰지 못한다."""
    return _ID_SAFE.sub("_", raw) or "T"


def area_diagram(
    title: str,
    children: list[tuple[str, list[str]]],
    edges: list[CallEdge],
    limit: DiagramLimit,
) -> Diagram | None:
    """1단 쪽의 구성도. 자식 묶음을 상자로 두고 그 사이의 호출을 잇는다.

    자식마다 subgraph 를 만들고 그 안에 대표 타입을 둔다. 사람이 이 그림 하나로 "이 자리가
    무엇으로 나뉘고 그 조각들이 서로 부르는가"를 읽는다.

    자식이 하나뿐이거나 그 사이에 호출이 없으면 그리지 않는다. 상자만 늘어놓은 그림은
    사이드바가 이미 하는 말이다.
    """
    if len(children) < 2:
        return None
    weight = _area_weights(children, edges)
    if not weight:
        return None

    shown = [group for group, _ in children][: limit.max_nodes]
    visible = set(shown)
    # 자리 번호를 id 로 쓴다. 이름을 id 로 만들면 한 줄이 100자를 넘어 소스 상한을 그림이
    # 아니라 식별자가 다 쓴다(kafka 실측: 상자만 2,888자로 상한 2,000자를 넘겼다).
    short = {group: f"A{position}" for position, group in enumerate(shown)}
    # 상자는 세로로 한 줄에 하나다. 레이아웃은 서로 부르지 않는 상자를 같은 층에 나란히
    # 놓으므로 그냥 두면 상자 넷이 한 줄에 서서 1,265px 이 된다. 보이지 않는 사슬
    # (`~~~`)로 층을 강제하면 가장 넓은 상자 하나의 폭이 그림의 폭이다(kafka 12장 실측:
    # 최대 983px 은 42자 잎이 만든 것이고 잎을 자르면 든다).
    lines = [line for line in (_directive_for(limit), "flowchart TB") if line]
    lines += _area_boxes(children, visible, short)
    if len(shown) > 1:
        lines.append("  " + " ~~~ ".join(short[group] for group in shown))
    drawn = [
        f"  {short[src]} -->|{count}| {short[dst]}"
        for (src, dst), count in weight.most_common()
        if src in visible and dst in visible
    ]
    if not drawn:
        return None

    def render(kept: list[str]) -> str:
        return "\n".join([*lines, *kept])

    reasons: list[str] = []
    if len(children) > len(shown):
        reasons.append(f"자식 {len(children)}개가 상한 {limit.max_nodes}개를 넘었다")
    source, kept = _fit(render, drawn, limit, reasons)
    if kept == 0:
        return None
    return Diagram(
        id=f"AREA-{title}",
        level="AREA",
        source=source,
        node_count=len(shown),
        edge_count=kept,
        degraded_reason="; ".join(dict.fromkeys(reasons)) or None,
    )


def _area_weights(
    children: list[tuple[str, list[str]]], edges: list[CallEdge]
) -> "Counter[tuple[str, str]]":
    """자식 사이의 호출 수. 같은 자식 안의 호출은 이 그림이 말할 것이 아니다."""
    owner: dict[str, str] = {}
    for group, members in children:
        for name in members:
            owner.setdefault(name, group)
    weight: Counter[tuple[str, str]] = Counter()
    for edge in edges:
        src, dst = owner.get(edge.src_type), owner.get(edge.dst_type)
        if src is not None and dst is not None and src != dst:
            weight[(src, dst)] += 1
    return weight


def _area_boxes(
    children: list[tuple[str, list[str]]], visible: set[str], short: dict[str, str]
) -> list[str]:
    """자식마다 상자 하나. 안에 대표 타입을 몇 개 둔다."""
    lines: list[str] = []
    for group, members in children:
        if group not in visible:
            continue
        lines.append(f'  subgraph {short[group]}["{_short(group, _MAX_AREA_TITLE)}"]')
        lines.append("    direction LR")
        lines += [
            f'    {short[group]}_{position}["{_short(name)}"]'
            for position, name in enumerate(members[:_MAX_AREA_MEMBERS])
        ]
        lines.append("  end")
    return lines


def _directive_for(limit: DiagramLimit) -> str:
    """레이아웃 지시문. `dagre`는 Mermaid 내장이라 적지 않는다."""
    if limit.layout == "dagre":
        return ""
    return f'%%{{init: {{"layout": "{limit.layout}"}}}}%%'
