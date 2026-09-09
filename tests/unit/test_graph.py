"""엣지 해석과 다이어그램 컴파일의 단위 검사.

해석 규칙이 바뀌면 여기부터 고친다 — 사양이 두 벌이 되지 않게 개정이 먼저다(C-TEST-1).
"""

from __future__ import annotations

import pytest

from repowiki.analyze.graph import (
    build_scope,
    module_edges,
    resolve_in_scope,
    package_index,
    python_index,
    resolve_dotted,
    resolve_type,
    subsystems,
    type_edges,
    type_index,
)
from repowiki.analyze.structure import module_of
from repowiki.analyze.symbols import Extraction, ImportRecord, PackageRecord, Reference
from repowiki.bundle.diagrams import subsystem_diagram, type_diagram
from repowiki.gate.mermaid import check_limits, check_page_blocks
from repowiki.models import (
    Diagram,
    DiagramLimit,
    Module,
    ModuleEdge,
    Span,
    Subsystem,
    SubsystemSource,
    Symbol,
    SymbolKind,
)


def _span(path: str = "a/src/main/java/A.java", line: int = 3) -> Span:
    return Span(path=path, start_line=line, end_line=line)


def _type(name: str, module: str, path: str) -> Symbol:
    return Symbol(kind=SymbolKind.CLASS, name=name, span=_span(path), module=module, language="java")


def _ref(message: str, name: str, module: str, owner: str, path: str = "c/C.java") -> Reference:
    return Reference(
        message=message, name=name, span=_span(path, 5), module=module, owner=owner, is_test=False
    )


def _extraction(references: list[Reference], symbols: list[Symbol]) -> Extraction:
    return Extraction(
        symbols=symbols, references=references, imports=[], packages=[], entry_points=[]
    )


def test_longest_prefix_resolves_package() -> None:
    """임포트는 가장 긴 패키지 접두사로 모듈을 찾는다."""
    index = {"org.a": {"core"}, "org.a.b": {"clients"}}
    assert resolve_dotted("org.a.b.C", index) == "clients"
    assert resolve_dotted("org.a.z.C", index) == "core"
    assert resolve_dotted("java.util.List", index) is None


def test_shared_package_resolves_only_within_home_module() -> None:
    """한 패키지를 두 모듈이 나눠 가지면 참조하는 모듈이 그중에 있을 때만 해석한다."""
    index = {"org.shared": {"core", "clients"}}
    assert resolve_dotted("org.shared.C", index, home="core") == "core"
    assert resolve_dotted("org.shared.C", index, home="tools") is None
    assert resolve_dotted("org.shared.C", index) is None


def test_package_index_is_order_independent() -> None:
    """입력 순서가 소유자를 바꾸지 않는다. 순서가 사실을 바꾸면 결정적이지 않다."""
    records = [
        PackageRecord(name="org.a", path="core/A.java", module="core", is_test=False),
        PackageRecord(name="org.a", path="clients/B.java", module="clients", is_test=False),
        PackageRecord(name="org.a", path="t/T.java", module="tests", is_test=True),
    ]
    forward = package_index(records)
    backward = package_index(list(reversed(records)))
    assert forward == backward == {"org.a": {"core", "clients"}}


def test_module_edges_skip_self_and_test() -> None:
    """같은 모듈로 가는 임포트와 테스트 소스의 임포트는 엣지가 아니다."""
    index = {"org.core": {"core"}, "org.client": {"clients"}}
    imports = [
        ImportRecord(target="org.client.C", span=_span(), module="core", is_test=False),
        ImportRecord(target="org.core.D", span=_span(), module="core", is_test=False),
        ImportRecord(target="org.client.E", span=_span(), module="core", is_test=True),
    ]
    edges, unresolved = module_edges(imports, index)
    assert [(e.src, e.dst, e.weight) for e in edges] == [("core", "clients", 1)]
    assert unresolved == 0


