"""엣지 해석과 다이어그램 컴파일의 단위 검사."""

from __future__ import annotations

from repowiki.analyze.graph import (
    module_edges,
    package_index,
    python_index,
    resolve_dotted,
    subsystems,
    type_edges,
    type_index,
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
    TypeEdgeKind,
)


def _span(path: str = "a/src/main/java/A.java", line: int = 3) -> Span:
    return Span(path=path, start_line=line, end_line=line)


def test_longest_prefix_resolves_package() -> None:
    """임포트는 가장 긴 패키지 접두사로 모듈을 찾는다."""
    index = {"org.a": "core", "org.a.b": "clients"}
    assert resolve_dotted("org.a.b.C", index) == "clients"
    assert resolve_dotted("org.a.z.C", index) == "core"
    assert resolve_dotted("java.util.List", index) is None


def test_module_edges_skip_self_and_test() -> None:
    """같은 모듈로 가는 임포트와 테스트 소스의 임포트는 엣지가 아니다."""
    index = {"org.core": "core", "org.client": "clients"}
    imports = [
        ImportRecord(target="org.client.C", span=_span(), module="core", is_test=False),
        ImportRecord(target="org.core.D", span=_span(), module="core", is_test=False),
        ImportRecord(target="org.client.E", span=_span(), module="core", is_test=True),
    ]
    edges, unresolved = module_edges(imports, index)
    assert [(e.src, e.dst, e.weight) for e in edges] == [("core", "clients", 1)]
    assert unresolved == 0


def test_package_index_prefers_main_scope() -> None:
    """패키지 소유자는 main 소스가 정한다."""
    records = [
        PackageRecord(name="org.a", path="t/A.java", module="tests", is_test=True),
        PackageRecord(name="org.a", path="a/A.java", module="core", is_test=False),
    ]
    assert package_index(records) == {"org.a": "core"}


def test_python_index_uses_directory_structure() -> None:
    """파이썬 점 이름은 디렉토리 구조에서 나온다."""
    paths = ["airflow-core/src/airflow/models/dag.py", "providers/amazon/src/amazon/hook.py"]
    roots = ["", "airflow-core", "providers/amazon"]
    index = python_index(paths, roots, module_of)
    assert index["airflow.models.dag"] == "airflow-core"
    assert resolve_dotted("airflow.models.dag.DAG", index) == "airflow-core"


def test_ambiguous_type_names_make_no_edge() -> None:
    """이름이 겹치는 타입은 해석하지 않는다 — 틀린 엣지보다 없는 엣지가 낫다."""
    symbols = [
        Symbol(kind=SymbolKind.CLASS, name="Config", span=_span("a/A.java"), module="a", language="java"),
        Symbol(kind=SymbolKind.CLASS, name="Config", span=_span("b/B.java"), module="b", language="java"),
        Symbol(kind=SymbolKind.CLASS, name="Client", span=_span("c/C.java"), module="c", language="java"),
    ]
    index = type_index(symbols)
    assert "Config" not in index
    assert "Client" in index

    extraction = Extraction(
        symbols=symbols,
        references=[
            Reference(
                message="ref.field_type",
                name="Config",
                span=_span("c/C.java", 5),
                module="c",
                owner="Client",
                is_test=False,
            ),
            Reference(
                message="ref.extends",
                name="Client",
                span=_span("a/A.java", 7),
                module="a",
                owner="Config",
                is_test=False,
            ),
        ],
        imports=[],
        packages=[],
        entry_points=[],
    )
    edges, unresolved = type_edges(extraction, index)
    assert unresolved == 1
    assert [(e.src, e.dst, e.kind) for e in edges] == [("Config", "Client", TypeEdgeKind.EXTENDS)]


def test_subsystems_prefer_build_tree() -> None:
    """빌드 트리가 상한 안에서 나뉘면 그것이 이긴다."""
    modules = [Module(id="core/a", build_file=None), Module(id="core/b", build_file=None), Module(id="tools/c", build_file=None)]
    groups = subsystems(modules, [], max_groups=15)
    assert {g.id for g in groups} == {"core", "tools"}
    assert all(g.source is SubsystemSource.BUILD_TREE for g in groups)


def test_diagram_degrades_instead_of_overflowing() -> None:
    """한도를 넘으면 노드를 줄이고 사유를 남긴다 — 조용히 자르지 않는다."""
    groups = [Subsystem(id=f"sub{i}", modules=[f"m{i}"], source=SubsystemSource.BUILD_TREE) for i in range(40)]
    edges = [ModuleEdge(src=f"m{i}", dst=f"m{i + 1}", weight=1) for i in range(39)]
    limit = DiagramLimit(level="L0", max_nodes=15, max_source_chars=2000, max_blocks_per_page=50)
    diagram = subsystem_diagram(groups, edges, limit)
    assert diagram.node_count <= 15
    assert diagram.degraded_reason is not None
    assert check_limits([diagram], {"L0": limit}, 1) == []


def test_type_diagram_is_absent_without_edges() -> None:
    """엣지가 없으면 다이어그램을 만들지 않는다."""
    limit = DiagramLimit(level="L2", max_nodes=25, max_source_chars=2000, max_blocks_per_page=50)
    assert type_diagram("core", [], limit) is None
