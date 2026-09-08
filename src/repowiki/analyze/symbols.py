"""ast-grep 매치를 선언, 참조, 임포트, 진입점으로 가른다. 순수 계산이다.

경계 계약: 입력은 `AstMatch` 목록(어댑터가 낸다)과 모듈 뿌리 목록이고, 출력은
이름 붙은 형태다. 여기서 파일을 열지 않는다.

사각: 참조의 소유 타입은 줄 범위 포함으로 정한다. 한 줄에 중첩 타입이 여럿 있으면
가장 안쪽이 이기지만, 같은 줄에서 시작하고 끝나는 형제 타입은 가릴 수 없다.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.domain import DomainFacts, is_test, language_of
from repowiki.analyze.structure import module_of
from repowiki.models import EntryPoint, EntryPointKind, Span, Symbol, SymbolKind

_DEF_MESSAGES = {
    "def.class": SymbolKind.CLASS,
    "def.interface": SymbolKind.INTERFACE,
    "def.enum": SymbolKind.ENUM,
    "def.record": SymbolKind.RECORD,
    "def.method": SymbolKind.METHOD,
    "def.constructor": SymbolKind.CONSTRUCTOR,
    "def.field": SymbolKind.FIELD,
    "def.function": SymbolKind.FUNCTION,
}

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
    """참조 하나. `owner`는 이 참조를 감싸는 타입의 이름이다."""

    message: str
    name: str
    span: Span
    module: str
    owner: str | None
    is_test: bool


class ImportRecord(BaseModel):
    """임포트 하나. `target`은 점으로 이은 이름이고 파일 경로가 아니다."""

    target: str
    span: Span
    module: str
    is_test: bool


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


def _dotted(text: str, keyword: str) -> str:
    """`package a.b.c;` 또는 `import static a.b.C.d;`에서 점 이름만 꺼낸다.

    입력은 한 줄짜리 평평한 토큰이라 문자열 연산으로 충분하다. 중첩 구조가 아니므로
    C-BRANCH-2의 대상이 아니다.
    """
    body = text.strip().removeprefix(keyword).strip()
    body = body.removeprefix("static").strip()
    body = body.split(";")[0].strip()
    return body.removesuffix(".*").strip()


def _python_import_targets(match: AstMatch) -> list[str]:
    """`import a.b` 와 `from a.b import c` 에서 대상 이름을 낸다."""
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


class _Buckets(BaseModel):
    """분류 결과를 담는 상자. 핸들러는 여기에만 쓴다."""

    symbols: list[Symbol] = []
    references: list[Reference] = []
    imports: list[ImportRecord] = []
    packages: list[PackageRecord] = []
    entry_points: list[EntryPoint] = []


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
    targets = (
        _python_import_targets(match)
        if ctx.language == "python" or match.message == "import.from"
        else [_dotted(match.text, "import")]
    )
    for target in targets:
        out.imports.append(
            ImportRecord(target=target, span=ctx.span, module=ctx.module, is_test=ctx.is_test)
        )


def _take_entry(match: AstMatch, ctx: _Context, out: _Buckets) -> None:
    # 테스트 소스의 진입점은 제품 표면이 아니다(PLAN §2.8 scope 분리).
    if ctx.is_test:
        return
    entry = _entry_point(match, ctx.span, ctx.module)
    if entry is not None:
        out.entry_points.append(entry)


def _handler_for(message: str):
    """message에서 핸들러로. 분기 대신 표로 고른다(C-BRANCH-1)."""
    if message in _DEF_MESSAGES:
        return _take_def
    if message.startswith("ref."):
        return _take_ref
    if message == "package":
        return _take_package
    if message in ("import", "import.from"):
        return _take_import
    if message.startswith("entry."):
        return _take_entry
    return None


def extract(matches: list[AstMatch], roots: list[str], facts: DomainFacts) -> Extraction:
    """매치를 종류별로 가른다. 알 수 없는 message는 조용히 버리지 않고 예외로 올린다."""
    out = _Buckets()
    defs_by_file: dict[str, list[Symbol]] = defaultdict(list)
    unknown: set[str] = set()

    for match in matches:
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
    return Extraction(
        symbols=out.symbols,
        references=out.references,
        imports=out.imports,
        packages=out.packages,
        entry_points=out.entry_points,
    )


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
        path: sorted(
            (s for s in items if s.kind in _TYPE_KINDS),
            key=lambda s: s.span.end_line - s.span.start_line,
        )
        for path, items in defs_by_file.items()
    }
    for symbol in symbols:
        if symbol.kind in _TYPE_KINDS:
            continue
        symbol.parent = _innermost(types_by_file.get(symbol.span.path, []), symbol.span)
    for reference in references:
        reference.owner = _innermost(types_by_file.get(reference.span.path, []), reference.span)


def _innermost(candidates: list[Symbol], span: Span) -> str | None:
    """`span`을 담는 가장 작은 타입의 이름. 후보는 범위가 좁은 순으로 정렬돼 있다."""
    for candidate in candidates:
        if candidate.span.start_line <= span.start_line and span.end_line <= candidate.span.end_line:
            return candidate.name
    return None
