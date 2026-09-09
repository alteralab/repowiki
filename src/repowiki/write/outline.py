"""위키의 차례. 쪽을 평평한 목록이 아니라 위에서 아래로 내려가는 나무로 세운다.

경계 계약: 입력은 사실이고 출력은 이름 붙은 나무다. 어떤 쪽을 만들지만 정하고 그 안에
무엇을 실을지는 `write/plan.py`가 정한다.

왜 나무인가. 처음 보는 저장소를 읽는 사람은 전체에서 시작해 관심 있는 자리로 내려간다.
평평한 목록은 그 길을 주지 않는다 — airflow 의 묶음 262개를 한 층에 늘어놓으면 사람이
어디서 시작해야 할지 알 수 없다.

2026-09-09 DeepWiki apache/kafka 실측이 이 형태의 근거다. 59쪽이 3단이고, 1단 아홉 쪽의
하위 링크가 평균 10.3개인 반면 2단은 1.0, 3단은 0이다. 1단 쪽은 자기 아래를 한 줄씩 소개하는
문이고, 잎에 가까울수록 내용이 깊다. 단마다 분량은 비슷하다(1단 907단어, 2단 882, 3단 839).

사각: 이 층은 나무의 뼈대만 만든다. 각 쪽의 제목이 사람에게 뜻이 있는지는 여기서 판정하지
못한다 — 이름은 코드에서 오고, 개념 이름은 쓰는 층이 제안한다.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from repowiki.models import Cluster, RepoFacts

# 한 부모 아래에 둘 자식의 상한. 이보다 많으면 사람이 목록으로 읽지 못한다.
MAX_CHILDREN = 12
# 개념 나무가 쓸 수 있는 쪽수. 위키 전체의 상한이 아니라 나무의 예산이다.
# 2026-09-09에 DeepWiki 저장소 17곳의 쪽수를 실측했다: 최소 12(commons-cli), 중앙 43,
# 최대 80(pytorch). 개요·도구사슬·흐름·이력·품질·사용례·낱말사전 일곱 쪽이 나무 밖에
# 따로 서므로 그만큼을 빼 둔다. 안 빼면 전체가 관측된 천장을 넘는다(kafka가 87쪽이었다).
# 예산은 어림이다. 나무가 부모마다 몫을 나눠 가지므로 실제 쪽수는 한둘 어긋난다(kafka 81).
FIXED_PAGES = 7
MAX_PAGES = 80 - FIXED_PAGES
# 부모 쪽을 세우려면 자식이 이만큼은 있어야 한다. 자식 하나짜리 부모는 한 번 더 누르게
# 만들 뿐 아무것도 더 말하지 않는다.
MIN_CHILDREN = 2


class Node(BaseModel):
    """차례의 자리 하나. `section`이 사이드바에 보이는 번호다."""

    key: str
    title: str
    section: str
    parent: str | None = None
    kind: str
    clusters: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    children: list[str] = Field(default_factory=list)


class Outline(BaseModel):
    """위키의 차례 전부. 순서가 곧 사이드바의 순서다."""

    nodes: list[Node] = Field(default_factory=list)

    def children_of(self, key: str) -> list[Node]:
        return [node for node in self.nodes if node.parent == key]


def _group_key(cluster: Cluster, depth: int) -> str:
    """이 묶음이 속할 상위 자리. 디렉토리를 `depth`만큼 자른 것이다."""
    parts = [piece for piece in cluster.directory.split("/") if piece not in ("", ".")]
    return "/".join(parts[:depth]) or cluster.module


def _short(name: str) -> str:
    """상위 자리의 이름. 경로의 마지막 조각이 사람이 아는 이름이다."""
    tail = [piece for piece in name.split("/") if piece]
    return tail[-1] if tail else name


# 1단을 세울 만큼 묶음이 많은가. 이보다 적으면 나무를 만들 것이 없어 평평하게 둔다.
MIN_CLUSTERS_FOR_TREE = 8


def _pick_depth(clusters: list[Cluster]) -> int:
    """상위 자리를 만들 디렉토리 깊이. 그 깊이에서 자리 수가 상한 안이면 그것이다.

    저장소마다 디렉토리의 모양이 다르다. 얕게 자르면 자리가 몇 개뿐이라 나무가 서지 않고,
    깊게 자르면 자리가 수십 개라 목록과 다르지 않다. 깊이를 늘려 가며 처음으로 쓸 만한
    수가 되는 자리를 고른다.
    """
    for depth in range(1, 6):
        groups = {_group_key(cluster, depth) for cluster in clusters}
        if MIN_CHILDREN <= len(groups) <= MAX_CHILDREN:
            return depth
    # 어느 깊이에서도 안 맞으면 가장 얕은 것으로 둔다. 자리가 많은 것보다 적은 쪽이 낫다.
    return 1


def _titles(nodes: list[Node], qualifiers: dict[str, str] | None = None) -> None:
    """같은 제목을 가진 자리를 구분한다.

    제목이 겹치면 사이드바에서 같은 이름이 여럿 보이고, 사람은 어느 것을 눌러야 할지
    모른다. 겹치는 것만 앞에 자리 이름을 붙인다. 부모가 있으면 부모의 이름이고, 평평한
    차례에서는 호출자가 준 한정자(디렉토리)다.
    """
    counted: dict[str, int] = defaultdict(int)
    for node in nodes:
        counted[node.title] += 1
    by_key = {node.key: node for node in nodes}
    marks = qualifiers or {}
    for node in nodes:
        if counted[node.title] < 2:
            continue
        parent = by_key.get(node.parent) if node.parent else None
        mark = parent.title if parent is not None and parent.title else marks.get(node.key, "")
        if mark and mark != node.title:
            node.title = f"{mark}: {node.title}"

    # 한정을 붙인 뒤에도 같은 이름이 남을 수 있다. 한 부모 아래 같은 디렉토리에서 커뮤니티가
    # 둘로 갈린 경우가 그렇다. 그때는 번호로 가른다 — 사이드바에서 구분되는 것이 먼저다.
    seen: dict[str, int] = defaultdict(int)
    for node in nodes:
        seen[node.title] += 1
        if seen[node.title] > 1:
            node.title = f"{node.title} ({seen[node.title]})"


def build(facts: RepoFacts) -> Outline:
    """사실에서 차례를 세운다.

    1단은 상위 자리(디렉토리 묶음)이고 2단이 개념 묶음이다. 상위 자리가 하나뿐인 저장소는
    1단을 두지 않는다 — 자식 하나짜리 부모는 한 번 더 누르게 만들 뿐이다.
    """
    clusters = list(facts.clusters)
    if not clusters:
        return Outline()

    # 묶음이 몇 개뿐이면 나무를 세울 것이 없다. 사이드바 한 층이면 다 보인다.
    if len(clusters) < MIN_CLUSTERS_FOR_TREE:
        return _flat(clusters)

    depth = _pick_depth(clusters)
    grouped: dict[str, list[Cluster]] = defaultdict(list)
    for cluster in clusters:
        grouped[_group_key(cluster, depth)].append(cluster)

    ranked = sorted(
        grouped.items(), key=lambda item: (-sum(len(c.members) for c in item[1]), item[0])
    )
    if len(ranked) < MIN_CHILDREN:
        return _flat(ranked[0][1] if ranked else clusters)

    nodes: list[Node] = []
    budget = MAX_PAGES
    for position, (group, members) in enumerate(ranked[:MAX_CHILDREN], start=1):
        section = str(position)
        parent_key = f"group-{group}"
        ordered = sorted(members, key=lambda c: (-len(c.members), c.title))
        share = max(1, min(MAX_CHILDREN, budget // max(1, MAX_CHILDREN - position + 1)))
        kept = ordered[:share]
        budget -= len(kept) + 1
        nodes.append(
            Node(
                key=parent_key,
                title=_short(group),
                section=section,
                kind="area",
                clusters=[cluster.id for cluster in kept],
                modules=sorted({cluster.module for cluster in members}),
                children=[f"cluster-{cluster.id}" for cluster in kept],
            )
        )
        for index, cluster in enumerate(kept, start=1):
            nodes.append(
                Node(
                    key=f"cluster-{cluster.id}",
                    title=cluster.title,
                    section=f"{section}.{index}",
                    parent=parent_key,
                    kind="concept",
                    clusters=[cluster.id],
                    modules=[cluster.module],
                )
            )
    _titles(nodes)
    return Outline(nodes=nodes)


def _flat(clusters: list[Cluster]) -> Outline:
    """상위 자리가 하나뿐인 저장소의 차례. 개념 묶음이 곧 1단이다."""
    ordered = sorted(clusters, key=lambda c: (-len(c.members), c.title))[:MAX_CHILDREN]
    nodes = [
        Node(
            key=f"cluster-{cluster.id}",
            title=cluster.title,
            section=str(position),
            kind="concept",
            clusters=[cluster.id],
            modules=[cluster.module],
        )
        for position, cluster in enumerate(ordered, start=1)
    ]
    # 평평한 차례에는 부모가 없다. 겹치는 제목은 디렉토리의 상위 조각으로 가른다.
    marks = {
        f"cluster-{cluster.id}": _short(str(PurePosixPath(cluster.directory).parent))
        for cluster in ordered
    }
    _titles(nodes, marks)
    return Outline(nodes=nodes)
