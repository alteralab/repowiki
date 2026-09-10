"""도식의 모양. 값은 kafka 위키를 실제 Chrome 으로 잰 데서 나왔다(2026-09-10).

사이트 본문은 823px 인데 사다리는 줄어든 뒤의 상자를 재고 있었다. 그래서 `TYPE` 이 25노드를
한 줄로 늘어놓아 5,187px 이 되어도 통과했고, 사람이 글자를 못 읽었다. 여기의 단언은 그때
바꾼 모양이 다시 세로 한 줄로 돌아가지 않게 지킨다. 실제 폭은 `evals/ladder` 가 잰다.
"""

from __future__ import annotations

from repowiki.bundle import diagrams
from repowiki.models import (
    CallEdge,
    DiagramLimit,
    Module,
    ModuleEdge,
    Span,
    Subsystem,
    SubsystemSource,
    Symbol,
    SymbolKind,
    TypeEdge,
    TypeEdgeKind,
)


def _limit(level: str, max_nodes: int = 12) -> DiagramLimit:
    return DiagramLimit(
        level=level, max_nodes=max_nodes, max_source_chars=2400, max_blocks_per_page=50
    )


def _span(path: str, line: int = 1) -> Span:
    return Span(path=path, start_line=line, end_line=line + 5)


def _type_edge(src: str, dst: str, kind: TypeEdgeKind) -> TypeEdge:
    return TypeEdge(
        src=src,
        dst=dst,
        kind=kind,
        span=_span(f"m/{src}.java"),
        src_module="m",
        dst_module="m",
        src_path=f"m/{src}.java",
        dst_path=f"m/{dst}.java",
    )


def _symbol(name: str, parent: str, kind: SymbolKind = SymbolKind.METHOD) -> Symbol:
    return Symbol(
        kind=kind, name=name, span=_span(f"m/{parent}.java"), module="m", language="java", parent=parent
    )


def test_type_detail_puts_every_neighbour_on_one_side() -> None:
    """이웃이 중심의 양쪽에 서면 층이 셋이고, 한쪽이면 둘이다. 폭은 층 수가 정한다."""
    edges = [
        _type_edge("Admin", "Base", TypeEdgeKind.EXTENDS),  # Admin 이 Base 를 상속
        _type_edge("Admin", "Config", TypeEdgeKind.FIELD_TYPE),  # Admin 이 Config 를 가짐
        _type_edge("Client", "Admin", TypeEdgeKind.FIELD_TYPE),  # Client 가 Admin 을 가짐
    ]
    diagram = diagrams.type_detail_diagram("Admin", [], edges, _limit("TYPE"))
    assert diagram is not None
    relation_lines = [line for line in diagram.source.splitlines() if " Admin" in line and "class" not in line]
    assert len(relation_lines) == 3
    # 모든 관계 줄이 이웃으로 시작하고 중심으로 끝난다. 화살표는 뒤집어 뜻을 지킨다.
    assert all(line.strip().endswith(" Admin") for line in relation_lines)
    assert "  direction LR" in diagram.source.splitlines()[1]
    # 뜻은 지킨다. Admin 이 Base 를 상속하고(`Base <|-- Admin`), Admin 이 Config 에 기대며
    # (`Config <.. Admin`), Client 가 Admin 에 기댄다(`Client ..> Admin`).
    assert "  N0 <|-- Admin" in relation_lines
    assert "  N1 <.. Admin" in relation_lines
    assert "  N2 ..> Admin" in relation_lines


def test_module_type_diagram_points_dependency_arrows_at_the_dependency() -> None:
    """`A ..> B` 는 A 가 B 에 기댄다는 뜻이다. 거꾸로 적으면 그림이 거짓을 말한다."""
    edges = [
        _type_edge("Admin", "Config", TypeEdgeKind.FIELD_TYPE),
        _type_edge("Admin", "Base", TypeEdgeKind.EXTENDS),
    ]
    diagram = diagrams.type_diagram("m", edges, _limit("L2"))
    assert diagram is not None
    ids = {
        label: line.split()[1].split("[")[0]
        for line in diagram.source.splitlines()
        for label in ("Admin", "Config", "Base")
        if f'["{label}"]' in line
    }
    assert f"  {ids['Admin']} ..> {ids['Config']}" in diagram.source
    assert f"  {ids['Base']} <|-- {ids['Admin']}" in diagram.source


def test_type_detail_truncates_long_labels_and_dedupes_overloads() -> None:
    """상자 폭은 가장 긴 라벨이 정한다. 오버로드는 상자에서 한 줄이다."""
    long_name = "InMemoryWindowStoreIteratorWrapperFactory"
    members = [_symbol("abortTransaction", "Admin"), _symbol("abortTransaction", "Admin")]
    edges = [_type_edge("Admin", long_name, TypeEdgeKind.FIELD_TYPE)]
    diagram = diagrams.type_detail_diagram("Admin", members, edges, _limit("TYPE"))
    assert diagram is not None
    assert long_name not in diagram.source
    assert long_name[: diagrams._MAX_LABEL - 1] + "…" in diagram.source
    assert diagram.source.count("+abortTransaction()") == 1
    assert diagram.degraded_reason is None


