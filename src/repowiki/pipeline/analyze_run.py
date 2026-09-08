"""결정층 실행. 입출력은 여기 모으고 판정은 순수 함수에 맡긴다(C-DEPTH-3).

경계 계약: `analyze_repo`는 작업본 경로를 받아 `RepoFacts` 하나를 낸다. 파일을 읽는
자리와 ast-grep을 부르는 자리는 이 모듈과 어댑터뿐이다. 실패는 예외로 올린다 —
빈 사실로 물러서지 않는다(C-REPORT-2).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from repowiki.adapters import astgrep, git
from repowiki.analyze import domain, graph, structure, symbols
from repowiki.bundle import diagrams
from pydantic import BaseModel

from repowiki.models import DiagramLimit, RepoFacts

_TOP_N = 20
_MAX_FLOWS = 10
_MAX_L2_MODULES = 5


def load_limits() -> dict[str, DiagramLimit]:
    """`data/diagram-limits.yml`이 한도의 정본이다(PLAN §2.5)."""
    raw = yaml.safe_load((domain.DATA_DIR / "diagram-limits.yml").read_text(encoding="utf-8"))
    return {
        level: DiagramLimit(
            level=level,
            max_nodes=values["max_nodes"],
            max_source_chars=values["max_source_chars"],
            max_blocks_per_page=values["max_blocks_per_page"],
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


def analyze_repo(root: Path) -> AnalyzeResult:
    """작업본 하나를 분석해 사실 묶음과 줄 수 표를 낸다."""
    facts = domain.load()
    head = git.head(root)
    tracked = git.tracked_files(root)
    kept, _ = structure.source_paths(tracked, facts)
    counts = _line_counts(root, kept, facts)

    profile = structure.build_profile(root.name, head.head_sha, tracked, counts, facts)
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
    edges, unresolved_imports = graph.module_edges(
        extraction.imports, index, owners=graph.type_owners(types)
    )

    type_edges, resolution = graph.type_edges(extraction, types)
    ranks = graph.file_ranks(type_edges, types, extraction.symbols)

    limits = load_limits()
    groups = graph.subsystems(modules, edges, limits["L0"].max_nodes)
    flows = graph.flows(extraction.entry_points, type_edges, types, _MAX_FLOWS)

    compiled = [diagrams.subsystem_diagram(groups, edges, limits["L0"])]
    for group in groups[: limits["L0"].max_nodes]:
        compiled.append(diagrams.module_diagram(group, modules, edges, limits["L1"]))
    for module in _busiest_modules(modules, _MAX_L2_MODULES):
        diagram = diagrams.type_diagram(module, type_edges, limits["L2"])
        if diagram is not None:
            compiled.append(diagram)

    facts_out = RepoFacts(
        profile=profile,
        modules=modules,
        module_edges=edges,
        subsystems=groups,
        symbols=[s for s in extraction.symbols if not s.is_test],
        type_edges=type_edges,
        entry_points=extraction.entry_points,
        file_ranks=ranks[:_TOP_N],
        flows=flows,
        diagrams=compiled,
        unresolved=[
            f"해석되지 않은 임포트 {unresolved_imports}건",
            f"선언이 없는 타입 이름 {resolution.unknown_name}건",
            f"모호한 타입 이름 {resolution.ambiguous}건",
            f"소유 타입 밖의 참조 {resolution.no_owner}건",
            f"미제공 호출 참조 {resolution.deferred_calls}건(해석기 채택 전)",
            f"엣지 종류 밖의 지역 타입 참조 {resolution.deferred_local_types}건",
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
