"""호출 해석의 단위 검사.

여기서 고정하는 것은 이름 가림 순서와 계수의 합이다. 가림 순서가 틀리면 같은 이름의 필드가
지역 변수를 가려 없는 호출이 사실이 되고, 계수의 합이 입력과 다르면 어딘가에서 조용히
사라진 것이다(C-REPORT-2).
"""

from __future__ import annotations

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.calls import (
    Binding,
    CallSite,
    Resolver,
    base_type,
    build_resolver,
    build_scopes,
    collect,
    member_table,
    module_owner,
    resolve,
)
from repowiki.analyze.symbols import ImportRecord
from repowiki.analyze.domain import DomainFacts
from repowiki.models import Span, Symbol, SymbolKind

FACTS = DomainFacts(
    extensions={".java": "java"},
    analyzed_languages=["java"],
    exclude_globs={},
    test_markers=["/src/test/"],
    build_files=["pom.xml"],
    kind_markers={},
)


def _match(message: str, line: int, captures: dict[str, str], path: str = "a/A.java") -> AstMatch:
    return AstMatch(
        rule_id=message,
        message=message,
        path=path,
        start_line=line,
        end_line=line,
        text="",
        name=captures.get("NAME"),
        captures=captures,
    )


def _symbol(kind: SymbolKind, name: str, start: int, end: int, parent: str | None = None) -> Symbol:
    return Symbol(
        kind=kind,
        name=name,
        span=Span(path="a/A.java", start_line=start, end_line=end),
        module=".",
        language="java",
        is_test=False,
        parent=parent,
    )


def test_base_type_strips_generics_arrays_and_qualifiers() -> None:
    assert base_type("Map<String, Option>") == "Map"
    assert base_type("java.util.List") == "List"
    assert base_type("Option[]") == "Option"


def test_module_owner_is_the_file_stem() -> None:
    assert module_owner("airflow/models/dag.py") == "dag"


def test_local_binding_shadows_field_of_the_same_name_after_its_declaration() -> None:
    bindings = [
        Binding(
            name="parser",
            type_name="Parser",
            scope="field",
            span=Span(path="a/A.java", start_line=3, end_line=3),
            owner_type="Holder",
        ),
        Binding(
            name="parser",
            type_name="DefaultParser",
            scope="local",
            span=Span(path="a/A.java", start_line=9, end_line=9),
            owner_type="Holder",
            owner_member="run",
        ),
    ]
    scope = build_scopes(bindings)["a/A.java"]
    assert scope.lookup("parser", "Holder", "run", 10).type_name == "DefaultParser"
    # 선언보다 앞의 호출은 지역 변수를 보지 못한다. 그 자리의 `parser`는 필드다.
    assert scope.lookup("parser", "Holder", "run", 8).type_name == "Parser"
    assert scope.lookup("parser", "Holder", "other", 99).type_name == "Parser"


def test_two_methods_of_the_same_name_in_one_file_do_not_share_a_scope() -> None:
    def _param(owner: str, type_name: str, line: int) -> Binding:
        return Binding(
            name="x",
            type_name=type_name,
            scope="param",
            span=Span(path="a/A.java", start_line=line, end_line=line),
            owner_type=owner,
            owner_member="run",
        )

    scope = build_scopes([_param("C1", "A", 2), _param("C2", "B", 20)])["a/A.java"]
    assert scope.lookup("x", "C1", "run", 3).type_name == "A"
    assert scope.lookup("x", "C2", "run", 21).type_name == "B"


def test_collect_reads_captures_and_assigns_owners() -> None:
    symbols = [
        _symbol(SymbolKind.CLASS, "Holder", 1, 20),
        _symbol(SymbolKind.METHOD, "run", 5, 12, parent="Holder"),
    ]
    matches = [
        _match("bind.field", 2, {"NAME": "parser", "TYPE": "Parser"}),
        _match("bind.local", 6, {"NAME": "tmp", "TYPE": "Option"}),
        _match("bind.call", 7, {"RECV": "parser", "NAME": "parse"}),
        _match("bind.call_bare", 8, {"NAME": "helper"}),
    ]
    bindings, sites = collect(matches, symbols, ["."], FACTS)
    assert [(b.name, b.type_name, b.scope) for b in bindings] == [
        ("parser", "Parser", "field"),
        ("tmp", "Option", "local"),
    ]
    assert bindings[0].owner_member is None
    assert bindings[1].owner_member == "run"
    assert [(s.receiver, s.method, s.owner_type, s.owner_member) for s in sites] == [
        ("parser", "parse", "Holder", "run"),
        ("", "helper", "Holder", "run"),
    ]


