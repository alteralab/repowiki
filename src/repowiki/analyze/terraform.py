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

import re
from collections import Counter
from pathlib import PurePosixPath

from pydantic import BaseModel

from repowiki.adapters.astgrep import AstMatch
from repowiki.analyze.domain import DomainFacts, is_test

_ROOT_DIR = "."


def terraform_module(path: str) -> str:
    """이 `.tf` 파일이 속한 Terraform 모듈. 그 파일이 있는 디렉토리다.

    저장소의 빌드 모듈과 다르다. 빌드 모듈은 pom.xml 이나 package.json 이 정하고
    Terraform 디렉토리를 알지 못해서, 일반적인 저장소의 루트와 `modules/*`와
    `examples/*`가 전부 한 모듈이 된다. 그러면 서로 다른 모듈의 `var.x`와 `local.x`와
    리소스가 같은 노드로 보이고, 어느 디렉토리에 선언이 없어야 할 참조도 다른 디렉토리에
    같은 주소가 있으면 이어진다. 실측에서 tf-vpc 의 주소 138개가 그렇게 충돌했다
    (2026-09-09 적대적 리뷰).

    Terraform 자신의 규칙이 이것이다. 한 디렉토리의 `.tf` 파일들이 한 모듈이고,
    다른 디렉토리는 `module` 블록으로만 부를 수 있다.
    """
    parent = str(PurePosixPath(path).parent)
    return _ROOT_DIR if parent in ("", ".") else parent
from repowiki.models import Span, TerraformBlock, TerraformEdge, TerraformFacts

# 참조 머리 가운데 선언을 가리키지 않는 것. 반복문 변수와 개수와 경로다.
# 이것을 엣지로 내면 모든 리소스가 `each`에 기대는 것으로 그려진다.
_NOT_A_DECLARATION = frozenset({"each", "count", "path", "terraform", "self"})

# URL 안의 사용자 정보(`https://user:token@host/...`). 모듈 소스는 원격 주소를 그대로
# 담을 수 있고 그 자리에 토큰이 들어간다. 키 이름이 없으므로 `corpus.mask`가 못 잡는다.
# 2026-09-09 적대적 리뷰가 `git::https://user:token@host/repo`가 facts.json 에 그대로
# 실리는 것을 재현했다. SC-2b.4 위반이다.
# ast-grep-ignore: regex-on-structure — 어휘: URL 의 userinfo 자리 판정이다.
_USERINFO = re.compile(r"(?<=//)[^/@\s]+@")

_LABELLED = {"def.resource", "def.data"}
_SINGLE = {"def.module", "def.variable", "def.output", "def.provider", "def.local"}


def _kind_of(message: str) -> str:
    return message.split(".", 1)[1]


def _blocks(matches: list[AstMatch], facts: DomainFacts) -> list[TerraformBlock]:
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
                # provider 는 alias 가 정체의 일부다. 다른 종류는 첫 라벨이다.
                type_name=(
                    match.captures.get("ALIAS", "").strip()
                    if match.message == "def.provider"
                    else match.captures.get("TYPE", "").strip()
                ),
                name=name,
                span=Span(
                    path=match.path, start_line=match.start_line, end_line=match.end_line
                ),
                module=terraform_module(match.path),
                is_test=is_test(match.path, facts),
            )
        )
    return sorted(found, key=lambda b: (b.span.path, b.span.start_line, b.address))


class _Owner(BaseModel):
    """참조의 소유자가 될 수 있는 자리. 선언일 수도 있고 아닐 수도 있다."""

    path: str
    start_line: int
    end_line: int
    address: str


def _owner_spans(
    blocks: list[TerraformBlock], matches: list[AstMatch]
) -> list[_Owner]:
    """소유자가 될 수 있는 자리 전부. 선언과, 선언이 아닌 최상위 블록이다.

    `terraform`과 `moved`와 `check` 같은 블록은 주소가 없어 선언으로 낼 수 없다. 그래도
    그 안의 참조에는 소유자가 있어야 한다. 없으면 서로 다른 블록의 관계가 한 파일 노드로
    뭉치고, 블록 수준의 결합이 사라진다(2026-09-10 적대적 리뷰).

    이것들은 `TerraformFacts.blocks`에 넣지 않는다. 선언이 아니기 때문이다 — 넣으면
    위키가 없는 선언을 있다고 말한다(C-REPORT-2).
    """
    found = [
        _Owner(
            path=block.span.path,
            start_line=block.span.start_line,
            end_line=block.span.end_line,
            address=block.address,
        )
        for block in blocks
    ]
    for match in matches:
        if match.message != "owner.block":
            continue
        kind = match.captures.get("KIND", "").strip()
        if not kind:
            continue
        name = match.captures.get("NAME", "").strip()
        found.append(
            _Owner(
                path=match.path,
                start_line=match.start_line,
                end_line=match.end_line,
                address=f"{kind}.{name}" if name else kind,
            )
        )
    return found