def test_module_type_diagram_is_left_to_right() -> None:
    """세로 classDiagram 은 같은 층의 타입을 한 줄로 늘어놓는다."""
    edges = [_type_edge("A", "B", TypeEdgeKind.FIELD_TYPE)]
    diagram = diagrams.type_diagram("m", edges, _limit("L2"))
    assert diagram is not None
    assert diagram.source.splitlines()[:2] == ["classDiagram", "  direction LR"]


def test_subsystem_diagram_is_top_to_bottom_and_module_labels_drop_the_prefix() -> None:
    """L0 는 세로다. L1 의 라벨은 묶음 접두어를 뗀다 — 쪽 제목이 그 접두어다."""
    groups = [
        Subsystem(id="connect", modules=["connect/api", "connect/runtime"], source=SubsystemSource.BUILD_TREE),
        Subsystem(id="clients", modules=["clients"], source=SubsystemSource.BUILD_TREE),
    ]
    module_edges = [
        ModuleEdge(src="connect/runtime", dst="connect/api", weight=5),
        ModuleEdge(src="connect/runtime", dst="clients", weight=2),
    ]
    top = diagrams.subsystem_diagram(groups, module_edges, _limit("L0"))
    assert top is not None
    assert "flowchart TB" in top.source
    modules = [
        Module(id="connect/api", build_file="b", main_file_count=3),
        Module(id="connect/runtime", build_file="b", main_file_count=9),
    ]
    inner = diagrams.module_diagram(groups[0], modules, module_edges, _limit("L1"))
    assert inner is not None
    assert '["runtime"]' in inner.source and '["api"]' in inner.source
    assert "connect/" not in inner.source.replace("M_connect_", "")


def test_history_diagram_is_a_bar_chart_of_commits() -> None:
    """timeline 은 분기당 200px 이라 본문에 세 분기밖에 안 든다."""
    periods = [
        {"label": "2025 Q1", "commits": 788, "top_path": "a/KafkaApis.scala", "top_revisions": 52},
        {"label": "2025 Q2", "commits": 597, "top_path": "b/Group.java", "top_revisions": 37},
    ]
    diagram = diagrams.history_diagram(periods, _limit("TIME"))
    assert diagram is not None
    assert "xychart-beta" in diagram.source
    assert f'"width": {diagrams._CHART_WIDTH}' in diagram.source
    assert 'x-axis ["2025 Q1", "2025 Q2"]' in diagram.source
    assert "bar [788, 597]" in diagram.source
    assert diagram.node_count == 2
    # 상한을 넘으면 최근만 남기고 그 사실을 적는다.
    many = [{"label": f"P{i}", "commits": i, "top_path": "", "top_revisions": 0} for i in range(15)]
    limited = diagrams.history_diagram(many, _limit("TIME", max_nodes=12))
    assert limited is not None and limited.node_count == 12
    assert "최근만" in (limited.degraded_reason or "")


def test_sequence_diagrams_fold_participant_names_and_tighten_spacing() -> None:
    """참가자 상자는 이름 폭만큼 넓어진다. 접지 않으면 긴 이름 하나가 상자 둘 자리를 먹는다."""
    call_edges = [
        CallEdge(
            src_type="RemoteLogMetadataSerde",
            src_member="deserialize",
            dst_type="RemoteLogSegmentMetadataSnapshotTransform",
            dst_member="fromApiMessageAndVersion",
            span=_span("m/Serde.java", 40),
            src_module="m",
            dst_module="m",
            src_path="m/Serde.java",
            dst_path="m/Transform.java",
            receiver_kind="static",
        )
    ]
    diagram = diagrams.member_sequence("RemoteLogMetadataSerde", "deserialize", call_edges, _limit("SEQ", 6))
    assert diagram is not None
    lines = diagram.source.splitlines()
    assert lines[0] == diagrams._SEQUENCE_DIRECTIVE and lines[1] == "sequenceDiagram"
    folded = next(line for line in lines if "P1 as" in line)
    assert "<br/>" in folded
    # 한 줄도 상자보다 길지 않다. 낱말 하나가 길어도 마찬가지다.
    assert all(len(piece) <= diagrams._WRAP_AT for piece in folded.split(" as ")[1].split("<br/>"))
    assert diagrams._wrap_name("Serialization") == "Serializat<br/>ion"


