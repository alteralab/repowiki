"""매치 분류의 단위 검사. 임포트 문법과 소유 타입 판정이 대상이다."""

from __future__ import annotations

import pytest

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.domain import DomainFacts
from repowiki.analyze.symbols import extract
from repowiki.models import SymbolKind


@pytest.fixture
def facts() -> DomainFacts:
    return DomainFacts(
        extensions={".java": "java", ".py": "python"},
        analyzed_languages=["java", "python"],
        exclude_globs={},
        test_markers=["/src/test/"],
        build_files=["pom.xml"],
        kind_markers={},
    )


def _match(message: str, text: str, path: str = "a/A.java", line: int = 1, name: str | None = None) -> AstMatch:
    return AstMatch(
        rule_id=message, message=message, path=path, start_line=line, end_line=line, text=text, name=name
    )


def test_java_import_forms(facts: DomainFacts) -> None:
    """정적 임포트와 와일드카드 임포트에서 점 이름만 남긴다."""
    matches = [
        _match("import", "import a.b.C;", line=1),
        _match("import", "import static a.b.C.d;", line=2),
        _match("import", "import a.b.*;", line=3),
    ]
    result = extract(matches, [""], facts)
    assert [record.target for record in result.imports] == ["a.b.C", "a.b.C.d", "a.b"]


def test_python_import_forms(facts: DomainFacts) -> None:
    """`import a, b`와 `from a.b import c`를 각각 대상으로 편다."""
    matches = [
        _match("import", "import os, sys as system", path="p/m.py", line=1),
        _match("import.from", "from a.b import c", path="p/m.py", line=2),
    ]
    result = extract(matches, [""], facts)
    assert [record.target for record in result.imports] == ["os", "sys", "a.b"]


def test_owner_is_the_innermost_type(facts: DomainFacts) -> None:
    """중첩 타입 안의 참조는 안쪽 타입이 소유한다."""
    matches = [
        AstMatch(
            rule_id="r", message="def.class", path="a/A.java", start_line=1, end_line=40, text="", name="Outer"
        ),
        AstMatch(
            rule_id="r", message="def.class", path="a/A.java", start_line=10, end_line=20, text="", name="Inner"
        ),
        _match("ref.field_type", "Config", line=15, name="Config"),
    ]
    result = extract(matches, [""], facts)
    assert result.references[0].owner == "Inner"


def test_reference_outside_any_type_has_no_owner(facts: DomainFacts) -> None:
    """어느 타입에도 안 들어간 참조는 소유자가 없다. 그 사실이 뒤에서 세어진다."""
    matches = [
        AstMatch(
            rule_id="r", message="def.class", path="a/A.java", start_line=10, end_line=20, text="", name="Only"
        ),
        _match("ref.field_type", "Config", line=30, name="Config"),
    ]
    result = extract(matches, [""], facts)
    assert result.references[0].owner is None


def test_unknown_message_fails_loudly(facts: DomainFacts) -> None:
    """룰이 새 message를 내면 조용히 버리지 않고 멈춘다."""
    with pytest.raises(ValueError, match="알 수 없는 룰 message"):
        extract([_match("mystery", "x")], [""], facts)


def test_test_scope_entry_points_are_dropped(facts: DomainFacts) -> None:
    """테스트 소스의 진입점은 제품 표면이 아니다."""
    matches = [
        _match("entry.main", "public static void main", path="a/src/test/java/T.java", line=3),
        _match("entry.main", "public static void main", path="a/src/main/java/M.java", line=3),
    ]
    result = extract(matches, [""], facts)
    assert len(result.entry_points) == 1
    assert result.entry_points[0].span.path == "a/src/main/java/M.java"


def test_symbol_kinds_map_from_rule_messages(facts: DomainFacts) -> None:
    """룰 message가 선언 종류로 그대로 옮겨진다."""
    matches = [
        _match("def.record", "record W()", name="W"),
        _match("def.interface", "interface I", name="I"),
    ]
    result = extract(matches, [""], facts)
    assert {s.kind for s in result.symbols} == {SymbolKind.RECORD, SymbolKind.INTERFACE}
