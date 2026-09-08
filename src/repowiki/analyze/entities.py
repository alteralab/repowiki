"""데이터 모델 사실: 엔티티, 속성, 외래 키. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 ast-grep 매치와 도메인 사실이고 출력은 이름 붙은 형태다.

무엇을 엔티티로 보는가는 원천이 정한다. 파이썬은 `__tablename__`을 선언한 클래스이고,
자바는 `@Entity`나 `@Table`이 붙은 클래스다. 둘 다 저장소가 스스로 "이것은 테이블이다"라고
적어 둔 자리라 추정이 아니다.

사각: 관계의 방향과 다중성은 외래 키 문자열과 애노테이션 이름에서만 읽는다. 실제 제약이
데이터베이스에 어떻게 걸렸는지는 보지 않는다. 이름 없이 만들어지는 관계(런타임 조인)도
보이지 않는다.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.domain import DomainFacts, is_test
from repowiki.analyze.structure import module_of
from repowiki.models import Span, Symbol, SymbolKind

_MAX_ATTRIBUTES = 12


class Attribute(BaseModel):
    """엔티티의 속성 하나."""

    name: str
    span: Span


class Relation(BaseModel):
    """엔티티 사이의 관계. `kind`는 원천이 말한 이름 그대로다."""

    src: str
    dst_table: str
    kind: str
    span: Span


class Entity(BaseModel):
    """테이블 하나. `table`은 저장소가 적어 둔 이름이고 `type_name`은 그 선언 타입이다."""

    table: str
    type_name: str
    module: str
    span: Span
    attributes: list[Attribute]


class EntityGraph(BaseModel):
    """데이터 모델 묶음. 엔티티가 없으면 빈 그래프다."""

    entities: list[Entity]
    relations: list[Relation]


def _strip_quotes(text: str) -> str:
    return text.strip().strip("\"'")


def _table_name(match: AstMatch) -> str:
    """`__tablename__ = "log"`이나 `@Table(name = "log")`에서 이름만 꺼낸다."""
    text = match.text
    if "=" in text:
        return _strip_quotes(text.split("=", 1)[1])
    if "(" in text and ")" in text:
        inner = text[text.index("(") + 1 : text.rindex(")")]
        if "=" in inner:
            return _strip_quotes(inner.split("=", 1)[1])
        return _strip_quotes(inner)
    return ""


def _foreign_table(match: AstMatch) -> str:
    """`ForeignKey("dag_version.id")`에서 대상 테이블 이름만 꺼낸다."""
    text = match.text
    if "(" not in text:
        return ""
    inner = text[text.index("(") + 1 :]
    target = _strip_quotes(inner.split(",")[0])
    return target.split(".")[0]


def _owner(types: list[Symbol], span: Span) -> Symbol | None:
    """이 자리를 감싸는 가장 작은 타입."""
    enclosing = [
        symbol
        for symbol in types
        if symbol.span.path == span.path
        and symbol.span.start_line <= span.start_line <= symbol.span.end_line
    ]
    if not enclosing:
        return None
    return min(enclosing, key=lambda s: s.span.end_line - s.span.start_line)


def build(
    matches: list[AstMatch], symbols: list[Symbol], roots: list[str], facts: DomainFacts
) -> EntityGraph:
    """매치와 선언에서 데이터 모델을 만든다. 감싸는 타입이 없는 표식은 버리고 세지 않는다."""
    types = [
        s
        for s in symbols
        if s.kind in (SymbolKind.CLASS, SymbolKind.RECORD, SymbolKind.INTERFACE) and not s.is_test
    ]
    by_type: dict[str, Entity] = {}
    attributes: dict[str, list[Attribute]] = defaultdict(list)
    relations: list[Relation] = []

    for match in matches:
        if not match.message.startswith("entity."):
            continue
        if is_test(match.path, facts):
            continue
        span = Span(path=match.path, start_line=match.start_line, end_line=match.end_line)
        owner = _owner(types, span)
        if owner is None:
            continue
        if match.message == "entity.table":
            table = _table_name(match) or owner.name
            by_type.setdefault(
                owner.name,
                Entity(
                    table=table,
                    type_name=owner.name,
                    module=module_of(match.path, roots),
                    span=owner.span,
                    attributes=[],
                ),
            )
        elif match.message == "entity.column":
            name = match.text.split(":")[0].split("=")[0].strip()
            attributes[owner.name].append(Attribute(name=name, span=span))
        elif match.message in ("entity.foreign_key", "entity.relation"):
            target = _foreign_table(match)
            if target:
                relations.append(
                    Relation(
                        src=owner.name,
                        dst_table=target,
                        kind=match.message.removeprefix("entity."),
                        span=span,
                    )
                )

    for type_name, entity in by_type.items():
        entity.attributes = attributes.get(type_name, [])[:_MAX_ATTRIBUTES]
    entities = sorted(by_type.values(), key=lambda e: (e.module, e.table))
    known_tables = {e.table for e in entities}
    kept = [
        relation
        for relation in relations
        if relation.dst_table in known_tables and relation.src in by_type
    ]
    kept.sort(key=lambda r: (r.src, r.dst_table, r.span.path, r.span.start_line))
    return EntityGraph(entities=entities, relations=kept)
