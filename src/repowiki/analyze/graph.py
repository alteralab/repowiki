"""모듈 엣지, 타입 엣지, 랭킹, 서브시스템, 흐름. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 `Extraction`과 모듈 목록이고 출력은 이름 붙은 형태다. 표준 계산
(PageRank, HITS, Louvain)은 networkx에 위임한다 — 직접 만들지 않는다(C-LIB-1).

사각: 이름 해석은 단순 이름으로 한다. 범위는 모듈 지역이 먼저고 그다음이 저장소 전역
유일이며, 둘 다 갈리면 해석하지 않고 내역별로 센다. 외부 라이브러리 타입은 선언이 없어
`unknown_name`으로 빠진다. 정규화된 이름(패키지까지 붙인 식별자)은 아직 없다.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx

from pydantic import BaseModel

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


def package_index(packages: list[PackageRecord]) -> dict[str, set[str]]:
    """패키지 이름에서 소유 모듈 집합으로. main 소스만 소유자로 인정한다.

    한 패키지를 여러 모듈이 나눠 가지는 것은 Java에서 흔하다. 먼저 본 것을 소유자로
    정하면 추출 순서가 사실을 바꾼다 — 그래서 집합으로 담고 해석 시점에 가린다.
    """
    index: dict[str, set[str]] = {}
    for record in sorted(packages, key=lambda r: (r.name, r.module, r.path)):
        if record.is_test:
            continue
        index.setdefault(record.name, set()).add(record.module)
    return index


def python_index(paths: list[str], module_roots: list[str], module_of) -> dict[str, set[str]]:
    """파이썬 점 이름에서 소유 모듈 집합으로. 파일 경로의 디렉토리 구조가 곧 점 이름이다.

    입력 순서에 기대지 않으려고 안에서 정렬한다. 같은 점 이름을 두 모듈이 제공하면
    둘 다 담고 해석 시점에 가린다.
    """
    index: dict[str, set[str]] = {}
    for path in sorted(paths):
        if not path.endswith(".py"):
            continue
        module_id = module_of(path, module_roots)
        relative = path[len(module_id) :].lstrip("/") if module_id != "." else path
        relative = relative.removeprefix("src/")
        dotted = relative.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
        if dotted:
            index.setdefault(dotted, set()).add(module_id)
    return index


def resolve_dotted(target: str, index: dict[str, set[str]], home: str | None = None) -> str | None:
    """가장 긴 접두사 일치로 모듈을 찾는다.

    소유자가 여럿이면 `home`(참조하는 쪽의 모듈)이 그중에 있을 때만 그것으로 정하고,
    아니면 해석하지 않는다. 먼저 본 것을 고르지 않는다 — 그 선택은 추출 순서에 기댄다.
    """
    parts = target.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ".".join(parts[:size])
        owners = index.get(candidate)
        if not owners:
            continue
        if len(owners) == 1:
            return next(iter(owners))
        if home is not None and home in owners:
            return home
        return None
    return None


class ImportCounts(BaseModel):
    """임포트 해석의 계수. 합이 입력과 같아야 한다(C-REPORT-2).

    저장소 밖과 못 푼 것을 가른다. 둘을 한 칸에 세면 "해석되지 않은 임포트 15,855건"처럼
    보이는데, 그 대부분은 표준 라이브러리와 서드파티라 풀 것이 아니라 풀 수 없는 것이다.
    """

    linked: int = 0
    self_module: int = 0
    external: int = 0
    unresolved: int = 0
    excluded_test: int = 0

    def total(self) -> int:
        return (
            self.linked
            + self.self_module
            + self.external
            + self.unresolved
            + self.excluded_test
        )


def module_edges(
    imports: list[ImportRecord],
    index: dict[str, set[str]],
    include_test: bool = False,
    scope: "NameScope | None" = None,
    resolve_path=None,
    is_external=None,
) -> tuple[list[ModuleEdge], ImportCounts]:
    """임포트를 모듈 엣지로 접는다. 해석되지 않은 임포트 수를 함께 낸다.

    해석은 정규화된 이름으로만 한다. `import a.b.C`는 패키지 `a.b`가 최상위로 선언한
    `C`를 찾고, 그런 선언이 없으면 외부 타입이므로 엣지를 만들지 않는다. 단순 이름이
    저장소 어딘가에 유일하다는 이유로 잇지 않는다 — 그러면 `java.util.stream.Stream`이
    저장소의 `Stream`으로 이어진다(dubbo 437건, kafka 1,508건 실측).

    와일드카드 임포트(`import a.b.*`)처럼 타입 이름이 없는 형태는 패키지 소유자로 찾고,
    소유자가 여럿이면 해석하지 않는다.

    `resolve_path`를 주면 그것이 먼저다. TypeScript 처럼 임포트가 점 이름이 아니라 파일
    경로인 언어를 위한 자리다 — `(문자열, 임포트한 파일) -> 대상 파일 경로 또는 빈 문자열`.
    """
    weights: Counter[tuple[str, str]] = Counter()
    evidence: dict[tuple[str, str], list] = defaultdict(list)
    counts = ImportCounts()
    ordered = sorted(
        imports, key=lambda r: (r.module, r.target, r.span.path, r.span.start_line)
    )
    for record in ordered:
        if record.is_test and not include_test:
            counts.excluded_test += 1
            continue
        target_module = _resolved_module(record, index, scope, resolve_path)
        if target_module is None:
            if is_external is not None and is_external(record):
                counts.external += 1
            else:
                counts.unresolved += 1
            continue
        if target_module == record.module:
            counts.self_module += 1
            continue
        counts.linked += 1
        key = (record.module, target_module)
        weights[key] += 1
        if len(evidence[key]) < 3:
            evidence[key].append(record.span)
    edges = [
        ModuleEdge(src=src, dst=dst, weight=weight, evidence=evidence[(src, dst)])
        for (src, dst), weight in sorted(weights.items())
    ]
    return edges, counts


def _resolved_module(
    record: ImportRecord, index: dict[str, set[str]], scope: "NameScope | None", resolve_path
) -> str | None:
    """이 임포트가 가리키는 모듈. 경로 해석기가 있으면 그것으로 먼저 푼다."""
    if resolve_path is not None and record.specifier:
        return resolve_path(record.specifier, record.span.path) or None
    return _import_target(record, index, scope)


def _declared_prefix(target: str, scope: "NameScope") -> str | None:
    """임포트 문자열에서 선언된 최상위 타입의 가장 긴 접두사를 찾아 그 선언 파일을 낸다.

    마지막 점이 패키지와 타입의 경계라는 보장은 없다. `a.b.Outer.Inner`는 중첩 타입이고
    `static a.b.C.CONST`는 정적 멤버라 경계가 더 앞에 있다. 그래서 뒤에서부터 줄여 가며
    선언된 이름을 만나는 자리를 경계로 삼는다. 어느 자리에서도 선언을 못 만나면 외부
    타입이다(dubbo 정적 임포트 1,598건, kafka 중첩 임포트 197건이 이 규칙으로 살아난다).
    """
    parts = target.split(".")
    for size in range(len(parts), 1, -1):
        package = ".".join(parts[: size - 1])
        simple = parts[size - 1]
        path = scope.declared(package, simple)
        if path is not None:
            return path
    return None


def _import_target(
    record: ImportRecord, index: dict[str, set[str]], scope: "NameScope | None"
) -> str | None:
    """임포트 하나가 가리키는 모듈. 정규화된 선언이 있을 때만 답한다."""
    if scope is not None and "." in record.target:
        path = _declared_prefix(record.target, scope)
        if path is not None:
            return scope.file_module.get(path)
    # 타입 선언이 아니라 패키지를 가리키는 형태(와일드카드, 파이썬 모듈)만 남는다.
    return resolve_dotted(record.target, index, home=record.module)


def type_index(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    """타입 이름에서 선언 목록으로. 같은 이름이 여럿이면 전부 담는다.

    이름 하나에 선언 하나만 남기면(전역 유일 조건) 같은 이름이 두 모듈에 있다는 이유로
    그 이름의 참조가 전부 사라진다. 실측에서 kafka 15,435건, dubbo 7,416건이 그렇게
    버려졌고 그중 각각 5,595건과 2,937건은 참조하는 모듈 안에서 유일했다. 해석은
    `resolve_type`이 범위 순서로 한다.
    """
    seen: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        if symbol.kind in _TYPE_KINDS and not symbol.is_test:
            seen[symbol.name].append(symbol)
    return {
        name: sorted(items, key=lambda s: (s.module, s.span.path, s.span.start_line))
        for name, items in seen.items()
    }


class NameScope(BaseModel):
    """이름을 선언으로 풀 때 쓰는 파일별 사실.

    Java 계열에서 파일의 임포트와 패키지가 단순 이름의 뜻을 정한다. 이 자료 없이
    이름만 보면 같은 이름의 다른 선언을 고를 수 있다.
    """

    file_package: dict[str, str] = {}
    file_imports: dict[str, dict[str, str]] = {}
    file_module: dict[str, str] = {}
    by_package: dict[str, dict[str, str]] = {}

    def declared(self, package: str, name: str) -> str | None:
        """그 패키지가 그 이름을 최상위로 선언한 파일. 없거나 둘 이상이면 `None`.

        중첩 타입은 여기 없다. 감싸는 타입 없이는 그 이름으로 부를 수 없기 때문이다.
        """
        return self.by_package.get(package, {}).get(name)


def _package_claims(
    extraction: Extraction, file_package: dict[str, str]
) -> dict[str, dict[str, set[str]]]:
    """(패키지, 이름) → 그 이름을 최상위로 선언한 파일들.

    중첩 타입은 넣지 않는다. 감싸는 타입 없이는 그 이름으로 부를 수 없어서, 패키지 수준
    선언처럼 다루면 다른 파일의 내부 클래스가 같은 이름의 참조를 가로챈다.
    """
    types_by_file: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in sorted(extraction.symbols, key=lambda s: (s.span.path, s.span.start_line)):
        if symbol.kind in _TYPE_KINDS and not symbol.is_test:
            types_by_file[symbol.span.path].append(symbol)

    claims: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path, items in sorted(types_by_file.items()):
        package = file_package.get(path)
        if package is None:
            continue
        for symbol in items:
            if not _is_nested(symbol, items):
                claims[package][symbol.name].add(path)
    return claims


def build_scope(extraction: Extraction) -> NameScope:
    """파일별 패키지와 임포트, 패키지별 최상위 선언 표를 만든다."""
    scope = NameScope()
    for record in sorted(extraction.packages, key=lambda r: r.path):
        scope.file_package[record.path] = record.name
        scope.file_module[record.path] = record.module
    for record in sorted(extraction.imports, key=lambda r: (r.span.path, r.target)):
        parts = record.target.rsplit(".", 1)
        if len(parts) == 2:
            scope.file_imports.setdefault(record.span.path, {})[parts[1]] = parts[0]

    # 같은 (패키지, 이름)을 두 파일이 주장하면 그 이름은 정규화되지 않는다. 넣지 않는다.
    for package, names in _package_claims(extraction, scope.file_package).items():
        for name, paths in names.items():
            if len(paths) == 1:
                scope.by_package.setdefault(package, {})[name] = next(iter(paths))
    return scope


def _is_nested(symbol: Symbol, siblings: list[Symbol]) -> bool:
    """같은 파일의 다른 타입이 이 타입을 감싸고 있는가."""
    for other in siblings:
        if other is symbol:
            continue
        if (
            other.span.start_line <= symbol.span.start_line
            and symbol.span.end_line <= other.span.end_line
            and (other.span.end_line - other.span.start_line)
            > (symbol.span.end_line - symbol.span.start_line)
        ):
            return True
    return False


def _by_path(index: dict[str, list[Symbol]], name: str, path: str) -> Symbol | None:
    for symbol in index.get(name, []):
        if symbol.span.path == path:
            return symbol
    return None


def resolve_in_scope(
    name: str,
    ref_path: str,
    home: str,
    index: dict[str, list[Symbol]],
    scope: NameScope,
    ts_declaring: dict[tuple[str, str], str] | None = None,
) -> Symbol | None:
    """이름을 선언으로 푼다. 범위 순서는 다섯이다.

    0. TypeScript 는 그 파일이 들여온 이름이 어느 파일에서 선언됐는지를 표로 받는다.
       상대 경로와 `paths` 무늬와 barrel 을 지난 답이라 다른 어느 범위보다 강하다.
       들여왔는데 저장소 밖이면 거기서 멈춘다.
    1. 그 파일이 명시적으로 임포트한 이름이면 그 패키지의 선언. 임포트한 패키지가
       저장소 안에 없으면 외부 타입이라 해석하지 않는다.
    2. 같은 패키지 안의 선언(임포트 없이 보이는 이름).
    3. 참조하는 모듈 안에서 유일한 선언.
    4. 저장소 전체에서 유일한 선언.

    앞쪽이 뒤쪽보다 강한 근거인 이유는 언어가 그렇게 정하기 때문이다. 모듈 지역
    유일성은 언어의 규칙이 아니라 추정이므로 임포트가 말해 주는 자리에서는 쓰지 않는다.

    0단이 없으면 TypeScript 참조가 3단과 4단으로 떨어진다. 그러면 외부 패키지의 타입이
    저장소 안의 같은 이름을 가진 무관한 타입으로 둔갑한다(2026-09-09 Codex 리뷰).
    """
    if ts_declaring is not None:
        declaring = ts_declaring.get((ref_path, name))
        if declaring is not None:
            return _by_path(index, name, declaring) if declaring else None
    imported = scope.file_imports.get(ref_path, {}).get(name)
    if imported is not None:
        # 그 파일이 이 이름을 명시적으로 임포트했다. 임포트한 패키지가 저장소 안에
        # 없으면 외부 타입이므로 해석을 멈춘다. 여기서 다음 범위로 넘어가면 같은
        # 이름의 저장소 안 선언을 외부 타입 자리에 앉히게 된다(`java.util.List`).
        path = scope.declared(imported, name)
        if path is None:
            return None
        return _by_path(index, name, path)
    own_package = scope.file_package.get(ref_path)
    if own_package is not None:
        path = scope.declared(own_package, name)
        if path is not None:
            found = _by_path(index, name, path)
            if found is not None:
                return found
    return resolve_type(name, home, index)


def resolve_type(name: str, home: str, index: dict[str, list[Symbol]]) -> Symbol | None:
    """이름을 선언으로 푼다. 범위 순서는 모듈 지역, 그다음 저장소 전역 유일이다.

    둘 다 갈리면 해석하지 않는다 — 틀린 엣지보다 없는 엣지가 낫다(PLAN §1 비목표).
    """
    candidates = index.get(name)
    if not candidates:
        return None
    local = [item for item in candidates if item.module == home]
    if len(local) == 1:
        return local[0]
    if len(local) > 1:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


class ResolutionCounts(BaseModel):
    """참조 하나가 어디로 갔는지의 전수 회계.

    항목은 서로 겹치지 않고 합은 입력 참조 수와 같다. 실패만 세면 "본 것 중 얼마가
    엣지가 됐는가"에 답할 수 없다.
    """

    emitted: int = 0
    self_edge: int = 0
    unknown_name: int = 0
    ambiguous: int = 0
    no_owner: int = 0
    deferred_calls: int = 0
    deferred_local_types: int = 0
    excluded_test: int = 0

    def total(self) -> int:
        """본 참조 수. 이 값이 입력과 다르면 어딘가에서 조용히 사라진 것이다."""
        return (
            self.emitted
            + self.self_edge
            + self.unknown_name
            + self.ambiguous
            + self.no_owner
            + self.deferred_calls
            + self.deferred_local_types
            + self.excluded_test
        )


def _qualified(name: str | None, path: str | None, scope: "NameScope | None") -> str | None:
    """`패키지.이름` 형태의 정규화된 이름. 패키지를 모르면 `None`."""
    if name is None or path is None or scope is None:
        return None
    package = scope.file_package.get(path)
    return f"{package}.{name}" if package else None


def type_edges(
    extraction: Extraction,
    index: dict[str, list[Symbol]],
    scope: NameScope | None = None,
    ts_declaring: dict[tuple[str, str], str] | None = None,
) -> tuple[list[TypeEdge], ResolutionCounts]:
    """참조를 타입 엣지로 바꾼다.

    호출 엣지(`ref.call`)와 지역 변수 타입(`ref.local_type`)은 여기서 만들지 않고 따로 센다.
    호출은 타입 관계가 아니라 멤버 관계라 `analyze/calls.py`가 수신자를 풀어 따로 낸다.
    지역 변수 타입은 `TypeGraph`의 엣지 종류에 없다. 둘 다 조용히 버리지 않는다(C-REPORT-2).
    """
    edges: list[TypeEdge] = []
    counts = ResolutionCounts()
    ordered = sorted(
        extraction.references,
        key=lambda r: (r.span.path, r.span.start_line, r.message, r.name),
    )
    for reference in ordered:
        if reference.is_test:
            counts.excluded_test += 1
            continue
        if reference.message == "ref.call":
            counts.deferred_calls += 1
            continue
        if reference.message == "ref.local_type":
            counts.deferred_local_types += 1
            continue
        kind = _REF_TO_EDGE.get(reference.message)
        if kind is None:
            raise ValueError(f"엣지 종류가 정해지지 않은 참조다: {reference.message}")
        if reference.owner is None:
            counts.no_owner += 1
            continue
        target = (
            resolve_in_scope(
                reference.name,
                reference.span.path,
                reference.module,
                index,
                scope,
                ts_declaring,
            )
            if scope is not None
            else resolve_type(reference.name, reference.module, index)
        )
        if target is None:
            if reference.name in index:
                counts.ambiguous += 1
            else:
                counts.unknown_name += 1
            continue
        if target.name == reference.owner:
            counts.self_edge += 1
            continue
        counts.emitted += 1
        edges.append(
            TypeEdge(
                src=reference.owner,
                dst=target.name,
                kind=kind,
                span=reference.span,
                src_module=reference.module,
                dst_module=target.module,
                src_path=reference.owner_path,
                dst_path=target.span.path,
                src_declaration=reference.owner_span,
                dst_declaration=target.span,
                src_qualified=_qualified(reference.owner, reference.owner_path, scope),
                dst_qualified=_qualified(target.name, target.span.path, scope),
            )
        )
    return edges, counts


def file_ranks(edges: list[TypeEdge], symbols: list[Symbol]) -> list[FileRank]:
    """타입 엣지를 파일 그래프로 접고 PageRank와 허브 점수를 RRF로 합친다."""
    graph = nx.DiGraph()
    file_module = {s.span.path: s.module for s in sorted(symbols, key=lambda s: s.span.path) if not s.is_test}
    for path, module in file_module.items():
        graph.add_node(path, module=module)
    for edge in edges:
        if edge.dst_path is None:
            continue
        src_path, dst_path = edge.span.path, edge.dst_path
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


def subsystems(modules: list[Module], edges: list[ModuleEdge]) -> list[Subsystem]:
    """서브시스템 분할. 빌드 트리가 먼저고, 그것이 안 나뉠 때만 Louvain이 나눈다.

    빌드 트리가 상한보다 많은 묶음을 내도 Louvain으로 물러서지 않는다. 그렇게 하면
    군집이 더 늘고(kafka 실측: 트리 23개 대 Louvain 39~40개) 시드마다 결과가 달라진다
    (쌍대 ARI 최소 0.82). 묶음이 많은 것은 분할의 문제가 아니라 다이어그램의 문제이고,
    그 자리에는 가독성 사다리가 있다(§2.5).
    """
    ids = [m.id for m in modules]
    tree = _build_tree_groups(ids)
    if len(tree) > 1:
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
    index: dict[str, list[Symbol]],
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
        hops = _walk(start, by_owner)
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


def _owner_type_at(entry: EntryPoint, index: dict[str, list[Symbol]]) -> str | None:
    """진입점을 감싸는 가장 안쪽 타입. 중첩 클래스가 바깥에 붙지 않게 한다."""
    best: tuple[int, str] | None = None
    for name, symbols in index.items():
        for symbol in symbols:
            if symbol.span.path != entry.span.path:
                continue
            if not (symbol.span.start_line <= entry.span.start_line <= symbol.span.end_line):
                continue
            size = symbol.span.end_line - symbol.span.start_line
            if best is None or (size, name) < best:
                best = (size, name)
    return best[1] if best is not None else None


def _walk(start: str, by_owner: dict[str, list[TypeEdge]]) -> list[FlowHop]:
    hops: list[FlowHop] = []
    seen = {start}
    frontier = start
    for _ in range(_MAX_FLOW_DEPTH):
        candidates = [e for e in by_owner.get(frontier, []) if e.dst not in seen]
        if not candidates:
            break
        # 교차 모듈 홉을 먼저 고른다. 흐름 페이지가 보여야 하는 것이 모듈을 넘는 경로다.
        # 나머지 키는 같은 입력에서 같은 홉을 고르게 하는 정렬 기준이다.
        edge = sorted(
            candidates,
            key=lambda e: (
                e.dst_module == e.src_module,
                e.dst_module or "",
                e.dst,
                e.kind,
                e.span.path,
                e.span.start_line,
            ),
        )[0]
        if edge.dst_path is None:
            break
        hops.append(
            FlowHop(
                src_module=edge.src_module,
                dst_module=edge.dst_module or edge.src_module,
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
