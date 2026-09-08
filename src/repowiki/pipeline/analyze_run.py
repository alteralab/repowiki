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


def _line_counts(root: Path, paths: list[str], facts: domain.DomainFacts) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        if domain.language_of(path, facts) is None:
            continue
        try:
            with (root / path).open("rb") as handle:
                counts[path] = sum(1 for _ in handle)
        except OSError:
            continue
    return counts


def analyze_repo(root: Path) -> RepoFacts:
    """작업본 하나를 분석해 사실 묶음을 낸다."""
    facts = domain.load()
    head = git.head(root)
    tracked = git.tracked_files(root)
    kept, _ = structure.source_paths(tracked, facts)
    counts = _line_counts(root, kept, facts)

    profile = structure.build_profile(root.name, head.head_sha, tracked, counts, facts)
    roots = structure.module_roots(kept, facts)
    modules = structure.build_modules(kept, roots, counts, facts)

    matches = [m for m in astgrep.scan(root) if domain.excluded_by(m.path, facts) is None]
    extraction = symbols.extract(matches, roots, facts)

    index = graph.package_index(extraction.packages)
    index.update(graph.python_index(kept, roots, structure.module_of))
    edges, unresolved_imports = graph.module_edges(extraction.imports, index)

    types = graph.type_index(extraction.symbols)
    type_edges, unresolved_types = graph.type_edges(extraction, types)
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

    return RepoFacts(
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
            f"해석되지 않은 타입 참조 {unresolved_types}건",
        ],
    )


def _busiest_modules(modules, count: int) -> list[str]:
    ordered = sorted(modules, key=lambda m: -m.main_file_count)
    return [m.id for m in ordered[:count]]


def write_facts(target: Path, facts: RepoFacts) -> Path:
    """사실을 JSON 하나로 쓴다. 경로는 호출자가 정한다."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(facts.model_dump_json(indent=2), encoding="utf-8")
    return target
