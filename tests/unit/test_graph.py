"""엣지 해석과 다이어그램 컴파일의 단위 검사.

해석 규칙이 바뀌면 여기부터 고친다 — 사양이 두 벌이 되지 않게 개정이 먼저다(C-TEST-1).
"""

from __future__ import annotations

import pytest

from repowiki.analyze.graph import (
    module_edges,
    package_index,
    python_index,
    resolve_dotted,
    resolve_type,
    subsystems,
    type_edges,
    type_index,
    type_owners,
)
from repowiki.analyze.structure import module_of
from repowiki.analyze.symbols import Extraction, ImportRecord, PackageRecord, Reference
from repowiki.bundle.diagrams import subsystem_diagram, type_diagram
from repowiki.gate.mermaid import check_limits
from repowiki.models import (
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
    """빌드 트리가 상한 안에서 나뉘면 그것이 이긴다."""
    modules = [
        Module(id="core/a", build_file=None),
        Module(id="core/b", build_file=None),
        Module(id="tools/c", build_file=None),
    ]
    groups = subsystems(modules, [], max_groups=15)
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
    assert check_limits([diagram], {"L0": limit}, 1) == []


def test_single_oversized_label_never_exceeds_the_limit() -> None:
    """노드 하나로도 상한을 못 맞추면 다이어그램을 비운다. 상한 초과를 내보내지 않는다."""
    huge = "x" * 500
    groups = [Subsystem(id=huge, modules=[huge], source=SubsystemSource.BUILD_TREE)]
    limit = DiagramLimit(level="L0", max_nodes=15, max_source_chars=100, max_blocks_per_page=50)
    diagram = subsystem_diagram(groups, [], limit)
    assert len(diagram.source) <= limit.max_source_chars
    assert diagram.degraded_reason is not None
    assert check_limits([diagram], {"L0": limit}, 1) == []


def test_type_diagram_is_absent_without_edges() -> None:
    """엣지가 없으면 다이어그램을 만들지 않는다."""
    limit = DiagramLimit(level="L2", max_nodes=25, max_source_chars=2000, max_blocks_per_page=50)
    assert type_diagram("core", [], limit) is None


def test_import_resolves_by_declared_type_before_package() -> None:
    """임포트가 가리키는 타입의 선언 모듈이 1순위다.

    한 패키지를 두 모듈이 나눠 가질 때 참조하는 모듈을 답으로 삼으면 실재하는 교차
    모듈 엣지가 자기 엣지로 흡수된다.
    """
    symbols = [_type("Shared", "clients", "clients/src/main/java/Shared.java")]
    owners = type_owners(type_index(symbols))
    index = {"org.shared": {"core", "clients"}}
    imports = [
        ImportRecord(target="org.shared.Shared", span=_span(), module="core", is_test=False)
    ]
    with_owners, _ = module_edges(imports, index, owners=owners)
    without_owners, _ = module_edges(imports, index)
    assert [(e.src, e.dst) for e in with_owners] == [("core", "clients")]
    assert without_owners == []
