"""결정층 실행. 입출력은 여기 모으고 판정은 순수 함수에 맡긴다(C-DEPTH-3).

경계 계약: `analyze_repo`는 작업본 경로를 받아 `RepoFacts` 하나를 낸다. 파일을 읽는
자리와 ast-grep을 부르는 자리는 이 모듈과 어댑터뿐이다. 실패는 예외로 올린다 —
빈 사실로 물러서지 않는다(C-REPORT-2).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import yaml

from repowiki.adapters import astgrep, git, githistory
from repowiki.analyze import (
    calls,
    clusters,
    corpus,
    domain,
    entities,
    graph,
    history,
    structure,
    symbols,
    toolchain,
    terraform,
    tsmodules,
)
from repowiki.analyze.domain import is_test
from repowiki.bundle import diagrams
from pydantic import BaseModel, Field

from repowiki.models import (
    CorpusFacts,
    DiagramLimit,
    EntityFacts,
    HistoryFacts,
    RepoFacts,
    SymbolKind,
    ToolchainFacts,
)

_TOP_N = 20
_MAX_FLOWS = 10
_MAX_L2_MODULES = 5
_HISTORY_MONTHS = 24
_TOP_COUPLINGS = 30
_MAX_CORPUS_FILES = 600
_MAX_MANIFESTS = 300
_MAX_TSCONFIGS = 200
_MAX_TYPE_DIAGRAMS = 24
_MAX_SEQUENCES_PER_TYPE = 2
_DIAGRAM_TYPE_KINDS = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ENUM, SymbolKind.RECORD}


def load_limits() -> dict[str, DiagramLimit]:
    """`data/diagram-limits.yml`이 한도의 정본이다(PLAN §2.5)."""
    raw = yaml.safe_load((domain.DATA_DIR / "diagram-limits.yml").read_text(encoding="utf-8"))
    return {
        level: DiagramLimit(
            level=level,
            max_nodes=values["max_nodes"],
            max_source_chars=values["max_source_chars"],
            max_blocks_per_page=values["max_blocks_per_page"],
            layout=values.get("layout", "dagre"),
        )
        for level, values in raw["levels"].items()
    }


class SourceReadError(RuntimeError):
    """소스를 읽지 못했다. 줄 수 0으로 물러서면 프로파일과 근거 게이트가 함께 거짓말한다."""


def _line_counts(root: Path, paths: list[str], facts: domain.DomainFacts) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        if domain.language_of(path, facts) is None:
            continue
        try:
            with (root / path).open("rb") as handle:
                counts[path] = sum(1 for _ in handle)
        except OSError as error:
            raise SourceReadError(f"소스를 읽지 못했다: {path} ({error})") from error
    return counts


class AnalyzeResult(BaseModel):
    """분석 산출. 근거 게이트가 줄 수를 필요로 해서 함께 낸다(C-PY-1)."""

    facts: RepoFacts
    line_counts: dict[str, int]


def _history(root: Path, kept: list[str], roots: list[str], facts: domain.DomainFacts):
    """이력 사실. git 저장소가 아니면 `None`을 낸다 — 없는 것을 지어내지 않는다."""
    if not (root / ".git").exists():
        return None
    commits = githistory.read_log(root, _HISTORY_MONTHS)
    known = set(kept)
    return HistoryFacts(
        window_months=_HISTORY_MONTHS,
        commit_count=len(commits),
        hotspots=[
            h.model_dump()
            for h in history.hotspots(commits, facts, known, structure.module_of, roots, _TOP_N)
        ],
        couplings=[
            c.model_dump() for c in history.couplings(commits, facts, known, _TOP_COUPLINGS)
        ],
        issue_keys=history.issue_keys(commits, facts.issue_patterns).model_dump(),
        periods=[p.model_dump() for p in history.periods(commits, facts, known)],
    )


class ReadResult(BaseModel):
    """파일 읽기의 결과. 못 읽은 것과 예산에 잘린 것을 함께 낸다(C-REPORT-2).

    사전만 돌려주면 "이 파일은 왜 사실에 없나"에 아무도 답하지 못한다. 300번째 뒤의 POM이
    조용히 사라지면 버전 표는 틀린 것이 아니라 없는 것이 되고, 읽는 사람은 그 차이를 모른다.
    """

    texts: dict[str, str] = Field(default_factory=dict)
    failed: list[str] = Field(default_factory=list)
    truncated: int = 0


def _read_text(root: Path, paths: list[str], budget: int) -> ReadResult:
    """비코드 파일을 읽는다. 읽지 못한 파일과 예산에 잘린 수를 함께 낸다.

    이진 파일과 깨진 인코딩이 섞여 있으므로 치환으로 읽는다. 여기서 얻은 문자열은 사실을
    만드는 재료이지 위키에 그대로 실리는 글이 아니다.
    """
    result = ReadResult(truncated=max(0, len(paths) - budget))
    for path in paths[:budget]:
        try:
            result.texts[path] = (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            result.failed.append(path)
    return result


def _corpus_and_toolchain(
    root: Path, tracked: list[str], kept: list[str], roots: list[str], facts: domain.DomainFacts
) -> tuple[CorpusFacts, ToolchainFacts, list[str]]:
    """비코드 사실과 도구 사슬 사실. 둘 다 파일 내용을 읽어야 하므로 함께 낸다.

    셋째 값은 미해석 보고다. 읽지 못했거나 예산에 잘린 것을 여기에 적어 위키의 `unresolved`로
    올린다.
    """
    source_paths = set(kept)
    test_paths = {path for path in tracked if is_test(path, facts)}
    citable = corpus.citable_paths(tracked, test_paths, source_paths)
    read = _read_text(root, citable, _MAX_CORPUS_FILES)
    corpus_facts = corpus.build(read.texts, tracked, source_paths, test_paths, roots)

    manifests = toolchain.manifest_paths(tracked)
    manifest_read = _read_text(root, manifests, _MAX_MANIFESTS)
    chain = toolchain.build(manifest_read.texts, roots)

    notes: list[str] = []
    for label, outcome in (("문서와 설정", read), ("빌드 파일", manifest_read)):
        if outcome.failed:
            notes.append(f"{label} {len(outcome.failed)}개를 읽지 못했다: {outcome.failed[:3]}")
        if outcome.truncated:
            notes.append(f"{label} {outcome.truncated}개가 읽기 예산을 넘어 사실에 없다")
    if chain.truncated:
        notes.append(f"의존 {chain.truncated}건이 상한을 넘어 사실에 없다")
    return corpus_facts, chain, notes


def _area_diagrams(groups, call_edges, limits):
    """1단 쪽의 구성도. 차례의 상위 자리마다 하나씩.

    차례를 여기서 다시 세우지 않고 묶음의 디렉토리로 같은 자리를 만든다. 계획 층이 세운
    차례와 같은 자리여야 그림을 찾을 수 있다.
    """
    from repowiki.write import outline

    by_id = {group.id: group for group in groups}
    tree = outline.build(SimpleNamespace(clusters=groups))
    found = []
    for area in (node for node in tree.nodes if node.kind == "area"):
        children = []
        for child in tree.children_of(area.key):
            group = by_id.get(child.clusters[0]) if child.clusters else None
            if group is None:
                continue
            # 묶음의 구성원 열쇠는 `경로#이름`이다. 그림의 라벨은 이름 쪽이다.
            names = [key.split("#", 1)[1] for key in group.members if "#" in key]
            children.append((child.title, names))
        diagram = diagrams.area_diagram(area.title, children, call_edges, limits["AREA"])
        if diagram is not None:
            found.append(diagram)
    return found


def _cluster_leads(groups, nodes) -> list[str]:
    """묶음마다 대표 타입 하나. 그 묶음의 페이지가 실을 그림의 주인공이다."""
    labels = {node.key: node.label for node in nodes}
    found: list[str] = []
    for group in groups:
        lead = clusters.lead_of(group, labels)
        if lead and lead not in found:
            found.append(lead)
    return found


def _typescript_resolver(root: Path, tracked: list[str]):
    """TypeScript 모듈 해석기. tsconfig 가 없으면 `None`이다.

    tsconfig 를 읽어야 별칭이 풀린다. 실측(airflow, 2026-09-09): 저장소 안을 가리키는
    임포트 3,313건 중 별칭이 2,186건이라, 이것 없이는 내부 임포트의 3분의 2를 잃는다.
    """
    names = [
        path
        for path in tracked
        if PurePosixPath(path).name.startswith("tsconfig") and path.endswith(".json")
    ]
    if not names:
        return None
    sources: dict[str, str] = {}
    for path in names[:_MAX_TSCONFIGS]:
        try:
            sources[path] = (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return tsmodules.build(tsmodules.load_configs(sources), tracked)


def _is_external_import(resolver):
    """이 임포트가 저장소 밖을 가리키는가.

    표준 라이브러리와 서드파티는 못 푼 것이 아니라 풀 것이 아니다. 한 칸에 세면 분석이
    실패한 것처럼 보인다. TypeScript 는 해석기가 그 판정을 하고, 나머지 언어는 아직
    가르지 못하므로 못 푼 것으로 남긴다.
    """

    def judge(record) -> bool:
        if resolver is None or not record.specifier:
            return False
        return resolver.resolve(record.specifier, record.span.path).kind == "external"

    return judge


def _module_of_path(resolver, roots: list[str], table=None, names_of=None):
    """해석된 파일 경로를 모듈 id 로 바꾸는 함수. 해석기가 없으면 `None`이다.

    수출 표를 주면 barrel 을 지나 원 선언 파일까지 간다. 실측(airflow, 2026-09-09):
    해석된 임포트의 25퍼센트가 `index.ts`를 가리키므로, 따라가지 않으면 그 넷 중 하나가
    선언 없는 파일을 가리킨다.
    """
    if resolver is None:
        return None

    def resolve(specifier: str, from_path: str) -> str:
        if table is None:
            target = resolver.resolve(specifier, from_path).target
        else:
            names = names_of(specifier, from_path) if names_of else []
            target = tsmodules.declaring_path(table, resolver, specifier, from_path, names)
        return structure.module_of(target, roots) if target else ""

    return resolve


def _ts_declaring(ts_resolver, table, imports) -> dict[tuple[str, str], str]:
    """TypeScript 임포트 하나하나가 실제로 닿는 선언 파일.

    `(부르는 파일, 들여온 이름) -> 선언 파일`이다. 이 표가 임포트 증명이고, 호출 해석기는
    이것만 보고 판단한다. 경로 산술과 barrel 따라가기는 여기서 끝난다(C-DEPTH-3).

    이름마다 따로 푼다. 모듈 엣지는 파일 대 파일이라 첫 이름으로 대표해도 되지만, 호출은
    이름마다 다른 파일에 있을 수 있다. `export { a } from './x'; export { b } from './y'`가
    그런 barrel 이다.
    """
    if ts_resolver is None or table is None:
        return {}
    found: dict[tuple[str, str], str] = {}
    # 입력 순서에 기대지 않는다. 같은 파일이 같은 로컬 이름을 두 번 들여오는 비정상 소스에서
    # ast-grep 스트림 순서가 답을 정하면 결과가 결정적이지 않다(2026-09-09 Codex 리뷰).
    for record in sorted(imports, key=lambda r: (r.span.path, r.span.start_line, r.specifier)):
        if not record.specifier or not record.names:
            continue
        for name in sorted(record.names):
            target = tsmodules.declaring_path(
                table, ts_resolver, record.specifier, record.span.path, [name]
            )
            # 못 푼 것도 빈 문자열로 남긴다. "이 파일이 이 이름을 밖에서 들여왔다"는 사실
            # 자체가 근거다. 표에 없으면 쓰는 쪽이 저장소 전역에서 같은 이름을 찾아 잇고,
            # 그러면 외부 패키지의 타입이 저장소 안의 무관한 타입으로 둔갑한다.
            found.setdefault((record.span.path, name), target or "")
    return found


def _structure_diagrams(groups, modules, edges, limits, root_name, entry_modules):
    """묶음 그림과 모듈 그림. 그릴 값이 없는 것은 컴파일러가 `None`을 낸다.

    서브시스템마다 페이지가 하나씩 생긴다. L0의 노드 상한은 한 그림에 몇 개를 그리느냐이지
    페이지를 몇 개 만드느냐가 아니다.
    """
    found = []
    overview = diagrams.subsystem_diagram(groups, edges, limits["L0"], entry_modules)
    if overview is not None:
        found.append(overview)
    for group in groups:
        diagram = diagrams.module_diagram(
            group, modules, edges, limits["L1"], root_name, entry_modules
        )
        if diagram is not None:
            found.append(diagram)
    return found


def _member_diagrams(symbols, type_edges, call_edges, ranks, limits, leads, labels):
    # 테스트 타입은 그림에서 갈라 보여야 한다. 협력 그림에 테스트가 섞여 있는데 표시가
    # 없으면 사람은 그것을 제품 코드의 이웃으로 읽는다.
    """타입 상세와 협력과 호출 순서 그림. 랭킹 상위 타입에만 만든다.

    모든 타입에 그림을 만들면 사실 파일이 그림으로 가득 찬다. 페이지가 실을 수 있는 것은
    한 쪽에 몇 개뿐이므로, 만드는 것도 그만큼이면 된다.
    """
    test_types = frozenset(s.name for s in symbols if s.is_test and not s.parent)
    order = {rank.path: position for position, rank in enumerate(ranks)}
    ranked = sorted(
        (
            s
            for s in symbols
            if s.kind in _DIAGRAM_TYPE_KINDS and not s.is_test and not s.parent
        ),
        key=lambda s: (order.get(s.span.path, len(order)), s.name),
    )
    # 묶음의 대표 타입은 순위와 무관하게 그림을 갖는다. 페이지가 하나 있는데 그림이 없으면
    # 그 쪽은 사람이 관계를 먼저 보는 방식으로 읽히지 않는다.
    wanted = {name: position for position, name in enumerate(leads)}
    types = sorted(
        {s.name: s for s in ranked[:_MAX_TYPE_DIAGRAMS]}
        | {s.name: s for s in ranked if s.name in wanted},
        key=lambda name: (wanted.get(name, len(wanted)), name),
    )
    types = [
        next(s for s in ranked if s.name == name) for name in types
    ][: _MAX_TYPE_DIAGRAMS + len(leads)]
    found = []
    for symbol in types:
        detail = diagrams.type_detail_diagram(
            symbol.name, symbols, type_edges, limits["TYPE"], labels
        )
        if detail is not None:
            found.append(detail)
        collaboration = diagrams.collaboration_diagram(
            symbol.name, call_edges, limits["COLLAB"], test_types
        )
        if collaboration is not None:
            found.append(collaboration)
        busiest = _busiest_members(symbol.name, call_edges)
        for member in busiest[:_MAX_SEQUENCES_PER_TYPE]:
            sequence = diagrams.member_sequence(symbol.name, member, call_edges, limits["SEQ"])
            if sequence is not None:
                found.append(sequence)
    return found


def _busiest_members(type_name: str, call_edges) -> list[str]:
    """그 타입에서 가장 많은 곳을 부르는 멤버부터. 시퀀스로 그릴 값이 있는 자리다."""
    counted: dict[str, int] = {}
    for edge in call_edges:
        if edge.src_type == type_name:
            counted[edge.src_member] = counted.get(edge.src_member, 0) + 1
    return [name for name, _ in sorted(counted.items(), key=lambda item: (-item[1], item[0]))]


def analyze_repo(root: Path) -> AnalyzeResult:
    """작업본 하나를 분석해 사실 묶음과 줄 수 표를 낸다."""
    facts = domain.load()
    head = git.head(root)
    tracked = git.tracked_files(root)
    kept, _ = structure.source_paths(tracked, facts)
    counts = _line_counts(root, kept, facts)

    profile = structure.build_profile(
        root.name, head.head_sha, tracked, counts, facts, head.remote_url
    )
    roots = structure.module_roots(kept, facts)
    modules = structure.build_modules(kept, roots, counts, facts)

    # 정본 순서를 여기서 못 박는다. ast-grep의 방출 순서는 보장되지 않고, 순서가
    # 사실을 바꾸면 같은 입력이 다른 위키를 낸다(Codex 5차 검증 지적).
    matches = sorted(
        (m for m in astgrep.scan(root) if domain.excluded_by(m.path, facts) is None),
        key=lambda m: (m.path, m.start_line, m.end_line, m.message, m.name or ""),
    )
    extraction = symbols.extract(matches, roots, facts)

    index = graph.package_index(extraction.packages)
    index.update(graph.python_index(kept, roots, structure.module_of))
    types = graph.type_index(extraction.symbols)
    scope = graph.build_scope(extraction)
    ts_resolver = _typescript_resolver(root, tracked)
    ts_exports = (
        tsmodules.build_export_table(extraction.symbols, extraction.reexports)
        if ts_resolver is not None
        else None
    )
    names_by_import = {
        (record.span.path, record.specifier): record.names
        for record in extraction.imports
        if record.specifier
    }
    edges, import_counts = graph.module_edges(
        extraction.imports,
        index,
        scope=scope,
        resolve_path=_module_of_path(
            ts_resolver,
            roots,
            ts_exports,
            lambda specifier, path: names_by_import.get((path, specifier), []),
        ),
        is_external=_is_external_import(ts_resolver),
    )

    # 표를 한 번만 만들어 타입 엣지와 호출 그래프가 같은 것을 본다. 두 번 만들면 두 답이
    # 갈릴 수 있고, 그러면 같은 이름이 쪽마다 다른 자리를 가리킨다(C-DUP-2).
    ts_declaring = _ts_declaring(ts_resolver, ts_exports, extraction.imports)
    type_edges, resolution = graph.type_edges(extraction, types, scope, ts_declaring)
    ranks = graph.file_ranks(type_edges, extraction.symbols)

    bindings, sites = calls.collect(matches, extraction.symbols, roots, facts)
    call_edges, call_counts = calls.resolve(
        sites,
        calls.build_resolver(
            extraction.symbols,
            bindings,
            extraction.imports,
            ts_declaring,
        ),
        lambda name, site: graph.resolve_in_scope(
            name, site.span.path, site.module, types, scope, ts_declaring
        ),
    )

    limits = load_limits()
    history_facts = _history(root, kept, roots, facts)
    model = entities.build(matches, extraction.symbols, roots, facts)
    entity_facts = EntityFacts(
        entities=[e.model_dump() for e in model.entities],
        relations=[r.model_dump() for r in model.relations],
    )
    groups = graph.subsystems(modules, edges)
    flows = graph.flows(extraction.entry_points, type_edges, types, _MAX_FLOWS)

    # 진입점을 품은 모듈. 처음 보는 사람이 어디서부터 읽어야 하는지를 그림이 먼저 말한다.
    entry_modules = frozenset(point.module for point in extraction.entry_points)
    compiled = _structure_diagrams(
        groups, modules, edges, limits, profile.root_name, entry_modules
    )
    for flow in flows:
        diagram = diagrams.flow_diagram(flow, limits["FLOW"])
        if diagram is not None:
            compiled.append(diagram)
    if history_facts is not None:
        diagram = diagrams.history_diagram(history_facts.periods, limits["TIME"])
        if diagram is not None:
            compiled.append(diagram)
    entity_diagram = diagrams.entity_diagram(
        entity_facts.entities, entity_facts.relations, limits["ER"]
    )
    if entity_diagram is not None:
        compiled.append(entity_diagram)
    for module in _busiest_modules(modules, _MAX_L2_MODULES):
        diagram = diagrams.type_diagram(module, type_edges, limits["L2"])
        if diagram is not None:
            compiled.append(diagram)
    nodes = clusters.type_nodes(extraction.symbols, ranks)
    concepts = clusters.cluster(nodes, clusters.relation_graph(nodes, type_edges, call_edges))
    leads = _cluster_leads(concepts, nodes)
    labels = {node.key: node.label for node in nodes}
    compiled += _member_diagrams(
        extraction.symbols, type_edges, call_edges, ranks, limits, leads, labels
    )
    compiled += _area_diagrams(concepts, call_edges, limits)

    corpus_facts, toolchain_facts, corpus_notes = _corpus_and_toolchain(
        root, tracked, kept, roots, facts
    )
    terraform_facts = terraform.build(matches, roots, facts)
    facts_out = RepoFacts(
        clusters=concepts,
        type_labels=labels,
        corpus=corpus_facts,
        toolchain=toolchain_facts,
        terraform=terraform_facts,
        call_edges=call_edges,
        history=history_facts,
        entities=entity_facts,
        profile=profile,
        modules=modules,
        module_edges=edges,
        subsystems=groups,
        # 테스트 선언도 싣는다. 테스트는 저자가 쓴 실행 가능한 사용 설명서라, 사용 예
        # 페이지의 유일한 근거다(DeepWiki commons-cli 7번 쪽이 그것이다).
        symbols=extraction.symbols,
        type_edges=type_edges,
        entry_points=extraction.entry_points,
        file_ranks=ranks[:_TOP_N],
        flows=flows,
        diagrams=compiled,
        unresolved=[
            f"임포트 {import_counts.total()}건 중 이은 것 {import_counts.linked}건,"
            f" 같은 모듈 {import_counts.self_module}건,"
            f" 저장소 밖 {import_counts.external}건,"
            f" 못 푼 것 {import_counts.unresolved}건,"
            f" 테스트 {import_counts.excluded_test}건",
            f"선언이 없는 타입 이름 {resolution.unknown_name}건",
            f"모호한 타입 이름 {resolution.ambiguous}건",
            f"소유 타입 밖의 참조 {resolution.no_owner}건",
            f"타입 엣지가 다루지 않는 호출 참조 {resolution.deferred_calls}건(호출 그래프가 따로 낸다)",
            f"엣지 종류 밖의 지역 타입 참조 {resolution.deferred_local_types}건",
            f"호출 해석 {call_counts.total()}건 중 낸 것 {call_counts.emitted}건,"
            f" 저장소 밖 {call_counts.external}건,"
            f" 체인 수신자 {call_counts.chained_receiver}건,"
            f" 못 푼 수신자 {call_counts.unknown_receiver}건,"
            f" 소유 멤버 없음 {call_counts.no_owner}건,"
            f" 자기 호출 {call_counts.self_call}건,"
            f" 테스트 {call_counts.excluded_test}건",
            *corpus_notes,
        ],
    )
    return AnalyzeResult(facts=facts_out, line_counts=counts)


def _busiest_modules(modules, count: int) -> list[str]:
    ordered = sorted(modules, key=lambda m: -m.main_file_count)
    return [m.id for m in ordered[:count]]


def write_facts(target: Path, facts: RepoFacts) -> Path:
    """사실을 JSON 하나로 쓴다. 경로는 호출자가 정한다."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(facts.model_dump_json(indent=2), encoding="utf-8")
    return target
