"""차례의 단위 검사.

여기서 고정하는 것은 나무의 모양이다. 평평한 목록이면 사람이 어디서 시작할지 모르고,
자식 하나짜리 부모가 있으면 한 번 더 누르게 만들 뿐이며, 같은 제목이 둘이면 사이드바에서
구분되지 않는다.
"""

from __future__ import annotations

from repowiki.models import Cluster, RepoFacts, RepoKind, RepoProfile
from repowiki.write.outline import MAX_CHILDREN, build


def _facts(clusters: list[Cluster]) -> RepoFacts:
    return RepoFacts(
        profile=RepoProfile(
            root_name="r", kind=RepoKind.CODE, head_sha="a1", file_count=1, languages={}
        ),
        modules=[],
        module_edges=[],
        subsystems=[],
        symbols=[],
        type_edges=[],
        entry_points=[],
        file_ranks=[],
        flows=[],
        diagrams=[],
        clusters=clusters,
    )


def _cluster(cid: str, title: str, directory: str, size: int = 8) -> Cluster:
    return Cluster(
        id=cid,
        title=title,
        directory=directory,
        module=directory.split("/")[0],
        members=[f"{directory}/f{n}.java#T{n}" for n in range(size)],
        source="directory",
    )


def test_a_single_area_repository_stays_flat() -> None:
    """상위 자리가 하나면 1단을 두지 않는다. 자식 하나짜리 부모는 한 번 더 누르게 만든다."""
    outline = build(_facts([_cluster("C0", "a", "src/x"), _cluster("C1", "b", "src/y")]))
    assert [node.kind for node in outline.nodes] == ["concept", "concept"]
    assert [node.section for node in outline.nodes] == ["1", "2"]


def test_many_areas_become_a_two_level_tree() -> None:
    clusters = [
        _cluster(f"C{n}", f"t{n}", f"mod{n % 4}/pkg{n}") for n in range(12)
    ]
    outline = build(_facts(clusters))
    areas = [node for node in outline.nodes if node.kind == "area"]
    assert len(areas) == 4
    for area in areas:
        assert outline.children_of(area.key)
        assert all(child.section.startswith(f"{area.section}.") for child in outline.children_of(area.key))


def test_duplicate_titles_are_disambiguated_by_their_area() -> None:
    """사이드바에 같은 이름이 둘이면 사람이 어느 것을 눌러야 할지 모른다."""
    clusters = [
        _cluster("C0", "models", "a/models"),
        _cluster("C1", "models", "b/models"),
        _cluster("C2", "other", "a/other"),
    ]
    titles = [node.title for node in build(_facts(clusters)).nodes]
    assert len(titles) == len(set(titles))
    assert "a: models" in titles and "b: models" in titles


def test_the_area_count_never_exceeds_the_cap() -> None:
    """자리가 스무 개면 목록과 다르지 않다."""
    clusters = [_cluster(f"C{n}", f"t{n}", f"m{n}/pkg") for n in range(40)]
    areas = [node for node in build(_facts(clusters)).nodes if node.kind == "area"]
    assert len(areas) <= MAX_CHILDREN


def test_an_empty_repository_makes_an_empty_outline() -> None:
    assert build(_facts([])).nodes == []


def test_titles_stay_unique_even_when_the_area_name_does_not_help() -> None:
    """같은 부모 아래 같은 디렉토리에서 커뮤니티가 둘로 갈리면 한정이 소용없다."""
    clusters = [
        _cluster("C0", "assignor", "coord/assignor"),
        _cluster("C1", "assignor", "coord/assignor"),
        _cluster("C2", "other", "coord/other"),
        _cluster("C3", "x", "web/x"),
        _cluster("C4", "y", "web/y"),
    ]
    titles = [node.title for node in build(_facts(clusters)).nodes]
    assert len(titles) == len(set(titles))