def test_area_diagram_stacks_boxes_vertically_with_an_invisible_chain() -> None:
    """서로 부르지 않는 상자는 같은 층에 나란히 놓인다. 사슬이 층을 강제한다."""
    children = [
        ("Alpha와 Beta", ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]),
        ("Store와 Cache", ["Store", "Cache"]),
        ("Lone와 Wolf", ["Lone"]),
    ]
    call_edges = [
        CallEdge(
            src_type="Alpha",
            src_member="run",
            dst_type="Store",
            dst_member="get",
            span=_span("m/Alpha.java", 3),
            src_module="m",
            dst_module="m",
            src_path="m/Alpha.java",
            dst_path="m/Store.java",
            receiver_kind="static",
        )
    ]
    limit = DiagramLimit(level="AREA", max_nodes=12, max_source_chars=2600, max_blocks_per_page=50, layout="elk")
    diagram = diagrams.area_diagram("core", children, call_edges, limit)
    assert diagram is not None
    assert "flowchart TB" in diagram.source
    assert diagram.source.count("    direction LR") == 3
    assert "  A0 ~~~ A1 ~~~ A2" in diagram.source
    # 잎은 셋까지다. 다섯을 가로로 늘어놓으면 상자 하나가 본문을 넘는다.
    assert "Delta" not in diagram.source and "Gamma" in diagram.source
    assert diagram.edge_count == 1


def test_relation_direction_for_every_kind() -> None:
    """관계 종류마다 (앞, 화살표, 뒤). 상속과 구현은 부모가 앞이고, 의존은 기대는 쪽이 앞이다."""
    cases = {
        TypeEdgeKind.EXTENDS: ("D", "<|--", "S"),
        TypeEdgeKind.IMPLEMENTS: ("D", "<|..", "S"),
        TypeEdgeKind.FIELD_TYPE: ("S", "..>", "D"),
        TypeEdgeKind.PARAM_TYPE: ("S", "..>", "D"),
    }
    for kind, expected in cases.items():
        assert diagrams._relation(_type_edge("Src", "Dst", kind), "S", "D") == expected


def test_neighbour_that_is_both_source_and_target_keeps_both_meanings() -> None:
    """한 이웃이 중심을 구현하면서 중심에 기댈 수 있다. 두 줄이 각각의 뜻을 지킨다."""
    edges = [
        _type_edge("Impl", "Admin", TypeEdgeKind.IMPLEMENTS),  # Impl 이 Admin 을 구현
        _type_edge("Admin", "Impl", TypeEdgeKind.PARAM_TYPE),  # Admin 이 Impl 을 인자로 받음
    ]
    diagram = diagrams.type_detail_diagram("Admin", [], edges, _limit("TYPE"))
    assert diagram is not None
    assert "  N0 ..|> Admin" in diagram.source
    assert "  N0 <.. Admin" in diagram.source


def test_truncated_labels_that_collide_get_numbers() -> None:
    """자른 라벨이 같아지면 어느 화살표가 어느 타입인지 못 읽는다. 번호가 가른다."""
    names = ["InMemoryWindowStore.IteratorWrapperOne", "InMemoryWindowStore.IteratorWrapperTwo", "Short"]
    labels = diagrams._distinct(names)
    assert labels["Short"] == "Short"
    assert labels[names[0]] != labels[names[1]]
    assert labels[names[0]].endswith(" #1") and labels[names[1]].endswith(" #2")
    # 그림에서도 그렇다.
    edges = [_type_edge("Admin", name, TypeEdgeKind.FIELD_TYPE) for name in names[:2]]
    diagram = diagrams.type_detail_diagram("Admin", [], edges, _limit("TYPE"))
    assert diagram is not None
    assert "#1" in diagram.source and "#2" in diagram.source


def test_history_chart_survives_hostile_labels_and_zero_counts() -> None:
    """따옴표·대괄호·줄바꿈이 든 라벨과 커밋 0건은 문법을 깨뜨리면 안 된다."""
    periods = [
        {"label": 'Q1 "a" [b]\nc', "commits": 0, "top_path": "", "top_revisions": 0},
        {"label": "Q2", "commits": -3, "top_path": "", "top_revisions": 0},
    ]
    diagram = diagrams.history_diagram(periods, _limit("TIME"))
    assert diagram is not None
    assert 'x-axis ["Q1 a b c", "Q2"]' in diagram.source
    assert 'y-axis "커밋" 0 --> 1' in diagram.source
    assert "bar [0, 0]" in diagram.source


def test_participant_names_do_not_leak_html() -> None:
    """참가자 이름의 `<`·`>`·`&` 는 삽입한 `<br/>` 와 섞여 HTML 로 읽힌다."""
    folded = diagrams._wrap_name("Map<K,V>&Co")
    assert "<" not in folded.replace("<br/>", "") and ">" not in folded.replace("<br/>", "")
    assert "&" not in folded
