#!/usr/bin/env python3
"""파이썬 선언 추출의 오라클 비교. 정답은 표준 라이브러리 `ast`가 낸다.

SPEC SC-1.2의 판정 도구다. 사람이 라벨하지 않는다 — 정답은 도구가 내고 사람은 불일치만
본다(PLAN §6 3). 표본은 seed 고정 무작위이고, 비교 단위는 (종류, 이름, 시작 줄)이다.

사용법:
    uv run python evals/oracles/python_ast_oracle.py <저장소 경로> [표본 수] [seed]

사각: `ast`는 파일이 문법에 맞을 때만 답한다. 파싱 실패 파일은 표본에서 빼고 그 수를
보고한다. 데코레이터가 붙은 선언의 시작 줄은 `ast`가 `def` 줄을 가리키고 ast-grep도
같은 줄을 가리키므로 이 비교에서는 어긋나지 않는다.
"""

from __future__ import annotations

import ast
import json
import random
import subprocess
import sys
from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "src" / "repowiki" / "data" / "sgconfig.yml"


def oracle_declarations(source: str) -> set[tuple[str, str, int]]:
    """`ast`가 보는 선언. 클래스와 함수만 본다 — ast-grep 룰이 내는 것과 같은 집합이다."""
    tree = ast.parse(source)
    found: set[tuple[str, str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            found.add(("class", node.name, node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.add(("function", node.name, node.lineno))
    return found


def ours(root: Path, paths: list[str]) -> dict[str, set[tuple[str, str, int]]]:
    """ast-grep이 보는 선언. 파일별로 모은다."""
    out = subprocess.run(  # noqa: S603
        ["ast-grep", "scan", "--config", str(RULES), "--json=stream", *paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ast-grep 실패: {out.stderr.strip()[:300]}")
    found: dict[str, set[tuple[str, str, int]]] = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        item = json.loads(line)
        message = item.get("message", "")
        if message not in ("def.class", "def.function"):
            continue
        name = item.get("metaVariables", {}).get("single", {}).get("NAME", {}).get("text")
        if not name:
            continue
        kind = "class" if message == "def.class" else "function"
        line_no = item["range"]["start"]["line"] + 1
        found.setdefault(item["file"], set()).add((kind, name, line_no))
    return found


def sample(root: Path, count: int, seed: int) -> list[str]:
    """표본 추출. seed를 고정해 재현한다."""
    candidates = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if ".git" not in p.parts and "node_modules" not in p.parts and ".venv" not in p.parts
    )
    rng = random.Random(seed)
    return rng.sample(candidates, min(count, len(candidates)))


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    paths = sample(root, count, seed)

    truth: dict[str, set[tuple[str, str, int]]] = {}
    unparsable = 0
    for path in list(paths):
        try:
            truth[path] = oracle_declarations((root / path).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            unparsable += 1
            paths.remove(path)

    mine = ours(root, paths)
    true_positive = false_positive = false_negative = 0
    mismatches: list[str] = []
    for path in paths:
        expected = truth.get(path, set())
        actual = mine.get(path, set())
        true_positive += len(expected & actual)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
        for item in sorted(expected - actual):
            mismatches.append(f"누락 {path} {item}")
        for item in sorted(actual - expected):
            mismatches.append(f"오검출 {path} {item}")

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    print(f"표본 {len(paths)}개 (파싱 실패로 제외 {unparsable}개), seed {seed}")
    print(f"정답 선언 {sum(len(v) for v in truth.values())}개, 추출 {sum(len(v) for v in mine.values())}개")
    print(f"precision {precision:.4f}  recall {recall:.4f}  (TP {true_positive} FP {false_positive} FN {false_negative})")
    for line in mismatches[:20]:
        print(f"  {line}")
    if len(mismatches) > 20:
        print(f"  ... 불일치 {len(mismatches)}건 중 20건만 보였다")
    return 0 if precision >= 0.98 and recall >= 0.98 else 1


if __name__ == "__main__":
    raise SystemExit(main())
