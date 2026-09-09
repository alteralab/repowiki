"""호출 그래프. 수신자 이름을 스코프에서 풀어 호출 엣지를 만든다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 `bind.*` 매치와 선언 목록과 이름 스코프이고, 출력은 호출 엣지와 계수다.

왜 필요한가. 타입 엣지는 "A가 B를 필드로 들고 있다"까지만 말한다. "A의 이 메서드가 B의
저 메서드를 부른다"는 말하지 못하고, 그것 없이는 시퀀스 다이어그램도 "누가 이것을 부르는가"
표도 만들 수 없다. DeepWiki apache/kafka의 도식 176개 중 29개가 시퀀스다(2026-09-09 실측).

해석 순서는 좁은 스코프부터다. 지역 변수 → 파라미터 → 필드 → 타입 이름(정적 호출).
이 순서는 언어의 이름 가림 규칙과 같다. 뒤집으면 같은 이름의 필드가 지역 변수를 가린다.

사각 셋. 체인 표현식(`a.b().c()`)의 수신자는 풀지 않는다 — 중간 반환 타입을 모른다.
상속받은 멤버를 통한 호출은 상위 타입까지 올라가지 않는다. 인터페이스 호출은 구현이 아니라
인터페이스로 간다. 셋 다 세어서 남긴다(C-REPORT-2).
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.domain import DomainFacts, is_test, language_of
from repowiki.analyze.structure import module_of
from repowiki.analyze.symbols import innermost
from repowiki.models import CallEdge, Span, Symbol, SymbolKind

_MEMBER_KINDS = {SymbolKind.METHOD, SymbolKind.CONSTRUCTOR, SymbolKind.FUNCTION}
_TYPE_KINDS = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ENUM, SymbolKind.RECORD}
_SELF_NAMES = ("this", "self", "cls")
_MODULE_LEVEL = "module"
_SCOPE_ORDER = ("local", "param", "field")


class Binding(BaseModel):
    """변수 하나의 선언 타입. `owner_member`가 있으면 그 메서드 안에서만 보인다."""

    name: str
    type_name: str
    scope: str
    span: Span
    owner_type: str | None = None
    owner_member: str | None = None


class CallSite(BaseModel):
    """호출 한 자리. `receiver`가 비면 수신자 없는 호출이다."""

    receiver: str
    method: str
    span: Span
    module: str
    language: str = ""
    owner_type: str | None = None
    owner_member: str | None = None
    is_test: bool = False


class CallCounts(BaseModel):
    """해석 계수. 합이 입력과 다르면 어딘가에서 조용히 사라진 것이다."""

    emitted: int = 0
    external: int = 0
    chained_receiver: int = 0
    unknown_receiver: int = 0
    no_owner: int = 0
    self_call: int = 0
    excluded_test: int = 0

    def total(self) -> int:
        return (
            self.emitted
            + self.external
            + self.chained_receiver
            + self.unknown_receiver
            + self.no_owner
            + self.self_call
            + self.excluded_test
        )


def base_type(text: str) -> str:
    """선언 타입에서 기본 이름만. 제네릭과 배열과 한정 이름을 벗긴다.

    `Map<String, Option>`은 `Map`이고 `java.util.List`는 `List`이며 `Option[]`은 `Option`이다.
    제네릭 인자 자체의 관계는 이미 `ref.field_type`이 따로 낸다.
    """
    head = text.split("<", 1)[0].strip()
    head = head.replace("[]", "").replace("*", "").strip()
    head = head.split("|")[0].strip()
    return head.rsplit(".", 1)[-1].strip()


def module_owner(path: str) -> str:
    """파일의 모듈 수준 이름. 감싸는 타입이 없는 선언과 호출의 집이다.

    파이썬은 클래스 밖의 함수가 흔하다. 소유 타입이 없다고 버리면 파이썬 저장소의 호출
    대부분이 사라진다.
    """
    stem = path.rsplit("/", 1)[-1]
    return stem.rsplit(".", 1)[0] or stem


def _plain_name(text: str) -> str:
    """대입 좌변에서 변수 이름만. `self.parser`는 `parser`다."""
    return text.strip().rsplit(".", 1)[-1].strip()


def _is_chained(receiver: str) -> bool:
    """수신자가 표현식이면 참. 이름 하나가 아니면 스코프로 풀 수 없다."""
    return not receiver.replace("_", "").replace("$", "").isalnum()


def collect(
    matches: list[AstMatch],
    symbols: list[Symbol],
    roots: list[str],
    facts: DomainFacts,
) -> tuple[list[Binding], list[CallSite]]:
    """`bind.*` 매치를 결합과 호출 자리로 가른다. 소유 타입과 소유 멤버를 함께 정한다."""
    types_by_file: dict[str, list[Symbol]] = defaultdict(list)
    members_by_file: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        if symbol.kind in _TYPE_KINDS:
            types_by_file[symbol.span.path].append(symbol)
        elif symbol.kind in _MEMBER_KINDS:
            members_by_file[symbol.span.path].append(symbol)

    bindings: list[Binding] = []
    sites: list[CallSite] = []
    for match in matches:
        if not match.message.startswith("bind."):
            continue
        span = Span(path=match.path, start_line=match.start_line, end_line=match.end_line)
        owner_type = innermost(types_by_file.get(match.path, []), span)
        owner_member = innermost(members_by_file.get(match.path, []), span)
        type_name = owner_type.name if owner_type is not None else module_owner(match.path)
        member_name = owner_member.name if owner_member is not None else None

        if match.message in ("bind.call", "bind.call_bare"):
            sites.append(
                CallSite(
                    receiver=match.captures.get("RECV", "").strip(),
                    method=match.captures.get("NAME", "").strip(),
                    span=span,
                    module=module_of(match.path, roots),
                    language=language_of(match.path, facts) or "",
                    owner_type=type_name,
                    owner_member=member_name,
                    is_test=is_test(match.path, facts),
                )
            )
            continue
        scope = _SCOPE_FOR.get(match.message)
        if scope is None:
            continue
        name, declared = match.captures.get("NAME", ""), match.captures.get("TYPE", "")
        if not name or not declared:
            continue
        bindings.append(
            Binding(
                name=_plain_name(name),
                type_name=base_type(declared),
                scope=scope,
                span=span,
                owner_type=type_name,
                owner_member=member_name if scope != "field" else None,
            )
        )
    return bindings, sites


_SCOPE_FOR = {
    "bind.field": "field",
    "bind.param": "param",
    "bind.local": "local",
    "bind.method": "signature",
}


class ScopeEntry(BaseModel):
    """이름 하나의 선언. 어느 타입의 어느 멤버 안에서, 몇 번째 줄에 선언됐는지를 함께 든다."""

    name: str
    type_name: str
    kind: str
    line: int
    owner_type: str
    owner_member: str | None = None


class Scope(BaseModel):
    """한 파일의 이름 표.

    이름만으로 표를 만들면 안 된다. 같은 파일의 `C1.run`과 `C2.run`이 표를 나눠 쓰면 뒤엣것이
    앞엣것의 파라미터를 덮어 `C1.run`이 부르지 않은 타입의 메서드를 부른 것이 된다. 그래서
    표의 열쇠는 (소유 타입, 소유 멤버, 이름)이다.

    지역 변수는 선언 줄보다 앞의 호출을 가리지 못한다. 자바에서 `x.call(); B x = ...;`는
    앞의 `x`가 다른 것이라는 뜻이다.
    """

    entries: list[ScopeEntry] = Field(default_factory=list)

    def lookup(
        self, receiver: str, owner_type: str | None, owner_member: str | None, line: int
    ) -> ScopeEntry | None:
        """수신자 이름의 선언. 좁은 스코프부터 보고, 지역 변수는 선언 뒤에서만 보인다."""
        named = [entry for entry in self.entries if entry.name == receiver]
        if not named:
            return None
        in_member = [
            entry
            for entry in named
            if entry.owner_member is not None
            and entry.owner_member == owner_member
            and entry.owner_type == owner_type
        ]
        locals_before = [
            entry for entry in in_member if entry.kind == "local" and entry.line <= line
        ]
        if locals_before:
            return max(locals_before, key=lambda entry: entry.line)
        params = [entry for entry in in_member if entry.kind == "param"]
        if params:
            return params[0]
        fields = [
            entry
            for entry in named
            if entry.kind == "field" and entry.owner_type == owner_type
        ]
        return fields[0] if fields else None


def build_scopes(bindings: list[Binding]) -> dict[str, Scope]:
    """파일마다 이름 표를 만든다. 가림 판정은 `Scope.lookup`이 한다."""
    by_path: dict[str, list[ScopeEntry]] = defaultdict(list)
    for binding in bindings:
        if binding.scope not in _SCOPE_ORDER or binding.owner_type is None:
            continue
        by_path[binding.span.path].append(
            ScopeEntry(
                name=binding.name,
                type_name=binding.type_name,
                kind=binding.scope,
                line=binding.span.start_line,
                owner_type=binding.owner_type,
                owner_member=binding.owner_member,
            )
        )
    return {
        path: Scope(entries=sorted(entries, key=lambda entry: (entry.line, entry.name)))
        for path, entries in by_path.items()
    }


def _receiver_kind(site: CallSite) -> str:
    """수신자의 모양. 이름 하나가 아니면 스코프로 풀 수 없다."""
    receiver = site.receiver
    if not receiver:
        return "bare"
    if receiver in _SELF_NAMES:
        return "self"
    if not receiver.replace("_", "").replace("$", "").isidentifier():
        return "chained"
    return "name"


class Resolver(BaseModel):
    """해석에 필요한 표들. 한 자리에 모아 두어야 호출마다 같은 규칙이 적용된다."""

    model_config = {"arbitrary_types_allowed": True}

    scopes: dict[str, Scope] = Field(default_factory=dict)
    members: dict[tuple[str, str, str], Symbol] = Field(default_factory=dict)
    module_functions: dict[tuple[str, str], Symbol] = Field(default_factory=dict)
    imported: dict[str, dict[str, str]] = Field(default_factory=dict)
    free_by_name: dict[str, list[Symbol]] = Field(default_factory=dict)
    # `(부르는 파일, 들여온 이름) -> 그 이름을 선언한 파일`. TypeScript 전용이다.
    # 이 모듈은 TypeScript 의 경로 규칙을 알지 않는다. 상대 경로와 `paths` 무늬와 barrel 을
    # 푸는 것은 analyze/tsmodules.py 의 일이고, 여기는 그것이 낸 답만 받는다(C-DEPTH-3).
    ts_declaring: dict[tuple[str, str], str] = Field(default_factory=dict)


def _member_in(resolver: Resolver, path: str, type_name: str, member: str) -> Symbol | None:
    """선언 파일까지 맞춰 멤버를 찾는다.

    타입 이름만으로 찾으면 서로 다른 패키지의 같은 이름 타입이 같은 칸을 나눠 쓴다. 그러면
    올바르게 푼 타입인데도 엉뚱한 파일의 선언을 근거로 달게 된다.
    """
    return resolver.members.get((path, type_name, member))


def _resolve_named(
    site: CallSite, resolver: Resolver, resolve_type, entry: ScopeEntry | None
) -> CallEdge | str:
    """수신자가 이름 하나인 호출."""
    if entry is not None:
        return _via_type(site, resolver, resolve_type(entry.type_name, site), entry.kind)
    if not site.receiver[:1].isupper():
        return "unknown_receiver"
    # 대문자로 시작하는 이름은 타입일 수 있다. 정적 호출이다.
    target = resolve_type(site.receiver, site)
    if target is None:
        return "unknown_receiver"
    return _via_type(site, resolver, target, "static")


def _via_type(site: CallSite, resolver: Resolver, target, kind: str) -> CallEdge | str:
    """대상 타입이 정해진 뒤의 공통 경로. 그 타입에 그 멤버가 선언돼 있어야 엣지다."""
    if target is None:
        return "external"
    declaration = _member_in(resolver, target.span.path, target.name, site.method)
    if declaration is None:
        return "external"
    return _edge(site, target, declaration, kind)


def _resolve_self(site: CallSite, resolver: Resolver) -> CallEdge | str:
    """`this.m()` / `self.m()`. 대상은 감싸는 타입이다."""
    if site.owner_type is None:
        return "no_owner"
    declaration = _member_in(resolver, site.span.path, site.owner_type, site.method)
    if declaration is None:
        return "external"
    if site.method == site.owner_member:
        return "self_call"
    return _edge(site, _OwnerRef(name=site.owner_type, module=site.module,
                                path=site.span.path), declaration, "self")


def _resolve_bare(site: CallSite, resolver: Resolver) -> CallEdge | str:
    """수신자가 없는 호출. 언어마다 뜻이 다르다.

    자바와 스칼라의 `m()`은 `this.m()`이다. 파이썬과 TypeScript 의 `m()`은 그렇지 않다.
    감싸는 클래스에 같은 이름의 메서드가 있어도 그것을 부르는 것이 아니라 모듈 수준이나
    임포트된 이름을 부르는 것이다. 두 갈래를 같이 다루면 없는 호출이 사실이 된다.

    같은 모듈 함수를 먼저 보는 것은 두 언어가 같고, 임포트를 증명하는 방법이 다르다.
    파이썬은 점 표기를 경로 조각으로 펴고, TypeScript 는 상대 경로와 `paths` 무늬와
    barrel 을 지나야 해서 이 모듈이 풀 수 없다. 그래서 그 답을 표로 받아 둔다.
    """
    if site.language not in ("python", "typescript", "tsx"):
        return _resolve_self(site, resolver)

    same_file = resolver.module_functions.get((site.span.path, site.method))
    if same_file is not None:
        return _edge(site, _owner_of(same_file), same_file, "module")

    if site.language in ("typescript", "tsx"):
        return _resolve_bare_ts(site, resolver)

    target_module = resolver.imported.get(site.span.path, {}).get(site.method)
    if target_module is None:
        return "unknown_receiver"
    declaration = _by_import(resolver, target_module, site.method, site.span.path)
    if declaration is None:
        return "external"
    return _edge(site, _owner_of(declaration), declaration, "import")


def _resolve_bare_ts(site: CallSite, resolver: Resolver) -> CallEdge | str:
    """TypeScript 의 수신자 없는 호출. 들여온 이름이 어느 파일에서 선언됐는지로 푼다.

    표에 없으면 그 이름을 들여오지 않았다는 뜻이고, 이으면 임포트하지도 않은 함수를
    부른다고 주장하게 된다(C-BRANCH-3). 표가 가리킨 파일에 그 이름의 모듈 수준 함수가
    없으면 저장소 밖이거나 함수가 아닌 것을 부른 것이다.
    """
    declaring = resolver.ts_declaring.get((site.span.path, site.method))
    if not declaring:
        return "unknown_receiver"
    found = [
        symbol
        for symbol in resolver.free_by_name.get(site.method, [])
        if symbol.span.path == declaring
    ]
    if len(found) != 1:
        return "external"
    return _edge(site, _owner_of(found[0]), found[0], "import")


def _module_segments(target: str, from_path: str) -> list[str] | None:
    """임포트 대상을 경로 조각으로 편다. 상대 임포트는 부르는 파일의 자리에서 푼다.

    `from .util import f`의 `.util`은 그 파일이 있는 디렉토리의 `util`이다. 점을 그냥 벗기면
    저장소 어디의 `util`이든 맞는 것으로 보이고, 그러면 없는 호출이 사실이 된다.
    """
    if not target:
        return None
    dots = len(target) - len(target.lstrip("."))
    tail = [piece for piece in target.lstrip(".").split(".") if piece]
    if dots == 0:
        return tail or None
    here = from_path.split("/")[:-1]
    up = dots - 1
    if up > len(here):
        return None
    base = here[: len(here) - up] if up else here
    return [*base, *tail] or None


def _by_import(
    resolver: Resolver, target_module: str, name: str, from_path: str
) -> Symbol | None:
    """임포트한 모듈 경로가 실제로 가리키는 저장소 안의 선언.

    경로 조각 단위로 맞춘다. 문자열 꼬리로 맞추면 `util`이 `pkg/notutil.py`에도 맞는다.
    맞는 파일이 없거나 여럿이면 잇지 않는다 — 없는 것을 있다고 하지 않는다(C-BRANCH-3).
    """
    segments = _module_segments(target_module, from_path)
    if not segments:
        return None
    candidates = [
        symbol
        for symbol in resolver.free_by_name.get(name, [])
        if _matches_module(symbol.span.path, segments)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _matches_module(path: str, segments: list[str]) -> bool:
    """파일 경로가 그 모듈 경로로 끝나는가. 패키지의 `__init__.py`도 그 모듈이다."""
    parts = path.split("/")
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts:
        parts = [*parts[:-1], parts[-1].rsplit(".", 1)[0]]
    return len(parts) >= len(segments) and parts[-len(segments) :] == segments


class _OwnerRef(BaseModel):
    """엣지의 출발 쪽 정체. 타입 선언이 없을 때(모듈 수준)도 같은 모양으로 다루려고 둔다."""

    name: str
    module: str
    path: str


def _owner_of(symbol: Symbol) -> _OwnerRef:
    """선언이 속한 집. 감싸는 타입이 있으면 그 타입, 없으면 그 파일의 모듈이다."""
    return _OwnerRef(
        name=symbol.parent or module_owner(symbol.span.path),
        module=symbol.module,
        path=symbol.span.path,
    )


def _edge(site: CallSite, owner: object, declaration: Symbol, kind: str) -> CallEdge:
    """엣지 하나. 대상 선언의 자리가 링크의 목적지다."""
    return CallEdge(
        src_type=site.owner_type or module_owner(site.span.path),
        src_member=site.owner_member or "",
        dst_type=getattr(owner, "name"),
        dst_member=declaration.name,
        span=site.span,
        src_module=site.module,
        dst_module=getattr(owner, "module", declaration.module),
        src_path=site.span.path,
        dst_path=declaration.span.path,
        receiver_kind=kind,
    )


def _resolve_one(site: CallSite, resolver: Resolver, resolve_type) -> CallEdge | str:
    """호출 자리 하나. 엣지를 내거나 어느 계수에 넣을지 이름으로 답한다."""
    shape = _receiver_kind(site)
    if shape == "chained":
        return "chained_receiver"
    if shape == "bare":
        return _resolve_bare(site, resolver)
    if shape == "self":
        return _resolve_self(site, resolver)
    entry = resolver.scopes.get(site.span.path, Scope()).lookup(
        site.receiver, site.owner_type, site.owner_member, site.span.start_line
    )
    return _resolve_named(site, resolver, resolve_type, entry)


def resolve(
    sites: list[CallSite], resolver: Resolver, resolve_type
) -> tuple[list[CallEdge], CallCounts]:
    """호출 자리를 호출 엣지로 바꾼다.

    `resolve_type`은 타입 이름과 자리를 받아 저장소 안의 선언을 내는 함수다. 없으면 저장소
    밖의 타입이라 외부 호출로 센다 — 그것은 실패가 아니라 사실이다.
    """
    edges: list[CallEdge] = []
    counts = CallCounts()
    ordered = sorted(sites, key=lambda s: (s.span.path, s.span.start_line, s.receiver, s.method))
    for site in ordered:
        if site.is_test:
            counts.excluded_test += 1
            continue
        if site.owner_member is None:
            counts.no_owner += 1
            continue
        outcome = _resolve_one(site, resolver, resolve_type)
        if isinstance(outcome, str):
            if not hasattr(counts, outcome):
                raise ValueError(f"계수에 없는 판정이다: {outcome}")
            setattr(counts, outcome, getattr(counts, outcome) + 1)
            continue
        counts.emitted += 1
        edges.append(outcome)
    return edges, counts


def member_table(symbols: list[Symbol]) -> dict[tuple[str, str, str], Symbol]:
    """`(선언 파일, 소유 이름, 멤버 이름)`에서 선언으로.

    파일까지 열쇠에 넣는 이유는 같은 이름의 타입이 여러 패키지에 있기 때문이다. 이름만
    보면 올바르게 푼 타입인데도 다른 패키지의 선언을 근거로 달게 된다.

    오버로드는 이름이 같고 시그니처가 다르다. 이 표는 이름 단위라 오버로드를 가르지 않는다 —
    호출 엣지도 이름 단위이므로 두 층의 알갱이가 같다.
    """
    table: dict[tuple[str, str, str], Symbol] = {}
    for symbol in sorted(symbols, key=lambda s: (s.span.path, s.span.start_line)):
        if symbol.kind not in _MEMBER_KINDS:
            continue
        owner = symbol.parent or module_owner(symbol.span.path)
        table.setdefault((symbol.span.path, owner, symbol.name), symbol)
    return table


def module_functions(symbols: list[Symbol]) -> dict[tuple[str, str], Symbol]:
    """`(파일, 이름)`에서 그 파일의 모듈 수준 함수로. 같은 파일 안의 호출을 푸는 표다."""
    table: dict[tuple[str, str], Symbol] = {}
    for symbol in sorted(symbols, key=lambda s: (s.span.path, s.span.start_line)):
        if symbol.kind == SymbolKind.FUNCTION and not symbol.parent:
            table.setdefault((symbol.span.path, symbol.name), symbol)
    return table


def free_by_name(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    """이름에서 모듈 수준 함수 선언 목록으로. 임포트 증명과 함께 쓰는 표다."""
    found: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in sorted(symbols, key=lambda s: (s.span.path, s.span.start_line)):
        if symbol.kind == SymbolKind.FUNCTION and not symbol.parent and not symbol.is_test:
            found[symbol.name].append(symbol)
    return dict(found)


def imported_names(imports) -> dict[str, dict[str, str]]:
    """파일마다 `들여온 이름 -> 그 이름이 온 모듈`.

    이 표가 임포트 증명이다. 이름이 저장소에서 유일하다는 것만으로 이으면, 임포트하지도 않은
    함수를 부른다고 주장하게 된다(C-BRANCH-3).
    """
    table: dict[str, dict[str, str]] = defaultdict(dict)
    for record in imports:
        for name in record.names:
            table[record.span.path].setdefault(name, record.target)
    return dict(table)


def build_resolver(
    symbols: list[Symbol],
    bindings: list[Binding],
    imports,
    ts_declaring: dict[tuple[str, str], str] | None = None,
) -> Resolver:
    """해석에 쓰는 표를 한 번에 만든다.

    `ts_declaring`은 TypeScript 임포트가 실제로 닿는 선언 파일이다. 주지 않으면 그 언어의
    수신자 없는 호출은 풀리지 않는다. 틀리게 잇는 것보다 안 잇는 것이 낫다.
    """
    return Resolver(
        scopes=build_scopes(bindings),
        members=member_table(symbols),
        module_functions=module_functions(symbols),
        imported=imported_names(imports),
        free_by_name=free_by_name(symbols),
        ts_declaring=ts_declaring or {},
    )
