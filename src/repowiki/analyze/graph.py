"""모듈 엣지, 타입 엣지, 랭킹, 서브시스템, 흐름. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 `Extraction`과 모듈 목록이고 출력은 이름 붙은 형태다. 표준 계산
(PageRank, HITS, Louvain)은 networkx에 위임한다 — 직접 만들지 않는다(C-LIB-1).

사각: 이름 해석은 저장소 안에서 유일한 선언에만 붙는다. 같은 이름의 타입이 두 모듈에
있으면 엣지를 만들지 않고 `unresolved`로 센다. 외부 라이브러리 타입도 같은 이유로 빠진다.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx

from repowiki.analyze.symbols import Extraction, ImportRecord, PackageRecord
from repowiki.models import (
    CrossModuleFlow,
    EntryPoint,
    FileRank,
    FlowHop,
    Module,
    ModuleEdge,
    Subsystem,
    SubsystemSource,
    Symbol,
    SymbolKind,
    TypeEdge,
    TypeEdgeKind,
)

_TYPE_KINDS = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ENUM, SymbolKind.RECORD}

_REF_TO_EDGE = {
    "ref.extends": TypeEdgeKind.EXTENDS,
    "ref.implements": TypeEdgeKind.IMPLEMENTS,
    "ref.field_type": TypeEdgeKind.FIELD_TYPE,
    "ref.param_type": TypeEdgeKind.PARAM_TYPE,
    "ref.type": TypeEdgeKind.FIELD_TYPE,
    "ref.new": TypeEdgeKind.PARAM_TYPE,
}

_MAX_FLOW_DEPTH = 4
_RRF_K = 60


def package_index(packages: list[PackageRecord]) -> dict[str, str]:
    """패키지 이름에서 모듈로. main 소스만 소유자로 인정한다."""
    index: dict[str, str] = {}
    for record in packages:
        if record.is_test:
            continue
        index.setdefault(record.name, record.module)
    return index


def python_index(paths: list[str], module_roots: list[str], module_of) -> dict[str, str]:
    """파이썬 점 이름에서 모듈로. 파일 경로의 디렉토리 구조가 곧 점 이름이다."""
    index: dict[str, str] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        module_id = module_of(path, module_roots)
        relative = path[len(module_id) :].lstrip("/") if module_id != "." else path
        relative = relative.removeprefix("src/")
        dotted = relative.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
        if dotted:
            index.setdefault(dotted, module_id)
    return index


def resolve_dotted(target: str, index: dict[str, str]) -> str | None:
    """가장 긴 접두사 일치로 모듈을 찾는다. 없으면 `None`."""
    parts = target.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ".".join(parts[:size])
        if candidate in index:
            return index[candidate]
    return None


def module_edges(
    imports: list[ImportRecord],
    index: dict[str, str],
    include_test: bool = False,
) -> tuple[list[ModuleEdge], int]:
    """임포트를 모듈 엣지로 접는다. 해석되지 않은 임포트 수를 함께 낸다."""
    weights: Counter[tuple[str, str]] = Counter()
    evidence: dict[tuple[str, str], list] = defaultdict(list)
    unresolved = 0
    for record in imports:
        if record.is_test and not include_test:
            continue
        target_module = resolve_dotted(record.target, index)
        if target_module is None:
            unresolved += 1
            continue
        if target_module == record.module:
            continue
        key = (record.module, target_module)
        weights[key] += 1
        if len(evidence[key]) < 3:
            evidence[key].append(record.span)
    edges = [
        ModuleEdge(src=src, dst=dst, weight=weight, evidence=evidence[(src, dst)])
        for (src, dst), weight in sorted(weights.items())
    ]
    return edges, unresolved


def type_index(symbols: list[Symbol]) -> dict[str, Symbol]:
    """타입 이름에서 선언으로. 이름이 겹치면 넣지 않는다 — 모호한 해석을 만들지 않는다."""
    seen: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        if symbol.kind in _TYPE_KINDS and not symbol.is_test:
            seen[symbol.name].append(symbol)
    return {name: items[0] for name, items in seen.items() if len(items) == 1}


def type_edges(extraction: Extraction, index: dict[str, Symbol]) -> tuple[list[TypeEdge], int]:
    """참조를 타입 엣지로 바꾼다. 호출 엣지는 만들지 않는다(PLAN §2.3 미채택 표기)."""
    edges: list[TypeEdge] = []
    unresolved = 0
    for reference in extraction.references:
        kind = _REF_TO_EDGE.get(reference.message)
        if kind is None or reference.is_test:
            continue
        if reference.owner is None:
            continue
        target = index.get(reference.name)
        if target is None:
            unresolved += 1
            continue
        if target.name == reference.owner:
            continue
        edges.append(
            TypeEdge(
                src=reference.owner,
                dst=target.name,
                kind=kind,
                span=reference.span,
                src_module=reference.module,
                dst_module=target.module,
            )
        )
    return edges, unresolved


def file_ranks(edges: list[TypeEdge], index: dict[str, Symbol], symbols: list[Symbol]) -> list[FileRank]:
    """타입 엣지를 파일 그래프로 접고 PageRank와 허브 점수를 RRF로 합친다."""
    graph = nx.DiGraph()
    file_module = {s.span.path: s.module for s in symbols if not s.is_test}
    for path, module in file_module.items():
        graph.add_node(path, module=module)
    for edge in edges:
        target = index.get(edge.dst)
        if target is None:
            continue
        src_path, dst_path = edge.span.path, target.span.path
        if src_path == dst_path:
            continue
        if graph.has_edge(src_path, dst_path):
            graph[src_path][dst_path]["weight"] += 1
        else:
            graph.add_edge(src_path, dst_path, weight=1)
    if graph.number_of_nodes() == 0:
        return []
    authority = nx.pagerank(graph, weight="weight")
    hub = nx.pagerank(graph.reverse(copy=True), weight="weight")
    ranked_authority = _rank_positions(authority)
    ranked_hub = _rank_positions(hub)
    ranks = []
    for path in graph.nodes:
        fused = 1 / (_RRF_K + ranked_authority[path]) + 1 / (_RRF_K + ranked_hub[path])
        ranks.append(
            FileRank(
                path=path,
                module=file_module.get(path, "."),
                authority=authority[path],
                hub=hub[path],
                fused=fused,
            )
        )
    ranks.sort(key=lambda r: r.fused, reverse=True)
    return ranks


def _rank_positions(scores: dict[str, float]) -> dict[str, int]:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return {path: position for position, (path, _) in enumerate(ordered, start=1)}


def subsystems(modules: list[Module], edges: list[ModuleEdge], max_groups: int) -> list[Subsystem]:
    """서브시스템 분할. 빌드 트리가 먼저고, 그것이 안 나뉘면 Louvain이 나눈다."""
    ids = [m.id for m in modules]
    tree = _build_tree_groups(ids)
    if 1 < len(tree) <= max_groups:
        return [
            Subsystem(id=name, modules=sorted(members), source=SubsystemSource.BUILD_TREE)
            for name, members in sorted(tree.items())
        ]
    graph = nx.Graph()
    graph.add_nodes_from(ids)
    for edge in edges:
        if graph.has_edge(edge.src, edge.dst):
            graph[edge.src][edge.dst]["weight"] += edge.weight
        else:
            graph.add_edge(edge.src, edge.dst, weight=edge.weight)
    communities = nx.community.louvain_communities(graph, weight="weight", seed=42)
    return [
        Subsystem(
            id=f"subsystem-{position}",
            modules=sorted(str(m) for m in community),
            source=SubsystemSource.LOUVAIN,
        )
        for position, community in enumerate(
            sorted(communities, key=lambda c: (-len(c), sorted(c)[0])), start=1
        )
    ]


def _build_tree_groups(module_ids: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for module_id in module_ids:
        head = module_id.split("/")[0] if module_id not in ("", ".") else "."
        groups[head].append(module_id)
    return groups


def flows(
    entry_points: list[EntryPoint],
    edges: list[TypeEdge],
    index: dict[str, Symbol],
    limit: int,
) -> list[CrossModuleFlow]:
    """진입점에서 타입 엣지를 따라가며 모듈 둘 이상을 지나는 경로를 만든다.

    호출 엣지가 없으므로 홉은 타입 관계다. 같은 모듈 안에서만 도는 경로는 버린다.
    """
    by_owner: dict[str, list[TypeEdge]] = defaultdict(list)
    for edge in edges:
        by_owner[edge.src].append(edge)
    results: list[CrossModuleFlow] = []
    for position, entry in enumerate(entry_points, start=1):
        start = _owner_type_at(entry, index)
        if start is None:
            continue
        hops = _walk(start, by_owner, index)
        modules = _ordered_modules(entry.module, hops)
        if len(modules) < 2:
            continue
        results.append(
            CrossModuleFlow(
                id=f"flow-{position}", entry=entry, hops=hops, modules=modules
            )
        )
        if len(results) >= limit:
            break
    return results


def _owner_type_at(entry: EntryPoint, index: dict[str, Symbol]) -> str | None:
    for name, symbol in index.items():
        if symbol.span.path != entry.span.path:
            continue
        if symbol.span.start_line <= entry.span.start_line <= symbol.span.end_line:
            return name
    return None


def _walk(start: str, by_owner: dict[str, list[TypeEdge]], index: dict[str, Symbol]) -> list[FlowHop]:
    hops: list[FlowHop] = []
    seen = {start}
    frontier = start
    for _ in range(_MAX_FLOW_DEPTH):
        candidates = [e for e in by_owner.get(frontier, []) if e.dst not in seen]
        if not candidates:
            break
        edge = sorted(candidates, key=lambda e: (e.dst_module != e.src_module, e.dst))[0]
        target = index.get(edge.dst)
        if target is None:
            break
        hops.append(
            FlowHop(
                src_module=edge.src_module,
                dst_module=edge.dst_module or target.module,
                kind=edge.kind,
                span=edge.span,
                symbol=edge.dst,
            )
        )
        seen.add(edge.dst)
        frontier = edge.dst
    return hops


def _ordered_modules(start_module: str, hops: list[FlowHop]) -> list[str]:
    ordered = [start_module]
    for hop in hops:
        if hop.dst_module != ordered[-1]:
            ordered.append(hop.dst_module)
    return ordered
