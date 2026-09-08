#!/usr/bin/env python3
"""랭킹의 오라클 대조. 정답은 저장소 자신의 문서가 무엇을 다루는가다.

SPEC SC-1.4는 "문서화된 핵심 모듈 목록 대비 precision@15"를 요구한다. 그 목록을 사람이
만들지 않으려면 저장소의 문서가 실제로 언급하는 모듈을 세면 된다. README와 `docs/`의
마크다운에서 모듈 이름이 몇 번 나오는지 세고, 언급이 있는 모듈을 문서화된 것으로 본다.

사용법:
    uv run python evals/oracles/rank_documentation_oracle.py <저장소 경로> [N]

사각: 이름이 흔한 모듈(`core`, `common`)은 문서에서 다른 뜻으로도 나온다. 그래서 이
대조는 상한이 아니라 하한의 근거다. 이름이 두 글자 이하이거나 흔한 영어 단어면 뺀다.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from repowiki.adapters import astgrep, git  # noqa: E402
from repowiki.analyze import domain, graph, structure, symbols  # noqa: E402

# 문서에서 모듈 이름으로 세면 안 되는 흔한 낱말. 도메인 사실이 아니라 이 측정의 잡음 목록이다.
_TOO_COMMON = {"src", "main", "test", "tests", "docs", "build", "tools", "examples", "lib"}


def documented_modules(root: Path, module_ids: list[str], strict: bool) -> set[str]:
    """문서가 언급하는 모듈. README와 `docs/` 마크다운만 본다.

    `strict`면 모듈의 전체 이름이나 전체 경로가 그대로 나올 때만 센다. 느슨한 판정은
    이름 구획 하나만 겹쳐도 세는데(`dubbo-rpc-api`를 `dubbo`로), 그러면 거의 모든 모듈이
    문서화된 것이 되어 검정력이 사라진다. 두 값을 다 보고한다.
    """
    facts = domain.load()
    tracked = git.tracked_files(root)
    kept, _ = structure.source_paths(tracked, facts)
    pages = [
        path
        for path in kept
        if path.endswith(".md") and (path.count("/") == 0 or path.startswith("docs/"))
    ]
    text = "\n".join(
        (root / page).read_text(encoding="utf-8", errors="replace") for page in pages
    )
    mentions: Counter[str] = Counter()
    for module_id in module_ids:
        name = module_id.split("/")[-1]
        if len(name) <= 2 or name.lower() in _TOO_COMMON:
            continue
        count = text.count(module_id) + (text.count(name) if name != module_id else 0)
        if not strict:
            pieces = [
                piece
                for piece in name.split("-")
                if len(piece) > 2 and piece.lower() not in _TOO_COMMON
            ]
            count += sum(text.count(piece) for piece in pieces)
        if count:
            mentions[module_id] = count
    return set(mentions)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    # 사실 파일의 랭킹은 상위 20파일로 잘려 있다. 모듈 순위를 재려면 전체 순위가
    # 필요하므로 여기서 다시 계산한다.
    facts_data = domain.load()
    tracked = git.tracked_files(root)
    kept, _ = structure.source_paths(tracked, facts_data)
    roots = structure.module_roots(kept, facts_data)
    counts = dict.fromkeys(kept, 1)
    modules = structure.build_modules(kept, roots, counts, facts_data)
    matches = sorted(
        (m for m in astgrep.scan(root) if domain.excluded_by(m.path, facts_data) is None),
        key=lambda m: (m.path, m.start_line, m.end_line, m.message, m.name or ""),
    )
    extraction = symbols.extract(matches, roots, facts_data)
    types = graph.type_index(extraction.symbols)
    scope = graph.build_scope(extraction)
    edges, _ = graph.type_edges(extraction, types, scope)
    ranks = graph.file_ranks(edges, extraction.symbols)

    scores: Counter[str] = Counter()
    for rank in ranks:
        scores[rank.module] += rank.fused
    predicted = [module for module, _ in scores.most_common(top_n)]

    module_ids = [m.id for m in modules]
    strict = documented_modules(root, module_ids, strict=True)
    loose = documented_modules(root, module_ids, strict=False)
    if not loose:
        print("문서가 언급하는 모듈이 없다. 이 저장소는 이 대조의 대상이 아니다.")
        return 2

    def score(documented: set[str]) -> float:
        hit = [module for module in predicted if module in documented]
        return len(hit) / len(predicted) if predicted else 0.0

    print(f"모듈 {len(module_ids)}개, 문서 언급 엄격 {len(strict)}개 / 느슨 {len(loose)}개")
    print(f"precision@{top_n} 엄격 {score(strict):.4f}, 느슨 {score(loose):.4f}")
    print(f"상위 목록: {predicted}")
    missing = [module for module in predicted if module not in strict]
    if missing:
        print(f"엄격 기준으로 문서에 없는 상위 모듈: {missing}")
    return 0 if score(strict) >= 0.6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
