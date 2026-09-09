#!/usr/bin/env python3
"""위키 쓰기 루프의 결정적 층. 모델이 판단할 것만 남기고 나머지를 여기서 한다.

왜 스크립트인가. 이 루프에는 모델이 매번 다시 할 이유가 없는 일이 넷 있다. 어느 작업을
받을지 정하는 순서, 게이트가 거부했을 때 임대를 다시 얻는 절차, 전부 끝났는지 판정하는 일,
그리고 마무리 뒤 산출물이 계획과 맞는지 확인하는 일이다. 넷 다 입력이 같으면 결과가 같다.
산문으로 두면 모델이 매번 다시 짜고, 다시 짤 때마다 다르게 짠다.

모델이 판단할 것은 남긴다. 어느 근거의 원문을 읽을지, 무엇을 쓸지, 자리표시자를 글의 어디에
둘지는 이 스크립트가 정하지 않는다.

필요한 것: `repowiki`가 설치된 파이썬 환경. 이 스크립트는 그 명령을 부르고, 문턱 값을 읽을
때만 `repowiki` 패키지를 임포트한다.

종료 코드
  0  했다
  1  게이트가 거부했다(사유를 표준 출력에 적는다)
  2  쓸 수 없다(작업장이 없다, 명령이 실패했다)
  3  받을 작업이 없다
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# 쪽 하나를 몇 번까지 다시 받아 낼지. 이보다 많이 거부되면 사람이 볼 문제다 —
# 같은 사유로 계속 거부되는 것은 글의 문제가 아니라 계획이나 사실 층의 문제다.
MAX_RESUBMITS = 3


def _run(args: list[str]) -> tuple[int, str]:
    """`repowiki`를 부르고 종료 코드와 출력을 낸다. 출력은 두 스트림을 합친다."""
    done = subprocess.run(  # noqa: S603
        ["repowiki", *args], capture_output=True, text=True, check=False
    )
    return done.returncode, (done.stdout + done.stderr).strip()


# 작업 상태를 담는 파일. 이 이름의 정본은 `repowiki`의 `Workspace.store_path`다.
STORE_NAME = "jobs.sqlite"


def _workspace(out: Path) -> Path:
    base = out / ".repowiki"
    if not (base / STORE_NAME).exists():
        print(f"작업장이 없다: {base}. 먼저 `repowiki run <작업본> --out {out}`을 돌린다")
        raise SystemExit(2)
    return base


def _job_ids(out: Path) -> list[str]:
    """계획된 작업 id를 섹션 순서로. 사이드바 순서와 같아 사람이 읽기 좋다."""
    base = _workspace(out)
    found: list[tuple[str, str]] = []
    for job_file in sorted(base.glob("jobs/*/job.json")):
        payload = json.loads(job_file.read_text(encoding="utf-8"))
        found.append((payload.get("section", ""), payload["id"]))
    return [job_id for _, job_id in sorted(found)]


def _states(out: Path) -> dict[str, str]:
    """작업 id에서 상태로. `job status`는 수만 주므로 저장소를 직접 읽는다."""
    import sqlite3

    connection = sqlite3.connect(_workspace(out) / STORE_NAME)
    try:
        rows = connection.execute("SELECT id, state FROM jobs").fetchall()
    finally:
        connection.close()
    return dict(rows)


def command_next(args: argparse.Namespace) -> int:
    """다음에 쓸 작업 하나를 받아 그 자리에서 지시문과 사실까지 낸다.

    받기와 보기를 나누면 모델이 두 명령을 순서대로 불러야 하고, 그 사이에 다른 작업이
    끼어들 수 있다. 한 번에 낸다.
    """
    out = Path(args.out).resolve()
    states = _states(out)
    pending = [job_id for job_id in _job_ids(out) if states.get(job_id) == "pending"]
    if not pending:
        remaining = {job_id: state for job_id, state in states.items() if state != "done"}
        print(f"대기 중인 작업이 없다. 남은 것 {remaining or '없음'}")
        return 3

    job_id = pending[0]
    code, message = _run(["job", "take", job_id, "--out", str(out), "--worker", args.worker])
    if code != 0:
        print(message)
        return 2
    code, shown = _run(["job", "show", job_id, "--out", str(out)])
    if code != 0:
        print(shown)
        return 2
    print(f"작업 {job_id}  (남은 대기 {len(pending) - 1}개)")
    print(f"제출: {Path(sys.argv[0]).name} submit --out {out} --job {job_id}")
    print()
    print(shown)
    return 0


def command_source(args: argparse.Namespace) -> int:
    """근거의 원문을 낸다. 어느 것을 읽을지는 모델이 정한다."""
    out = Path(args.out).resolve()
    code, shown = _run(
        ["job", "show", args.job, "--out", str(out), "--source", args.ids]
    )
    print(shown)
    return 0 if code == 0 else 2


def command_submit(args: argparse.Namespace) -> int:
    """제출한다. 거부되면 임대를 다시 얻어 두어 모델이 고쳐 바로 다시 낼 수 있게 한다.

    거부는 임대를 푼다. 그 사실을 모델이 기억하게 두면 매번 "빌리지 않은 작업이다"를 만나고,
    그때마다 임대를 다시 얻는 절차를 다시 짠다.
    """
    out = Path(args.out).resolve()
    page = _workspace(out) / "jobs" / args.job / "page.json"
    if not page.exists():
        print(f"제출할 파일이 없다: {page}")
        return 2

    code, message = _run(["job", "submit", str(page), "--out", str(out), "--worker", args.worker])
    if code == 0:
        print(message)
        return 0

    print(message)
    retaken, _ = _run(["job", "take", args.job, "--out", str(out), "--worker", args.worker])
    if retaken == 0:
        print(f"임대를 다시 얻었다. 고친 뒤 같은 명령으로 다시 낸다: {page}")
    return 1


def command_finish(args: argparse.Namespace) -> int:
    """전부 끝났는지 보고, 묶고, 사이트를 만든다. 쪽 수가 계획과 맞는지 확인한다."""
    out = Path(args.out).resolve()
    states = _states(out)
    unfinished = {job_id: state for job_id, state in states.items() if state != "done"}
    if unfinished:
        print(f"끝나지 않은 작업이 있다: {unfinished}")
        return 2

    code, message = _run(["bundle", "--out", str(out)])
    print(message)
    if code != 0:
        return 2
    written = len(list((out / "wiki").rglob("*.md"))) - 1  # index.md 는 쪽이 아니다
    if written != len(states):
        print(f"쪽 수가 맞지 않는다: 계획 {len(states)}개, 낸 것 {written}개")
        return 2

    if args.skip_site:
        return 0
    code, message = _run(["site", "--out", str(out)])
    print(message)
    return 0 if code == 0 else 2


def command_thresholds(_args: argparse.Namespace) -> int:
    """게이트가 실제로 쓰는 문턱 값. 문서에 숫자를 박아 두면 정본이 바뀔 때 거짓이 된다."""
    try:
        from repowiki.gate.page import MIN_CITATIONS, WORD_FLOOR_RATIO, WORDS_PER_CITATION
        from repowiki.models import PageType
        from repowiki.write.plan import target_words
    except ImportError as error:
        print(f"`repowiki` 패키지를 읽지 못했다: {error}")
        return 2

    print(f"인용 최소 {MIN_CITATIONS}건, 산문 {WORDS_PER_CITATION}단어마다 한 건 이상")
    print(f"분량 하한은 그 종류의 목표 분량 × {WORD_FLOOR_RATIO}")
    for page_type in PageType:
        target = target_words(page_type)
        print(f"  {page_type.value:24} 목표 {target}단어  하한 {int(target * WORD_FLOOR_RATIO)}단어")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wiki_loop.py", description="위키 쓰기 루프의 결정적 층"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="다음 작업을 받고 지시문과 사실을 낸다")
    nxt.add_argument("--out", required=True)
    nxt.add_argument("--worker", default="session")
    nxt.set_defaults(handler=command_next)

    source = sub.add_parser("source", help="고른 근거의 원문을 낸다")
    source.add_argument("--out", required=True)
    source.add_argument("--job", required=True)
    source.add_argument("--ids", required=True, help="쉼표로 구분한 근거 id (예: E1,E5,E12)")
    source.set_defaults(handler=command_source)

    submit = sub.add_parser("submit", help="제출하고, 거부되면 임대를 다시 얻는다")
    submit.add_argument("--out", required=True)
    submit.add_argument("--job", required=True)
    submit.add_argument("--worker", default="session")
    submit.set_defaults(handler=command_submit)

    finish = sub.add_parser("finish", help="묶고 사이트를 만들고 쪽 수를 확인한다")
    finish.add_argument("--out", required=True)
    finish.add_argument("--skip-site", action="store_true", help="사이트를 만들지 않는다")
    finish.set_defaults(handler=command_finish)

    thresholds = sub.add_parser("thresholds", help="게이트가 쓰는 문턱 값을 낸다")
    thresholds.set_defaults(handler=command_thresholds)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
