"""진입점. 실패는 종료 상태로 말한다(C-REPORT-5).

출력 층이라 표준 출력을 쓴다(ruff T201 면제는 `ruff.toml`이 선언한다).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repowiki.adapters.jobs import JobError
from repowiki.adapters.node import DiagramSource, parse_diagrams
from repowiki.gate.evidence import check_evidence
from repowiki.gate.mermaid import check_limits
from repowiki.pipeline.analyze_run import analyze_repo, load_limits, write_facts
from repowiki.adapters.site import serve
from repowiki.pipeline.write_run import (
    Workspace,
    build_site,
    bundle,
    describe,
    load_facts,
    next_job,
    prepare,
    status,
    submit,
    take,
    write_manifest,
)


def _cmd_analyze(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"오류: 디렉토리가 아니다: {root}", file=sys.stderr)
        return 2
    result = analyze_repo(root)
    facts = result.facts
    out = Path(args.out).resolve()
    target = write_facts(out / "facts.json", facts)

    evidence_violations = check_evidence(facts, result.line_counts)
    for violation in evidence_violations[:10]:
        print(
            f"근거 위반 {violation.subject} {violation.rule}: {violation.detail}", file=sys.stderr
        )

    limits = load_limits()
    violations = check_limits(facts.diagrams, limits)
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
    if facts.history is not None:
        top = facts.history.hotspots[0] if facts.history.hotspots else None
        print(
            f"  이력 {facts.history.window_months}개월 커밋 {facts.history.commit_count}개,"
            f" 핫스팟 {len(facts.history.hotspots)}개, 결합 {len(facts.history.couplings)}쌍"
            + (f", 최다 수정 {top['path']} {top['revisions']}회" if top else "")
        )
    (out / "source-root.txt").write_text(str(root), encoding="utf-8")
    print(f"  사실 파일 {target}")
    print(f"  근거 위반 {len(evidence_violations)}건")
    passed = len(facts.diagrams) - len({f.id for f in parse_failures})
    print(f"  Mermaid 파서 통과 {passed}/{len(facts.diagrams)} (두 판)")
    for note in facts.unresolved:
        print(f"  미해석 {note}")
    return 1 if violations or parse_failures or evidence_violations else 0


def _source_root(out: Path, given: str | None) -> Path | None:
    """근거 원문을 읽을 작업본. 인자가 없으면 분석이 적어 둔 자리를 쓴다.

    없으면 `None`이고, 그때 브리핑에는 원문 없이 자리만 실린다. 작업본이 사라진 뒤에도
    사실 파일만으로 위키를 다시 쓸 수 있어야 하므로 이것은 실패가 아니다.
    """
    if given:
        return Path(given).resolve()
    marker = out / "source-root.txt"
    if not marker.exists():
        return None
    candidate = Path(marker.read_text(encoding="utf-8").strip())
    return candidate if candidate.is_dir() else None


def _cmd_write(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    facts = load_facts(out)
    repo = _source_root(out, getattr(args, "repo", None))
    workspace, count = prepare(out, facts, repo)
    write_manifest(workspace, facts)
    print(f"작업 {count}개를 만들었다: {workspace.base}")
    if repo is None:
        print("  작업본이 없어 근거 원문 없이 브리핑을 만들었다. `--repo`로 지정할 수 있다")
    else:
        print(f"  근거 원문을 {repo}에서 읽었다")
    print("세션 드라이버로 쓰려면 `repowiki job next --out <이 디렉토리>`부터 시작한다")
    return 0


def _cmd_job_next(args: argparse.Namespace) -> int:
    workspace = Workspace(root=str(Path(args.out).resolve()))
    job = next_job(workspace, args.worker)
    if job is None:
        counts = status(workspace)
        print(f"대기 중인 작업이 없다. 상태 {counts}")
        return 0
    print(f"작업 {job.id}")
    print(f"  지시문 {job.payload}/brief.md")
    print(f"  사실   {job.payload}/job.json")
    print(f"  제출   repowiki job submit {job.payload}/page.json --out {args.out}")
    return 0


def _cmd_job_submit(args: argparse.Namespace) -> int:
    workspace = Workspace(root=str(Path(args.out).resolve()))
    try:
        violations = submit(workspace, Path(args.page).resolve(), args.worker)
    except (JobError, FileNotFoundError) as error:
        # 진입점은 실패를 종료 상태로 말한다. 역추적을 사용자에게 보이지 않는다.
        print(f"제출 거부: {error}", file=sys.stderr)
        return 1
    for violation in violations:
        print(f"게이트 거부 {violation.rule}: {violation.detail}", file=sys.stderr)
    if violations:
        return 1
    counts = status(workspace)
    print(f"받았다. 상태 {counts}")
    return 0


def _cmd_bundle(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    workspace = Workspace(root=str(out))
    facts = load_facts(out)
    wiki, count = bundle(workspace, out, facts)
    counts = status(workspace)
    print(f"페이지 {count}개를 {wiki}에 냈다. 작업 상태 {counts}")
    if counts.get("pending"):
        print(f"아직 쓰지 않은 작업이 {counts['pending']}개 있다", file=sys.stderr)
        return 1
    return 0


def _cmd_site(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    facts = load_facts(out)
    site_out, pages, seconds = build_site(out, facts.profile.root_name, args.offline)
    print(f"정적 사이트 {pages}쪽을 {seconds}초에 만들었다: {site_out}")
    if not args.open:
        print(f"열려면 `repowiki site --out {args.out} --open`")
        return 0
    server, url = serve(site_out, args.port)
    print(f"{url} 에서 연다. 멈추려면 Ctrl+C")
    if args.browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def _cmd_job_show(args: argparse.Namespace) -> int:
    workspace = Workspace(root=str(Path(args.out).resolve()))
    wanted = [item.strip() for item in (args.source or "").split(",") if item.strip()]
    print(describe(workspace, args.job, wanted))
    return 0


def _cmd_job_take(args: argparse.Namespace) -> int:
    workspace = Workspace(root=str(Path(args.out).resolve()))
    job = take(workspace, args.job, args.worker)
    directory = workspace.job_dir(job.id)
    print(f"작업 {job.id}")
    print(f"  지시문 {directory / 'brief.md'}")
    print(f"  제출   repowiki job submit {directory / 'page.json'} --out {args.out}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """분석과 계획을 한 번에 돌린다. 쪽을 쓰는 것은 사람이나 세션의 일이다."""
    code = _cmd_analyze(args)
    if code != 0:
        return code
    print()
    return _cmd_write(args)


def _cmd_status(args: argparse.Namespace) -> int:
    workspace = Workspace(root=str(Path(args.out).resolve()))
    counts = status(workspace)
    print(f"작업 상태 {counts}")
    return 0


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

    write = sub.add_parser("write", help="사실에서 페이지 작업을 만든다")
    write.add_argument(
        "--repo", default=None, help="근거 원문을 읽을 작업본 경로(없으면 분석이 적어 둔 자리)"
    )
    write.add_argument("--out", default="out", help="사실 파일이 있는 디렉토리")
    write.set_defaults(handler=_cmd_write)

    job = sub.add_parser("job", help="세션 드라이버의 작업 교환")
    job_sub = job.add_subparsers(dest="job_command", required=True)

    job_next = job_sub.add_parser("next", help="대기 중인 작업 하나를 받는다")
    job_next.add_argument("--out", default="out")
    job_next.add_argument("--worker", default="session")
    job_next.set_defaults(handler=_cmd_job_next)

    job_submit = job_sub.add_parser("submit", help="쓴 페이지를 제출한다")
    job_submit.add_argument("page", help="page.json 경로")
    job_submit.add_argument("--out", default="out")
    job_submit.add_argument("--worker", default="session")
    job_submit.set_defaults(handler=_cmd_job_submit)

    job_show = job_sub.add_parser("show", help="작업 하나를 사람이 읽을 형태로 낸다")
    job_show.add_argument("job", help="작업 id")
    job_show.add_argument("--out", default="out")
    job_show.add_argument(
        "--source", default="", help="원문을 함께 볼 근거 id 목록(쉼표로 구분, 예: E1,E5)"
    )
    job_show.set_defaults(handler=_cmd_job_show)

    job_take = job_sub.add_parser("take", help="작업 하나를 이름으로 지정해 받는다")
    job_take.add_argument("job", help="작업 id")
    job_take.add_argument("--out", default="out")
    job_take.add_argument("--worker", default="session")
    job_take.set_defaults(handler=_cmd_job_take)

    job_status = job_sub.add_parser("status", help="작업 상태를 본다")
    job_status.add_argument("--out", default="out")
    job_status.set_defaults(handler=_cmd_status)

    run = sub.add_parser("run", help="분석과 페이지 계획을 한 번에 돌린다")
    run.add_argument("repo", help="분석할 작업본 경로")
    run.add_argument("--out", default="out", help="산출 디렉토리")
    run.add_argument(
        "--skip-parse", action="store_true", help="Mermaid 파서 게이트를 건너뛴다(Node 없는 환경)"
    )
    run.set_defaults(handler=_cmd_run)

    bundle_cmd = sub.add_parser("bundle", help="제출된 페이지를 위키로 낸다")
    bundle_cmd.add_argument("--out", default="out")
    bundle_cmd.set_defaults(handler=_cmd_bundle)

    site = sub.add_parser("site", help="위키를 정적 사이트로 만들고 루프백에서 연다")
    site.add_argument("--out", default="out")
    site.add_argument("--open", action="store_true", help="빌드 뒤 127.0.0.1에서 연다")
    site.add_argument("--browser", action="store_true", help="브라우저를 함께 띄운다")
    site.add_argument("--port", type=int, default=8765)
    site.add_argument("--offline", action="store_true", help="npm ci를 오프라인으로 돌린다")
    site.set_defaults(handler=_cmd_site)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
