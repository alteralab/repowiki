"""TypeScript 모듈 해석. 임포트 문자열을 저장소 안의 파일로 푼다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 tsconfig 내용과 추적 파일 목록이고 출력은 이름 붙은 형태다. 파일을 여는
것은 호출자의 일이다.

왜 별도 모듈인가. 자바 계열의 해석은 "패키지 선언 + 임포트 + 같은 패키지"다. TypeScript에는
패키지 선언이 없고 임포트의 뜻이 **파일 경로**로 정해진다. `graph.py`의 `NameScope`를 그대로
쓰면 `./lib`과 `@app/core`에 점 이름 규칙을 적용하게 되고, 모듈 지역 유일성 폴백이 우연한
이름 일치를 사실로 승격한다. 엣지 0개를 그럴듯한 오답 엣지로 바꾸는 것이 그것이다.

해석은 경로 산술이다. 타입 추론이 아니다. 상대 경로를 잇고, tsconfig의 `paths` 무늬를
치환하고, `baseUrl`을 앞에 붙이고, 확장자와 `index` 후보를 순서대로 시험한다. 이 넷으로
실제 저장소 임포트의 대부분이 풀린다(2026-09-09 airflow 실측: 저장소 안 임포트 2,682건 중
별칭·절대가 58%, 상대가 42%).

사각 넷. `package.json`의 `exports`와 `imports` 조건부 해석은 하지 않는다. project reference의
`outDir` 되짚기는 하지 않는다. `.d.ts`의 앰비언트 선언과 전역 선언은 보지 않는다. 그리고
재수출을 따라 원 선언까지 가는 일은 이 모듈이 아니라 수출 표의 일이다.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

# 확장자를 붙여 시험하는 순서. TypeScript 자신의 순서를 따른다 — `.ts`가 `.tsx`보다 앞이고
# `.d.ts`가 마지막이다. 순서가 곧 우선순위라 바꾸면 다른 파일로 풀린다.
_SUFFIXES = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mts", ".cts")
_INDEX_STEMS = ("index",)
# 이 확장자를 가진 파일만 모듈이 된다.
_MODULE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")


class TsConfig(BaseModel):
    """tsconfig 하나가 정하는 해석 규칙. `directory`는 그 파일이 놓인 디렉토리다."""

    path: str
    directory: str
    base_url: str | None = None
    paths: dict[str, list[str]] = Field(default_factory=dict)
    extends: str | None = None
    references: list[str] = Field(default_factory=list)


class Resolution(BaseModel):
    """임포트 하나의 해석 결과. `target`이 비면 저장소 밖이거나 풀지 못한 것이다."""

    specifier: str
    from_path: str
    target: str = ""
    kind: str


def parse_jsonc(text: str) -> dict:
    """주석과 후행 쉼표가 있는 JSON을 읽는다.

    tsconfig는 JSON이 아니라 JSONC다. 표준 파서로는 못 읽고, 못 읽었다고 건너뛰면 그
    저장소의 별칭을 통째로 잃는다. 문자열 안의 슬래시를 주석으로 오인하지 않도록 한 번만
    훑는다.
    """
    out: list[str] = []
    quote = ""
    escaped = False
    position = 0
    while position < len(text):
        character = text[position]
        if quote:
            out.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            position += 1
            continue
        if character in "\"'":
            quote = character
            out.append(character)
            position += 1
            continue
        if text.startswith("//", position):
            end = text.find("\n", position)
            position = len(text) if end == -1 else end
            continue
        if text.startswith("/*", position):
            end = text.find("*/", position + 2)
            position = len(text) if end == -1 else end + 2
            continue
        out.append(character)
        position += 1
    cleaned = _drop_trailing_commas("".join(out))
    return json.loads(cleaned) if cleaned.strip() else {}


def _drop_trailing_commas(text: str) -> str:
    """`,` 뒤에 닫는 괄호만 오는 자리를 지운다. 문자열 안은 건드리지 않는다."""
    out: list[str] = []
    quote = ""
    escaped = False
    for position, character in enumerate(text):
        if quote:
            out.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
            out.append(character)
            continue
        if character == ",":
            rest = text[position + 1 :].lstrip()
            if rest[:1] in ("}", "]"):
                continue
        out.append(character)
    return "".join(out)


def load_configs(sources: dict[str, str]) -> list[TsConfig]:
    """tsconfig 파일 내용에서 규칙을 읽는다. 못 읽는 파일은 건너뛰고 세지 않는다."""
    found: list[TsConfig] = []
    for path in sorted(sources):
        try:
            data = parse_jsonc(sources[path])
        except (json.JSONDecodeError, ValueError):
            continue
        options = data.get("compilerOptions") or {}
        found.append(
            TsConfig(
                path=path,
                directory=str(PurePosixPath(path).parent),
                base_url=options.get("baseUrl"),
                paths={k: list(v) for k, v in (options.get("paths") or {}).items()},
                extends=data.get("extends"),
                references=[
                    str(item.get("path", "")) for item in (data.get("references") or [])
                ],
            )
        )
    return found


def _join(base: str, relative: str) -> str:
    """POSIX 경로를 잇고 `.`과 `..`을 편다. 뿌리 밖으로 나가면 빈 문자열이다."""
    parts: list[str] = []
    for piece in PurePosixPath(base).joinpath(relative).parts:
        if piece == "..":
            if not parts:
                return ""
            parts.pop()
        elif piece != ".":
            parts.append(piece)
    return "/".join(parts)


class Resolver(BaseModel):
    """저장소 하나의 TypeScript 모듈 해석기.

    `files`는 추적 파일 전부다. 후보를 만들 때마다 이 집합에 있는지 보는 것이 해석의 전부라,
    파일 시스템을 다시 묻지 않는다.
    """

    files: set[str] = Field(default_factory=set)
    # 규칙이 걸리는 디렉토리에서 그 규칙으로. 긴 경로가 먼저 걸리도록 정렬해 둔다.
    rules: list[TsConfig] = Field(default_factory=list)

    def rule_for(self, from_path: str) -> TsConfig | None:
        """이 파일에 적용되는 tsconfig. 가장 가까운 조상의 것이고, 규칙이 가장 많은 것이다.

        한 저장소에 tsconfig가 여럿이다(airflow는 UI, ts-sdk, 플러그인마다 따로 있다).
        게다가 한 디렉토리에도 `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`이
        함께 있고 별칭은 그중 하나에만 적혀 있다. 먼저 나온 것을 고르면 별칭이 없는 파일이
        걸려 그 디렉토리 전체의 별칭을 잃는다.
        """
        directory = str(PurePosixPath(from_path).parent)
        while True:
            here = [
                rule
                for rule in self.rules
                if rule.directory == directory and (rule.paths or rule.base_url)
            ]
            if here:
                return max(here, key=lambda rule: (len(rule.paths), rule.path))
            if directory in ("", "."):
                return None
            parent = str(PurePosixPath(directory).parent)
            if parent == directory:
                return None
            directory = parent

    def probe(self, candidate: str) -> str:
        """후보 경로에 확장자와 `index`를 붙여 실제 파일을 찾는다. 없으면 빈 문자열이다."""
        if not candidate:
            return ""
        stem = candidate
        suffix = PurePosixPath(candidate).suffix
        if suffix in (".js", ".jsx", ".mjs", ".cjs"):
            # `./a.js`로 적고 `./a.ts`가 있는 경우. NodeNext의 관례라 실제 `.js` 파일보다
            # 먼저 본다. 두 파일이 다 있으면 소스가 `.ts` 쪽이다.
            stem = candidate.rsplit(".", 1)[0]
            found = self._first(stem, (".ts", ".tsx", ".mts", ".cts"))
            if found:
                return found
        if suffix in _MODULE_SUFFIXES and candidate in self.files:
            return candidate
        return self._first(stem, _SUFFIXES) or self._first_index(stem)

    def _first(self, stem: str, suffixes: tuple[str, ...]) -> str:
        """확장자를 순서대로 붙여 처음 있는 파일. 순서가 곧 우선순위다."""
        for suffix in suffixes:
            found = f"{stem}{suffix}"
            if found in self.files:
                return found
        return ""

    def _first_index(self, stem: str) -> str:
        """디렉토리 안의 `index` 파일. 디렉토리를 가리키는 임포트가 이것으로 풀린다."""
        for index in _INDEX_STEMS:
            found = self._first(f"{stem}/{index}", _SUFFIXES)
            if found:
                return found
        return ""

    def resolve(self, specifier: str, from_path: str) -> Resolution:
        """임포트 문자열 하나를 푼다.

        순서는 TypeScript의 순서다. 상대 경로가 먼저이고, 그다음이 `paths` 무늬, 그다음이
        `baseUrl`이다. 셋 다 아니면 저장소 밖의 패키지다.
        """
        if specifier.startswith("."):
            base = str(PurePosixPath(from_path).parent)
            target = self.probe(_join(base, specifier))
            kind = "relative" if target else "unresolved-relative"
            return Resolution(
                specifier=specifier, from_path=from_path, target=target, kind=kind
            )

        rule = self.rule_for(from_path)
        if rule is not None:
            target = self._by_paths(specifier, rule)
            if target:
                return Resolution(
                    specifier=specifier, from_path=from_path, target=target, kind="alias"
                )
            target = self._by_base_url(specifier, rule)
            if target:
                return Resolution(
                    specifier=specifier, from_path=from_path, target=target, kind="base-url"
                )
        return Resolution(specifier=specifier, from_path=from_path, kind="external")

    def _by_paths(self, specifier: str, rule: TsConfig) -> str:
        """`paths` 무늬 치환. 별표 하나만 다루는 것이 TypeScript의 규칙이다.

        무늬가 여럿 걸리면 별표 앞이 긴 것이 이긴다. `*`는 무엇이든 걸리므로 마지막이다.
        """
        root = _join(rule.directory, rule.base_url or ".")
        for pattern in sorted(rule.paths, key=lambda p: (-len(p.split("*")[0]), p)):
            prefix, star, suffix = pattern.partition("*")
            if star:
                if not (specifier.startswith(prefix) and specifier.endswith(suffix)):
                    continue
                middle = specifier[len(prefix) : len(specifier) - len(suffix) or None]
            elif specifier != pattern:
                continue
            else:
                middle = ""
            for template in rule.paths[pattern]:
                candidate = template.replace("*", middle) if star else template
                target = self.probe(_join(root, candidate))
                if target:
                    return target
        return ""

    def _by_base_url(self, specifier: str, rule: TsConfig) -> str:
        """`baseUrl` 아래에서 찾는다. `baseUrl`이 없으면 하지 않는다."""
        if rule.base_url is None:
            return ""
        return self.probe(_join(_join(rule.directory, rule.base_url), specifier))


def build(configs: list[TsConfig], files: list[str]) -> Resolver:
    """해석기 하나를 만든다. 규칙은 `extends`를 따라 합친다."""
    by_path = {rule.path: rule for rule in configs}
    merged: list[TsConfig] = []
    for rule in configs:
        merged.append(_with_inherited(rule, by_path, set()))
    # 깊은 디렉토리가 먼저 걸리게 둔다. `rule_for`가 가까운 조상부터 본다.
    merged.sort(key=lambda rule: (-len(rule.directory.split("/")), rule.path))
    return Resolver(files=set(files), rules=merged)


def _with_inherited(
    rule: TsConfig, by_path: dict[str, TsConfig], seen: set[str]
) -> TsConfig:
    """`extends`가 가리키는 규칙을 물려받는다. 자기 값이 이기고 고리는 멈춘다."""
    if rule.extends is None or rule.path in seen:
        return rule
    parent_path = _join(rule.directory, rule.extends)
    parent = by_path.get(parent_path) or by_path.get(f"{parent_path}.json")
    if parent is None:
        return rule
    inherited = _with_inherited(parent, by_path, seen | {rule.path})
    return rule.model_copy(
        update={
            "base_url": rule.base_url if rule.base_url is not None else inherited.base_url,
            "paths": {**inherited.paths, **rule.paths},
        }
    )
