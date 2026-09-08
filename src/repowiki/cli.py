"""진입점. 실패는 종료 상태로 말한다(C-REPORT-5).

출력 층이라 표준 출력을 쓴다(ruff T201 면제는 `ruff.toml`이 선언한다).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repowiki.adapters.node import DiagramSource, parse_diagrams
from repowiki.gate.mermaid import check_limits
from repowiki.pipeline.analyze_run import analyze_repo, load_limits, write_facts


def _cmd_analyze(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"오류: 디렉토리가 아니다: {root}", file=sys.stderr)
        return 2
    facts = analyze_repo(root)
    out = Path(args.out).resolve()
    target = write_facts(out / "facts.json", facts)

    limits = load_limits()
    violations = check_limits(facts.diagrams, limits, len(facts.diagrams))
    for violation in violations:
        print(f"한도 위반 {violation.diagram_id} {violation.rule}: {violation.detail}", file=sys.stderr)

    parse_failures = []
    if not args.skip_parse:
        sources = [DiagramSource(id=d.id, source=d.source) for d in facts.diagrams]
        parse_failures = [r for r in parse_diagrams(sources) if not r.ok]
        for failure in parse_failures:
            print(f"파서 실패 {failure.id} ({failure.version}): {failure.error}", file=sys.stderr)

    profile = facts.profile
    print(f"저장소 {profile.root_name} 종류 {profile.kind.value} 커밋 {profile.head_sha[:12]}")
    print(f"  파일 {profile.file_count}개, 모듈 {len(facts.modules)}개, 서브시스템 {len(facts.subsystems)}개")
    print(f"  심볼 {len(facts.symbols)}개, 타입 엣지 {len(facts.type_edges)}개, 모듈 엣지 {len(facts.module_edges)}개")
    print(f"  진입점 {len(facts.entry_points)}개, 흐름 {len(facts.flows)}개, 다이어그램 {len(facts.diagrams)}개")
    print(f"  사실 파일 {target}")
    passed = len(facts.diagrams) - len({f.id for f in parse_failures})
    print(f"  Mermaid 파서 통과 {passed}/{len(facts.diagrams)} (두 판)")
    for note in facts.unresolved:
        print(f"  미해석 {note}")
    return 1 if violations or parse_failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repowiki", description="저장소에서 아키텍처 위키를 만든다")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="결정층 분석만 실행한다")
    analyze.add_argument("repo", help="분석할 작업본 경로")
    analyze.add_argument("--out", default="out", help="사실 파일을 쓸 디렉토리")
    analyze.add_argument(
        "--skip-parse", action="store_true", help="Mermaid 파서 게이트를 건너뛴다(Node 없는 환경)"
    )
    analyze.set_defaults(handler=_cmd_analyze)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
