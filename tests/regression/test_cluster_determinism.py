"""묶음의 순서가 해시 시드에 흔들리지 않는지 고정한다.

`facts.json`은 `PYTHONHASHSEED`가 달라도 바이트 단위로 같아야 한다(PLAN §2.9). 2026-09-10
kafka 실측에서 시드 1과 2의 묶음 구성은 같은데 같은 크기의 커뮤니티 순서가 서로 바뀌어
묶음 id와 그림 순서가 갈렸다. 원인은 networkx가 커뮤니티를 크기로만 정렬하고 같은 크기의
순서를 부분 그래프 뷰가 집합을 훑는 순서에 맡기는 것이다.

한 프로세스 안에서는 시드를 바꿀 수 없으므로 자식 프로세스를 시드마다 띄운다. 시드 몇 개가
우연히 같은 순서를 낼 수 있어 여럿을 본다 — 고치기 전 코드는 시드 0~15 중 5개가 다른
순서를 냈다.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

SEEDS = range(12)

# 배경 노드가 많아야 부분 그래프 뷰가 "짧은" 집합 쪽을 훑는다(networkx FilterAtlas 규칙:
# 집합의 두 배가 전체보다 작을 때). 같은 크기의 클리크 둘은 크기순 정렬로 갈리지 않는다.
_PROBE = """
import networkx as nx
from repowiki.analyze import clusters
from repowiki.analyze.clusters import TypeNode


def node(i):
    return TypeNode(
        key=f"dir/f{i}.java#T{i}", name=f"T{i}", label=f"T{i}", path=f"dir/f{i}.java",
        directory="dir", module=".", rank=999,
    )


graph = nx.Graph()
for i in range(200):
    graph.add_node(f"bg/f{i}.java#B{i}")
members = [node(i) for i in range(12)]
for member in members:
    graph.add_node(member.key)
for block in (range(0, 6), range(6, 12)):
    block = list(block)
    for a in block:
        for b in block:
            if a < b:
                graph.add_edge(members[a].key, members[b].key, weight=1)
print([[n.name for n in group] for group in clusters._split(members, graph)])
"""


def _split_order(seed: int) -> str:
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, env=env, check=True
    )
    return done.stdout.strip()


@pytest.mark.parametrize("seed", SEEDS)
def test_split_order_is_the_same_under_every_hash_seed(seed: int) -> None:
    """어느 시드에서든 시드 0과 같은 순서를 낸다."""
    assert _split_order(seed) == _split_order(0)
