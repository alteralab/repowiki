#!/usr/bin/env python3
"""의존 상한 검사. SPEC SC-0.5의 판정 도구다.

세는 것: 런타임 직접 의존(pyproject의 `[project].dependencies`), 락이 해석한 패키지 수,
설치된 네이티브 휠 수(순수 파이썬이 아닌 것), Node 직접 의존 수.

**쓰이지 않는 직접 의존도 잡는다.** 개수만 세면 상한 안이라는 이유로 죽은 의존이 남고,
그것이 없는 기능을 있는 것처럼 보이게 한다. 공급망 검토 표면도 함께 늘어난다.

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


# 임포트 이름이 배포 이름과 다른 것들. 자동으로 알 길이 없어 여기 적는다.
# 새 의존을 더할 때 이름이 다르면 여기도 함께 고친다(C-COMMENT-1).
IMPORT_NAMES = {
    "ast-grep-cli": "ast_grep_cli",
    "python-hcl2": "hcl2",
    "dockerfile-parse": "dockerfile_parse",
    "langgraph-checkpoint-sqlite": "langgraph.checkpoint.sqlite",
    "langchain-core": "langchain_core",
    "PyYAML": "yaml",
}
# 파이썬으로 임포트하지 않고 명령으로 부르는 의존. 어댑터가 `subprocess`로 쓴다.
CALLED_AS_COMMAND = {"ast-grep-cli"}
# 우리가 임포트하지 않고 다른 라이브러리를 통해 기대는 의존. 왜 필요한지를 값에 적는다.
# 여기 적는 것은 "그 라이브러리가 알아서 끌어오겠지"에 기대지 않겠다는 선언이다 — 실제로
# `numpy`는 `langchain-core`가 우연히 끌어와 동작하다가 그 의존을 빼자 랭킹이 깨졌다.
USED_THROUGH = {
    "numpy": "networkx 3.x 의 pagerank 가 numpy 배열로 계산한다",
    "scipy": "networkx 3.x 의 pagerank 가 scipy 희소 행렬로 계산한다",
}


def _requirement_name(spec: str) -> str:
    """`pkg==1.2.3 ; marker`에서 배포 이름만."""
    head = spec.split(";", 1)[0]
    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
        head = head.split(separator, 1)[0]
    return head.strip()


def unused_direct(direct: list[str]) -> list[str]:
    """제품 코드가 임포트하지 않는 직접 의존.

    `src/` 전체를 문자열로 훑는다. 임포트 형태가 여럿이라 AST로 세는 것보다 정확도가
    높지는 않지만, "어디에도 이름이 안 나온다"는 판정에는 충분하고 오탐이 없는 쪽이다.
    """
    sources = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((ROOT / "src").rglob("*.py"))
    )
    found: list[str] = []
    for spec in direct:
        name = _requirement_name(spec)
        if name in CALLED_AS_COMMAND or name in USED_THROUGH:
            continue
        module = IMPORT_NAMES.get(name, name.replace("-", "_"))
        root = module.split(".", 1)[0]
        if root not in sources:
            found.append(name)
    return found


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
    for name, reason in sorted(USED_THROUGH.items()):
        if any(_requirement_name(spec) == name for spec in direct):
            print(f"간접 사용: {name} — {reason}")

    unused = unused_direct(direct)
    if unused:
        print(f"쓰이지 않는 직접 의존 {len(unused)}개: {', '.join(unused)}", file=sys.stderr)
        print(
            "제품 코드가 임포트하지 않는다. 그 기능이 들어오는 커밋에서 함께 더한다.",
            file=sys.stderr,
        )
        failed = True

    if failed:
        print("상한을 넘었다. PLAN §8의 추가 검사 목록을 통과했는지 확인하라.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
