"""도메인 사실 적재와 경로 분류. 변하는 사실은 `data/`가 소유한다(C-DOMAIN-1).

경계 계약: 이 모듈은 파일 시스템의 `data/*.yml`만 읽고 저장소는 읽지 않는다.
적재는 모듈 임포트 시가 아니라 호출 시에 한다 — 상태를 읽는 함수에 캐시를 걸지
않기 위해서다(C-PY-3).
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

import yaml
from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class DomainFacts(BaseModel):
    """`data/`가 소유한 사실 묶음. 호출자는 이 형태로만 받는다(C-PY-1)."""

    extensions: dict[str, str]
    analyzed_languages: list[str]
    exclude_globs: dict[str, str]
    test_markers: list[str]
    build_files: list[str]
    kind_markers: dict[str, list[str]]


def load() -> DomainFacts:
    """`data/`의 세 파일을 읽어 한 형태로 낸다."""
    languages = yaml.safe_load((DATA_DIR / "languages.yml").read_text(encoding="utf-8"))
    exclude = yaml.safe_load((DATA_DIR / "exclude.yml").read_text(encoding="utf-8"))
    build = yaml.safe_load((DATA_DIR / "buildfiles.yml").read_text(encoding="utf-8"))
    return DomainFacts(
        extensions=languages["extensions"],
        analyzed_languages=languages["analyzed"],
        exclude_globs=exclude["globs"],
        test_markers=exclude["test_markers"],
        build_files=build["files"],
        kind_markers=build["kind_markers"],
    )


def language_of(path: str, facts: DomainFacts) -> str | None:
    """확장자로 언어를 정한다. 표에 없으면 `None`."""
    suffix = Path(path).suffix
    return facts.extensions.get(suffix)


_ANY_DIR_PREFIX = "**/"
_ANY_DIR_SUFFIX = "/**"


def _matches(path: str, glob: str) -> bool:
    """글로브 하나를 판정한다. 지원하는 형태는 둘이다.

    `**/name/**`는 경로 어디든 그 이름의 디렉토리 구획이 있으면 참이다. fnmatch의 `*`는
    구분자를 넘어 매치해서 이 형태를 그대로 넘기면 맨 앞 구획을 놓친다(`target/A.class`).
    나머지 형태는 fnmatch에 맡긴다.
    """
    if glob.startswith(_ANY_DIR_PREFIX) and glob.endswith(_ANY_DIR_SUFFIX):
        segment = glob[len(_ANY_DIR_PREFIX) : -len(_ANY_DIR_SUFFIX)]
        return segment in path.split("/")[:-1]
    return fnmatch(path, glob)


def excluded_by(path: str, facts: DomainFacts) -> str | None:
    """제외 글로브에 걸리면 그 글로브를, 아니면 `None`을 낸다."""
    for glob in facts.exclude_globs:
        if _matches(path, glob):
            return glob
    return None


def is_test(path: str, facts: DomainFacts) -> bool:
    """테스트 소스인가. 제외가 아니라 분리의 근거다."""
    probe = f"/{path}"
    return any(marker in probe for marker in facts.test_markers)