def test_python_index_keeps_every_owner() -> None:
    """같은 점 이름을 두 모듈이 제공하면 둘 다 담고 해석 시점에 가린다."""
    paths = [
        "airflow-core/src/airflow/models/dag.py",
        "providers/amazon/src/airflow/models/dag.py",
    ]
    roots = ["", "airflow-core", "providers/amazon"]
    index = python_index(paths, roots, module_of)
    assert index["airflow.models.dag"] == {"airflow-core", "providers/amazon"}
    assert resolve_dotted("airflow.models.dag.DAG", index) is None
    assert resolve_dotted("airflow.models.dag.DAG", index, home="airflow-core") == "airflow-core"


def test_python_index_is_order_independent() -> None:
    """호출자가 넘긴 순서가 결과를 바꾸지 않는다."""
    paths = ["b/src/pkg/mod.py", "a/src/pkg/mod.py"]
    roots = ["", "a", "b"]
    assert python_index(paths, roots, module_of) == python_index(
        list(reversed(paths)), roots, module_of
    )


def test_duplicate_type_names_resolve_within_module() -> None:
    """같은 이름이 두 모듈에 있어도 참조하는 모듈 안에서 유일하면 해석한다."""
    symbols = [_type("Config", "a", "a/A.java"), _type("Config", "b", "b/B.java")]
    index = type_index(symbols)
    assert len(index["Config"]) == 2
    assert resolve_type("Config", "a", index).module == "a"
    assert resolve_type("Config", "tools", index) is None


def test_test_scope_declaration_does_not_shadow_production() -> None:
    """테스트 소스의 같은 이름 선언은 제품 선언을 가리지 않는다."""
    production = _type("Client", "core", "core/src/main/java/Client.java")
    duplicate = Symbol(
        kind=SymbolKind.CLASS,
        name="Client",
        span=_span("core/src/test/java/Client.java"),
        module="core",
        language="java",
        is_test=True,
    )
    index = type_index([production, duplicate])
    assert resolve_type("Client", "core", index) is production


def test_ambiguous_names_are_counted_by_reason() -> None:
    """해석 실패는 사유별로 센다. 합계 하나로는 어디를 고칠지 알 수 없다."""
    symbols = [_type("Config", "a", "a/A.java"), _type("Config", "b", "b/B.java")]
    index = type_index(symbols)
    extraction = _extraction(
        [
            _ref("ref.field_type", "Config", "tools", "Tool"),
            _ref("ref.field_type", "Missing", "tools", "Tool"),
            Reference(
                message="ref.field_type",
                name="Config",
                span=_span("x/X.java"),
                module="a",
                owner=None,
                is_test=False,
            ),
            _ref("ref.call", "doThing", "a", "A"),
            _ref("ref.local_type", "Config", "a", "A"),
        ],
        symbols,
    )
    edges, counts = type_edges(extraction, index)
    assert edges == []
    assert counts.ambiguous == 1
    assert counts.unknown_name == 1
    assert counts.no_owner == 1
    assert counts.deferred_calls == 1
    assert counts.deferred_local_types == 1


def test_unknown_reference_message_fails_loudly() -> None:
    """엣지 종류가 정해지지 않은 참조는 조용히 버리지 않는다."""
    symbols = [_type("Client", "c", "c/C.java")]
    extraction = _extraction([_ref("ref.mystery", "Client", "a", "A")], symbols)
    with pytest.raises(ValueError, match="엣지 종류가 정해지지 않은"):
        type_edges(extraction, type_index(symbols))


def test_type_edges_are_order_independent() -> None:
    """참조 순서가 엣지 목록을 바꾸지 않는다."""
    symbols = [_type("Client", "c", "c/C.java"), _type("Server", "s", "s/S.java")]
    index = type_index(symbols)
    references = [
        _ref("ref.field_type", "Client", "a", "App", "a/App.java"),
        _ref("ref.extends", "Server", "a", "App", "a/App.java"),
    ]
    forward, _ = type_edges(_extraction(references, symbols), index)
    backward, _ = type_edges(_extraction(list(reversed(references)), symbols), index)
    assert [(e.src, e.dst, e.kind) for e in forward] == [(e.src, e.dst, e.kind) for e in backward]


def test_subsystems_prefer_build_tree() -> None:
    """빌드 트리가 나뉘면 그것이 이긴다. 묶음이 많아도 Louvain으로 물러서지 않는다."""
    modules = [
        Module(id="core/a", build_file=None),
        Module(id="core/b", build_file=None),
        Module(id="tools/c", build_file=None),
    ]
    groups = subsystems(modules, [])
    assert {g.id for g in groups} == {"core", "tools"}
    assert all(g.source is SubsystemSource.BUILD_TREE for g in groups)


