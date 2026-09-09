"""Terraform 선언과 그 사이 엣지(PLAN §2.7).

경계 계약: 입력은 ast-grep 매치와 모듈 경계이고 출력은 `TerraformFacts`다. 파일을 읽지
않고 명령을 부르지 않는다(C-DEPTH-3).

파서는 ast-grep 하나다. `python-hcl2`를 쓰지 않는다 — ast-grep 0.45.3 의 `hcl` 문법이
블록과 속성과 참조 표현식을 모두 낸다는 것을 실측했고(2026-09-09, terraform-aws-vpc
77개 파일에서 블록 1823개), 줄 번호가 함께 나온다. 파서를 둘 두면 같은 사실을 두 자리에서
말하게 되고 그 둘이 어긋날 수 있다(C-DUP-2).

`terraform graph`를 부르지 않는다. 그것은 초기화된 작업 디렉토리와 제공자 다운로드를
요구한다. 오프라인 반입이 전제인 이 도구의 기본 경로에 둘 수 없다(PLAN §3).

사각: 값을 평가하지 않는다. `source = local.base`처럼 계산된 모듈 소스는 그 문자열
그대로 남고, `count`와 `for_each`가 만드는 실체의 개수는 세지 않는다. 선언이 무엇을
가리키는지까지가 이 모듈의 답이다.
"""

from __future__ import annotations

from collections import Counter

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.domain import DomainFacts, is_test
from repowiki.analyze.structure import module_of
from repowiki.models import Span, TerraformBlock, TerraformEdge, TerraformFacts

# 참조 머리 가운데 선언을 가리키지 않는 것. 반복문 변수와 개수와 경로다.
# 이것을 엣지로 내면 모든 리소스가 `each`에 기대는 것으로 그려진다.
_NOT_A_DECLARATION = frozenset({"each", "count", "path", "terraform", "self"})

_LABELLED = {"def.resource", "def.data"}
_SINGLE = {"def.module", "def.variable", "def.output", "def.provider", "def.local"}


def _kind_of(message: str) -> str:
    return message.split(".", 1)[1]


def _blocks(
    matches: list[AstMatch], roots: list[str], facts: DomainFacts
) -> list[TerraformBlock]:
    """선언 매치를 블록으로. 순서는 파일과 줄 순서다 — 결정적이어야 한다."""
    found: list[TerraformBlock] = []
    for match in matches:
        if match.message not in _LABELLED | _SINGLE:
            continue
        name = match.captures.get("NAME", "").strip()
        if not name:
            continue
        found.append(
            TerraformBlock.make(
                kind=_kind_of(match.message),
                type_name=match.captures.get("TYPE", "").strip(),
                name=name,
                span=Span(
                    path=match.path, start_line=match.start_line, end_line=match.end_line
                ),
                module=module_of(match.path, roots),
                is_test=is_test(match.path, facts),
            )
        )
    return sorted(found, key=lambda b: (b.span.path, b.span.start_line, b.address))


def _owner(blocks: list[TerraformBlock], span: Span) -> str:
    """이 자리를 감싸는 최상위 블록의 주소. 없으면 파일 이름이다.

    가장 안쪽을 고른다. 최상위 블록은 겹치지 않지만 같은 파일의 두 블록이 이어져 있으므로
    줄 범위로 골라야 한다.
    """
    inside = [
        block
        for block in blocks
        if block.span.path == span.path
        and block.span.start_line <= span.start_line
        and span.end_line <= block.span.end_line
    ]
    if not inside:
        return span.path.rsplit("/", 1)[-1]
    return min(inside, key=lambda b: b.span.end_line - b.span.start_line).address


def _edge_kind(head: str) -> str:
    """참조 머리에서 엣지 종류로. 머리가 셋 중 하나가 아니면 리소스 참조다."""
    return head if head in ("module", "var", "local", "data") else "resource"


def _source_edge(
    match: AstMatch, src: str, span: Span, roots: list[str], counts: Counter[str]
) -> TerraformEdge | None:
    """`module` 블록의 `source`. 대상은 주소가 아니라 경로나 레지스트리 이름이다."""
    target = match.captures.get("NAME", "").strip()
    if not target:
        counts["빈 모듈 소스"] += 1
        return None
    return TerraformEdge(
        src=src, dst=target, kind="source", span=span, module=module_of(match.path, roots)
    )


def _use_edge(
    match: AstMatch, src: str, span: Span, roots: list[str], counts: Counter[str]
) -> TerraformEdge | None:
    """표현식 안의 참조 하나. 머리가 선언을 가리키지 않으면 엣지가 아니다."""
    head = match.captures.get("HEAD", "").strip()
    name = match.captures.get("NAME", "").strip()
    if not head or not name:
        counts["이름 없는 참조"] += 1
        return None
    if head in _NOT_A_DECLARATION:
        counts[f"선언이 아닌 머리 {head}"] += 1
        return None
    # `data`만 이름이 두 단계다(`data.<타입>.<이름>`). 나머지는 머리와 이름 하나로 선언
    # 주소가 정해지고, 그 뒤는 그 선언의 속성이라 엣지의 대상이 아니다.
    if head == "data":
        second = match.captures.get("SECOND", "").strip()
        if not second:
            counts["이름이 모자란 data 참조"] += 1
            return None
        dst = f"data.{name}.{second}"
    else:
        dst = f"{head}.{name}"
    return TerraformEdge(
        src=src, dst=dst, kind=_edge_kind(head), span=span, module=module_of(match.path, roots)
    )


_EDGE_BUILDERS = {"ref.module_source": _source_edge, "ref.use": _use_edge}


def build(
    matches: list[AstMatch], roots: list[str], facts: DomainFacts
) -> TerraformFacts | None:
    """Terraform 사실. 선언이 하나도 없으면 `None`이다."""
    blocks = _blocks(matches, roots, facts)
    if not blocks:
        return None

    counts: Counter[str] = Counter()
    edges: list[TerraformEdge] = []
    for match in matches:
        make = _EDGE_BUILDERS.get(match.message)
        if make is None:
            continue
        span = Span(path=match.path, start_line=match.start_line, end_line=match.end_line)
        edge = make(match, _owner(blocks, span), span, roots, counts)
        if edge is not None:
            edges.append(edge)

    # 선언에 닿지 않는 참조는 엣지로 내지 않는다. `for k, v in ...`의 `v`와 `dynamic`
    # 블록의 반복 이름이 그런 것이고, 그것들은 무엇에 기대는지를 말하지 않는다. 이으면
    # 위키가 없는 결합을 그린다(C-BRANCH-3). 대신 세어서 어디로 갔는지 남긴다(C-REPORT-2).
    known = {block.address for block in blocks}
    kept = [edge for edge in edges if edge.kind == "source" or edge.dst in known]
    counts["선언에 닿지 않는 참조"] += len(edges) - len(kept)

    kept.sort(key=lambda e: (e.span.path, e.span.start_line, e.src, e.dst, e.kind))
    return TerraformFacts(
        blocks=blocks,
        edges=kept,
        unresolved=[
            f"{reason} {count}건" for reason, count in sorted(counts.items()) if count
        ],
    )
