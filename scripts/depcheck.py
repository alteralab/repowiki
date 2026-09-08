#!/usr/bin/env python3
"""의존 상한 검사. SPEC SC-0.5의 판정 도구다.

세는 것: 런타임 직접 의존(pyproject의 `[project].dependencies`), 락이 해석한 패키지 수,
설치된 네이티브 휠 수(순수 파이썬이 아닌 것), Node 직접 의존 수.

상한을 넘으면 종료 상태 1이다(C-REPORT-5). 상한의 정본은 PLAN §8이고 이 스크립트는
그 값을 여기 적어 둔다 — 상한이 바뀌면 PLAN과 같은 커밋에서 고친다(C-COMMENT-1).

사각: 네이티브 판정은 이 기계에 설치된 것만 본다. 다른 플랫폼의 휠 구성은 Phase 5의
플랫폼별 측정이 본다.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CAPS = {
    "python_direct": 12,
    "node_direct": 20,
    "native_wheels": 15,
}


def python_direct() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def node_direct() -> list[str]:
    import json

    package = ROOT / "package.json"
    if not package.exists():
        return []
    data = json.loads(package.read_text(encoding="utf-8"))
    return sorted({*data.get("dependencies", {}), *data.get("devDependencies", {})})


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def runtime_closure() -> set[str]:
    """런타임 직접 의존에서 시작해 락의 의존 그래프를 닫는다.

    dev 그룹과 extra는 세지 않는다. 상한이 재는 것은 반입 이미지에 들어가는 집합이다.
    """
    lock = ROOT / "uv.lock"
    if not lock.exists():
        return set()
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    edges = {
        _normalize(pkg["name"]): [_normalize(dep["name"]) for dep in pkg.get("dependencies", [])]
        for pkg in data.get("package", [])
    }
    seen: set[str] = set()
    queue = [_normalize(spec.split(">")[0].split("=")[0].split("[")[0]) for spec in python_direct()]
    while queue:
        name = queue.pop()
        if name in seen or name not in edges:
            continue
        seen.add(name)
        queue.extend(edges[name])
    return seen


def resolved_packages() -> int:
    lock = ROOT / "uv.lock"
    if not lock.exists():
        return 0
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    return len(data.get("package", []))


def native_wheels(closure: set[str]) -> list[str]:
    """런타임 폐포 안에서 순수 파이썬이 아닌 배포판을 센다.

    근거는 설치된 WHEEL의 `Root-Is-Purelib: false`다. dev 그룹과 extra의 네이티브 휠은
    반입 이미지에 없으므로 폐포 밖은 세지 않는다.
    """
    found: list[str] = []
    for site in (ROOT / ".venv").rglob("site-packages"):
        for wheel in site.glob("*.dist-info/WHEEL"):
            name = _normalize(wheel.parent.name.split("-")[0])
            if name not in closure:
                continue
            text = wheel.read_text(encoding="utf-8", errors="replace")
            if "Root-Is-Purelib: false" in text:
                found.append(name)
    return sorted(set(found))


def main() -> int:
    direct = python_direct()
    node = node_direct()
    closure = runtime_closure()
    native = native_wheels(closure)
    counts = {
        "python_direct": len(direct),
        "node_direct": len(node),
        "native_wheels": len(native),
    }
    print(f"해석 패키지(락 전체): {resolved_packages()}개, 런타임 폐포: {len(closure)}개")
    failed = False
    for key, cap in CAPS.items():
        value = counts[key]
        mark = "초과" if value > cap else "이내"
        print(f"{key}: {value}개 (상한 {cap}) {mark}")
        if value > cap:
            failed = True
    if native:
        print(f"네이티브: {', '.join(native)}")
    if failed:
        print("상한을 넘었다. PLAN §8의 추가 검사 목록을 통과했는지 확인하라.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