def test_diagram_degrades_instead_of_overflowing() -> None:
    """한도를 넘으면 노드를 줄이고 사유를 남긴다 — 조용히 자르지 않는다."""
    groups = [
        Subsystem(id=f"sub{i}", modules=[f"m{i}"], source=SubsystemSource.BUILD_TREE)
        for i in range(40)
    ]
    edges = [ModuleEdge(src=f"m{i}", dst=f"m{i + 1}", weight=1) for i in range(39)]
    limit = DiagramLimit(level="L0", max_nodes=15, max_source_chars=2000, max_blocks_per_page=50)
    diagram = subsystem_diagram(groups, edges, limit)
    assert diagram.node_count <= 15
    assert diagram.degraded_reason is not None
    assert check_limits([diagram], {"L0": limit}) == []


def test_single_oversized_label_never_exceeds_the_limit() -> None:
    """노드 하나로도 상한을 못 맞추면 다이어그램을 비운다. 상한 초과를 내보내지 않는다."""
    huge = "x" * 500
    groups = [Subsystem(id=huge, modules=[huge], source=SubsystemSource.BUILD_TREE)]
    limit = DiagramLimit(level="L0", max_nodes=15, max_source_chars=100, max_blocks_per_page=50)
    diagram = subsystem_diagram(groups, [], limit)
    assert len(diagram.source) <= limit.max_source_chars
    assert diagram.degraded_reason is not None
    assert check_limits([diagram], {"L0": limit}) == []


def test_type_diagram_is_absent_without_edges() -> None:
    """엣지가 없으면 다이어그램을 만들지 않는다."""
    limit = DiagramLimit(level="L2", max_nodes=25, max_source_chars=2000, max_blocks_per_page=50)
    assert type_diagram("core", [], limit) is None


def test_import_resolves_by_qualified_declaration() -> None:
    """임포트는 정규화된 선언으로만 푼다.

    한 패키지를 두 모듈이 나눠 가져도 `a.b.C`를 최상위로 선언한 파일이 하나면 답이
    정해진다. 참조하는 모듈을 답으로 삼으면 실재하는 교차 모듈 엣지가 자기 엣지로
    흡수된다.
    """
    declaration = _type("Shared", "clients", "clients/src/main/java/Shared.java")
    scope = build_scope(
        _scope_extraction(
            [declaration],
            [
                _package("clients/src/main/java/Shared.java", "org.shared"),
                _package("core/src/main/java/User.java", "org.shared"),
            ],
            [],
        )
    )
    index = {"org.shared": {"core", "clients"}}
    imports = [
        ImportRecord(target="org.shared.Shared", span=_span(), module="core", is_test=False)
    ]
    with_scope, _ = module_edges(imports, index, scope=scope)
    without_scope, _ = module_edges(imports, index)
    assert [(e.src, e.dst) for e in with_scope] == [("core", "clients")]
    assert without_scope == []


def test_external_import_makes_no_module_edge() -> None:
    """저장소가 선언하지 않은 이름을 임포트하면 외부 타입이다. 동명 선언으로 잇지 않는다."""
    local = _type("Stream", "core", "core/src/main/java/org/y/Stream.java")
    scope = build_scope(
        _scope_extraction(
            [local],
            [
                _package("core/src/main/java/org/y/Stream.java", "org.y"),
                _package("core/src/main/java/org/y/User.java", "org.y"),
            ],
            [],
        )
    )
    imports = [
        ImportRecord(
            target="java.util.stream.Stream",
            span=_span("core/src/main/java/org/y/User.java"),
            module="core",
            is_test=False,
        )
    ]
    edges, unresolved = module_edges(imports, {"org.y": {"core"}}, scope=scope)
    assert edges == []
    assert unresolved == 1


