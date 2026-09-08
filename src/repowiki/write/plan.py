"""페이지 계획. 사실에서 쓸 페이지와 그 페이지가 볼 사실 조각을 정한다(PLAN §2.9).

경계 계약: 입력은 `RepoFacts`이고 출력은 `PageJob` 목록이다. 순수 계산이라 같은 사실에서
같은 계획이 나온다. LLM은 여기서 정한 조각 밖을 보지 못한다 — 그것이 근거 강제의 절반이다.

슬라이스 경계는 PLAN §2.9를 따른다. module 페이지는 모듈 하나, subsystem 페이지는 그
서브시스템의 모듈 전부, overview와 flows는 저장소 전체다.

사각: 이 모듈은 무엇을 쓸지 정할 뿐 무엇이 중요한지 판단하지 않는다. 중요도는 랭킹이
정하고, 랭킹의 정확성은 별도 판정이다(SC-1.4).
"""

from __future__ import annotations

import hashlib
import json

from repowiki.models import (
    Diagram,
    Evidence,
    PageJob,
    PageType,
    RepoFacts,
    Span,
)

_MAX_MODULE_PAGES = 12
_ROOT_SLUG = "root"


def slug(identifier: str) -> str:
    """모듈이나 서브시스템 id를 파일 이름으로 바꾼다.

    저장소 루트는 id가 `.`이라 그대로 쓰면 `..md`가 된다. 경로 구분자는 붙임표로 바꾼다.
    """
    if identifier in ("", "."):
        return _ROOT_SLUG
    return identifier.strip("./").replace("/", "-") or _ROOT_SLUG


_MAX_EVIDENCE = 40
_MAX_SYMBOLS = 25


