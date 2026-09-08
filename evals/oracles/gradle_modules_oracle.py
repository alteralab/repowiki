#!/usr/bin/env python3
"""모듈 경계의 오라클 대조. 정답은 빌드 도구 자신의 선언이다.

Gradle은 `settings.gradle`의 `include`가, Maven은 `pom.xml`의 `<module>`이 그 저장소의
모듈을 선언한다. 사람이 목록을 만들지 않는다(PLAN §6 3).

사용법:
    uv run python evals/oracles/gradle_modules_oracle.py <저장소 경로>

사각: `include`를 변수나 반복문으로 만드는 빌드 파일은 이 방식으로 못 읽는다. 그런
저장소는 표본에서 빼고 그 사실을 보고한다 — 조용히 0으로 세지 않는다(C-REPORT-2).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from repowiki.adapters import git  # noqa: E402
from repowiki.analyze import domain, structure  # noqa: E402

# Groovy 문법을 읽는 것이 아니라 include 블록 안의 문자열 리터럴만 본다.
# ast-grep-ignore: regex-on-structure — 어휘: 작은따옴표로 둘러싼 토큰 하나를 뽑는 문자집합 판정이다.
_QUOTED = re.compile(r"'([^']+)'")


def gradle_modules(root: Path) -> set[str] | None:
    """`settings.gradle`의 include 선언. 파일이 없으면 `None`."""
    for name in ("settings.gradle", "settings.gradle.kts"):
        settings = root / name
        if not settings.exists():
            continue
        text = settings.read_text(encoding="utf-8", errors="replace")
        if "include" not in text:
            return None
        block = text.split("include", 1)[1].split("project(", 1)[0]
        declared = {
            item.replace(":", "/").strip("/")
            for item in _QUOTED.findall(block)
            # 판 번호, 플러그인 좌표, 환경 변수 이름은 모듈이 아니다. include 블록에
            # 섞여 있는 리터럴을 그대로 세면 정답이 부풀려진다.
            if item
            and not item[0].isdigit()
            and "." not in item.split(":")[0]
            and not item.isupper()
        }
        return {item for item in declared if item}
    return None


def maven_modules(root: Path) -> set[str]:
    """`pom.xml`의 `<module>` 선언을 재귀로 모은다."""
    found: set[str] = set()
    for pom in root.rglob("pom.xml"):
        if any(part in (".git", "target") for part in pom.parts):
            continue
        try:
            tree = ElementTree.parse(pom)
        except ElementTree.ParseError:
            continue
        prefix = pom.parent.relative_to(root).as_posix().strip(".")
        for element in tree.iter():
            if element.tag.endswith("}module") or element.tag == "module":
                name = (element.text or "").strip()
                if name:
                    found.add(f"{prefix}/{name}".strip("/"))
    return found


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    facts = domain.load()
    tracked = git.tracked_files(root)
    kept, _ = structure.source_paths(tracked, facts)
    counts = dict.fromkeys(kept, 1)
    roots = structure.module_roots(kept, facts)
    detected = {m.id for m in structure.build_modules(kept, roots, counts, facts) if m.id != "."}

    declared = gradle_modules(root)
    source = "settings.gradle"
    if declared is None:
        declared = maven_modules(root)
        source = "pom.xml"
    if not declared:
        print("빌드 선언에서 모듈 목록을 읽지 못했다. 이 저장소는 이 대조의 대상이 아니다.")
        return 2

    hit = detected & declared
    precision = len(hit) / len(detected) if detected else 0.0
    recall = len(hit) / len(declared) if declared else 0.0
    print(f"정답 원천 {source}, 선언 {len(declared)}개, 감지 {len(detected)}개, 일치 {len(hit)}개")
    print(f"precision {precision:.4f}  recall {recall:.4f}")
    missed = sorted(declared - detected)
    extra = sorted(detected - declared)
    if missed:
        print(f"선언에만 있는 모듈 {len(missed)}개: {missed[:10]}")
    if extra:
        print(f"감지에만 있는 모듈 {len(extra)}개: {extra[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
