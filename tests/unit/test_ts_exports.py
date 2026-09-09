"""TypeScript 수출 표의 단위 검사.

여기서 고정하는 것은 barrel 을 따라 원 선언까지 가는 길이다. 따라가지 않으면 `index.ts`를
가리키는 임포트가 선언 없는 파일을 가리키고, 그 자리에서 만든 엣지는 실제 관계가 아니다.
"""

from __future__ import annotations

from repowiki.analyze.symbols import ReExportRecord
from repowiki.analyze.tsmodules import build, build_export_table, load_configs, resolve_export
from repowiki.models import Span, Symbol, SymbolKind

FILES = [
    "p/tsconfig.json",
    "p/index.ts",
    "p/inner.ts",
    "p/deep.ts",
    "p/mid.ts",
    "p/user.ts",
]


def _symbol(name: str, path: str) -> Symbol:
    return Symbol(
        kind=SymbolKind.CLASS,
        name=name,
        span=Span(path=path, start_line=1, end_line=2),
        module=".",
        language="typescript",
        is_test=False,
    )


def _record(kind: str, specifier: str, path: str, line: int, name: str = "") -> ReExportRecord:
    return ReExportRecord(kind=kind, specifier=specifier, name=name, path=path, line=line)


def _resolver():
    return build(load_configs({"p/tsconfig.json": "{}"}), FILES)


def test_a_star_reexport_is_followed_to_the_declaring_file() -> None:
    table = build_export_table(
        [_symbol("Inner", "p/inner.ts")],
        [_record("star", "./inner", "p/index.ts", 1)],
    )
    assert resolve_export(table, _resolver(), "p/index.ts", "Inner") == "p/inner.ts"


def test_a_renamed_reexport_maps_the_outward_name_to_the_original() -> None:
    """`export { Deep as Renamed }`. 밖에서 부르는 이름은 `Renamed`이고 선언은 `Deep`이다."""
    table = build_export_table(
        [_symbol("Deep", "p/deep.ts")],
        [
            _record("name", "./deep", "p/index.ts", 1, "Deep"),
            _record("alias", "./deep", "p/index.ts", 1, "Renamed"),
        ],
    )
    resolver = _resolver()
    assert resolve_export(table, resolver, "p/index.ts", "Renamed") == "p/deep.ts"
    # 원래 이름으로는 이 barrel 에서 나가지 않는다.
    assert resolve_export(table, resolver, "p/index.ts", "Deep") == ""


def test_one_alias_among_several_names_binds_to_the_first() -> None:
    """`export { A as B, C } from`. 별칭은 첫 이름에 붙고 둘째는 그대로 나간다."""
    table = build_export_table(
        [_symbol("Deep", "p/deep.ts"), _symbol("Other", "p/deep.ts")],
        [
            _record("name", "./deep", "p/index.ts", 1, "Deep"),
            _record("name", "./deep", "p/index.ts", 1, "Other"),
            _record("alias", "./deep", "p/index.ts", 1, "Renamed"),
        ],
    )
    resolver = _resolver()
    assert resolve_export(table, resolver, "p/index.ts", "Renamed") == "p/deep.ts"
    assert resolve_export(table, resolver, "p/index.ts", "Other") == "p/deep.ts"


def test_a_chain_of_barrels_is_followed() -> None:
    table = build_export_table(
        [_symbol("Deep", "p/deep.ts")],
        [
            _record("star", "./mid", "p/index.ts", 1),
            _record("star", "./deep", "p/mid.ts", 1),
        ],
    )
    assert resolve_export(table, _resolver(), "p/index.ts", "Deep") == "p/deep.ts"


def test_a_cycle_of_barrels_stops_instead_of_looping() -> None:
    """barrel 이 서로를 가리키면 멈춘다. 무한히 따라가면 분석이 끝나지 않는다."""
    table = build_export_table(
        [],
        [
            _record("star", "./mid", "p/index.ts", 1),
            _record("star", "./index", "p/mid.ts", 1),
        ],
    )
    assert resolve_export(table, _resolver(), "p/index.ts", "Nothing") == ""


def test_a_namespace_reexport_becomes_an_own_name() -> None:
    """`export * as ns from`은 이름 하나로 묶여 나간다. 개별 이름을 따라가지 않는다."""
    table = build_export_table([], [_record("namespace", "./inner", "p/index.ts", 1, "ns")])
    assert resolve_export(table, _resolver(), "p/index.ts", "ns") == "p/index.ts"


def test_a_name_the_barrel_does_not_export_is_not_invented() -> None:
    table = build_export_table(
        [_symbol("Inner", "p/inner.ts")], [_record("star", "./inner", "p/index.ts", 1)]
    )
    assert resolve_export(table, _resolver(), "p/index.ts", "Missing") == ""
