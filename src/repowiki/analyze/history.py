"""이력 사실: 핫스팟, 시간 결합, 이슈 키. 순수 계산이다(C-DEPTH-3).

경계 계약: 입력은 커밋 목록(어댑터가 낸다)과 도메인 사실이고, 출력은 이름 붙은 형태다.

핫스팟은 수정 횟수로 센다. 줄 단위 churn은 blobless 클론에서 얻을 수 없어 쓰지 않는다.
시간 결합의 산식과 기본값은 code-maat와 같게 두었다(PLAN §2.9). 그래야 그 도구를 오라클로
쓸 수 있다: `결합도 = 함께 바뀐 횟수 / 두 파일 수정 횟수의 평균`.

사각: 큰 커밋 하나가 결합을 만들어 낸다. `max_changeset_size`로 그런 커밋을 제외하지만
경계값 근처의 커밋은 여전히 잡음이다.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from pydantic import BaseModel

from repowiki.adapters.githistory import Commit
from repowiki.analyze.domain import DomainFacts, excluded_by

MIN_REVISIONS = 5
MIN_SHARED_REVISIONS = 5
MIN_COUPLING = 0.30
MAX_CHANGESET_SIZE = 30


class Hotspot(BaseModel):
    """자주 바뀌는 파일. `revisions`는 창 안의 수정 횟수다."""

    path: str
    module: str
    revisions: int
    authors: int
    last_date: str


class Coupling(BaseModel):
    """함께 바뀌는 두 파일. 값은 code-maat와 같은 산식이다."""

    left: str
    right: str
    shared: int
    coupling: float


class Period(BaseModel):
    """분기 하나의 집계. timeline이 이 자료로 그려진다."""

    label: str
    commits: int
    top_path: str
    top_revisions: int


class IssueKeys(BaseModel):
    """커밋 제목에서 뽑은 이슈 키의 분포. 값은 비율이 아니라 건수다."""

    total_commits: int
    counts: dict[str, int]


class History(BaseModel):
    """이력 사실 묶음."""

    window_months: int
    commit_count: int
    hotspots: list[Hotspot]
    couplings: list[Coupling]
    issue_keys: IssueKeys


def _tracked(commit: Commit, facts: DomainFacts, known: set[str]) -> list[str]:
    """지금도 존재하고 제외 대상이 아닌 경로만 남긴다."""
    return [
        path
        for path in commit.paths
        if path in known and excluded_by(path, facts) is None
    ]


def hotspots(
    commits: list[Commit], facts: DomainFacts, known: set[str], module_of, roots: list[str], top: int
) -> list[Hotspot]:
    """수정 횟수 상위 파일. 같은 횟수면 경로 사전순으로 가른다."""
    revisions: Counter[str] = Counter()
    authors: dict[str, set[str]] = defaultdict(set)
    last_date: dict[str, str] = {}
    for commit in commits:
        for path in _tracked(commit, facts, known):
            revisions[path] += 1
            authors[path].add(commit.author)
            last_date.setdefault(path, commit.date)
    ordered = sorted(revisions.items(), key=lambda item: (-item[1], item[0]))
    return [
        Hotspot(
            path=path,
            module=module_of(path, roots),
            revisions=count,
            authors=len(authors[path]),
            last_date=last_date.get(path, ""),
        )
        for path, count in ordered[:top]
    ]


def couplings(
    commits: list[Commit],
    facts: DomainFacts,
    known: set[str],
    top: int,
    min_revisions: int = MIN_REVISIONS,
    min_shared: int = MIN_SHARED_REVISIONS,
    min_coupling: float = MIN_COUPLING,
    max_changeset: int = MAX_CHANGESET_SIZE,
) -> list[Coupling]:
    """시간 결합. 기본값과 산식은 code-maat와 같다(오라클 대조를 위해서다)."""
    revisions: Counter[str] = Counter()
    shared: Counter[tuple[str, str]] = Counter()
    for commit in commits:
        paths = sorted(set(_tracked(commit, facts, known)))
        if not paths or len(paths) > max_changeset:
            continue
        for path in paths:
            revisions[path] += 1
        for index, left in enumerate(paths):
            for right in paths[index + 1 :]:
                shared[(left, right)] += 1

    results: list[Coupling] = []
    for (left, right), count in shared.items():
        if count < min_shared:
            continue
        if revisions[left] < min_revisions or revisions[right] < min_revisions:
            continue
        average = (revisions[left] + revisions[right]) / 2
        degree = count / average if average else 0.0
        if degree < min_coupling:
            continue
        results.append(
            Coupling(left=left, right=right, shared=count, coupling=round(degree, 4))
        )
    results.sort(key=lambda item: (-item.coupling, -item.shared, item.left, item.right))
    return results[:top]


def periods(commits: list[Commit], facts: DomainFacts, known: set[str]) -> list[Period]:
    """분기별 커밋 수와 그 분기에 가장 많이 바뀐 파일.

    달 단위는 24개월 창에서 24칸이라 그림이 길어지고, 해 단위는 두 칸뿐이라 추이가
    보이지 않는다. 분기가 그 사이다.
    """
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    for commit in commits:
        parts = commit.date.split("-")
        if len(parts) < 2:
            continue
        quarter = (int(parts[1]) - 1) // 3 + 1
        label = f"{parts[0]} Q{quarter}"
        totals[label] += 1
        for path in _tracked(commit, facts, known):
            buckets[label][path] += 1
    result: list[Period] = []
    for label in sorted(totals):
        top = buckets[label].most_common(1)
        result.append(
            Period(
                label=label,
                commits=totals[label],
                top_path=top[0][0] if top else "",
                top_revisions=top[0][1] if top else 0,
            )
        )
    return result


def issue_keys(commits: list[Commit], patterns: dict[str, str]) -> IssueKeys:
    """커밋 제목에서 이슈 키를 센다. 패턴은 데이터가 소유한다(C-DOMAIN-1)."""
    counts: Counter[str] = Counter()
    # 커밋 제목은 한 줄짜리 평평한 문자열이고 이슈 키는 고정 형식이다. 중첩 구조가 아니다.
    # ast-grep-ignore: regex-on-structure — 어휘: 한 줄 제목에서 고정 형식 키를 찾는 판정이다.
    compiled = {name: re.compile(pattern) for name, pattern in patterns.items()}
    for commit in commits:
        for name, expression in compiled.items():
            if expression.search(commit.subject):
                counts[name] += 1
    return IssueKeys(total_commits=len(commits), counts=dict(sorted(counts.items())))
