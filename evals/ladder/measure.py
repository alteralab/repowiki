#!/usr/bin/env python3
"""가독성 사다리 판정. SPEC SC-1.6의 측정 도구다.

PLAN §2.5의 세 조건을 잰다. 1440px 폭에서 (a) 엣지 교차 10개 이하, (b) 라벨 잘림 0,
(c) 가로 스크롤 없음. 렌더는 실제 Chrome이 하고(`render_measure.mjs`) 이 스크립트는
좌표에서 교차 수를 세어 판정한다(C-DEPTH-3).

사용법:
    uv run python evals/ladder/measure.py <facts.json> [facts.json ...]

사각: 교차 수는 경로를 24구간으로 표본한 꺾은선에서 센다. 곡선이 아주 짧은 구간에서
스치듯 만나는 교차는 표본 사이로 빠질 수 있다. 값은 하한이다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDERER = HERE / "render_measure.mjs"
ROOT = HERE.parent.parent

MAX_CROSSINGS = 10
LADDER_LEVELS = {"L0", "L1"}


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    """두 선분이 서로를 가로지르는가. 끝점이 닿기만 한 것은 교차로 세지 않는다."""
    d1, d2 = _orientation(p3, p4, p1), _orientation(p3, p4, p2)
    d3, d4 = _orientation(p1, p2, p3), _orientation(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def count_crossings(edges: list[list[list[float]]]) -> int:
    """엣지 꺾은선 사이의 교차 수. 같은 엣지 안의 자기 교차는 세지 않는다."""
    polylines = [[(float(x), float(y)) for x, y in points] for points in edges]
    total = 0
    for first, second in combinations(range(len(polylines)), 2):
        a, b = polylines[first], polylines[second]
        crossed = False
        for i in range(len(a) - 1):
            for j in range(len(b) - 1):
                if _segments_cross(a[i], a[i + 1], b[j], b[j + 1]):
                    crossed = True
                    break
            if crossed:
                break
        total += 1 if crossed else 0
    return total


def render(diagrams: list[dict]) -> list[dict]:
    """Chrome으로 렌더해 좌표를 받는다."""
    payload = json.dumps(diagrams)
    out = subprocess.run(  # noqa: S603
        ["node", str(RENDERER)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"렌더 실패: {out.stderr.strip()[:400]}")
    return json.loads(out.stdout)


def _judge(measured: dict, engine: str, repo: str) -> tuple[tuple, bool]:
    """측정 하나를 판정한다. 세 조건 중 하나라도 어기면 다음 단으로 간다."""
    if not measured.get("ok"):
        return (repo, measured["id"], engine, -1, -1, -1, False, "렌더 실패"), False
    crossings = count_crossings(measured["edge_points"])
    truncated = measured["truncated_labels"]
    hscroll = measured["hscroll"]
    reason = []
    if crossings > MAX_CROSSINGS:
        reason.append(f"교차 {crossings}")
    if truncated:
        reason.append(f"라벨 잘림 {truncated}")
    if hscroll:
        reason.append(f"가로 스크롤 {measured['width']}px > {measured['content_width']}px")
    passed = not reason
    row = (
        repo,
        measured["id"],
        engine,
        measured["nodes"],
        len(measured["edge_points"]),
        crossings,
        passed,
        ", ".join(reason) or "통과",
    )
    return row, passed


def _diagrams_of(facts: dict) -> list[dict]:
    return [
        {"id": d["id"], "level": d["level"], "source": d["source"]}
        for d in facts["diagrams"]
        if d["level"] in LADDER_LEVELS
    ]


def main() -> int:
    if len(sys.argv) < 2:
        print("사용법: measure.py <facts.json> [...]", file=sys.stderr)
        return 2

    rows: list[tuple] = []
    failures = 0
    for argument in sys.argv[1:]:
        facts = json.loads(Path(argument).read_text(encoding="utf-8"))
        repo = facts["profile"]["root_name"]
        diagrams = _diagrams_of(facts)
        if not diagrams:
            continue
        # 엔진은 소스 머리의 init 지시문이 정한다. 지시문이 없으면 Mermaid 내장 dagre다.
        engines = {
            d["id"]: ("elk" if "layout" in d["source"][:60] else "dagre") for d in diagrams
        }
        for measured in render(diagrams):
            row, passed = _judge(measured, engines.get(measured["id"], "dagre"), repo)
            rows.append(row)
            failures += 0 if passed else 1

    print(f"{'저장소':<12} {'다이어그램':<28} {'엔진':<6} {'노드':>4} {'엣지':>4} {'교차':>4}  판정")
    for repo, name, engine, nodes, edges, crossings, passed, reason in rows:
        mark = "통과" if passed else "강등"
        print(f"{repo:<12} {name:<28} {engine:<6} {nodes:>4} {edges:>4} {crossings:>4}  {mark} {reason}")
    total = len(rows)
    print(f"\n합계 {total}개 중 사다리 통과 {total - failures}개, 다음 단으로 갈 것 {failures}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