def _owner(owners: list[_Owner], span: Span) -> str:
    """이 자리를 감싸는 가장 안쪽 자리의 주소. 없으면 파일 이름이다.

    가장 안쪽을 고른다. 최상위 블록은 겹치지 않지만 같은 파일의 두 블록이 이어져 있으므로
    줄 범위로 골라야 한다. 같은 크기로 겹치면 주소로 갈라 순서를 고정한다.
    """
    inside = [
        owner
        for owner in owners
        if owner.path == span.path
        and owner.start_line <= span.start_line
        and span.end_line <= owner.end_line
    ]
    if not inside:
        return span.path.rsplit("/", 1)[-1]
    return min(inside, key=lambda o: (o.end_line - o.start_line, o.address)).address


def _edge_kind(head: str) -> str:
    """참조 머리에서 엣지 종류로. 머리가 셋 중 하나가 아니면 리소스 참조다."""
    return head if head in ("module", "var", "local", "data") else "resource"


def _source_edge(
    match: AstMatch, src: str, span: Span, counts: Counter[str]
) -> TerraformEdge | None:
    """`module` 블록의 `source`. 대상은 주소가 아니라 경로나 레지스트리 이름이다.

    URL 의 사용자 정보는 가린다. 어디서 가져오는지는 남기고 무엇으로 인증하는지는 지운다.
    """
    target = match.captures.get("NAME", "").strip()
    if not target:
        counts["빈 모듈 소스"] += 1
        return None
    masked = _USERINFO.sub("<자격증명 가림>@", target)
    if masked != target:
        counts["자격증명을 가린 모듈 소스"] += 1
        target = masked
    return TerraformEdge(
        src=src, dst=target, kind="source", span=span, module=terraform_module(match.path)
    )


def _use_edge(
    match: AstMatch, src: str, span: Span, counts: Counter[str]
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
        src=src, dst=dst, kind=_edge_kind(head), span=span, module=terraform_module(match.path)
    )


def _provider_edge(
    match: AstMatch, src: str, span: Span, counts: Counter[str]
) -> TerraformEdge | None:
    """`provider = aws.west`. 이 리소스가 어느 제공자 구성을 쓰는가."""
    name = match.captures.get("NAME", "").strip()
    if not name:
        counts["이름 없는 provider 선택"] += 1
        return None
    alias = match.captures.get("ALIAS", "").strip()
    dst = f"provider.{name}.{alias}" if alias else f"provider.{name}"
    return TerraformEdge(
        src=src, dst=dst, kind="provider", span=span, module=terraform_module(match.path)
    )


_EDGE_BUILDERS = {
    "ref.module_source": _source_edge,
    "ref.use": _use_edge,
    "ref.provider": _provider_edge,
}


def _iterators(matches: list[AstMatch]) -> dict[str, set[str]]:
    """파일마다 그 파일이 묶는 반복 이름. `for`의 변수와 `dynamic` 블록의 라벨이다.

    정확한 어휘 범위가 아니라 파일 단위로 모은다. ast-grep 은 이름을 범위에 묶어 주지
    않으므로 그보다 좁게 잡을 수 없다. 넓게 제외하는 쪽으로 기운 판정이다 — 제외를 덜 하면
    없는 결합이 사실이 되고, 더 하면 있는 결합이 빠진다. 두 실수의 값이 다르다.
    """
    found: dict[str, set[str]] = {}
    for match in matches:
        if match.message != "ref.iterator":
            continue
        name = (match.captures.get("NAME") or match.text).strip().strip('"')
        if name:
            found.setdefault(match.path, set()).add(name)
    return found


def build(matches: list[AstMatch], facts: DomainFacts) -> TerraformFacts | None:
    """Terraform 사실. 선언이 하나도 없으면 `None`이다."""
    blocks = _blocks(matches, facts)
    if not blocks:
        return None

    counts: Counter[str] = Counter()
    owners = _owner_spans(blocks, matches)
    iterators = _iterators(matches)
    edges: list[TerraformEdge] = []
    for match in matches:
        make = _EDGE_BUILDERS.get(match.message)
        if make is None:
            continue
        span = Span(path=match.path, start_line=match.start_line, end_line=match.end_line)
        if match.message == "ref.use":
            head = match.captures.get("HEAD", "").strip()
            if head in iterators.get(match.path, ()):
                counts["반복 이름"] += 1
                continue
        edge = make(match, _owner(owners, span), span, counts)
        if edge is not None:
            edges.append(edge)

    # 선언에 닿지 않는 참조는 엣지로 내지 않는다. `for k, v in ...`의 `v`와 `dynamic`
    # 블록의 반복 이름이 그런 것이고, 그것들은 무엇에 기대는지를 말하지 않는다. 이으면
    # 위키가 없는 결합을 그린다(C-BRANCH-3). 대신 세어서 어디로 갔는지 남긴다(C-REPORT-2).
    # 같은 Terraform 모듈 안에서만 선언을 찾는다. 저장소 전체에서 찾으면 다른 디렉토리의
    # 같은 이름이 이 디렉토리의 참조를 받아 준다.
    known = {(block.module, block.address) for block in blocks}
    kept = [
        edge
        for edge in edges
        if edge.kind == "source" or (edge.module, edge.dst) in known
    ]
    counts["선언에 닿지 않는 참조"] += len(edges) - len(kept)

    kept.sort(key=lambda e: (e.span.path, e.span.start_line, e.src, e.dst, e.kind))
    return TerraformFacts(
        blocks=blocks,
        edges=kept,
        unresolved=[
            f"{reason} {count}건" for reason, count in sorted(counts.items()) if count
        ],
    )
