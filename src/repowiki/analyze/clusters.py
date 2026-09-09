"""개념 묶음. 페이지의 단위를 빌드 모듈이 아니라 타입의 묶음으로 정한다(docs/plans/depth.md D).

경계 계약: 입력은 타입 선언과 관계 엣지이고 출력은 이름 붙은 묶음이다. 순수 계산이라 같은
사실에서 같은 묶음이 나온다.

왜 빌드 모듈이 아닌가. 모듈이 하나뿐인 저장소가 흔하고, 그런 저장소는 모듈을 페이지 단위로
삼는 한 영원히 한 쪽이다. 사람이 읽고 싶은 단위는 빌드 산출물이 아니라 개념이다.

묶는 순서는 셋이다. 먼저 디렉토리로 가른다 — 자바는 디렉토리가 곧 패키지이고, 파이썬과
스칼라도 사람이 디렉토리로 나누어 둔다. 그다음 너무 작은 묶음을 부모 디렉토리로 올려
합친다. 마지막으로 너무 큰 묶음만 관계 그래프의 커뮤니티로 쪼갠다.

디렉토리를 먼저 보는 이유는 그것이 저자가 손으로 적어 둔 분류이기 때문이다. 커뮤니티
검출은 저자가 나누지 않은 자리에만 쓴다.

**올려 합치는 단계가 없으면 큰 저장소가 무너진다.** 디렉토리마다 한 묶음이면 airflow 는
묶음 831개가 나오고 그중 51퍼센트가 타입 두 개 이하다(2026-09-09 실측). 타입 두 개짜리
쪽은 목록이지 글이 아니고, 831쪽짜리 위키는 훑을 수 없다.

사각: 이름은 코드에서만 짓는다. "Type Handling System" 같은 개념 이름은 코드에 없으므로
짓지 못하고, 그 자리에는 대표 타입의 이름이 들어간다. 개념 이름은 쓰는 층이 제목으로
제안하고 사람이 판정할 자리다.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities
from pydantic import BaseModel

from repowiki.models import (
    CallEdge,
    Cluster,
    FileRank,
    Symbol,
    SymbolKind,
    TypeEdge,
    TypeEdgeKind,
)

_TYPE_KINDS = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ENUM, SymbolKind.RECORD}
# 관계의 무게. 상속은 "같은 이야기"라는 가장 강한 신호이고, 파라미터 타입은 가장 약하다.
_EDGE_WEIGHT = {
    TypeEdgeKind.EXTENDS: 4,
    TypeEdgeKind.IMPLEMENTS: 4,
    TypeEdgeKind.FIELD_TYPE: 2,
    TypeEdgeKind.PARAM_TYPE: 1,
}
_CALL_WEIGHT_CAP = 3
_MIN_TYPES = 2
# 한 묶음이 쪽 하나가 되려면 이만큼은 담아야 한다. 이보다 작으면 부모 디렉토리로 올린다.
_MIN_PAGE_TYPES = 6
# 한 디렉토리를 쪼개는 문턱. 저자가 한 패키지에 모아 둔 것을 기계가 쪼개려면 그 패키지가
# 한 쪽에 담기지 않을 만큼 커야 한다.
_MAX_TYPES = 16
_TITLE_TYPES = 2


class TypeNode(BaseModel):
    """묶임의 단위. `key`가 정체이고 `label`이 사람이 읽는 이름이다.

    `name`만으로는 부족하다. `Option.Builder`와 `TextStyle.Builder`가 둘 다 `Builder`라
    이름만 보이면 어느 것인지 모른다.
    """

    key: str
    name: str
    label: str
    path: str
    directory: str
    module: str
    rank: int


def key_of(symbol: Symbol) -> str:
    """타입의 정체. 이름만으로는 같은 이름의 다른 타입을 구분하지 못한다."""
    return f"{symbol.span.path}#{symbol.name}"


def type_nodes(symbols: list[Symbol], ranks: list[FileRank]) -> list[TypeNode]:
    """타입 선언을 묶임의 단위로 만든다. 테스트 선언은 페이지의 주인공이 아니다."""
    order = {rank.path: position for position, rank in enumerate(ranks)}
    found = [
        TypeNode(
            key=key_of(symbol),
            name=symbol.name,
            label=f"{symbol.parent}.{symbol.name}" if symbol.parent else symbol.name,
            path=symbol.span.path,
            directory=str(PurePosixPath(symbol.span.path).parent),
            module=symbol.module,
            rank=order.get(symbol.span.path, len(order)),
        )
        for symbol in symbols
        if symbol.kind in _TYPE_KINDS and not symbol.is_test
    ]
    found.sort(key=lambda node: (node.directory, node.rank, node.name, node.path))
    return found


def relation_graph(
    nodes: list[TypeNode], type_edges: list[TypeEdge], call_edges: list[CallEdge]
) -> nx.Graph:
    """타입 사이의 무게 있는 무향 그래프.

    방향을 버리는 이유는 묶음이 방향을 묻지 않기 때문이다. "A가 B를 쓴다"와 "B가 A를 쓴다"는
    둘 다 "A와 B는 같은 이야기다"라는 같은 신호다.
    """
    by_name: dict[tuple[str, str], str] = {}
    for node in nodes:
        by_name.setdefault((node.path, node.name), node.key)
    graph = nx.Graph()
    for node in nodes:
        graph.add_node(node.key)

    for edge in sorted(type_edges, key=lambda e: (e.span.path, e.span.start_line, e.src, e.dst)):
        src = by_name.get((edge.src_path or "", edge.src))
        dst = by_name.get((edge.dst_path or "", edge.dst))
        if src is None or dst is None or src == dst:
            continue
        _add_weight(graph, src, dst, _EDGE_WEIGHT.get(edge.kind, 1))

    calls: dict[tuple[str, str], int] = defaultdict(int)
    for edge in call_edges:
        src = by_name.get((edge.src_path, edge.src_type))
        dst = by_name.get((edge.dst_path, edge.dst_type))
        if src is None or dst is None or src == dst:
            continue
        calls[tuple(sorted((src, dst)))] += 1
    for (src, dst), count in sorted(calls.items()):
        _add_weight(graph, src, dst, min(count, _CALL_WEIGHT_CAP))
    return graph


def _add_weight(graph: nx.Graph, src: str, dst: str, weight: int) -> None:
    if graph.has_edge(src, dst):
        graph[src][dst]["weight"] += weight
    else:
        graph.add_edge(src, dst, weight=weight)


def _title(members: list[TypeNode], directory: str, source: str) -> str:
    """묶음의 이름.

    디렉토리를 통째로 쓰는 묶음만 디렉토리 이름을 가진다. 그 이름은 저자가 적어 둔 분류라
    대표 타입 이름보다 강한 근거다. 하지만 한 디렉토리를 여럿으로 쪼갠 묶음들이 같은
    디렉토리 이름을 나눠 가지면 이름이 정체를 잃는다 — 그때는 대표 타입이 이름이다.
    """
    segment = PurePosixPath(directory).name
    if source == "directory" and segment and segment not in _MEANINGLESS_SEGMENTS:
        return segment
    # 중첩 타입은 제목으로 삼지 않는다. `Option.Builder`는 `Option`의 일부라, 그것을 묶음의
    # 대표로 세우면 페이지 이름이 부분을 전체처럼 말한다.
    outer = [node for node in members if "." not in node.label] or members
    top = sorted(outer, key=lambda node: (node.rank, node.name))[:_TITLE_TYPES]
    return "와 ".join(node.label for node in top) or segment or "묶음"


_MEANINGLESS_SEGMENTS = {"", ".", "src", "main", "java", "scala", "python", "test", "lib"}


def cluster(nodes: list[TypeNode], graph: nx.Graph) -> list[Cluster]:
    """타입을 개념 묶음으로 나눈다.

    디렉토리로 가르고, 작은 것을 부모로 올려 합치고, 큰 것만 커뮤니티로 쪼갠다.
    """
    by_directory: dict[str, list[TypeNode]] = defaultdict(list)
    for node in nodes:
        by_directory[node.directory].append(node)

    merged = _lift_small(by_directory)
    found: list[Cluster] = []
    for directory in sorted(merged):
        members = merged[directory]
        if len(members) <= _MAX_TYPES:
            found.append(_make(members, directory, "directory", len(found)))
            continue
        for group in _split(members, graph):
            found.append(_make(group, directory, "community", len(found)))
    return found


def _lift_small(by_directory: dict[str, list[TypeNode]]) -> dict[str, list[TypeNode]]:
    """작은 묶음을 부모 디렉토리로 올린다.

    가장 깊은 디렉토리부터 본다. 그래야 올린 것이 부모에 합쳐진 뒤 그 부모도 여전히
    작으면 다시 위로 올라간다. 더 올릴 부모가 없으면 그 자리에 남는다 — 저장소 뿌리의
    작은 묶음은 그것이 전부이기 때문이다.
    """
    working = {directory: list(members) for directory, members in by_directory.items()}
    while True:
        # 매번 가장 깊은 것부터 다시 본다. 한 번만 훑으면 부모가 자식을 받은 뒤 여전히
        # 작아도 그대로 남는다 — airflow 는 그래서 831개가 594개까지만 줄었다.
        candidate = None
        for directory in sorted(working, key=lambda name: (-len(name.split("/")), name)):
            if len(working[directory]) >= _MIN_PAGE_TYPES:
                continue
            parent = str(PurePosixPath(directory).parent)
            if parent != directory and parent not in ("", "."):
                candidate = (directory, parent)
                break
        if candidate is None:
            break
        directory, parent = candidate
        working.setdefault(parent, []).extend(working.pop(directory))
    return {directory: members for directory, members in working.items() if members}


def _make(members: list[TypeNode], directory: str, source: str, position: int) -> Cluster:
    ordered = sorted(members, key=lambda node: (node.rank, node.name, node.path))
    return Cluster(
        id=f"C{position}",
        title=_title(ordered, directory, source),
        directory=directory,
        module=ordered[0].module if ordered else ".",
        members=[node.key for node in ordered],
        source=source,
    )


def _split(members: list[TypeNode], graph: nx.Graph) -> list[list[TypeNode]]:
    """한 디렉토리를 커뮤니티로 쪼갠다. 쪼갤 수 없으면 통째로 낸다.

    관계가 없는 타입은 커뮤니티가 되지 않으므로 따로 모아 하나로 낸다. 그것들을 낱개로
    페이지 삼으면 내용 없는 쪽이 무더기로 생긴다.
    """
    keys = {node.key for node in members}
    by_key = {node.key: node for node in members}
    subgraph = graph.subgraph(keys)
    connected = [key for key in sorted(keys) if subgraph.degree(key) > 0]
    if len(connected) < _MIN_TYPES:
        return [members]

    communities = greedy_modularity_communities(subgraph.subgraph(connected), weight="weight")
    groups: list[list[TypeNode]] = []
    placed: set[str] = set()
    for community in communities:
        group = sorted(
            (by_key[key] for key in community), key=lambda node: (node.rank, node.name)
        )
        # 쪽이 될 만큼 크지 않은 조각은 만들지 않는다. 남은 것은 아래에서 한 묶음이 되거나
        # 가장 큰 묶음에 붙는다 — 디렉토리 하나를 타입 두 개짜리 조각으로 흩으면 쪼개기가
        # 문제를 푸는 것이 아니라 만든다.
        if len(group) < _MIN_PAGE_TYPES:
            continue
        groups.append(group)
        placed.update(node.key for node in group)
    leftover = sorted(
        (by_key[key] for key in sorted(keys - placed)), key=lambda node: (node.rank, node.name)
    )
    if not leftover:
        return groups or [members]
    if len(leftover) >= _MIN_PAGE_TYPES or not groups:
        groups.append(leftover)
        return groups
    # 남은 것이 쪽이 될 만큼 크지 않으면 가장 큰 묶음에 붙인다. 작은 페이지는 목록과
    # 다르지 않고, 그런 쪽이 수백 개면 위키를 훑을 수 없다.
    biggest = max(groups, key=len)
    biggest.extend(leftover)
    biggest.sort(key=lambda node: (node.rank, node.name))
    return groups


def lead_of(group: Cluster, labels: dict[str, str]) -> str:
    """묶음의 대표 타입 이름.

    그림을 만드는 층과 페이지를 만드는 층이 같은 대표를 골라야 한다. 두 곳에서 따로 고르면
    한쪽이 만든 그림을 다른 쪽이 찾지 못해 페이지에 그림이 없다(C-DUP-2).

    중첩 타입은 대표가 되지 못한다. 부분을 묶음의 얼굴로 세울 수 없고, 그림 생성기도 최상위
    타입만 그린다.
    """
    for key in group.members:
        label = labels.get(key, key.split("#")[-1])
        if "." not in label:
            return label
    return labels.get(group.members[0], "").split(".")[0] if group.members else group.title
