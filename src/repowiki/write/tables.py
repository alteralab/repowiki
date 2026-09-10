"""페이지에 실을 사실 표를 만든다. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 사실이고 출력은 `FactTable`이다. Markdown 표기는 `bundle/tables.py`가
소유한다 — 여기서 만드는 것은 값이지 글자가 아니다.

표의 모든 값에는 그 값을 적은 자리가 함께 붙는다. 값과 근거가 같은 줄에 있어야 사람이 그
숫자를 믿을 수 있고, 틀렸을 때 어디를 고쳐야 하는지 안다.
"""

from __future__ import annotations

from repowiki.bundle.links import Citer, citer_for
from repowiki.models import FactTable, RepoFacts, Span, Symbol, SymbolKind

_MAX_ROWS = 30
_MEMBER_KINDS = {SymbolKind.METHOD, SymbolKind.CONSTRUCTOR, SymbolKind.FUNCTION}


def _cite(span: Span, citer: Citer | None = None) -> str:
    """표의 근거 칸. 소스로 갈 수 있으면 링크다.

    표의 값은 사람이 그대로 믿는 자리다. 그 자리에서 바로 코드로 갈 수 없으면, 믿을지 말지를
    판단할 방법이 경로를 손으로 찾는 것뿐이다.
    """
    return (citer or Citer()).markdown(span)


def _citer(facts: RepoFacts) -> Citer:
    """이 저장소의 인용기. 원격과 분석 커밋이 링크를 만든다."""
    return citer_for(facts.profile.remote_url, facts.profile.head_sha)


def language_table(facts: RepoFacts) -> FactTable | None:
    """언어와 런타임의 버전. 저장소가 적어 둔 자리를 함께 싣는다."""
    chain = facts.toolchain
    if chain is None or not chain.languages:
        return None
    citer = _citer(facts)
    rows = [
        [item.language, item.version, item.source, _cite(item.span, citer)]
        for item in chain.languages[:_MAX_ROWS]
    ]
    return FactTable(
        id="lang-versions",
        title="언어와 런타임 버전",
        columns=["언어", "버전", "선언 자리", "근거"],
        rows=rows,
        note="저장소가 빌드 파일에 적어 둔 값이다. 실제로 설치되는 버전이 아니다.",
    )


def dependency_table(facts: RepoFacts, module: str | None = None) -> FactTable | None:
    """라이브러리와 그 버전. 모듈을 주면 그 모듈이 선언한 것만 싣는다."""
    chain = facts.toolchain
    if chain is None or not chain.dependencies:
        return None
    items = [item for item in chain.dependencies if module is None or item.module == module]
    if not items:
        return None
    citer = _citer(facts)
    rows = [
        [
            item.name,
            item.version or "(빌드가 정함)",
            item.scope,
            item.ecosystem,
            _cite(item.span, citer),
        ]
        for item in items[:_MAX_ROWS]
    ]
    note = "빌드 파일이 선언한 좌표다. 잠금 파일은 보지 않는다."
    if len(items) > _MAX_ROWS:
        note = f"{note} 선언 {len(items)}건 중 앞 {_MAX_ROWS}건이다."
    if chain.truncated:
        note = f"{note} 저장소 전체에서 {chain.truncated}건은 상한을 넘어 사실에 담기지 않았다."
    return FactTable(
        id=f"deps-{module or 'all'}",
        title="라이브러리 버전" if module is None else f"{module}의 라이브러리 버전",
        columns=["좌표", "버전", "범위", "생태계", "근거"],
        rows=rows,
        note=note,
    )


def member_table(
    type_name: str,
    path: str,
    symbols: list[Symbol],
    label: str = "",
    citer: Citer | None = None,
) -> FactTable | None:
    """한 타입의 멤버. 사람이 "이 타입으로 무엇을 할 수 있는가"를 먼저 읽는 자리다.

    타입의 정체는 이름이 아니라 선언 파일이다. 이름만 보면 저장소 곳곳의 `Builder`가 한 표에
    모여, 이 페이지와 상관없는 멤버가 이 타입의 멤버로 실린다.
    """
    mine = [
        s for s in symbols if s.parent == type_name and s.span.path == path and not s.is_test
    ]
    if not mine:
        return None
    ordered = sorted(mine, key=lambda s: (s.kind.value, s.name, s.span.start_line))
    rows = [
        [
            f"`{symbol.name}`",
            symbol.kind.value,
            _cite(symbol.span, citer),
        ]
        for symbol in ordered[:_MAX_ROWS]
    ]
    note = ""
    if len(ordered) > _MAX_ROWS:
        note = f"멤버 {len(ordered)}개 중 앞 {_MAX_ROWS}개다."
    return FactTable(
        id=f"members-{type_name}",
        title=f"{label or type_name}의 멤버",
        columns=["이름", "종류", "근거"],
        rows=rows,
        note=note,
    )


def type_inventory(
    title: str,
    labels: dict[str, str],
    symbols: list[Symbol],
    citer: Citer | None = None,
) -> FactTable | None:
    """묶음이 담은 타입 목록. 페이지가 무엇을 다루는지 한눈에 보이는 자리다."""
    if not symbols:
        return None
    ordered = sorted(symbols, key=lambda s: (s.span.path, s.name))
    rows = [
        [
            f"`{labels.get(f'{s.span.path}#{s.name}', s.name)}`",
            s.kind.value,
            _cite(s.span, citer),
        ]
        for s in ordered[:_MAX_ROWS]
    ]
    return FactTable(
        id=f"types-{title}",
        title=f"{title}이 담은 타입",
        columns=["타입", "종류", "근거"],
        rows=rows,
        note=f"타입 {len(ordered)}개 중 앞 {len(rows)}개다." if len(ordered) > _MAX_ROWS else "",
    )


