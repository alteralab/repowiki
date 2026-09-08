#!/usr/bin/env python3
"""Java 선언 추출의 대조. 두 번째 원천은 ast-grep `outline`이다.

PLAN §2.7의 "`outline` 교체 규칙"이 요구하는 identity 대조다. 두 경로가 같은 파서를
쓰므로 독립 오라클이 아니다 — 그 한계를 여기 적는다(C-GATE-2). 독립 오라클(javaparser)은
반입이 필요해 이 스크립트의 대상이 아니다.

비교 단위는 (종류, 이름, 시작 줄)이다. 두 경로는 선언의 시작을 다르게 잡는다 — kind 룰은
선언자(`defaultArgName = ...`)를, outline은 애노테이션과 수식어를 포함한 선언 전체를
가리킨다. 그래서 엄격 일치와 함께 줄 허용치 3을 둔 일치도 보고한다. 허용치 안의 차이는
결함이 아니라 규약 차이다.

사용법:
    uv run python evals/oracles/java_outline_oracle.py <저장소 경로> [표본 수] [seed]
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "src" / "repowiki" / "data" / "sgconfig.yml"

_RULE_KIND = {
    "def.class": "class",
    "def.interface": "interface",
    "def.enum": "enum",
    "def.record": "record",
    "def.method": "method",
    "def.constructor": "constructor",
    "def.field": "field",
}

_OUTLINE_KIND = {
    "class": "class",
    "interface": "interface",
    "enum": "enum",
    "record": "record",
    "method": "method",
    "constructor": "constructor",
    "field": "field",
    "property": "field",
}

Declaration = tuple[str, str, int]


def _run(root: Path, args: list[str]) -> str:
    out = subprocess.run(  # noqa: S603
        ["ast-grep", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise RuntimeError(f"ast-grep 실패: {out.stderr.strip()[:300]}")
    return out.stdout


def kind_rules(root: Path, paths: list[str]) -> dict[str, set[Declaration]]:
    found: dict[str, set[Declaration]] = {}
    stdout = _run(root, ["scan", "--config", str(RULES), "--json=stream", *paths])
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        item = json.loads(line)
        kind = _RULE_KIND.get(item.get("message", ""))
        if kind is None:
            continue
        name = item.get("metaVariables", {}).get("single", {}).get("NAME", {}).get("text")
        if not name:
            continue
        found.setdefault(item["file"], set()).add((kind, name, item["range"]["start"]["line"] + 1))
    return found


def _walk_items(items: list[dict], into: set[Declaration]) -> None:
    for item in items:
        kind = _OUTLINE_KIND.get(item.get("symbolType", ""))
        name = item.get("name")
        if kind is not None and name:
            into.add((kind, name, item["range"]["start"]["line"] + 1))
        _walk_items(item.get("members", []), into)


def outline(root: Path, paths: list[str]) -> dict[str, set[Declaration]]:
    found: dict[str, set[Declaration]] = {}
    stdout = _run(root, ["outline", "--json=stream", "--items", "all", *paths])
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        payload = json.loads(line)
        path = payload["path"]
        relative = str(Path(path).relative_to(root)) if Path(path).is_absolute() else path
        declarations: set[Declaration] = set()
        _walk_items(payload.get("items", []), declarations)
        found[relative] = declarations
    return found


def sample(root: Path, count: int, seed: int) -> list[str]:
    candidates = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.java")
        if ".git" not in p.parts and "/src/test/" not in p.as_posix()
    )
    rng = random.Random(seed)
    return rng.sample(candidates, min(count, len(candidates)))


def _match_within_tolerance(
    rules: list[Declaration], outline_items: list[Declaration], tolerance: int
) -> list[tuple[Declaration, Declaration]]:
    """같은 (종류, 이름)이 허용치 안의 줄에 있으면 같은 선언으로 본다."""
    pool = list(outline_items)
    matched: list[tuple[Declaration, Declaration]] = []
    for item in rules:
        for candidate in pool:
            if item[0] == candidate[0] and item[1] == candidate[1] and abs(item[2] - candidate[2]) <= tolerance:
                matched.append((item, candidate))
                pool.remove(candidate)
                break
    return matched


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    paths = sample(root, count, seed)

    mine = kind_rules(root, paths)
    theirs = outline(root, paths)

    agree = only_rules = only_outline = 0
    near = 0
    notes: list[str] = []
    for path in paths:
        a, b = mine.get(path, set()), theirs.get(path, set())
        agree += len(a & b)
        remaining_rules = sorted(a - b)
        remaining_outline = sorted(b - a)
        matched = _match_within_tolerance(remaining_rules, remaining_outline, tolerance=3)
        near += len(matched)
        only_rules += len(remaining_rules) - len(matched)
        only_outline += len(remaining_outline) - len(matched)
        for item in remaining_rules:
            if item not in {pair[0] for pair in matched}:
                notes.append(f"kind 룰만 {path} {item}")
        for item in remaining_outline:
            if item not in {pair[1] for pair in matched}:
                notes.append(f"outline만 {path} {item}")

    total_rules = agree + near + only_rules
    total_outline = agree + near + only_outline
    print(f"표본 {len(paths)}개, seed {seed}")
    print(f"kind 룰 {total_rules}개, outline {total_outline}개")
    print(f"엄격 일치 {agree}개, 규약 차이(허용치 3줄) {near}개, kind 룰만 {only_rules}개, outline만 {only_outline}개")
    agree += near
    if total_outline:
        print(f"outline 기준 kind 룰 recall {agree / total_outline:.4f}")
    if total_rules:
        print(f"kind 룰 기준 outline recall {agree / total_rules:.4f}")
    kinds = Counter(note.split("('")[1].split("'")[0] for note in notes if note.startswith("kind 룰만"))
    print(f"kind 룰에만 있는 선언의 종류 분포: {dict(kinds.most_common())}")
    for line in notes[:15]:
        print(f"  {line}")
    if len(notes) > 15:
        print(f"  ... 불일치 {len(notes)}건 중 15건만 보였다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
