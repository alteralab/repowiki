"""저장소의 비코드 파일을 인용 가능한 사실로 만든다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 파일 경로와 내용이고 출력은 이름 붙은 형태다. 파일을 여는 것은 호출자의
일이다.

왜 필요한가. 도메인 어휘와 운영 지식은 코드가 아니라 `README.md`와 `docs/**/*.md`와
`config/*.properties`와 CI 정의에 적혀 있다. 코드만 읽으면 구조는 보이고 뜻은 안 보인다.

두 가지를 낸다. 문서의 제목 계층과 설정의 키다. 둘 다 자리(줄 범위)를 들고 있어 인용이
된다. 본문 전체를 사실로 만들지는 않는다 — 그것은 쓰는 층이 브리핑에서 읽을 원문이다.

사각: 제목만 색인하므로 제목 없는 산문은 자리를 얻지 못한다. 설정 키는 형식별 파서 없이
줄 모양으로 읽으므로 여러 줄 값과 중첩 블록의 깊이는 이름에 반영되지 않는다.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import yaml
from pydantic import BaseModel

from repowiki.analyze.domain import DATA_DIR
from repowiki.analyze.structure import module_of
from repowiki.models import ConfigKey, CorpusFacts, FileRole, Heading, Span

# `.txt`는 문서가 아니다. `NOTICE.txt`와 `requirements.txt`는 `#`으로 시작하는 줄을 담고
# 있어 Markdown 제목으로 읽으면 라이선스 문구가 문서의 절이 된다.
_DOC_SUFFIXES = (".md", ".markdown", ".rst", ".adoc")
_CONFIG_SUFFIXES = (".properties", ".yml", ".yaml", ".toml", ".ini", ".conf", ".cfg")
_CI_MARKERS = ("/.github/workflows/", "/.gitlab-ci", "/Jenkinsfile", "/.circleci/")
_SCRIPT_SUFFIXES = (".sh", ".bash", ".bat", ".ps1")
_BUILD_NAMES = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "go.mod",
    "Cargo.toml",
    "Makefile",
    "Dockerfile",
)
_ROLE_SUFFIXES = (
    ("doc", _DOC_SUFFIXES),
    ("config", _CONFIG_SUFFIXES),
    ("script", _SCRIPT_SUFFIXES),
)
_MAX_HEADINGS = 60
# 제목의 글자 상한. 이보다 길면 제목이 아니라 문장이다.
_MAX_TITLE = 90
_MAX_KEYS = 80


class SecretRules(BaseModel):
    """자격 증명 판정 규칙. 정본은 `data/secrets.yml`이다."""

    key_markers: list[str]
    value_prefixes: list[str]
    redaction: str


def load_secret_rules() -> SecretRules:
    raw = yaml.safe_load((DATA_DIR / "secrets.yml").read_text(encoding="utf-8"))
    return SecretRules(**raw)


def mask(key: str, value: str, rules: SecretRules) -> str:
    """비밀로 보이는 값을 가린다. 값이 있었다는 사실은 남긴다.

    가리는 쪽으로 기운 판정이다. 가리지 않아야 할 값을 가리면 위키가 덜 말하고, 가려야 할
    값을 안 가리면 위키가 비밀을 퍼뜨린다. 두 실수의 값이 다르다(C-SEC-1).
    """
    lowered = key.lower()
    if any(marker in lowered for marker in rules.key_markers):
        return rules.redaction
    if any(value.startswith(prefix) for prefix in rules.value_prefixes):
        return rules.redaction
    return value


def role_of(path: str, is_test_path: bool, is_source: bool) -> str:
    """파일의 역할. 판정 순서가 곧 우선순위다.

    테스트 판정이 가장 앞이다. `tests/` 아래의 `README.md`는 문서가 아니라 테스트 자료라,
    페이지가 그것을 도메인 근거로 인용하면 틀린 말을 하게 된다.
    """
    name = PurePosixPath(path).name
    suffix = PurePosixPath(path).suffix.lower()
    if is_test_path:
        return "test"
    if any(marker in f"/{path}" for marker in _CI_MARKERS):
        return "ci"
    if name in _BUILD_NAMES or name.startswith("Dockerfile"):
        return "build"
    by_suffix = next(
        (role for role, suffixes in _ROLE_SUFFIXES if suffix in suffixes),
        None,
    )
    if by_suffix is not None:
        return by_suffix
    return "main" if is_source else "data"


def headings_of(path: str, text: str) -> list[Heading]:
    """Markdown 제목을 자리와 함께 낸다. 코드 울타리 안의 `#`은 제목이 아니다."""
    found: list[Heading] = []
    in_fence = False
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or not line.startswith("#"):
            continue
        level = len(line) - len(line.lstrip("#"))
        rest = line[level:]
        # ATX 제목은 우물 정 자 뒤에 공백이 와야 한다. `###not-a-heading`은 제목이 아니라
        # 본문이고, 그것을 절로 세면 없는 절이 근거가 된다.
        if level > 6 or (rest and not rest[:1].isspace()):
            continue
        title = rest.strip().rstrip("#").strip()
        if not title or len(title) > _MAX_TITLE:
            continue
        found.append(
            Heading(
                path=path,
                level=level,
                title=title,
                span=Span(path=path, start_line=number, end_line=number),
            )
        )
    # 절의 끝을 정한 뒤에 상한을 건다. 먼저 자르면 마지막으로 남은 제목의 절이 그 뒤의
    # 형제 제목까지 삼킨다.
    found = _with_section_ends(found, len(lines))[:_MAX_HEADINGS]
    if not found and lines:
        # 제목 없는 문서도 인용할 자리가 있어야 한다. commons-cli의 `README.md`가 그렇다 —
        # 배지와 산문만 있고 `#`이 하나도 없다. 자리를 안 주면 그 저장소의 도메인 설명을
        # 페이지가 인용할 방법이 사라진다.
        return [
            Heading(
                path=path,
                level=1,
                title=PurePosixPath(path).name,
                span=Span(path=path, start_line=1, end_line=len(lines)),
            )
        ]
    return found


def _with_section_ends(found: list[Heading], last_line: int) -> list[Heading]:
    """제목의 자리를 그 절의 끝까지 늘린다.

    제목 한 줄만 가리키는 인용은 "이 문서의 이 절"이 아니라 "이 글자들"을 가리킨다. 사람이
    링크를 눌렀을 때 읽고 싶은 것은 절이다.
    """
    for position, heading in enumerate(found):
        following = next(
            (
                later
                for later in found[position + 1 :]
                if later.level <= heading.level
            ),
            None,
        )
        end = (following.span.start_line - 1) if following is not None else last_line
        heading.span = Span(
            path=heading.path,
            start_line=heading.span.start_line,
            end_line=max(heading.span.start_line, end),
        )
    return found


def config_keys_of(path: str, text: str, rules: SecretRules | None = None) -> list[ConfigKey]:
    """설정 키를 자리와 함께 낸다. 형식별 파서 없이 줄 모양으로 읽는다.

    `a.b=c`(properties)와 `key: value`(YAML)와 `key = value`(TOML/INI)가 대상이다. 목록
    항목과 주석은 키가 아니다.
    """
    found: list[ConfigKey] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";", "-", "[")):
            continue
        key, separator, value = _split_setting(stripped)
        if not separator or not key or " " in key:
            continue
        # 값이 없는 줄은 YAML 블록을 여는 줄이다. 키만 있고 값이 없는 항목은 읽는 사람에게
        # 아무것도 말하지 않으므로 설정 사실로 세지 않는다.
        if not value.strip():
            continue
        cleaned = value.strip().strip("\"'")[:120]
        found.append(
            ConfigKey(
                path=path,
                key=key,
                value=mask(key, cleaned, rules or load_secret_rules()),
                span=Span(path=path, start_line=number, end_line=number),
            )
        )
        if len(found) >= _MAX_KEYS:
            break
    return found


def _split_setting(stripped: str) -> tuple[str, str, str]:
    """`키 구분자 값`으로 가른다. 구분자가 없으면 가운데가 빈 문자열이다."""
    for separator in ("=", ":"):
        head, found, tail = stripped.partition(separator)
        if found:
            return head.strip(), found, tail
    return stripped, "", ""


def build(
    sources: dict[str, str],
    all_paths: list[str],
    source_paths: set[str],
    test_paths: set[str],
    roots: list[str],
) -> CorpusFacts:
    """비코드 사실을 만든다. `sources`에는 문서와 설정 파일의 내용만 담겨 있으면 된다."""
    roles = [
        FileRole(
            path=path,
            role=role_of(path, path in test_paths, path in source_paths),
            module=module_of(path, roots),
        )
        for path in sorted(all_paths)
    ]
    headings: list[Heading] = []
    config_keys: list[ConfigKey] = []
    rules = load_secret_rules()
    by_role = {item.path: item.role for item in roles}
    for path in sorted(sources):
        role = by_role.get(path)
        if role == "doc":
            headings += headings_of(path, sources[path])
        elif role in ("config", "ci"):
            config_keys += config_keys_of(path, sources[path], rules)
    return CorpusFacts(roles=roles, headings=headings, config_keys=config_keys)


def citable_paths(paths: list[str], test_paths: set[str], source_paths: set[str]) -> list[str]:
    """내용을 읽어야 하는 비코드 파일. 이 목록이 곧 읽기 예산이다."""
    return sorted(
        path
        for path in paths
        if role_of(path, path in test_paths, path in source_paths) in ("doc", "config", "ci")
    )