def config_table(facts: RepoFacts, prefix: str | None = None) -> FactTable | None:
    """설정 키와 값. 운영자가 무엇을 돌릴 수 있는지 읽는 자리다."""
    corpus = facts.corpus
    if corpus is None or not corpus.config_keys:
        return None
    items = [
        item for item in corpus.config_keys if prefix is None or item.path.startswith(prefix)
    ]
    if not items:
        return None
    citer = _citer(facts)
    rows = [
        [f"`{item.key}`", f"`{item.value}`" if item.value else "", _cite(item.span, citer)]
        for item in items[:_MAX_ROWS]
    ]
    return FactTable(
        id=f"config-{prefix or 'all'}",
        title="설정 키",
        columns=["키", "값", "근거"],
        rows=rows,
        note=f"키 {len(items)}건 중 앞 {len(rows)}건이다." if len(items) > _MAX_ROWS else "",
    )


def period_table(facts: RepoFacts) -> FactTable | None:
    """분기마다 커밋 수와 가장 많이 바뀐 파일. 이력 그림이 커밋 수만 그리므로 파일 이름은
    이 표가 유일한 자리다(2026-09-10, timeline 을 막대그래프로 바꾸면서 옮겼다).

    이력 사실에는 줄 범위가 없어 근거 칸이 없다. 값의 출처는 git 이력 자체다.
    """
    history = facts.history
    if history is None or not history.periods:
        return None
    rows = [
        [
            str(period.get("label", "")),
            str(period.get("commits", 0)),
            f"`{period['top_path']}`" if period.get("top_path") else "",
            str(period.get("top_revisions", "")) if period.get("top_path") else "",
        ]
        for period in history.periods[-_MAX_ROWS:]
    ]
    return FactTable(
        id="history-periods",
        title="분기별 커밋과 가장 많이 바뀐 파일",
        columns=["분기", "커밋", "가장 많이 바뀐 파일", "그 파일의 변경 횟수"],
        rows=rows,
        note=f"최근 {history.window_months}개월 창의 분기다. 값은 git 이력에서 셌다.",
    )


def module_table(facts: RepoFacts) -> FactTable | None:
    """모듈 목록과 크기. 저장소가 무엇으로 나뉘는지 처음 보는 사람이 읽는 자리다."""
    if len(facts.modules) < 2:
        return None
    ordered = sorted(facts.modules, key=lambda m: -m.main_file_count)
    outgoing = {m.id: 0 for m in facts.modules}
    incoming = {m.id: 0 for m in facts.modules}
    for edge in facts.module_edges:
        outgoing[edge.src] = outgoing.get(edge.src, 0) + 1
        incoming[edge.dst] = incoming.get(edge.dst, 0) + 1
    rows = [
        [
            f"`{module.id}`",
            str(module.main_file_count),
            ", ".join(sorted(module.languages)),
            str(outgoing.get(module.id, 0)),
            str(incoming.get(module.id, 0)),
        ]
        for module in ordered[:_MAX_ROWS]
    ]
    return FactTable(
        id="modules",
        title="모듈",
        columns=["모듈", "제품 파일", "언어", "기대는 모듈 수", "기대어지는 모듈 수"],
        rows=rows,
        note=f"모듈 {len(ordered)}개 중 앞 {len(rows)}개다." if len(ordered) > _MAX_ROWS else "",
    )


def callers_table(type_name: str, facts: RepoFacts) -> FactTable | None:
    """이 타입의 멤버를 누가 부르는가. 호출 그래프가 있어야 만들 수 있는 표다."""
    incoming = [e for e in facts.call_edges if e.dst_type == type_name]
    if not incoming:
        return None
    citer = _citer(facts)
    ordered = sorted(
        incoming, key=lambda e: (e.dst_member, e.src_type, e.src_member, e.span.start_line)
    )
    seen: set[tuple[str, str, str]] = set()
    rows: list[list[str]] = []
    for edge in ordered:
        key = (edge.dst_member, edge.src_type, edge.src_member)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            [
                f"`{edge.dst_member}`",
                f"`{edge.src_type}.{edge.src_member}`",
                edge.receiver_kind,
                _cite(edge.span, citer),
            ]
        )
        if len(rows) >= _MAX_ROWS:
            break
    return FactTable(
        id=f"callers-{type_name}",
        title=f"{type_name}을 부르는 자리",
        columns=["불리는 멤버", "부르는 자리", "수신자 종류", "근거"],
        rows=rows,
        note="수신자를 스코프에서 푼 호출만이다. 체인 표현식과 상속받은 멤버는 빠진다.",
    )


def test_inventory(symbols: list[Symbol], citer: Citer | None = None) -> FactTable | None:
    """테스트 파일과 그 안의 검사 수. 사용 예 쪽이 무엇을 근거로 삼는지 보이는 자리다."""
    counted: dict[str, int] = {}
    first: dict[str, Span] = {}
    for symbol in symbols:
        if symbol.is_test and symbol.kind in _MEMBER_KINDS:
            counted[symbol.span.path] = counted.get(symbol.span.path, 0) + 1
            first.setdefault(symbol.span.path, symbol.span)
    if not counted:
        return None
    rows = [
        [_cite(Span(path=path, start_line=1, end_line=1), citer), str(count)]
        for path, count in sorted(counted.items(), key=lambda item: (-item[1], item[0]))[:_MAX_ROWS]
    ]
    return FactTable(
        id="tests",
        title="테스트 파일",
        columns=["파일", "검사 수"],
        rows=rows,
        note=f"테스트 파일 {len(counted)}개 중 앞 {len(rows)}개다."
        if len(counted) > _MAX_ROWS
        else "",
    )
