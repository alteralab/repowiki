"""ast-grep 매치를 선언, 참조, 임포트, 진입점으로 가른다. 순수 계산이다.

경계 계약: 입력은 `AstMatch` 목록(어댑터가 낸다)과 모듈 뿌리 목록이고, 출력은
이름 붙은 형태다. 여기서 파일을 열지 않는다.

사각: 참조의 소유 타입은 줄 범위 포함으로 정한다. 한 줄에 중첩 타입이 여럿 있으면
가장 안쪽이 이기지만, 같은 줄에서 시작하고 끝나는 형제 타입은 가릴 수 없다.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.domain import DomainFacts, is_test, language_of
from repowiki.analyze.structure import module_of
from repowiki.models import EntryPoint, EntryPointKind, Span, Symbol, SymbolKind

# Terraform 선언은 코드의 심볼이 아니다. 리소스는 클래스도 함수도 아니라서 `SymbolKind`에
# 넣을 자리가 없고, 억지로 넣으면 위키가 없는 종류를 있다고 말한다(C-REPORT-2).
# analyze/terraform.py 가 원본 매치에서 직접 읽는다.
_TERRAFORM_MESSAGES = frozenset(
    {
        "def.resource",
        "def.data",
        "def.module",
        "def.variable",
        "def.output",
        "def.provider",
        "def.local",
        # 참조도 코드의 타입 참조가 아니다. `var.cidr`은 타입 사이의 관계가 아니라
        # 선언 사이의 관계이고, 그 그래프는 analyze/terraform.py 가 따로 낸다.
        "ref.use",
        "ref.module_source",
    }
)

_DEF_MESSAGES = {
    "def.class": SymbolKind.CLASS,
    "def.interface": SymbolKind.INTERFACE,
    "def.enum": SymbolKind.ENUM,
    "def.record": SymbolKind.RECORD,
    "def.method": SymbolKind.METHOD,
    "def.constructor": SymbolKind.CONSTRUCTOR,
    "def.field": SymbolKind.FIELD,
    "def.function": SymbolKind.FUNCTION,
    "def.type": SymbolKind.TYPE_ALIAS,
}

# 다른 선언을 감쌀 수 있는 종류. 타입 별칭은 멤버를 갖지 않으므로 여기 없다.
_TYPE_KINDS = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ENUM, SymbolKind.RECORD}

_ENTRY_ANNOTATIONS = {
    "RestController": EntryPointKind.ROUTE,
    "Controller": EntryPointKind.ROUTE,
    "RequestMapping": EntryPointKind.ROUTE,
    "GetMapping": EntryPointKind.ROUTE,
    "PostMapping": EntryPointKind.ROUTE,
    "PutMapping": EntryPointKind.ROUTE,
    "DeleteMapping": EntryPointKind.ROUTE,
    "PatchMapping": EntryPointKind.ROUTE,
    "KafkaListener": EntryPointKind.LISTENER,
    "RabbitListener": EntryPointKind.LISTENER,
    "JmsListener": EntryPointKind.LISTENER,
    "SqsListener": EntryPointKind.LISTENER,
    "EventListener": EntryPointKind.LISTENER,
    "Scheduled": EntryPointKind.SCHEDULER,
}


class Reference(BaseModel):
    """참조 하나. `owner`는 이 참조를 감싸는 타입이고 `owner_path`가 그 선언 파일이다.

    이름만으로는 같은 이름의 다른 타입을 구분하지 못한다. 경로가 식별자다.
    """

    message: str
    name: str
    span: Span
    module: str
    owner: str | None
    owner_path: str | None = None
    owner_span: Span | None = None
    is_test: bool


class ReExportRecord(BaseModel):
    """재수출 매치 하나. 표를 만들 재료다.

    `kind`는 `star`, `named`, `alias`, `namespace` 중 하나다. `named`와 `alias`는 같은
    자리에서 따로 나오므로 줄 번호로 짝을 맞춘다 — ast-grep 이 안쪽 필드와 바깥 필드를
    한 매치에서 함께 잡지 못한다.
    """

    kind: str
    specifier: str
    name: str = ""
    path: str
    line: int


class ImportRecord(BaseModel):
    """임포트 하나. `target`은 점으로 이은 이름이고 파일 경로가 아니다.

    `names`는 `from a.b import c, d`가 이 파일에 들여온 이름이다. 이것이 없으면 파이썬의
    수신자 없는 호출을 임포트로 증명할 수 없고, 증명 없이 이으면 성립하지 않는 호출을
    사실로 만든다.
    """

    target: str
    span: Span
    module: str
    is_test: bool
    names: list[str] = Field(default_factory=list)
    # TypeScript 는 임포트 문자열이 파일 경로를 정한다. 점 이름 규칙으로 바꿔 담으면
    # `./lib`과 `@app/core`가 뜻을 잃는다. 원문을 그대로 들고 간다.
    specifier: str = ""


class PackageRecord(BaseModel):
    """파일이 선언한 패키지. Java 계열에서만 나온다."""

    name: str
    path: str
    module: str
    is_test: bool


class Extraction(BaseModel):
    """한 번의 스캔에서 나온 전부."""

    symbols: list[Symbol]
    references: list[Reference]
    imports: list[ImportRecord]
    packages: list[PackageRecord]
    entry_points: list[EntryPoint]
    reexports: list[ReExportRecord] = Field(default_factory=list)


def _dotted(text: str, keyword: str) -> str:
    """`package a.b.c;` 또는 `import static a.b.C.d;`에서 점 이름만 꺼낸다.

    입력은 한 줄짜리 평평한 토큰이라 문자열 연산으로 충분하다. 중첩 구조가 아니므로
    C-BRANCH-2의 대상이 아니다.
    """
    body = text.strip().removeprefix(keyword).strip()
    body = body.removeprefix("static").strip()
    body = body.split(";")[0].strip()
    return body.removesuffix(".*").strip()


def _scala_import_targets(text: str) -> list[str]:
    """Scala 임포트에서 대상 이름을 낸다.

    세 형태를 읽는다. `import a.b.C`는 그대로, `import a.b.{C, D}`는 둘로 펴고,
    `import a.b._`는 패키지를 가리킨다. 중괄호 안의 별칭(`C => E`)은 왼쪽 이름을 쓴다.
    """
    body = text.strip().removeprefix("import").strip()
    if body.endswith("._"):
        return [body[:-2]]
    if "{" not in body:
        return [body] if body else []
    package, _, rest = body.partition("{")
    package = package.rstrip(".")
    names = []
    for piece in rest.rstrip("}").split(","):
        name = piece.split("=>")[0].strip()
        if name and name != "_":
            names.append(f"{package}.{name}")
    return names or [package]


def _python_import_targets(match: AstMatch) -> list[str]:
    """`import a.b` 와 `from a.b import c` 에서 대상 모듈 이름을 낸다."""
    text = match.text.strip()
    if text.startswith("from "):
        head = text[len("from ") :].split(" import ")[0].strip()
        return [head] if head else []
    body = text.removeprefix("import").strip()
    targets = []
    for piece in body.split(","):
        name = piece.strip().split(" as ")[0].strip()
        if name:
            targets.append(name)
    return targets


def python_imported_names(text: str) -> list[str]:
    """`from a.b import c, d as e`가 들여온 이름. 별칭이 있으면 별칭이 그 파일의 이름이다."""
    stripped = text.strip()
    if not stripped.startswith("from ") or " import " not in stripped:
        return []
    body = stripped.split(" import ", 1)[1]
    body = body.strip().lstrip("(").rstrip(")").strip()
    found: list[str] = []
    for piece in body.split(","):
        name = piece.strip()
        if not name or name == "*":
            continue
        if " as " in name:
            name = name.split(" as ", 1)[1].strip()
        if name.isidentifier():
            found.append(name)
    return found


class _Buckets(BaseModel):
    """분류 결과를 담는 상자. 핸들러는 여기에만 쓴다."""

    symbols: list[Symbol] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    imports: list[ImportRecord] = Field(default_factory=list)
    packages: list[PackageRecord] = Field(default_factory=list)
    entry_points: list[EntryPoint] = Field(default_factory=list)
    reexports: list[ReExportRecord] = Field(default_factory=list)
    # `(파일, 임포트 문자열, 이름)`. 추출이 끝난 뒤 임포트 기록에 붙인다 — 매치 순서가
    # 정해져 있지 않아 그 자리에서 붙이면 어떤 파일은 이름이 통째로 빠진다.
    import_names: list[tuple[str, str, str]] = Field(default_factory=list)


class _Context(BaseModel):
    """한 매치의 분류에 필요한 파생 사실."""

    module: str
    is_test: bool
    language: str
    span: Span


def _take_def(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    out.symbols.append(
        Symbol(
            kind=_DEF_MESSAGES[match.message],
            name=match.name or match.text.strip()[:80],
            span=ctx.span,
            module=ctx.module,
            language=ctx.language,
            is_test=ctx.is_test,
        )
    )


def _take_ref(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    out.references.append(
        Reference(
            message=match.message,
            name=match.name or match.text.strip(),
            span=ctx.span,
            module=ctx.module,
            owner=None,
            is_test=ctx.is_test,
        )
    )


def _take_package(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    out.packages.append(
        PackageRecord(
            name=_dotted(match.text, "package"),
            path=match.path,
            module=ctx.module,
            is_test=ctx.is_test,
        )
    )


def _take_import(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    if ctx.language == "python" or match.message == "import.from":
        targets = _python_import_targets(match)
    elif ctx.language == "scala":
        targets = _scala_import_targets(match.text)
    else:
        targets = [_dotted(match.text, "import")]
    names = python_imported_names(match.text) if match.message == "import.from" else []
    for target in targets:
        out.imports.append(
            ImportRecord(
                target=target,
                span=ctx.span,
                module=ctx.module,
                is_test=ctx.is_test,
                names=names,
            )
        )


def _take_ts_import(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    """TypeScript 임포트. 문자열 원문을 그대로 담는다.

    `target`에도 같은 값을 넣는 이유는 이 형태를 읽는 다른 자리(미해석 계수)가 `target`을
    보기 때문이다. 해석은 `analyze/tsmodules.py`가 `specifier`로 한다.
    """
    raw = (match.captures.get("SOURCE") or "").strip().strip("\"'")
    if not raw:
        return
    out.imports.append(
        ImportRecord(
            target=raw,
            specifier=raw,
            span=ctx.span,
            module=ctx.module,
            is_test=ctx.is_test,
        )
    )


def _take_ts_import_name(match: AstMatch, _ctx: _Context, out: _Buckets) -> None:
    """`import { A } from "./x"`의 이름 하나.

    임포트 문장과 이름은 매치 순서가 정해져 있지 않다. 이름을 따로 모아 두고 추출이 끝난 뒤
    문장에 붙인다 — 순서에 기대면 어떤 파일에서는 이름이 통째로 빠진다(airflow 실측:
    barrel 을 가리키는 765건 중 이름이 붙은 것이 49건뿐이었다).
    """
    raw = (match.captures.get("SRC") or "").strip().strip("\"'")
    name = (match.captures.get("NAME") or "").strip()
    if raw and name:
        out.import_names.append((match.path, raw, name))


def _take_reexport(match: AstMatch, _ctx: _Context, out: _Buckets) -> None:
    """재수출 매치. 종류마다 담는 값이 다르다."""
    kind = match.message.removeprefix("reexport.")
    raw = (match.captures.get("SOURCE") or match.captures.get("SRC") or "").strip().strip("\"'")
    if not raw:
        return
    out.reexports.append(
        ReExportRecord(
            kind=kind,
            specifier=raw,
            name=(match.captures.get("NAME") or match.captures.get("ALIAS") or "").strip(),
            path=match.path,
            line=match.start_line,
        )
    )


def _ignore(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    """다른 분석기가 가져가는 매치. 이 층에서는 아무것도 하지 않는다."""


def _take_entry(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    # 테스트 소스의 진입점은 제품 표면이 아니다(PLAN §2.8 scope 분리).
    if ctx.is_test:
        return
    entry = _entry_point(match, ctx.span, ctx.module)
    if entry is not None:
        out.entry_points.append(entry)


# 다른 분석기가 원본 매치에서 직접 읽는 message. 여기서는 흘려보내되 미상으로 세지 않는다.
_CONSUMED_ELSEWHERE = ("entity.",)


# message에서 핸들러로 가는 표. 분기 대신 표로 고른다(C-BRANCH-1).
# `entity.*`는 다른 분석기가 원본 매치에서 직접 읽으므로 여기서는 흘려보낸다.
_PREFIX_HANDLERS: tuple[tuple[str, object], ...] = (
    ("ref.", "_take_ref"),
    ("entry.", "_take_entry"),
    ("entity.", "_ignore"),
    # `bind.*`는 이름과 타입을 묶은 매치다. 호출 해석기(analyze/calls.py)가 소비한다.
    ("bind.", "_ignore"),
    ("reexport.", "_take_reexport"),
)

_EXACT_HANDLERS: dict[str, str] = {
    "package": "_take_package",
    "import": "_take_import",
    "import.from": "_take_import",
    "import.ts": "_take_ts_import",
    "import.name": "_take_ts_import_name",
}


def _handler_for(message: str):
    """message에 대응하는 핸들러. 없으면 `None`이고 호출자가 미상으로 센다."""
    table = globals()
    if message in _DEF_MESSAGES:
        return _take_def
    name = _EXACT_HANDLERS.get(message)
    if name is None:
        name = next((handler for prefix, handler in _PREFIX_HANDLERS if message.startswith(prefix)), None)
    return table[name] if name else None


def extract(matches: list[AstMatch], roots: list[str], facts: DomainFacts) -> Extraction:
    """매치를 종류별로 가른다. 알 수 없는 message는 조용히 버리지 않고 예외로 올린다."""
    out = _Buckets()
    defs_by_file: dict[str, list[Symbol]] = defaultdict(list)
    unknown: set[str] = set()

    for match in matches:
        if match.message in _TERRAFORM_MESSAGES:
            # analyze/terraform.py 가 원본 매치에서 읽는다. 미상으로 세지 않는다.
            continue
        handler = _handler_for(match.message)
        if handler is None:
            unknown.add(match.message)
            continue
        ctx = _Context(
            module=module_of(match.path, roots),
            is_test=is_test(match.path, facts),
            language=language_of(match.path, facts) or "unknown",
            span=Span(path=match.path, start_line=match.start_line, end_line=match.end_line),
        )
        before = len(out.symbols)
        handler(match, ctx, out)
        if handler is _take_def and len(out.symbols) > before:
            defs_by_file[match.path].append(out.symbols[-1])

    if unknown:
        raise ValueError(f"알 수 없는 룰 message: {sorted(unknown)}")

    _assign_owners(out.symbols, out.references, defs_by_file)
    _attach_import_names(out)
    return Extraction(
        symbols=out.symbols,
        references=out.references,
        imports=out.imports,
        packages=out.packages,
        entry_points=out.entry_points,
        reexports=out.reexports,
    )


def _attach_import_names(out: _Buckets) -> None:
    """모아 둔 이름을 임포트 기록에 붙인다. 매치 순서에 기대지 않는다."""
    by_place: dict[tuple[str, str], ImportRecord] = {}
    for record in out.imports:
        if record.specifier:
            by_place.setdefault((record.span.path, record.specifier), record)
    for path, specifier, name in out.import_names:
        record = by_place.get((path, specifier))
        if record is not None and name not in record.names:
            record.names.append(name)


def _entry_point(match: AstMatch, span: Span, module: str) -> EntryPoint | None:
    if match.message == "entry.main":
        return EntryPoint(kind=EntryPointKind.MAIN, name="main", span=span, module=module)
    if match.message == "entry.annotation":
        for annotation, kind in _ENTRY_ANNOTATIONS.items():
            if annotation in match.text:
                return EntryPoint(
                    kind=kind, name=annotation, span=span, module=module, framework="spring"
                )
        return None
    if match.message == "entry.decorator":
        return EntryPoint(
            kind=EntryPointKind.ROUTE, name=match.text.strip()[:60], span=span, module=module
        )
    return None


def _assign_owners(
    symbols: list[Symbol],
    references: list[Reference],
    defs_by_file: dict[str, list[Symbol]],
) -> None:
    """선언의 부모 타입과 참조의 소유 타입을 줄 범위 포함으로 정한다."""
    types_by_file: dict[str, list[Symbol]] = {
        path: [s for s in items if s.kind in _TYPE_KINDS] for path, items in defs_by_file.items()
    }
    for symbol in symbols:
        # 중첩 타입도 부모를 가진다. `Option.Builder`와 `TextStyle.Builder`는 이름이 같고
        # 부모가 다르다. 부모를 안 붙이면 위키의 라벨이 둘을 구분하지 못한다.
        candidates = [
            other
            for other in types_by_file.get(symbol.span.path, [])
            if other.span != symbol.span or other.name != symbol.name
        ]
        parent = innermost(candidates, symbol.span)
        symbol.parent = parent.name if parent is not None else None
    for reference in references:
        owner = innermost(types_by_file.get(reference.span.path, []), reference.span)
        reference.owner = owner.name if owner is not None else None
        reference.owner_path = owner.span.path if owner is not None else None
        # 소유 선언의 위치를 그대로 들고 간다. 나중에 (경로, 이름)으로 다시 찾으면
        # 한 파일에 같은 이름의 선언이 둘일 때 뒤엣것이 앞엣것을 덮는다.
        reference.owner_span = owner.span if owner is not None else None


def innermost(candidates: list[Symbol], span: Span) -> Symbol | None:
    """`span`을 담는 가장 작은 타입.

    같은 크기의 후보가 둘 이상이면 소유자를 정하지 않는다. 사전순으로 하나를 고르면
    재현은 되지만 근거 없는 선택이 사실이 된다(C-BRANCH-3).
    """
    enclosing = [
        candidate
        for candidate in candidates
        if candidate.span.start_line <= span.start_line and span.end_line <= candidate.span.end_line
    ]
    if not enclosing:
        return None
    smallest = min(c.span.end_line - c.span.start_line for c in enclosing)
    tied = [c for c in enclosing if c.span.end_line - c.span.start_line == smallest]
    if len(tied) > 1:
        return None
    return tied[0]