def test_resolve_emits_field_call_and_counts_every_site() -> None:
    parser = _symbol(SymbolKind.CLASS, "Parser", 1, 10)
    parse = _symbol(SymbolKind.METHOD, "parse", 2, 4, parent="Parser")
    symbols = [parser, parse]
    sites = [
        CallSite(
            receiver="parser",
            method="parse",
            span=Span(path="a/A.java", start_line=7, end_line=7),
            module=".",
            owner_type="Holder",
            owner_member="run",
        ),
        CallSite(
            receiver="buf.toString()",
            method="length",
            span=Span(path="a/A.java", start_line=8, end_line=8),
            module=".",
            owner_type="Holder",
            owner_member="run",
        ),
        CallSite(
            receiver="unknownThing",
            method="go",
            span=Span(path="a/A.java", start_line=9, end_line=9),
            module=".",
            owner_type="Holder",
            owner_member="run",
        ),
    ]
    scopes = build_scopes(
        [
            Binding(
                name="parser",
                type_name="Parser",
                scope="field",
                span=Span(path="a/A.java", start_line=3, end_line=3),
                owner_type="Holder",
            )
        ]
    )
    edges, counts = resolve(
        sites,
        Resolver(scopes=scopes, members=member_table(symbols)),
        lambda name, _site: parser if name == "Parser" else None,
    )
    assert [(e.src_type, e.src_member, e.dst_type, e.dst_member) for e in edges] == [
        ("Holder", "run", "Parser", "parse")
    ]
    assert edges[0].receiver_kind == "field"
    assert counts.chained_receiver == 1
    assert counts.unknown_receiver == 1
    assert counts.total() == len(sites)


def _free(path: str, name: str = "helper") -> Symbol:
    return Symbol(
        kind=SymbolKind.FUNCTION,
        name=name,
        span=Span(path=path, start_line=3, end_line=6),
        module=".",
        language="python",
        is_test=False,
    )


def _py_site(method: str = "helper") -> CallSite:
    return CallSite(
        receiver="",
        method=method,
        span=Span(path="pkg/main.py", start_line=9, end_line=9),
        module=".",
        language="python",
        owner_type="Runner",
        owner_member="run",
    )


def _import(path: str, target: str, names: list[str]) -> ImportRecord:
    return ImportRecord(
        target=target,
        span=Span(path=path, start_line=1, end_line=1),
        module=".",
        is_test=False,
        names=names,
    )


def test_a_python_bare_call_resolves_only_when_the_import_proves_it() -> None:
    helper = _free("pkg/util.py")
    resolver = build_resolver(
        [helper], [], [_import("pkg/main.py", "pkg.util", ["helper"])]
    )
    edges, counts = resolve([_py_site()], resolver, lambda _name, _site: None)
    assert [(e.dst_type, e.dst_member, e.receiver_kind) for e in edges] == [
        ("util", "helper", "import")
    ]
    assert counts.total() == 1


def test_a_python_bare_call_without_an_import_is_not_resolved() -> None:
    resolver = build_resolver([_free("pkg/util.py")], [], [])
    edges, counts = resolve([_py_site()], resolver, lambda _name, _site: None)
    assert edges == []
    assert counts.unknown_receiver == 1


def test_a_python_bare_call_is_not_attributed_to_the_enclosing_class() -> None:
    method = Symbol(
        kind=SymbolKind.METHOD,
        name="helper",
        span=Span(path="pkg/main.py", start_line=4, end_line=5),
        module=".",
        language="python",
        is_test=False,
        parent="Runner",
    )
    resolver = build_resolver([method], [], [])
    edges, counts = resolve([_py_site()], resolver, lambda _name, _site: None)
    assert edges == []
    assert counts.unknown_receiver == 1


def test_a_java_bare_call_is_the_enclosing_type() -> None:
    method = Symbol(
        kind=SymbolKind.METHOD,
        name="helper",
        span=Span(path="a/A.java", start_line=4, end_line=5),
        module=".",
        language="java",
        is_test=False,
        parent="Holder",
    )
    site = CallSite(
        receiver="",
        method="helper",
        span=Span(path="a/A.java", start_line=9, end_line=9),
        module=".",
        language="java",
        owner_type="Holder",
        owner_member="run",
    )
    edges, _ = resolve([site], build_resolver([method], [], []), lambda _name, _site: None)
    assert [(e.dst_type, e.dst_member, e.receiver_kind) for e in edges] == [
        ("Holder", "helper", "self")
    ]


def test_same_named_types_in_different_files_do_not_share_members() -> None:
    def _type(path: str) -> Symbol:
        return Symbol(
            kind=SymbolKind.CLASS,
            name="Client",
            span=Span(path=path, start_line=1, end_line=20),
            module=".",
            language="java",
            is_test=False,
        )

    def _method(path: str) -> Symbol:
        return Symbol(
            kind=SymbolKind.METHOD,
            name="send",
            span=Span(path=path, start_line=5, end_line=8),
            module=".",
            language="java",
            is_test=False,
            parent="Client",
        )

    table = member_table([_method("a/Client.java"), _method("b/Client.java")])
    assert ("a/Client.java", "Client", "send") in table
    assert ("b/Client.java", "Client", "send") in table
    assert table[("a/Client.java", "Client", "send")].span.path == "a/Client.java"