def test_nested_type_does_not_claim_a_package_name() -> None:
    """중첩 타입은 패키지 수준 선언이 아니다. 다른 파일의 참조를 가로채면 안 된다."""
    outer = Symbol(
        kind=SymbolKind.CLASS,
        name="Outer",
        span=Span(path="a/src/main/java/org/y/Outer.java", start_line=1, end_line=100),
        module="a",
        language="java",
    )
    inner = Symbol(
        kind=SymbolKind.CLASS,
        name="Node",
        span=Span(path="a/src/main/java/org/y/Outer.java", start_line=10, end_line=20),
        module="a",
        language="java",
    )
    scope = build_scope(
        _scope_extraction(
            [outer, inner], [_package("a/src/main/java/org/y/Outer.java", "org.y")], []
        )
    )
    assert scope.declared("org.y", "Outer") == "a/src/main/java/org/y/Outer.java"
    assert scope.declared("org.y", "Node") is None


def _package(path: str, name: str) -> PackageRecord:
    return PackageRecord(name=name, path=path, module=path.split("/")[0], is_test=False)


def _scope_extraction(symbols: list[Symbol], packages: list[PackageRecord], imports: list[ImportRecord]) -> Extraction:
    return Extraction(
        symbols=symbols, references=[], imports=imports, packages=packages, entry_points=[]
    )


def test_explicit_import_decides_which_declaration() -> None:
    """파일이 임포트한 패키지의 선언이 이긴다. 모듈 지역 동명이인보다 강한 근거다."""
    far = _type("Codec", "clients", "clients/src/main/java/org/x/Codec.java")
    near = _type("Codec", "core", "core/src/main/java/org/y/Codec.java")
    index = type_index([far, near])
    scope = build_scope(
        _scope_extraction(
            [far, near],
            [
                _package("clients/src/main/java/org/x/Codec.java", "org.x"),
                _package("core/src/main/java/org/y/Codec.java", "org.y"),
                _package("core/src/main/java/org/y/User.java", "org.y"),
            ],
            [
                ImportRecord(
                    target="org.x.Codec",
                    span=_span("core/src/main/java/org/y/User.java"),
                    module="core",
                    is_test=False,
                )
            ],
        )
    )
    found = resolve_in_scope(
        "Codec", "core/src/main/java/org/y/User.java", "core", index, scope
    )
    assert found is far


def test_import_from_outside_the_repository_is_not_resolved() -> None:
    """저장소에 없는 패키지를 임포트했으면 외부 타입이다. 동명 선언을 앉히지 않는다."""
    local = _type("List", "core", "core/src/main/java/org/y/List.java")
    index = type_index([local])
    scope = build_scope(
        _scope_extraction(
            [local],
            [
                _package("core/src/main/java/org/y/List.java", "org.y"),
                _package("core/src/main/java/org/y/User.java", "org.y"),
            ],
            [
                ImportRecord(
                    target="java.util.List",
                    span=_span("core/src/main/java/org/y/User.java"),
                    module="core",
                    is_test=False,
                )
            ],
        )
    )
    assert resolve_in_scope("List", "core/src/main/java/org/y/User.java", "core", index, scope) is None


def test_same_package_declaration_needs_no_import() -> None:
    """같은 패키지 안의 이름은 임포트 없이 보인다."""
    sibling = _type("Helper", "core", "core/src/main/java/org/y/Helper.java")
    other = _type("Helper", "tools", "tools/src/main/java/org/z/Helper.java")
    index = type_index([sibling, other])
    scope = build_scope(
        _scope_extraction(
            [sibling, other],
            [
                _package("core/src/main/java/org/y/Helper.java", "org.y"),
                _package("core/src/main/java/org/y/User.java", "org.y"),
                _package("tools/src/main/java/org/z/Helper.java", "org.z"),
            ],
            [],
        )
    )
    found = resolve_in_scope("Helper", "core/src/main/java/org/y/User.java", "core", index, scope)
    assert found is sibling