def _hash(payload: dict) -> str:
    """페이지 입력의 해시. 정규 직렬화는 PLAN §2.9를 따른다."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence(items: list[tuple[str, Span, str]]) -> list[Evidence]:
    """근거 목록. id는 자리 번호이고 페이지 본문은 이 id로만 인용한다."""
    return [
        Evidence(id=f"E{position}", span=span, note=note)
        for position, (_, span, note) in enumerate(items[:_MAX_EVIDENCE], start=1)
    ]


def _module_facts(facts: RepoFacts, module_id: str) -> tuple[dict, list[tuple[str, Span, str]]]:
    """모듈 하나의 슬라이스. 그 모듈에 닿는 것만 담는다."""
    module = next((m for m in facts.modules if m.id == module_id), None)
    symbols = [s for s in facts.symbols if s.module == module_id][:_MAX_SYMBOLS]
    inbound = [e for e in facts.module_edges if e.dst == module_id]
    outbound = [e for e in facts.module_edges if e.src == module_id]
    types = [e for e in facts.type_edges if e.src_module == module_id][:_MAX_EVIDENCE]
    entries = [e for e in facts.entry_points if e.module == module_id]
    hotspots = []
    if facts.history is not None:
        hotspots = [h for h in facts.history.hotspots if h.get("module") == module_id]

    payload = {
        "module": module.model_dump() if module is not None else {"id": module_id},
        "depends_on": [{"module": e.dst, "weight": e.weight} for e in outbound],
        "depended_on_by": [{"module": e.src, "weight": e.weight} for e in inbound],
        "symbols": [
            {"kind": s.kind.value, "name": s.name, "cite": s.span.cite()} for s in symbols
        ],
        "type_relations": [
            {"from": e.src, "to": e.dst, "kind": e.kind.value, "cite": e.span.cite()}
            for e in types[:_MAX_SYMBOLS]
        ],
        "entry_points": [
            {"kind": e.kind.value, "name": e.name, "cite": e.span.cite()} for e in entries
        ],
        "hotspots": hotspots[:5],
    }
    evidence: list[tuple[str, Span, str]] = []
    evidence += [(s.name, s.span, f"{s.kind.value} {s.name}") for s in symbols]
    evidence += [(e.dst, e.span, f"{e.src}가 {e.dst}를 {e.kind.value}") for e in types]
    evidence += [(e.name, e.span, f"진입점 {e.kind.value} {e.name}") for e in entries]
    for edge in outbound:
        for span in edge.evidence:
            evidence.append((edge.dst, span, f"{edge.src}가 {edge.dst}를 임포트"))
    return payload, evidence


def _overview_facts(facts: RepoFacts) -> tuple[dict, list[tuple[str, Span, str]]]:
    """저장소 전체의 슬라이스. 모듈 목록과 서브시스템과 진입점이 뼈대다."""
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
        "top_files": [
            {"path": r.path, "module": r.module} for r in facts.file_ranks[:10]
        ],
        "unresolved": facts.unresolved,
    }
    evidence: list[tuple[str, Span, str]] = [
        (e.name, e.span, f"진입점 {e.kind.value} {e.name}") for e in facts.entry_points[:15]
    ]
    for edge in sorted(facts.module_edges, key=lambda e: -e.weight)[:15]:
        for span in edge.evidence[:1]:
            evidence.append((edge.dst, span, f"{edge.src}가 {edge.dst}를 임포트"))
    return payload, evidence


def _flow_facts(facts: RepoFacts) -> tuple[dict, list[tuple[str, Span, str]]]:
    """흐름 페이지의 슬라이스. 홉마다 근거가 있다."""
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
    return payload, evidence


def _history_facts(facts: RepoFacts) -> tuple[dict, list[tuple[str, Span, str]]]:
    """이력 페이지의 슬라이스. 인용 span이 없는 유일한 페이지다."""
    history = facts.history
    payload = {
        "window_months": history.window_months if history else 0,
        "commit_count": history.commit_count if history else 0,
        "hotspots": history.hotspots if history else [],
        "couplings": history.couplings if history else [],
        "issue_keys": history.issue_keys if history else {},
    }
    return payload, []


def _diagrams_for(facts: RepoFacts, prefix: str) -> list[Diagram]:
    return [d for d in facts.diagrams if d.id.startswith(prefix)]


def build_jobs(facts: RepoFacts) -> list[PageJob]:
    """쓸 페이지를 정하고 각 페이지의 작업을 만든다."""
    jobs: list[PageJob] = []

    payload, evidence = _overview_facts(facts)
    jobs.append(
        PageJob(
            id="overview-architecture",
            path="overview/architecture.md",
            type=PageType.ARCHITECTURE_OVERVIEW,
            title=f"{facts.profile.root_name} 구조 개요",
            purpose="이 저장소가 무엇으로 나뉘고 무엇이 무엇에 기대는지 처음 보는 사람에게 보인다",
            facts=payload,
            evidence=_evidence(evidence),
            diagrams=_diagrams_for(facts, "L0"),
            input_hash=_hash(payload),
        )
    )

    if facts.flows:
        payload, evidence = _flow_facts(facts)
        jobs.append(
            PageJob(
                id="overview-flows",
                path="overview/flows.md",
                type=PageType.FLOWS,
                title="교차 모듈 흐름",
                purpose="진입점에서 시작해 모듈 경계를 넘는 경로를 홉마다 근거와 함께 보인다",
                facts=payload,
                evidence=_evidence(evidence),
                diagrams=_diagrams_for(facts, "FLOW-"),
                input_hash=_hash(payload),
            )
        )

    for subsystem in facts.subsystems:
        members = [m for m in facts.modules if m.id in set(subsystem.modules)]
        member_ids = set(subsystem.modules)
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
        subsystem_evidence = [
            (e.dst, span, f"{e.src}가 {e.dst}를 임포트")
            for e in internal
            for span in e.evidence[:1]
        ]
        if not subsystem_evidence:
            # 모듈이 하나뿐인 묶음은 안쪽 엣지가 없다. 그 모듈의 선언을 근거로 쓴다.
            for member in sorted(members, key=lambda m: -m.main_file_count)[:2]:
                subsystem_evidence += [
                    (symbol.name, symbol.span, f"{symbol.kind.value} {symbol.name}")
                    for symbol in facts.symbols
                    if symbol.module == member.id
                ][:5]
        jobs.append(
            PageJob(
                id=f"subsystem-{slug(subsystem.id)}",
                path=f"subsystems/{slug(subsystem.id)}.md",
                type=PageType.SUBSYSTEM,
                title=f"서브시스템 {subsystem.id}",
                purpose="이 묶음이 무엇을 맡고 안에서 어떻게 나뉘는지 보인다",
                facts=payload,
                evidence=_evidence(subsystem_evidence),
                diagrams=_diagrams_for(facts, f"L1-{subsystem.id}"),
                input_hash=_hash(payload),
            )
        )

    ranked = sorted(facts.modules, key=lambda m: -m.main_file_count)[:_MAX_MODULE_PAGES]
    for module in ranked:
        payload, evidence = _module_facts(facts, module.id)
        jobs.append(
            PageJob(
                id=f"module-{slug(module.id)}",
                path=f"modules/{slug(module.id)}.md",
                type=PageType.MODULE,
                title=f"모듈 {module.id}",
                purpose="이 모듈의 책임과 경계면 계약과 실패 모드를 근거와 함께 보인다",
                facts=payload,
                evidence=_evidence(evidence),
                diagrams=_diagrams_for(facts, f"L2-{module.id}"),
                input_hash=_hash(payload),
            )
        )

    if facts.history is not None:
        payload, _ = _history_facts(facts)
        jobs.append(
            PageJob(
                id="history-hotspots",
                path="history/hotspots.md",
                type=PageType.HISTORY,
                title="변경 핫스팟",
                purpose="최근 자주 바뀐 자리와 함께 바뀌는 짝을 보인다",
                facts=payload,
                evidence=[],
                diagrams=_diagrams_for(facts, "TIME-"),
                input_hash=_hash(payload),
            )
        )
    return jobs
