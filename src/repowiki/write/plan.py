"""페이지 계획. 사실에서 쓸 페이지와 그 페이지가 볼 사실 조각을 정한다(docs/plans/depth.md D).

경계 계약: 입력은 `RepoFacts`이고 출력은 `PageJob` 목록이다. 순수 계산이라 같은 사실에서
같은 계획이 나온다.

페이지의 단위는 빌드 모듈이 아니라 개념 묶음이다. 모듈이 하나뿐인 저장소는 모듈을 단위로
삼는 한 영원히 한 쪽이고, 사람이 읽고 싶은 단위는 빌드 산출물이 아니라 개념이다.

이 계획 층이 할 일은 한 쪽이 촘촘한 글이 될 만큼의 사실과 근거를 실어 주는 것이다. 근거가
스무 건뿐인 쪽은 스무 문장 넘게 쓸 수 없다. 목표 밀도는 `docs/plans/depth.md`에 적혀 있다.

사각: 이 모듈은 무엇을 쓸지 정할 뿐 무엇이 중요한지 판단하지 않는다. 중요도는 랭킹이 정하고,
랭킹의 정확성은 별도 판정이다(SC-1.4).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

import yaml

from pydantic import BaseModel

from repowiki.analyze import clusters
from repowiki.analyze.domain import DATA_DIR
from repowiki.bundle.links import Citer, citer_for
from repowiki.models import (
    Cluster,
    Diagram,
    Evidence,
    FactTable,
    PageJob,
    PageType,
    RepoFacts,
    Span,
    SymbolKind,
)
from repowiki.write import outline
from repowiki.write import tables as fact_tables

_ROOT_SLUG = "root"
_DEFAULT_BUDGET = {"max_diagrams": 4, "target_words": 700}
_MAX_EVIDENCE = 60
# 한 파일이 한 쪽의 근거에서 차지할 수 있는 최대 자리. 이 상한이 없으면 멤버가 많은 타입
# 하나가 근거 예산을 다 먹고 다른 파일이 밀려난다. 실측(kafka, 2026-09-10): 81쪽 중 73쪽이
# 상한 60에 걸려 있었고, 한 쪽에서 파일 하나가 근거의 27%(중앙), p90 67%, 최대 100%를
# 차지했다. 한 쪽은 근거 60개 중 38개가 한 파일이었다.
#
# 넘치는 것을 버리지 않는다. 뒤로 미룬다 — 다른 파일이 자리를 잡은 뒤 남으면 다시 담는다.
# 그래야 근거가 넓어지면서도 예산을 놀리지 않는다.
_MAX_PER_FILE = 6
_MAX_SYMBOLS = 40
_MAX_MODULE_PAGES = 12
_MAX_CONCEPT_PAGES = 40
_TYPE_LIKE = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ENUM, SymbolKind.RECORD}
_MEMBER_LIKE = {SymbolKind.METHOD, SymbolKind.CONSTRUCTOR, SymbolKind.FUNCTION}


def slug(identifier: str) -> str:
    """모듈이나 묶음 id를 파일 이름으로 바꾼다.

    저장소 루트는 id가 `.`이라 그대로 쓰면 `..md`가 된다. 경로 구분자는 붙임표로 바꾼다.
    """
    if identifier in ("", "."):
        return _ROOT_SLUG
    # URL에 실릴 이름이라 아스키만 남긴다. 한글 제목을 그대로 쓰면 주소가 퍼센트 인코딩으로
    # 뒤덮여 사람이 링크를 읽지 못한다.
    lowered = identifier.strip("./").lower()
    safe = "".join(ch if (ch.isascii() and ch.isalnum()) else "-" for ch in lowered)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or _ROOT_SLUG


def _hash(*parts: object) -> str:
    """페이지 입력의 해시. 정규 직렬화는 PLAN §2.9를 따른다.

    출력에 영향을 주는 것을 전부 덮어야 한다. 사실만 해시하면 도식이나 표의 값이 바뀌어도
    해시가 그대로라, 증분 재생성이 바뀐 페이지를 다시 쓰지 않는다.
    """
    payload = [
        part.model_dump(mode="json") if isinstance(part, BaseModel) else part for part in parts
    ]
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence(items: list[tuple[str, Span, str]]) -> list[Evidence]:
    """근거 목록. id는 자리 번호이고 페이지 본문은 이 id로만 인용한다.

    같은 자리가 두 번 들어오면 하나로 줄인다. 같은 줄을 가리키는 근거가 둘이면 페이지는
    같은 것을 두 이름으로 인용하게 된다.
    """
    unique: list[tuple[Span, str]] = []
    seen: set[tuple[str, int, int]] = set()
    for _, span, note in items:
        key = (span.path, span.start_line, span.end_line)
        if key in seen:
            continue
        seen.add(key)
        unique.append((span, note))

    # 1차: 파일마다 상한까지만 담는다. 2차: 남은 자리를 미뤄 둔 것으로 채운다.
    # 순서는 그대로 둔다 — 계획 층이 준 순서가 중요도이고 여기서 다시 매기지 않는다.
    counted: Counter[str] = Counter()
    first: list[tuple[Span, str]] = []
    deferred: list[tuple[Span, str]] = []
    for span, note in unique:
        if counted[span.path] < _MAX_PER_FILE:
            counted[span.path] += 1
            first.append((span, note))
        else:
            deferred.append((span, note))
    chosen = (first + deferred)[:_MAX_EVIDENCE]
    return [
        Evidence(id=f"E{position + 1}", span=span, note=note)
        for position, (span, note) in enumerate(chosen)
    ]


def _rank_key(facts: RepoFacts) -> dict[str, int]:
    """파일 경로에서 랭킹 순위로. 순위가 없는 파일은 맨 뒤다."""
    return {rank.path: position for position, rank in enumerate(facts.file_ranks)}


def _by_rank(facts: RepoFacts, items: list, path_of) -> list:
    order = _rank_key(facts)
    return sorted(items, key=lambda item: (order.get(path_of(item), len(order)), path_of(item)))


def _diagrams_for(facts: RepoFacts, prefix: str) -> list[Diagram]:
    """접두사로 고르는 도식. 자리 번호나 이름이 뒤에 붙는 종류에 쓴다."""
    return [d for d in facts.diagrams if d.id.startswith(prefix)]


def _diagram(facts: RepoFacts, diagram_id: str) -> list[Diagram]:
    """id가 정확히 같은 도식. 이름이 다른 이름의 앞부분인 경우가 흔하다.

    `COLLAB-Option`을 접두사로 고르면 `COLLAB-OptionGroup`과 `COLLAB-Options`까지 딸려 온다.
    그러면 한 쪽에 같은 그림이 두 번 실린다.
    """
    return [d for d in facts.diagrams if d.id == diagram_id]


def _unique(diagrams: list[Diagram]) -> list[Diagram]:
    """같은 도식을 두 번 싣지 않는다. 순서는 처음 나온 자리를 지킨다."""
    seen: set[str] = set()
    found: list[Diagram] = []
    for diagram in diagrams:
        if diagram.id in seen:
            continue
        seen.add(diagram.id)
        found.append(diagram)
    return found


def load_budgets() -> dict[str, dict]:
    """페이지 종류별 예산. `data/diagram-limits.yml`이 정본이다.

    한 상한을 모든 쪽에 물리지 않는다. 구조 개요는 저장소를 여러 각도에서 보여야 하고,
    버전 표만 있는 쪽에는 그릴 것이 없다.
    """
    raw = yaml.safe_load((DATA_DIR / "diagram-limits.yml").read_text(encoding="utf-8"))
    return raw.get("pages", {})


def _budget(page_type: PageType) -> dict:
    return load_budgets().get(page_type.value, _DEFAULT_BUDGET)


def target_words(page_type: PageType) -> int:
    """이 종류의 쪽이 목표하는 분량. 게이트의 하한이 이 값에서 나온다."""
    return _budget(page_type).get("target_words", _DEFAULT_BUDGET["target_words"])


def _citer(facts: RepoFacts) -> Citer:
    """이 저장소의 인용기. 표의 근거 칸이 소스 링크가 된다."""
    return citer_for(facts.profile.remote_url, facts.profile.head_sha)


def _keep(tables: list[FactTable | None]) -> list[FactTable]:
    return [table for table in tables if table is not None]


def _doc_evidence(facts: RepoFacts, limit: int) -> list[tuple[str, Span, str]]:
    """저장소 문서의 절을 근거로. 도메인 어휘는 코드가 아니라 여기에 적혀 있다."""
    corpus = facts.corpus
    if corpus is None:
        return []
    return [
        (heading.title, heading.span, f"문서 절 {heading.title}")
        for heading in corpus.headings[:limit]
    ]


def _job(
    job_id: str,
    path: str,
    page_type: PageType,
    title: str,
    purpose: str,
    payload: dict,
    evidence: list[tuple[str, Span, str]],
    diagrams: list[Diagram],
    tables: list[FactTable],
    section: str,
    parent: str | None = None,
) -> PageJob:
    allowed = _budget(page_type).get("max_diagrams", _DEFAULT_BUDGET["max_diagrams"])
    chosen = diagrams[:allowed]
    items = _evidence(evidence)
    return PageJob(
        id=job_id,
        path=path,
        type=page_type,
        title=title,
        purpose=purpose,
        facts=payload,
        section=section,
        parent=parent,
        evidence=items,
        diagrams=chosen,
        tables=tables,
        input_hash=_hash(
            payload,
            [item.model_dump(mode="json", exclude={"text"}) for item in items],
            [diagram.model_dump(mode="json") for diagram in chosen],
            [table.model_dump(mode="json") for table in tables],
            {"path": path, "type": page_type.value, "section": section, "parent": parent},
        ),
    )


def _overview_job(facts: RepoFacts) -> PageJob:
    """1. 개요. 저장소가 무엇이고 무엇으로 나뉘는지."""
    payload = {
        "repository": facts.profile.model_dump(),
        "subsystems": [
            {"id": s.id, "modules": s.modules, "source": s.source.value} for s in facts.subsystems
        ],
        "modules": [
            {"id": m.id, "files": m.main_file_count, "languages": m.languages}
            for m in sorted(facts.modules, key=lambda m: -m.main_file_count)[:20]
        ],
        "edges": [
            {"from": e.src, "to": e.dst, "weight": e.weight}
            for e in sorted(facts.module_edges, key=lambda e: -e.weight)[:20]
        ],
        "entry_points": [
            {"kind": e.kind.value, "name": e.name, "module": e.module, "cite": e.span.cite()}
            for e in facts.entry_points[:15]
        ],
        "top_files": [{"path": r.path, "module": r.module} for r in facts.file_ranks[:10]],
        "unresolved": facts.unresolved,
    }
    evidence: list[tuple[str, Span, str]] = _doc_evidence(facts, 12)
    evidence += [
        (e.name, e.span, f"진입점 {e.kind.value} {e.name}") for e in facts.entry_points[:15]
    ]
    for edge in sorted(facts.module_edges, key=lambda e: -e.weight)[:15]:
        for span in edge.evidence[:1]:
            evidence.append((edge.dst, span, f"{edge.src}가 {edge.dst}를 임포트"))
    top_types = _by_rank(
        facts,
        [s for s in facts.symbols if s.kind in _TYPE_LIKE and not s.is_test],
        lambda s: s.span.path,
    )[:15]
    evidence += [(s.name, s.span, f"{s.kind.value} {s.name}") for s in top_types]
    return _job(
        "overview-architecture",
        "overview/architecture.md",
        PageType.ARCHITECTURE_OVERVIEW,
        f"{facts.profile.root_name} 구조 개요",
        "이 저장소가 무엇이고 무엇으로 나뉘며 무엇이 무엇에 기대는지 처음 보는 사람에게 보인다",
        payload,
        evidence,
        _overview_diagrams(facts),
        _keep([fact_tables.module_table(facts), fact_tables.language_table(facts)]),
        "A",
    )


def _overview_diagrams(facts: RepoFacts) -> list[Diagram]:
    """구조 개요가 실을 도식. 전체 그림 하나로는 저장소를 설명하지 못한다.

    묶음 그림 다음에 서브시스템 그림들이 오고, 그다음에 가장 많이 불리는 타입들의 협력
    그림이 온다. 셋은 같은 저장소를 다른 배율로 보는 것이다.
    """
    found = _diagrams_for(facts, "L0") + _diagrams_for(facts, "L1-")
    for name in _busiest_types(facts):
        found += _diagram(facts, f"COLLAB-{name}")
    return _unique(found)


def _busiest_types(facts: RepoFacts) -> list[str]:
    """호출을 가장 많이 받는 타입부터. 저장소의 중심을 호출 수로 본 것이다."""
    counted: dict[str, int] = {}
    for edge in facts.call_edges:
        counted[edge.dst_type] = counted.get(edge.dst_type, 0) + 1
    return [name for name, _ in sorted(counted.items(), key=lambda item: (-item[1], item[0]))]


def _stack_job(facts: RepoFacts) -> PageJob | None:
    """도구 사슬. 언어와 라이브러리의 버전을 표로."""
    chain = facts.toolchain
    if chain is None or (not chain.languages and not chain.dependencies):
        return None
    payload = {
        "languages": [item.model_dump(mode="json") for item in chain.languages],
        "dependencies": [item.model_dump(mode="json") for item in chain.dependencies[:60]],
        "truncated": chain.truncated,
        "kind": facts.profile.kind.value,
    }
    evidence: list[tuple[str, Span, str]] = [
        (item.language, item.span, f"{item.language} {item.version} 선언")
        for item in chain.languages
    ]
    evidence += [
        (item.name, item.span, f"의존 {item.name} {item.version}")
        for item in chain.dependencies[:40]
    ]
    return _job(
        "overview-stack",
        "overview/stack.md",
        PageType.STACK,
        "언어와 라이브러리 버전",
        "이 저장소가 어떤 언어의 어느 판으로 서 있고 무엇에 의존하는지 표로 보인다",
        payload,
        evidence,
        [],
        _keep([fact_tables.language_table(facts), fact_tables.dependency_table(facts)]),
        "A1",
        parent="overview-architecture",
    )


def _concept_jobs(facts: RepoFacts) -> list[PageJob]:
    """차례를 따라 쪽을 만든다. 1단은 자식을 소개하는 문이고 2단이 본문이다.

    묶음은 결정층이 정해 사실에 담아 둔 것을 그대로 쓴다. 여기서 다시 계산하면 그림을 만든
    묶음과 페이지가 된 묶음이 달라질 수 있다.
    """
    tree = outline.build(facts)
    if not tree.nodes:
        return []
    by_id = {group.id: group for group in facts.clusters}
    labels = dict(facts.type_labels)
    paths = {node.key: _outline_path(node) for node in tree.nodes}

    jobs: list[PageJob] = []
    for node in tree.nodes:
        siblings = [
            {"title": other.title, "path": paths[other.key]}
            for other in tree.nodes
            if other.parent == node.parent and other.key != node.key
        ]
        if node.kind == "area":
            jobs.append(_area_job(facts, tree, node, by_id, labels, paths, siblings))
            continue
        group = by_id.get(node.clusters[0]) if node.clusters else None
        if group is None:
            continue
        jobs.append(
            _concept_job(facts, group, labels, siblings, node, paths[node.key])
        )
    return jobs


def _outline_path(node) -> str:
    """차례의 자리 하나가 쓸 파일. 번호가 앞에 붙어 사이드바 순서와 파일 순서가 같다."""
    folder = "areas" if node.kind == "area" else "concepts"
    return f"{folder}/{node.section.replace('.', '-')}-{slug(node.title)}.md"


def _area_job(
    facts: RepoFacts,
    tree,
    node,
    by_id: dict,
    labels: dict[str, str],
    paths: dict[str, str],
    siblings: list[dict],
) -> PageJob:
    """1단 쪽. 이 자리가 무엇으로 나뉘는지 소개하고 아래로 내려가는 문을 연다."""
    children = tree.children_of(node.key)
    groups = [by_id[key] for child in children for key in child.clusters if key in by_id]
    keys = {key for group in groups for key in group.members}
    names = {key.split("#", 1)[1] for key in keys if "#" in key}
    types = [
        symbol
        for symbol in facts.symbols
        if symbol.kind in _TYPE_LIKE
        and not symbol.is_test
        and f"{symbol.span.path}#{symbol.name}" in keys
    ]
    payload = {
        "area": {"title": node.title, "modules": node.modules},
        "children": [
            {
                "title": child.title,
                "path": paths[child.key],
                "types": [
                    labels.get(key, key.split("#")[-1])
                    for key in (by_id[child.clusters[0]].members if child.clusters else [])
                ][:8],
            }
            for child in children
        ],
        "calls_between": _call_summary(
            [
                edge
                for edge in facts.call_edges
                if edge.src_type in names and edge.dst_type in names
            ]
        ),
    }
    evidence = [
        (symbol.name, symbol.span, f"{symbol.kind.value} {symbol.name}")
        for symbol in _by_rank(facts, types, lambda s: s.span.path)[:_MAX_EVIDENCE]
    ]
    job = _job(
        f"area-{slug(node.title)}",
        paths[node.key],
        PageType.AREA,
        node.title,
        "이 자리가 무엇으로 나뉘는지 보이고 아래 쪽마다 무엇을 다루는지 한 줄로 소개한다",
        payload,
        evidence,
        _diagram(facts, f"AREA-{node.title}"),
        _keep([fact_tables.type_inventory(node.title, labels, types, _citer(facts))]),
        node.section,
    )
    job.siblings = siblings
    return job


def concept_slugs(groups: list[Cluster]) -> dict[str, str]:
    """묶음마다 파일 이름. 겹치는 제목만 디렉토리로 한정한다.

    두 디렉토리가 같은 제목의 묶음을 낼 수 있고(`a/util`과 `b/util`), 그때 두 쪽이 같은
    파일을 덮어쓴다. 겹치지 않는 제목까지 한정하면 주소가 길어지기만 한다.
    """
    counted: dict[str, int] = {}
    for group in groups:
        base = slug(group.title)
        counted[base] = counted.get(base, 0) + 1
    found: dict[str, str] = {}
    for group in groups:
        base = slug(group.title)
        if counted[base] == 1:
            found[group.id] = base
            continue
        tail = slug(group.directory).rsplit("-", 1)[-1]
        found[group.id] = f"{tail}-{base}" if tail and tail != _ROOT_SLUG else base
    return found


def _concept_job(
    facts: RepoFacts,
    group: Cluster,
    labels: dict[str, str],
    siblings: list[dict],
    node,
    path: str,
) -> PageJob:
    """묶음 한 쪽. 담은 타입과 그 멤버와 안팎의 호출이 이 쪽의 사실이다."""
    keys = set(group.members)
    types = [
        s
        for s in facts.symbols
        if s.kind in _TYPE_LIKE and not s.is_test and f"{s.span.path}#{s.name}" in keys
    ]
    # 구성원 판정은 선언 정체성으로 한다. 이름만 보면 다른 패키지의 같은 이름 타입이 이 쪽에
    # 섞이고, 파일만 보면 한 파일의 다른 묶음 타입이 섞인다.
    owners = {(s.name, s.span.path) for s in types}
    members = [
        s
        for s in facts.symbols
        if s.kind in _MEMBER_LIKE
        and not s.is_test
        and (s.parent or "", s.span.path) in owners
    ]
    inside = [
        e
        for e in facts.type_edges
        if (e.src, e.src_path or "") in owners and (e.dst, e.dst_path or "") in owners
    ]
    outgoing = [
        e
        for e in facts.call_edges
        if (e.src_type, e.src_path) in owners and (e.dst_type, e.dst_path) not in owners
    ]
    incoming = [
        e
        for e in facts.call_edges
        if (e.dst_type, e.dst_path) in owners and (e.src_type, e.src_path) not in owners
    ]

    payload = {
        "cluster": {"title": group.title, "directory": group.directory, "source": group.source},
        "types": [
            {
                "name": labels.get(f"{s.span.path}#{s.name}", s.name),
                "kind": s.kind.value,
                "cite": s.span.cite(),
            }
            for s in sorted(types, key=lambda s: (s.span.path, s.name))
        ],
        "members": [
            {"type": s.parent, "name": s.name, "kind": s.kind.value, "cite": s.span.cite()}
            for s in _by_rank(facts, members, lambda s: s.span.path)[:_MAX_SYMBOLS]
        ],
        "relations": [
            {"from": e.src, "to": e.dst, "kind": e.kind.value, "cite": e.span.cite()}
            for e in inside[:_MAX_SYMBOLS]
        ],
        "calls_out": _call_summary(outgoing),
        "calls_in": _call_summary(incoming),
    }
    evidence: list[tuple[str, Span, str]] = [
        (s.name, s.span, f"{s.kind.value} {s.name}")
        for s in _by_rank(facts, types, lambda s: s.span.path)
    ]
    evidence += [
        (s.name, s.span, f"{s.parent}.{s.name}")
        for s in _by_rank(facts, members, lambda s: s.span.path)[:_MAX_SYMBOLS]
    ]
    evidence += [
        (e.dst, e.span, f"{e.src}가 {e.dst}를 {e.kind.value}") for e in inside[:15]
    ]
    evidence += [
        (e.dst_type, e.span, f"{e.src_type}.{e.src_member}가 {e.dst_type}.{e.dst_member}를 부른다")
        for e in outgoing[:15]
    ]
    # 이 묶음을 바깥에서 부르는 자리. `calls_in`으로 수는 이미 세면서 근거로는 안 넘기고
    # 있었다. 그래서 근거가 묶음 안쪽 파일에만 갇혔다. 실측(kafka, 2026-09-10): 묶음
    # 449개 중 375개에 바깥 호출자가 있고 그 파일 수가 중앙 5개다.
    #
    # 부르는 쪽을 읽어야 이 묶음의 경계면 계약이 실제로 어떻게 쓰이는지 쓸 수 있다.
    # 안쪽만 읽으면 "이 타입은 이런 메서드를 가진다"에서 닫힌다.
    evidence += [
        (e.src_type, e.span, f"{e.src_type}.{e.src_member}가 이 묶음의 {e.dst_type}를 부른다")
        for e in incoming[:15]
    ]

    ranked = _by_rank(facts, types, lambda s: s.span.path)
    # 대표 타입은 결정층과 같은 규칙으로 고른다. 다르면 그림을 못 찾는다.
    lead_name = clusters.lead_of(group, labels)
    diagrams = _diagram(facts, f"TYPE-{lead_name}") + _diagram(facts, f"COLLAB-{lead_name}")
    for symbol in ranked[:3]:
        diagrams += _diagrams_for(facts, f"SEQ-{symbol.name}.")
    diagrams = _unique(diagrams)
    job = _job(
        f"concept-{slug(node.title)}-{node.section.replace('.', '-')}",
        path,
        PageType.CONCEPT,
        node.title,
        "이 묶음이 무엇을 맡고 그 안의 타입들이 서로 어떻게 일하는지 근거와 함께 보인다",
        payload,
        evidence,
        diagrams,
        _keep(
            [
                fact_tables.type_inventory(group.title, labels, types, _citer(facts)),
                _member_table_for(facts, labels, types, members),
                fact_tables.callers_table(lead_name, facts),
            ]
        ),
        node.section,
        parent=f"area-{slug(node.title)}" if node.parent else "overview-architecture",
    )
    # 형제 쪽 목록을 함께 준다. 교차 링크가 있어야 위키가 목록이 아니라 그물이 된다.
    job.siblings = [item for item in siblings if item["path"] != job.path]
    return job


def _member_table_for(facts: RepoFacts, labels: dict[str, str], types: list, members: list):
    """멤버 표. 묶음에서 멤버가 가장 많은 타입에 대해 만든다."""
    name, path = _richest(types, members)
    if not name:
        return None
    return fact_tables.member_table(
        name, path, facts.symbols, labels.get(f"{path}#{name}", name), _citer(facts)
    )


def _richest(types: list, members: list) -> tuple[str, str]:
    """멤버가 가장 많은 타입의 (이름, 선언 파일).

    대표 타입이 멤버 하나짜리 인터페이스인 묶음이 있다. 그 표는 한 줄이라 읽는 사람에게
    아무것도 말하지 않는다. 이름과 파일을 함께 내는 이유는 같은 이름의 타입이 여럿이기
    때문이다.
    """
    declared = {(symbol.name, symbol.span.path) for symbol in types}
    counted: dict[tuple[str, str], int] = {}
    for member in members:
        key = (member.parent or "", member.span.path)
        if key in declared:
            counted[key] = counted.get(key, 0) + 1
    if not counted:
        return ("", "")
    return max(counted.items(), key=lambda item: (item[1], item[0]))[0]


def _call_summary(edges: list) -> list[dict]:
    """호출을 짝 단위로 줄인다. 낱개로 실으면 브리핑이 호출 목록이 된다."""
    counted: dict[tuple[str, str], dict] = {}
    for edge in edges:
        key = (edge.src_type, edge.dst_type)
        entry = counted.setdefault(
            key, {"from": edge.src_type, "to": edge.dst_type, "count": 0, "cite": edge.span.cite()}
        )
        entry["count"] += 1
    return sorted(counted.values(), key=lambda item: -item["count"])[:20]


def _flow_job(facts: RepoFacts) -> PageJob | None:
    """교차 모듈 흐름. 진입점에서 시작해 경계를 넘는 경로."""
    if not facts.flows:
        return None
    payload = {
        "flows": [
            {
                "id": flow.id,
                "entry": {
                    "kind": flow.entry.kind.value,
                    "name": flow.entry.name,
                    "cite": flow.entry.span.cite(),
                },
                "modules": flow.modules,
                "hops": [
                    {
                        "from": hop.src_module,
                        "to": hop.dst_module,
                        "symbol": hop.symbol,
                        "kind": hop.kind.value,
                        "cite": hop.span.cite(),
                    }
                    for hop in flow.hops
                ],
            }
            for flow in facts.flows
        ]
    }
    evidence: list[tuple[str, Span, str]] = []
    for flow in facts.flows:
        evidence.append((flow.entry.name, flow.entry.span, f"진입점 {flow.entry.name}"))
        evidence += [(h.symbol, h.span, f"{h.src_module}에서 {h.dst_module}로") for h in flow.hops]
    return _job(
        "overview-flows",
        "overview/flows.md",
        PageType.FLOWS,
        "교차 모듈 흐름",
        "진입점에서 시작해 모듈 경계를 넘는 경로를 홉마다 근거와 함께 보인다",
        payload,
        evidence,
        _diagrams_for(facts, "FLOW-"),
        [],
        "A2",
        parent="overview-architecture",
    )


def _module_jobs(facts: RepoFacts) -> list[PageJob]:
    """모듈이 여럿인 저장소만 모듈 쪽을 만든다.

    모듈이 하나면 그 쪽은 개요와 같은 말을 한다. 같은 말을 두 쪽에 쓰는 것은 위키를 늘리는
    것이 아니라 읽는 사람의 시간을 쓰는 것이다.

    개념 나무가 섰으면 이 쪽을 만들지 않는다. 나무의 1단이 이미 같은 자리를 다루고, 둘을
    함께 두면 사이드바에 같은 번호가 두 번 나온다.
    """
    if len(facts.modules) < 2 or outline.build(facts).nodes:
        return []
    ranked = sorted(facts.modules, key=lambda m: -m.main_file_count)[:_MAX_MODULE_PAGES]
    jobs: list[PageJob] = []
    for position, module in enumerate(ranked, start=1):
        in_module = [s for s in facts.symbols if s.module == module.id and not s.is_test]
        symbols = _by_rank(facts, in_module, lambda s: s.span.path)[:_MAX_SYMBOLS]
        outbound = [e for e in facts.module_edges if e.src == module.id]
        inbound = [e for e in facts.module_edges if e.dst == module.id]
        types = _by_rank(
            facts,
            [e for e in facts.type_edges if e.src_module == module.id],
            lambda e: e.span.path,
        )[:_MAX_SYMBOLS]
        entries = [e for e in facts.entry_points if e.module == module.id]
        payload = {
            "module": module.model_dump(),
            "depends_on": [{"module": e.dst, "weight": e.weight} for e in outbound],
            "depended_on_by": [{"module": e.src, "weight": e.weight} for e in inbound],
            "symbols": [
                {"kind": s.kind.value, "name": s.name, "cite": s.span.cite()} for s in symbols
            ],
            "type_relations": [
                {"from": e.src, "to": e.dst, "kind": e.kind.value, "cite": e.span.cite()}
                for e in types
            ],
            "entry_points": [
                {"kind": e.kind.value, "name": e.name, "cite": e.span.cite()} for e in entries
            ],
        }
        evidence: list[tuple[str, Span, str]] = [
            (s.name, s.span, f"{s.kind.value} {s.name}") for s in symbols
        ]
        evidence += [(e.dst, e.span, f"{e.src}가 {e.dst}를 {e.kind.value}") for e in types]
        evidence += [(e.name, e.span, f"진입점 {e.kind.value} {e.name}") for e in entries]
        for edge in outbound:
            for span in edge.evidence[:2]:
                evidence.append((edge.dst, span, f"{edge.src}가 {edge.dst}를 임포트"))
        jobs.append(
            _job(
                f"module-{slug(module.id)}",
                f"modules/{slug(module.id)}.md",
                PageType.MODULE,
                f"모듈 {module.id}",
                "이 모듈의 책임과 경계면 계약과 실패 모드를 근거와 함께 보인다",
                payload,
                evidence,
                _diagram(facts, f"L2-{module.id}"),
                _keep([fact_tables.dependency_table(facts, module.id)]),
                f"3.{position}",
            )
        )
    return jobs


def _subsystem_jobs(facts: RepoFacts) -> list[PageJob]:
    """서브시스템 쪽. 모듈이 여럿이고 개념 나무가 없을 때만 뜻이 있다."""
    if len(facts.modules) < 2 or outline.build(facts).nodes:
        return []
    jobs: list[PageJob] = []
    for position, subsystem in enumerate(facts.subsystems, start=1):
        member_ids = set(subsystem.modules)
        members = [m for m in facts.modules if m.id in member_ids]
        internal = [
            e for e in facts.module_edges if e.src in member_ids and e.dst in member_ids
        ]
        payload = {
            "subsystem": subsystem.id,
            "modules": [
                {"id": m.id, "files": m.main_file_count, "languages": m.languages}
                for m in sorted(members, key=lambda m: -m.main_file_count)
            ],
            "internal_edges": [
                {"from": e.src, "to": e.dst, "weight": e.weight} for e in internal
            ],
        }
        evidence = [
            (e.dst, span, f"{e.src}가 {e.dst}를 임포트")
            for e in internal
            for span in e.evidence[:2]
        ]
        if not evidence:
            for member in sorted(members, key=lambda m: -m.main_file_count)[:3]:
                ranked = _by_rank(
                    facts,
                    [s for s in facts.symbols if s.module == member.id and s.kind in _TYPE_LIKE],
                    lambda s: s.span.path,
                )
                evidence += [
                    (symbol.name, symbol.span, f"{symbol.kind.value} {symbol.name}")
                    for symbol in ranked
                ][:6]
        jobs.append(
            _job(
                f"subsystem-{slug(subsystem.id)}",
                f"subsystems/{slug(subsystem.id)}.md",
                PageType.SUBSYSTEM,
                f"서브시스템 {subsystem.id}",
                "이 묶음이 무엇을 맡고 안에서 어떻게 나뉘는지 보인다",
                payload,
                evidence,
                _diagram(facts, f"L1-{subsystem.id}"),
                [],
                f"3.{position}",
            )
        )
    return jobs


def _history_job(facts: RepoFacts) -> PageJob | None:
    """이력. 최근 자주 바뀐 자리와 함께 바뀌는 짝."""
    history = facts.history
    if history is None:
        return None
    payload = {
        "window_months": history.window_months,
        "commit_count": history.commit_count,
        "hotspots": history.hotspots,
        "couplings": history.couplings,
        "issue_keys": history.issue_keys,
    }
    # 이력 사실에는 줄 범위가 없다. 핫스팟 파일의 대표 선언을 그 파일의 자리로 삼는다 —
    # "이 파일이 자주 바뀐다"는 주장의 근거는 그 파일 자체다.
    hot_paths = [str(item.get("path", "")) for item in history.hotspots[:20]]
    by_path: dict[str, Span] = {}
    for symbol in facts.symbols:
        if symbol.kind in _TYPE_LIKE and symbol.span.path in hot_paths:
            by_path.setdefault(symbol.span.path, symbol.span)
    # 자리를 선언의 머리로 좁힌다. 이력 쪽이 그 파일에서 필요한 것은 "무엇이 여기 사는가"
    # 이지 그 타입의 본문 전부가 아니다. 좁히지 않으면 3만 줄짜리 시험 클래스가 근거 자리
    # 하나가 되고, 원문은 어차피 앞쪽만 잘려 실린다. 그 잘린 앞쪽은 필드 선언이라 이력이
    # 말하려는 것과 상관이 없다(2026-09-10 실측: 가장 많이 잘린 자리 셋이 전부 시험
    # 파일이었고 각각 3만, 1만 5천, 1만 4천 줄이 잘렸다).
    evidence = [
        (
            path,
            Span(
                path=path,
                start_line=by_path[path].start_line,
                end_line=min(
                    by_path[path].end_line, by_path[path].start_line + _HOTSPOT_LINES
                ),
            ),
            f"자주 바뀌는 파일 {path}",
        )
        for path in hot_paths
        if path in by_path
    ]
    return _job(
        "history-hotspots",
        "history/hotspots.md",
        PageType.HISTORY,
        "변경 핫스팟",
        "최근 자주 바뀐 자리와 함께 바뀌는 짝을 보인다",
        payload,
        evidence,
        _diagrams_for(facts, "TIME-"),
        [],
        "B1",
    )


def _quality_job(facts: RepoFacts) -> PageJob | None:
    """빌드와 CI와 코드 품질. 코퍼스 층이 없으면 만들 수 없는 쪽이다."""
    corpus = facts.corpus
    if corpus is None:
        return None
    ci_roles = [item for item in corpus.roles if item.role in ("ci", "build")]
    ci_keys = _spread(
        [item for item in corpus.config_keys if _is_pipeline(item.path)], lambda item: item.path
    )
    if not ci_roles:
        return None
    payload = {
        "pipeline_files": [item.path for item in ci_roles][:40],
        "config_keys": [item.model_dump(mode="json") for item in ci_keys[:40]],
        "toolchain": [
            item.model_dump(mode="json")
            for item in (facts.toolchain.languages if facts.toolchain else [])
        ],
    }
    evidence = [(item.key, item.span, f"설정 {item.key}") for item in ci_keys[:30]]
    return _job(
        "quality-pipeline",
        "quality/pipeline.md",
        PageType.QUALITY,
        "빌드와 검사 파이프라인",
        "이 저장소가 무엇으로 빌드되고 어떤 검사를 통과해야 병합되는지 보인다",
        payload,
        evidence,
        [],
        _keep([fact_tables.language_table(facts), fact_tables.config_table(facts)]),
        "B2",
    )


def _spread(items: list, key_of, per_file: int = 8) -> list:
    """파일마다 고르게 뽑는다. 앞에서부터 자르면 이름이 뒤인 파일이 통째로 빠진다.

    설정 키를 경로 순으로 잘라 담으면 알파벳이 뒤인 파일의 키가 하나도 실리지 않는다.
    그 파일이 가장 중요한 파일일 수 있다(`workflows/maven.yml`이 그렇다).
    """
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(key_of(item), []).append(item)
    found: list = []
    for name in sorted(grouped):
        found += grouped[name][:per_file]
    return found


def _is_pipeline(path: str) -> bool:
    return any(
        marker in f"/{path}"
        for marker in ("/.github/", "/.gitlab-ci", "/Jenkinsfile", "/.circleci/", "/checkstyle")
    )


def _usage_job(facts: RepoFacts) -> PageJob | None:
    """사용 예. 테스트가 이 저장소를 어떻게 쓰는지 보이는 쪽이다.

    테스트는 저자가 쓴 실행 가능한 사용 설명서다. 산문은 낡아도 통과하는 테스트는 낡지
    않으므로, "이것을 어떻게 쓰는가"의 가장 믿을 만한 근거다.
    """
    tests = [s for s in facts.symbols if s.is_test and s.kind in _MEMBER_LIKE]
    if len(tests) < 5:
        return None
    ranked = _by_rank(facts, tests, lambda s: s.span.path)[:_MAX_SYMBOLS]
    payload = {
        "test_members": [
            {"type": s.parent, "name": s.name, "cite": s.span.cite()} for s in ranked
        ],
        "test_files": sorted({s.span.path for s in ranked})[:20],
    }
    evidence = [(s.name, s.span, f"테스트 {s.parent}.{s.name}") for s in ranked]
    return _job(
        "usage-examples",
        "usage/examples.md",
        PageType.USAGE,
        "사용 예",
        "테스트가 이 저장소를 어떻게 쓰는지 실제 자리와 함께 보인다",
        payload,
        evidence,
        [],
        _keep([fact_tables.test_inventory(facts.symbols, _citer(facts))]),
        "B3",
    )


def _data_job(facts: RepoFacts) -> PageJob | None:
    """데이터 모델. 엔티티가 있을 때만."""
    model = facts.entities
    if model is None or not model.entities:
        return None
    payload = {"entities": model.entities[:40], "relations": model.relations[:60]}
    evidence = [
        (
            str(item.get("table", "")),
            Span.model_validate(item["span"]),
            f"엔티티 {item.get('table', '')}",
        )
        for item in model.entities[:30]
        if isinstance(item.get("span"), dict)
    ]
    return _job(
        "data-model",
        "data/model.md",
        PageType.DATA_MODEL,
        "데이터 모델",
        "저장소가 선언한 테이블과 그 사이의 외래 키를 보인다",
        payload,
        evidence,
        _diagrams_for(facts, "ER-"),
        [],
        "B4",
    )


# 핫스팟 근거 한 자리가 들 줄 수. 선언의 머리가 그 파일이 무엇인지 말한다.
_HOTSPOT_LINES = 40

_GLOSSARY_AREAS = 12
_GLOSSARY_TERMS_PER_AREA = 6


def _glossary_job(facts: RepoFacts) -> PageJob | None:
    """낱말 사전. 이 저장소에서 쓰는 말이 어느 코드 실체인지 잇는 쪽이다.

    처음 온 사람이 회의에서 듣는 말과 코드에서 보는 이름이 다르면 둘을 잇는 자리가 없다.
    이름 있는 대형 저장소는 대체로 이 쪽을 둔다. 다만 보편은 아니다 — 2026-09-10에
    사이트맵 조각에서 고르게 뽑은 저장소 37곳에서는 마지막 쪽이 Glossary 인 것이 3곳뿐이고,
    내가 골랐던 대형 16곳에서는 12곳이었다. 앞선 커밋 메시지가 "예외가 없다"고 적은 것은
    표본 편향이었다.

    결정층이 낼 수 있는 것은 후보와 그 선언 자리까지다. 무엇이 이 저장소의 낱말이고 그것이
    무슨 뜻인지는 원문을 읽어야 나오므로 쓰는 층의 몫이다.

    묶음은 큰 것부터 고른다. 사실에 담긴 순서는 디렉토리 사전순이라 그대로 앞에서 자르면
    구성원 하나짜리 묶음과 빌드 도구 디렉토리가 낱말이 된다(kafka 실측 2026-09-10:
    `api-checker` 1개, `gradle` 6개, `scripts` 14개가 들어갔다). 큰 묶음이 그 저장소가
    실제로 이야기하는 것이다.
    """
    groups = sorted(facts.clusters, key=lambda c: (-len(c.members), c.title))[:_GLOSSARY_AREAS]
    if not groups:
        return None
    labels = {node.key: node.label for node in clusters.type_nodes(facts.symbols, facts.file_ranks)}
    declarations = {f"{s.span.path}#{s.name}": s.span for s in facts.symbols if not s.parent}
    evidence: list[tuple[str, Span, str]] = []
    terms: list[dict] = []
    for group in groups:
        picked: list[str] = []
        for key in group.members[:_GLOSSARY_TERMS_PER_AREA]:
            name = labels.get(key, "")
            span = declarations.get(key)
            if not name or span is None:
                continue
            picked.append(name)
            evidence.append((name, span, f"{group.title}의 {name} 선언"))
        if picked:
            terms.append({"area": group.title, "candidates": picked})
    if not evidence:
        return None
    return _job(
        "glossary",
        "glossary.md",
        PageType.GLOSSARY,
        "낱말 사전",
        "이 저장소에서 쓰는 말이 어느 코드 실체를 가리키는지 선언 자리와 함께 잇는다",
        {"terms": terms},
        evidence,
        [],
        [],
        "Z1",
        parent="overview-architecture",
    )


def build_jobs(facts: RepoFacts) -> list[PageJob]:
    """쓸 페이지를 정하고 각 페이지의 작업을 만든다.

    순서가 곧 사이드바의 순서다. 개요가 먼저이고 개념이 본문이며 나머지가 뒤따른다.
    """
    # 개요와 부록은 글자 번호를, 개념 나무는 숫자 번호를 쓴다. 한 벌을 나눠 쓰면 사이드바에
    # 같은 번호가 두 번 나온다.
    jobs: list[PageJob] = [_overview_job(facts)]
    optional = [
        _stack_job(facts),
        _flow_job(facts),
        *_concept_jobs(facts),
        *_subsystem_jobs(facts),
        *_module_jobs(facts),
        _data_job(facts),
        _history_job(facts),
        _quality_job(facts),
        _usage_job(facts),
        # 낱말 사전은 언제나 마지막이다. 조사한 DeepWiki 저장소 10곳이 모두 그렇다.
        _glossary_job(facts),
    ]
    jobs += [job for job in optional if job is not None]
    return jobs
