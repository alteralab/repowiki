#!/usr/bin/env python3
"""서브시스템 분할의 시드 안정성. SPEC SC-1.3의 후반부를 잰다.

같은 입력에 시드만 바꿔 Louvain을 돌리고 분할끼리의 조정 랜드 지수(ARI)를 잰다. ARI는
표준 지표라 scikit-learn에 맡긴다(C-LIB-1). 평가 전용 의존이라 런타임 밖이다.

사용법:
    uv run --all-extras python evals/oracles/subsystem_stability.py <저장소 경로> [시드 수]

사각: 빌드 트리로 나뉘는 저장소는 시드가 결과를 바꾸지 않으므로 이 측정의 대상이 아니다.
그 사실을 출력이 말한다 — 조용히 1.0을 내지 않는다(C-REPORT-2).
"""

from __future__ import annotations

import statistics
import sys
from itertools import combinations
from pathlib import Path

import networkx as nx
from sklearn.metrics import adjusted_rand_score

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from repowiki.adapters import astgrep, git  # noqa: E402
from repowiki.analyze import domain, graph, structure, symbols  # noqa: E402


def _module_graph(root: Path):
    facts = domain.load()
    tracked = git.tracked_files(root)
    kept, _ = structure.source_paths(tracked, facts)
    roots = structure.module_roots(kept, facts)
    counts = dict.fromkeys(kept, 1)
    modules = structure.build_modules(kept, roots, counts, facts)
    matches = sorted(
        (m for m in astgrep.scan(root) if domain.excluded_by(m.path, facts) is None),
        key=lambda m: (m.path, m.start_line, m.end_line, m.message, m.name or ""),
    )
    extraction = symbols.extract(matches, roots, facts)
    index = graph.package_index(extraction.packages)
    index.update(graph.python_index(kept, roots, structure.module_of))
    types = graph.type_index(extraction.symbols)
    edges, _ = graph.module_edges(extraction.imports, index, owners=graph.type_owners(types))
    return modules, edges


def _labels(modules, edges, seed: int) -> list[int]:
    ids = [m.id for m in modules]
    g = nx.Graph()
    g.add_nodes_from(ids)
    for edge in edges:
        if g.has_edge(edge.src, edge.dst):
            g[edge.src][edge.dst]["weight"] += edge.weight
        else:
            g.add_edge(edge.src, edge.dst, weight=edge.weight)
    communities = nx.community.louvain_communities(g, weight="weight", seed=seed)
    owner = {node: position for position, group in enumerate(communities) for node in group}
    return [owner[i] for i in ids]


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    seed_count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    modules, edges = _module_graph(root)
    tree = {m.id.split("/")[0] for m in modules}
    print(f"모듈 {len(modules)}개, 모듈 엣지 {len(edges)}개, 빌드 트리 최상위 {len(tree)}개")

    runs = [_labels(modules, edges, seed) for seed in range(seed_count)]
    scores = [adjusted_rand_score(a, b) for a, b in combinations(runs, 2)]
    sizes = [len(set(run)) for run in runs]
    print(f"시드 {seed_count}개, 군집 수 {min(sizes)}~{max(sizes)}")
    print(f"쌍대 ARI 최소 {min(scores):.4f}, 중앙값 {statistics.median(scores):.4f}, 평균 {statistics.mean(scores):.4f}")
    return 0 if min(scores) >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