def test_resolution_counts_account_for_every_reference() -> None:
    """참조 하나하나가 어느 항목엔가 들어간다. 합이 입력과 같아야 회계다."""
    symbols = [_type("Client", "c", "c/C.java")]
    index = type_index(symbols)
    references = [
        _ref("ref.field_type", "Client", "a", "App", "a/App.java"),
        _ref("ref.field_type", "Missing", "a", "App", "a/App.java"),
        _ref("ref.call", "doThing", "a", "App", "a/App.java"),
        _ref("ref.local_type", "Client", "a", "App", "a/App.java"),
        Reference(
            message="ref.field_type",
            name="Client",
            span=_span("t/T.java"),
            module="t",
            owner="T",
            is_test=True,
        ),
        Reference(
            message="ref.field_type",
            name="Client",
            span=_span("c/C.java"),
            module="c",
            owner="Client",
            is_test=False,
        ),
    ]
    edges, counts = type_edges(_extraction(references, symbols), index)
    assert counts.total() == len(references)
    assert counts.emitted == len(edges) == 1
    assert counts.self_edge == 1
    assert counts.excluded_test == 1


def _flow_edge(src: str, dst: str, src_module: str, dst_module: str, line: int) -> "TypeEdge":
    from repowiki.models import TypeEdge, TypeEdgeKind

    return TypeEdge(
        src=src,
        dst=dst,
        kind=TypeEdgeKind.FIELD_TYPE,
        span=_span(f"{src_module}/{src}.java", line),
        src_module=src_module,
        dst_module=dst_module,
        dst_path=f"{dst_module}/{dst}.java",
    )


def test_flow_prefers_crossing_a_module_boundary() -> None:
    """다음 홉은 교차 모듈을 먼저 고른다. 흐름 페이지가 보여야 하는 것이 그 경계다."""
    from repowiki.analyze.graph import flows
    from repowiki.models import EntryPoint, EntryPointKind

    symbols = [
        _type("Entry", "a", "a/Entry.java"),
        _type("Near", "a", "a/Near.java"),
        _type("Far", "b", "b/Far.java"),
    ]
    symbols[0].span.end_line = 50
    index = type_index(symbols)
    edges = [_flow_edge("Entry", "Near", "a", "a", 10), _flow_edge("Entry", "Far", "a", "b", 11)]
    entry = EntryPoint(
        kind=EntryPointKind.MAIN, name="main", span=_span("a/Entry.java", 5), module="a"
    )
    result = flows([entry], edges, index, limit=5)
    assert len(result) == 1
    assert result[0].hops[0].dst_module == "b"
    assert result[0].modules == ["a", "b"]


def test_flow_is_order_independent_and_terminates_on_cycles() -> None:
    """엣지 순서가 흐름을 바꾸지 않고, 순환이 있어도 멈춘다."""
    from repowiki.analyze.graph import flows
    from repowiki.models import EntryPoint, EntryPointKind

    symbols = [
        _type("Entry", "a", "a/Entry.java"),
        _type("Mid", "b", "b/Mid.java"),
        _type("Back", "a", "a/Back.java"),
    ]
    symbols[0].span.end_line = 50
    index = type_index(symbols)
    edges = [
        _flow_edge("Entry", "Mid", "a", "b", 10),
        _flow_edge("Mid", "Back", "b", "a", 11),
        _flow_edge("Back", "Entry", "a", "a", 12),
    ]
    entry = EntryPoint(
        kind=EntryPointKind.MAIN, name="main", span=_span("a/Entry.java", 5), module="a"
    )
    forward = flows([entry], edges, index, limit=5)
    backward = flows([entry], list(reversed(edges)), index, limit=5)
    assert [h.symbol for h in forward[0].hops] == [h.symbol for h in backward[0].hops]
    assert len(forward[0].hops) <= 4


def test_same_named_types_are_separate_nodes() -> None:
    """같은 이름의 다른 타입을 한 노드로 합치면 없는 관계를 그린다."""
    from repowiki.models import TypeEdge, TypeEdgeKind

    limit = DiagramLimit(level="L2", max_nodes=25, max_source_chars=2000, max_blocks_per_page=50)
    edges = [
        TypeEdge(
            src="Builder",
            dst="Option",
            kind=TypeEdgeKind.FIELD_TYPE,
            span=_span("core/Option.java", 10),
            src_module="core",
            dst_module="core",
            src_path="core/Option.java",
            dst_path="core/Option.java",
        ),
        TypeEdge(
            src="Builder",
            dst="Parser",
            kind=TypeEdgeKind.FIELD_TYPE,
            span=_span("core/Parser.java", 12),
            src_module="core",
            dst_module="core",
            src_path="core/Parser.java",
            dst_path="core/Parser.java",
        ),
    ]
    diagram = type_diagram("core", edges, limit)
    assert diagram is not None
    assert diagram.source.count('["Builder"]') == 2


