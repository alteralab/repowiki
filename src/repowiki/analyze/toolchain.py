"""도구 사슬 사실: 언어 버전과 라이브러리 버전. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 빌드 파일의 경로와 내용이고 출력은 이름 붙은 형태다. 파일을 여는 것은
호출자의 일이다.

버전은 저장소가 스스로 적어 둔 자리에서만 읽는다. `pom.xml`의 컴파일러 속성,
`pyproject.toml`의 `requires-python`, `package.json`의 `engines`, `go.mod`의 `go` 줄이
그런 자리다. 잠금 파일(`package-lock.json`, `uv.lock`)은 보지 않는다 — 잠금은 이 기계가
설치한 결과이고 저장소가 선언한 계약이 아니다.

파서는 줄 단위 훑기다. XML이나 TOML 파서를 쓰지 않는 이유는 하나다. 근거에는 줄 번호가
있어야 하는데 그 파서들은 줄 번호를 주지 않는다.

사각: 선언만 읽는다. 실제로 어떤 버전이 해석되어 설치되는지는 보지 못한다. 상속받은 부모
POM이 저장소 밖에 있으면 그 속성은 풀리지 않고 `${...}` 그대로 남는다.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from repowiki.analyze.structure import module_of
from repowiki.models import Dependency, Span, ToolchainFacts, ToolVersion

_MAX_DEPENDENCIES = 400
_GRADLE_CONFIGS = (
    "implementation",
    "api",
    "compileOnly",
    "runtimeOnly",
    "testImplementation",
    "testRuntimeOnly",
    "testCompileOnly",
    "annotationProcessor",
    "developmentOnly",
)
_PY_SPEC_BREAKS = "<>=!~^[; (@"


def _span(path: str, line: int) -> Span:
    return Span(path=path, start_line=line, end_line=line)


def _tag(line: str, name: str) -> str | None:
    """`<name>값</name>`에서 값만 꺼낸다. 한 줄 안에 닫히지 않으면 `None`이다."""
    opening, closing = f"<{name}>", f"</{name}>"
    start = line.find(opening)
    if start == -1:
        return None
    end = line.find(closing, start)
    if end == -1:
        return None
    return line[start + len(opening) : end].strip()


def _any_tag(line: str) -> tuple[str, str] | None:
    """줄이 `<이름>값</이름>` 하나뿐이면 그 짝을 낸다."""
    stripped = line.strip()
    if not stripped.startswith("<") or "</" not in stripped:
        return None
    name = stripped[1 : stripped.find(">")] if ">" in stripped else ""
    if not name or " " in name:
        return None
    value = _tag(stripped, name)
    return None if value is None else (name, value)


_MAVEN_LANGUAGE_KEYS = {
    "maven.compiler.release": "Java",
    "maven.compiler.source": "Java",
    "maven.compiler.target": "Java",
    "java.version": "Java",
    "kotlin.version": "Kotlin",
    "scala.version": "Scala",
}


def _maven_properties(text: str) -> dict[str, str]:
    """`<properties>` 안의 값을 표로 만든다. `${...}` 해석에 쓴다."""
    table: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("<properties>"):
            inside = True
            continue
        if stripped.startswith("</properties>"):
            inside = False
            continue
        if not inside:
            continue
        pair = _any_tag(stripped)
        if pair is not None:
            table[pair[0]] = pair[1]
    return table


def _resolve(value: str, properties: dict[str, str]) -> str:
    """`${key}` 하나를 푼다. 표에 없으면 적힌 그대로 남긴다."""
    if not value.startswith("${") or not value.endswith("}"):
        return value
    return properties.get(value[2:-1], value)


def _maven_languages(path: str, text: str, merged: dict[str, str], module: str):
    """POM의 컴파일러 속성에서 언어 버전만 꺼낸다."""
    found: list[ToolVersion] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        for key, language in _MAVEN_LANGUAGE_KEYS.items():
            value = _tag(stripped, key)
            if value:
                found.append(
                    ToolVersion(
                        language=language,
                        version=_resolve(value, merged),
                        source=key,
                        module=module,
                        span=_span(path, number),
                    )
                )
    return found


_MAVEN_COORDINATE_TAGS = ("groupId", "artifactId", "version", "scope")


def _management_delta(stripped: str) -> int:
    """`<dependencyManagement>` 깊이의 변화. 여는 줄이 1이고 닫는 줄이 -1이다."""
    if stripped.startswith("<dependencyManagement>"):
        return 1
    if stripped.startswith("</dependencyManagement>"):
        return -1
    return 0


def _maven_dependencies(path: str, text: str, merged: dict[str, str], module: str):
    """POM의 의존 블록을 훑는다.

    `<dependencyManagement>` 안의 항목은 의존이 아니라 버전 정책이라 목록에 넣지 않고
    버전 표로만 쓴다. 그것을 의존으로 세면 부모 POM 하나가 저장소 전체의 의존이 된다.
    """
    dependencies: list[Dependency] = []
    managed: dict[str, str] = {}
    in_management = 0
    block: dict[str, str] = {}
    block_line = 0
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        in_management += _management_delta(stripped)
        if stripped.startswith("<dependency>"):
            block, block_line = {}, number
        elif stripped.startswith("</dependency>"):
            entry = _maven_entry(block, merged, module, _span(path, block_line))
            if entry is None:
                block = {}
            elif in_management > 0:
                managed.setdefault(entry.name, entry.version)
                block = {}
            else:
                dependencies.append(entry)
                block = {}
        else:
            pair = _any_tag(stripped)
            if pair is not None and pair[0] in _MAVEN_COORDINATE_TAGS:
                block[pair[0]] = pair[1]
    for dependency in dependencies:
        if not dependency.version:
            dependency.version = managed.get(dependency.name, "")
    return dependencies


def _maven_entry(
    block: dict[str, str], merged: dict[str, str], module: str, span: Span
) -> Dependency | None:
    """의존 블록 하나를 형태로 만든다. 좌표가 없으면 `None`이다."""
    group = _resolve(block.get("groupId", ""), merged)
    artifact = _resolve(block.get("artifactId", ""), merged)
    if not group or not artifact:
        return None
    return Dependency(
        name=f"{group}:{artifact}",
        version=_resolve(block.get("version", ""), merged),
        scope=block.get("scope", "compile"),
        ecosystem="maven",
        module=module,
        span=span,
    )


def _maven(path: str, text: str, properties: dict[str, str], module: str):
    """POM 하나에서 언어 버전과 의존을 꺼낸다."""
    merged = dict(properties)
    merged.update(_maven_properties(text))
    return _maven_languages(path, text, merged, module), _maven_dependencies(
        path, text, merged, module
    )


def _quoted(line: str) -> list[str]:
    """줄 안의 따옴표 문자열 전부. 한 번만 훑는다.

    홑따옴표와 겹따옴표를 따로 훑으면 안 된다. `"pkg; python_version < \'3.12\'"`처럼
    한 문자열 안에 다른 따옴표가 들어 있으면 그 안쪽이 별개의 값으로 잡히고, 위키에 `3.12`
    라는 없는 패키지가 실린다.
    """
    found: list[str] = []
    quote = ""
    buffer: list[str] = []
    escaped = False
    for character in line:
        if quote:
            if escaped:
                buffer.append(character)
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                found.append("".join(buffer))
                quote, buffer = "", []
            else:
                buffer.append(character)
        elif character in "\"'":
            quote, buffer, escaped = character, [], False
    return found


def _gradle(path: str, text: str, module: str):
    """Gradle 빌드 스크립트. 좌표 문자열과 툴체인 선언만 본다."""
    languages: list[ToolVersion] = []
    dependencies: list[Dependency] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        for marker, language in (
            ("sourceCompatibility", "Java"),
            ("targetCompatibility", "Java"),
            ("JavaLanguageVersion.of(", "Java"),
            ("jvmToolchain(", "Java"),
        ):
            if marker not in stripped:
                continue
            value = _gradle_version(stripped, marker)
            if value:
                languages.append(
                    ToolVersion(
                        language=language,
                        version=value,
                        source=marker.rstrip("(."),
                        module=module,
                        span=_span(path, number),
                    )
                )
        configuration = stripped.split("(")[0].split(" ")[0].strip()
        if configuration not in _GRADLE_CONFIGS or "project(" in stripped:
            continue
        for literal in _quoted(stripped):
            parts = literal.split(":")
            if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
                continue
            dependencies.append(
                Dependency(
                    name=f"{parts[0]}:{parts[1]}",
                    version=parts[2] if len(parts) == 3 else "",
                    scope=configuration,
                    ecosystem="gradle",
                    module=module,
                    span=_span(path, number),
                )
            )
    return languages, dependencies


def _gradle_version(line: str, marker: str) -> str:
    """`sourceCompatibility = JavaVersion.VERSION_11`이나 `of(17)`에서 숫자만."""
    if marker.endswith("("):
        start = line.find(marker) + len(marker)
        end = line.find(")", start)
        return line[start:end].strip().strip("\"'") if end != -1 else ""
    tail = line.split("=", 1)[1].strip() if "=" in line else ""
    if not tail:
        return ""
    tail = tail.strip("\"'")
    return tail.rsplit("_", 1)[-1] if "VERSION_" in tail else tail


def _catalog_entry(value: str, versions: dict[str, str]) -> tuple[str, str]:
    """카탈로그 한 줄에서 좌표와 버전을 꺼낸다. 근거가 없으면 버전은 빈 문자열이다.

    `module = "g:a"`와 `group = "g", name = "a"` 두 형태를 모두 읽는다. 버전은 `version`이
    적혀 있거나 `version.ref`가 `[versions]`에 있을 때만 채운다 — 값의 모양만 보고 고르면
    `classifier = "docs.api"` 같은 것이 버전 칸에 들어간다.
    """
    module = _keyed(value, "module")
    if not module:
        group, name = _keyed(value, "group"), _keyed(value, "name")
        module = f"{group}:{name}" if group and name else ""
    reference = _keyed(value, "version.ref")
    if reference:
        return module, versions.get(reference, "")
    return module, _keyed(value, "version")


def _keyed(value: str, key: str) -> str:
    """`key = "값"` 또는 `key.ref = "값"`에서 값만. 없으면 빈 문자열이다."""
    marker = f"{key} ="
    position = value.find(marker)
    if position == -1:
        marker = f"{key}="
        position = value.find(marker)
        if position == -1:
            return ""
    return next(iter(_quoted(value[position + len(marker) :])), "")


def _version_catalog(path: str, text: str, module: str) -> list[Dependency]:
    """`gradle/libs.versions.toml`. `[versions]`를 풀어 `[libraries]`에 붙인다."""
    versions: dict[str, str] = {}
    dependencies: list[Dependency] = []
    section = ""
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key, value = key.strip(), value.strip()
        if section == "versions":
            versions[key] = next(iter(_quoted(value)), value.strip("\"'"))
            continue
        if section != "libraries":
            continue
        name, pinned = _catalog_entry(value, versions)
        if name:
            dependencies.append(
                Dependency(
                    name=name,
                    version=pinned,
                    scope="catalog",
                    ecosystem="gradle",
                    module=module,
                    span=_span(path, number),
                )
            )
    return dependencies


def _python_name(spec: str) -> tuple[str, str]:
    """PEP 508 요구사항을 이름과 버전 제약으로 가른다.

    `requests[security]>=2; python_version<"3.12"`의 버전 제약은 `>=2`뿐이다. extras와 환경
    표식을 버전 칸에 넣으면 버전 표가 버전이 아닌 것을 버전이라고 말한다.
    """
    text = spec.strip().strip(",")
    # 환경 표식은 세미콜론 뒤다. 버전이 아니다.
    text = text.split(";", 1)[0].strip()
    name = text
    for position, character in enumerate(text):
        if character in _PY_SPEC_BREAKS:
            name = text[:position]
            break
    name = name.strip()
    rest = text[len(name) :].strip()
    # extras는 대괄호 안이다. 버전이 아니다.
    if rest.startswith("["):
        closing = rest.find("]")
        rest = rest[closing + 1 :].strip() if closing != -1 else ""
    return name, rest


def _pyproject_array(path: str, stripped: str, number: int, scope: str, module: str):
    """의존 배열의 한 줄에서 항목을 꺼낸다."""
    found: list[Dependency] = []
    for literal in _quoted(stripped):
        name, constraint = _python_name(literal)
        if name:
            found.append(
                Dependency(
                    name=name,
                    version=constraint,
                    scope=scope,
                    ecosystem="pypi",
                    module=module,
                    span=_span(path, number),
                )
            )
    return found


def _dependency_group(section: str, key: str) -> str:
    """이 키가 어떤 의존 묶음인지. 의존 묶음이 아니면 빈 문자열이다."""
    if section == "project" and key == "dependencies":
        return "main"
    if section.endswith("optional-dependencies") or section.endswith("dependency-groups"):
        return key
    return ""


def _pyproject_array_scope(section: str, stripped: str) -> str:
    """이 줄이 **여러 줄에 걸쳐** 여는 배열이 어떤 의존 묶음인지. 아니면 빈 문자열이다."""
    if not stripped.endswith("[") or "=" not in stripped:
        return ""
    return _dependency_group(section, stripped.split("=", 1)[0].strip())


def _pyproject_inline_array(section: str, stripped: str) -> str:
    """한 줄에서 열고 닫는 배열(`api = ["x==1"]`)의 묶음 이름. 아니면 빈 문자열이다."""
    if "= [" not in stripped or not stripped.rstrip().endswith("]"):
        return ""
    return _dependency_group(section, stripped.split("=", 1)[0].strip())


def _poetry_line(path: str, stripped: str, number: int, module: str):
    """`[tool.poetry.dependencies]` 한 줄. `python` 키만 언어다."""
    key = stripped.split("=", 1)[0].strip()
    value = next(iter(_quoted(stripped)), "")
    if key == "python":
        return [
            ToolVersion(
                language="Python",
                version=value,
                source="tool.poetry.dependencies.python",
                module=module,
                span=_span(path, number),
            )
        ], []
    return [], [
        Dependency(
            name=key,
            version=value,
            scope="main",
            ecosystem="pypi",
            module=module,
            span=_span(path, number),
        )
    ]


def _pyproject(path: str, text: str, module: str):
    """`pyproject.toml`. `requires-python`과 의존 배열만 본다."""
    languages: list[ToolVersion] = []
    dependencies: list[Dependency] = []
    section = ""
    array_scope = ""
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]") and "=" not in stripped:
            section, array_scope = stripped[1:-1], ""
        elif array_scope:
            array_scope = "" if stripped.startswith("]") else array_scope
            if array_scope:
                dependencies += _pyproject_array(path, stripped, number, array_scope, module)
        else:
            found, deps, array_scope = _pyproject_line(path, stripped, number, section, module)
            languages += found
            dependencies += deps
    return languages, dependencies


def _pyproject_line(path: str, stripped: str, number: int, section: str, module: str):
    """배열 밖의 줄 하나. 여는 배열이면 그 묶음 이름을 셋째 값으로 낸다."""
    if stripped.startswith("requires-python"):
        value = next(iter(_quoted(stripped)), "")
        found = (
            [
                ToolVersion(
                    language="Python",
                    version=value,
                    source="requires-python",
                    module=module,
                    span=_span(path, number),
                )
            ]
            if value
            else []
        )
        return found, [], ""
    inline = _pyproject_inline_array(section, stripped)
    if inline:
        return [], _pyproject_array(path, stripped, number, inline, module), ""
    opened = _pyproject_array_scope(section, stripped)
    if opened:
        return [], [], opened
    if section.endswith("poetry.dependencies") and "=" in stripped:
        found, deps = _poetry_line(path, stripped, number, module)
        return found, deps, ""
    return [], [], ""


_NPM_SCOPES = {
    "dependencies": "main",
    "devDependencies": "dev",
    "peerDependencies": "peer",
    "optionalDependencies": "optional",
}


def _package_json(path: str, text: str, module: str):
    """`package.json`. 중괄호 깊이로 구역을 가른다 — 값에는 줄 번호가 필요하다."""
    languages: list[ToolVersion] = []
    dependencies: list[Dependency] = []
    scope = ""
    in_engines = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("}"):
            scope, in_engines = "", False
            continue
        key = next(iter(_quoted(stripped)), "")
        if stripped.endswith("{"):
            if key == "engines":
                in_engines = True
            elif key in _NPM_SCOPES:
                scope = _NPM_SCOPES[key]
            else:
                scope, in_engines = "", False
            continue
        literals = _quoted(stripped)
        if len(literals) < 2:
            continue
        if in_engines:
            languages.append(
                ToolVersion(
                    language=literals[0].capitalize(),
                    version=literals[1],
                    source="engines",
                    module=module,
                    span=_span(path, number),
                )
            )
        elif scope:
            dependencies.append(
                Dependency(
                    name=literals[0],
                    version=literals[1],
                    scope=scope,
                    ecosystem="npm",
                    module=module,
                    span=_span(path, number),
                )
            )
    return languages, dependencies


def _go_mod(path: str, text: str, module: str):
    """`go.mod`. `go` 줄이 언어 버전이고 `require`가 의존이다."""
    languages: list[ToolVersion] = []
    dependencies: list[Dependency] = []
    in_require = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("go ") and not in_require:
            languages.append(
                ToolVersion(
                    language="Go",
                    version=stripped.split(" ", 1)[1].strip(),
                    source="go",
                    module=module,
                    span=_span(path, number),
                )
            )
            continue
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require and stripped.startswith(")"):
            in_require = False
            continue
        entry = stripped.removeprefix("require ").strip() if stripped.startswith("require ") else (
            stripped if in_require else ""
        )
        if not entry or entry.startswith("//"):
            continue
        parts = entry.split()
        if len(parts) >= 2 and parts[1].startswith("v"):
            dependencies.append(
                Dependency(
                    name=parts[0],
                    version=parts[1],
                    scope="indirect" if "// indirect" in stripped else "main",
                    ecosystem="go",
                    module=module,
                    span=_span(path, number),
                )
            )
    return languages, dependencies


def _cargo(path: str, text: str, module: str):
    """`Cargo.toml`. `rust-version`과 의존 구역만 본다."""
    languages: list[ToolVersion] = []
    dependencies: list[Dependency] = []
    section = ""
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key == "rust-version":
            languages.append(
                ToolVersion(
                    language="Rust",
                    version=next(iter(_quoted(stripped)), ""),
                    source="rust-version",
                    module=module,
                    span=_span(path, number),
                )
            )
            continue
        if not section.endswith("dependencies"):
            continue
        version = next(iter(_quoted(stripped.split("=", 1)[1])), "")
        if "version" in stripped and "{" in stripped:
            tail = stripped.split("version", 1)[1]
            version = next(iter(_quoted(tail)), version)
        dependencies.append(
            Dependency(
                name=key,
                version=version,
                scope="dev" if section.startswith("dev-") else "main",
                ecosystem="cargo",
                module=module,
                span=_span(path, number),
            )
        )
    return languages, dependencies


_PIN_FILES = {
    ".java-version": "Java",
    ".nvmrc": "Node",
    ".python-version": "Python",
    ".ruby-version": "Ruby",
    ".go-version": "Go",
}


def _pin(path: str, text: str, module: str) -> list[ToolVersion]:
    """`.python-version` 같은 한 줄 고정 파일과 `.tool-versions`."""
    name = PurePosixPath(path).name
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if name == ".tool-versions":
        found: list[ToolVersion] = []
        for number, line in enumerate(text.splitlines(), start=1):
            parts = line.split()
            if len(parts) >= 2 and not line.startswith("#"):
                found.append(
                    ToolVersion(
                        language=parts[0].capitalize(),
                        version=parts[1],
                        source=".tool-versions",
                        module=module,
                        span=_span(path, number),
                    )
                )
        return found
    language = _PIN_FILES.get(name)
    if language is None or not lines:
        return []
    return [
        ToolVersion(
            language=language, version=lines[0], source=name, module=module, span=_span(path, 1)
        )
    ]


MANIFESTS = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "libs.versions.toml",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    ".tool-versions",
    *_PIN_FILES,
)


def manifest_paths(paths: list[str]) -> list[str]:
    """도구 사슬을 적어 둔 파일만 고른다. 잠금 파일과 벤더 디렉토리는 뺀다."""
    chosen = [
        path
        for path in paths
        if PurePosixPath(path).name in MANIFESTS
        and "node_modules/" not in path
        and "/vendor/" not in path
    ]
    return sorted(chosen)


def _catalog_only(path: str, text: str, module: str):
    """버전 카탈로그는 언어 버전을 적지 않는다."""
    return [], _version_catalog(path, text, module)


_PARSERS = {
    "build.gradle": _gradle,
    "build.gradle.kts": _gradle,
    "settings.gradle": _gradle,
    "libs.versions.toml": _catalog_only,
    "pyproject.toml": _pyproject,
    "package.json": _package_json,
    "go.mod": _go_mod,
    "Cargo.toml": _cargo,
}


def _parse_one(path: str, text: str, shared: dict[str, str], module: str):
    """빌드 파일 하나를 그 종류에 맞는 파서로 넘긴다.

    표로 고르는 이유는 하나다. 새 생태계를 붙이는 일이 표에 줄 하나를 더하는 일이어야
    하고, 이 함수를 다시 읽는 일이 되면 안 된다.
    """
    name = PurePosixPath(path).name
    if name == "pom.xml":
        return _maven(path, text, shared, module)
    parser = _PARSERS.get(name)
    if parser is not None:
        return parser(path, text, module)
    return _pin(path, text, module), []


def _unique(dependencies: list[Dependency]) -> list[Dependency]:
    """같은 생태계의 같은 모듈에서 같은 이름이 여러 번 나오면 첫 자리만 남긴다."""
    dependencies.sort(key=lambda d: (d.ecosystem, d.module, d.name, d.scope))
    kept: list[Dependency] = []
    seen: set[tuple[str, str, str]] = set()
    for dependency in dependencies:
        key = (dependency.ecosystem, dependency.module, dependency.name)
        if key in seen:
            continue
        seen.add(key)
        kept.append(dependency)
    return kept


def _is_pom(path: str) -> bool:
    return PurePosixPath(path).name == "pom.xml"


def _parent_relative(text: str) -> str | None:
    """`<parent>` 블록의 `<relativePath>`. 블록이 없으면 `None`, 비어 있으면 기본값이다.

    Maven의 기본 `relativePath`는 `../pom.xml`이다. 명시적으로 빈 값이면 저장소 밖(원격
    저장소)의 부모라는 뜻이라 따라갈 자리가 없다.
    """
    start = text.find("<parent>")
    if start == -1:
        return None
    end = text.find("</parent>", start)
    block = text[start : end if end != -1 else len(text)]
    if "<relativePath" not in block:
        return "../pom.xml"
    value = _tag(block, "relativePath")
    if value is None:
        # `<relativePath/>`는 자기 닫는 빈 태그다. 저장소 밖의 부모를 뜻한다.
        return None
    return value.strip() or None


def _resolve_parent(path: str, relative: str, poms: dict[str, str]) -> str | None:
    """자식 POM의 경로와 상대 경로에서 부모 POM의 경로를 만든다."""
    base = PurePosixPath(path).parent
    candidate = base / relative
    parts: list[str] = []
    for piece in candidate.parts:
        if piece == "..":
            if not parts:
                # 저장소 뿌리 밖으로 나간다. 그 부모는 이 작업본에 없다 — 남은 `..`을
                # 조용히 버리면 뿌리의 POM이 엉뚱하게 부모가 된다.
                return None
            parts.pop()
            continue
        if piece != ".":
            parts.append(piece)
    target = "/".join(parts)
    if not target.endswith("pom.xml"):
        target = f"{target}/pom.xml" if target else "pom.xml"
    return target if target in poms else None


def _maven_inheritance(poms: dict[str, str]) -> dict[str, dict[str, str]]:
    """POM마다 그 조상들이 물려주는 속성 표를 만든다.

    조상의 값은 자식의 값에 덮이지 않는다 — 자식이 자기 속성을 다시 적으면 그것이 이긴다.
    사슬에 고리가 생기면(잘못 적힌 relativePath) 그 자리에서 멈춘다.
    """
    own = {path: _maven_properties(text) for path, text in poms.items()}
    parents: dict[str, str | None] = {}
    for path, text in poms.items():
        relative = _parent_relative(text)
        parents[path] = _resolve_parent(path, relative, poms) if relative else None

    inherited: dict[str, dict[str, str]] = {}
    for path in poms:
        merged: dict[str, str] = {}
        seen = {path}
        current = parents.get(path)
        while current is not None and current not in seen:
            seen.add(current)
            for key, value in own.get(current, {}).items():
                merged.setdefault(key, value)
            current = parents.get(current)
        inherited[path] = merged
    return inherited


def build(sources: dict[str, str], roots: list[str]) -> ToolchainFacts:
    """빌드 파일 내용에서 도구 사슬 사실을 만든다.

    POM의 속성은 **실제 부모 사슬을 따라서만** 물려받는다. 저장소의 모든 POM을 한 통에
    섞으면 아무 관계도 없는 형제 모듈의 `${x.version}`이 서로의 값으로 풀려 위키가 틀린
    버전을 싣는다. 부모를 증명하지 못하면 `${...}`를 적힌 그대로 남긴다.
    """
    poms = {path: sources[path] for path in sorted(sources) if _is_pom(path)}
    inherited = _maven_inheritance(poms)

    languages: list[ToolVersion] = []
    dependencies: list[Dependency] = []
    for path in sorted(sources):
        found, deps = _parse_one(
            path, sources[path], inherited.get(path, {}), module_of(path, roots)
        )
        languages += found
        dependencies += deps

    unique = _unique(dependencies)
    return ToolchainFacts(
        languages=_dedupe_languages(languages),
        dependencies=unique[:_MAX_DEPENDENCIES],
        truncated=max(0, len(unique) - _MAX_DEPENDENCIES),
    )


def _dedupe_languages(found: list[ToolVersion]) -> list[ToolVersion]:
    """같은 언어의 같은 버전 선언이 여러 자리에 있으면 첫 자리만 남긴다.

    Maven 저장소는 `source`와 `target`에 같은 값을 적는다. 표에 같은 줄을 두 번 실으면
    읽는 사람은 두 값이 다른 것을 뜻하는 줄 안다.
    """
    found.sort(key=lambda v: (v.language, v.version, v.module, v.span.path, v.span.start_line))
    kept: list[ToolVersion] = []
    seen: set[tuple[str, str, str]] = set()
    for version in found:
        key = (version.language, version.version, version.module)
        if key in seen:
            continue
        seen.add(key)
        kept.append(version)
    return kept