def _java_scope(symbols_in: list[Symbol], packages: list[PackageRecord]) -> "object":
    return build_scope(_scope_extraction(symbols_in, packages, []))


def test_nested_and_static_imports_resolve_to_the_declaring_module() -> None:
    """마지막 점이 패키지 경계라는 보장은 없다.

    `a.b.Outer.Inner`는 중첩 타입이고 `static a.b.C.CONST`는 정적 멤버다. 둘 다 선언된
    최상위 이름까지 줄여 가며 찾아야 그 모듈에 닿는다.
    """
    outer = _type("Outer", "clients", "clients/src/main/java/org/x/Outer.java")
    constants = _type("Const", "clients", "clients/src/main/java/org/x/Const.java")
    scope = _java_scope(
        [outer, constants],
        [
            _package("clients/src/main/java/org/x/Outer.java", "org.x"),
            _package("clients/src/main/java/org/x/Const.java", "org.x"),
            _package("core/src/main/java/org/y/User.java", "org.y"),
        ],
    )
    here = _span("core/src/main/java/org/y/User.java")
    imports = [
        ImportRecord(target="org.x.Outer.Inner", span=here, module="core", is_test=False),
        ImportRecord(target="org.x.Const.LIMIT", span=here, module="core", is_test=False),
        ImportRecord(target="org.z.Absent.THING", span=here, module="core", is_test=False),
    ]
    edges, unresolved = module_edges(imports, {"org.x": {"clients"}}, scope=scope)
    assert [(e.src, e.dst, e.weight) for e in edges] == [("core", "clients", 2)]
    assert unresolved == 1


def test_er_diagram_is_absent_without_entities() -> None:
    """엔티티가 없으면 ER 다이어그램을 만들지 않는다. 없는 모델을 지어내지 않는다."""
    from repowiki.bundle.diagrams import entity_diagram

    limit = DiagramLimit(level="ER", max_nodes=10, max_source_chars=2000, max_blocks_per_page=50)
    assert entity_diagram([], [], limit) is None


def test_flow_diagram_needs_a_module_boundary() -> None:
    """모듈을 넘지 않는 흐름은 시퀀스로 그리지 않는다. 보여 줄 경계가 없다."""
    from repowiki.analyze.graph import flows
    from repowiki.models import EntryPoint, EntryPointKind

    symbols = [_type("Entry", "a", "a/Entry.java"), _type("Near", "a", "a/Near.java")]
    symbols[0].span.end_line = 50
    index = type_index(symbols)
    edges = [_flow_edge("Entry", "Near", "a", "a", 10)]
    entry = EntryPoint(
        kind=EntryPointKind.MAIN, name="main", span=_span("a/Entry.java", 5), module="a"
    )
    assert flows([entry], edges, index, limit=5) == []


def test_page_block_limit_uses_the_lowest_cap_of_the_levels_the_page_carries() -> None:
    """한 쪽의 블록 상한은 그 쪽이 실은 층 중 가장 낮은 값이다."""
    wide = DiagramLimit(level="L0", max_nodes=6, max_source_chars=2000, max_blocks_per_page=5)
    narrow = DiagramLimit(level="SEQ", max_nodes=8, max_source_chars=2000, max_blocks_per_page=2)
    limits = {"L0": wide, "SEQ": narrow}

    def _d(level: str, position: int) -> Diagram:
        return Diagram(
            id=f"{level}-{position}", level=level, source="flowchart LR", node_count=1, edge_count=0
        )

    assert check_page_blocks("p", [_d("L0", 1), _d("SEQ", 2)], limits) == []
    over = check_page_blocks("p", [_d("L0", 1), _d("SEQ", 2), _d("SEQ", 3)], limits)
    assert [v.rule for v in over] == ["blocks-per-page"]


def test_a_page_without_diagrams_has_nothing_to_check() -> None:
    assert check_page_blocks("p", [], {}) == []
