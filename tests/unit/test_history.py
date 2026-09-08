"""이력 계산의 단위 검사. 핫스팟, 시간 결합, 이슈 키가 대상이다."""

from __future__ import annotations

import pytest

from repowiki.adapters.githistory import Commit, _parse
from repowiki.analyze.domain import DomainFacts
from repowiki.analyze.history import couplings, hotspots, issue_keys


@pytest.fixture
def facts() -> DomainFacts:
    return DomainFacts(
        extensions={".java": "java"},
        analyzed_languages=["java"],
        exclude_globs={"**/target/**": "빌드 산출물"},
        test_markers=["/src/test/"],
        build_files=["pom.xml"],
        kind_markers={},
        issue_patterns={"jira": r"\b[A-Z][A-Z0-9]{1,9}-[0-9]+\b", "minor": "^MINOR:"},
    )


def _commit(sha: str, paths: list[str], author: str = "a", subject: str = "s") -> Commit:
    return Commit(sha=sha, date="2026-01-01", author=author, subject=subject, paths=paths)


def test_log_parsing_keeps_commits_without_paths() -> None:
    """병합 커밋처럼 파일이 없는 커밋도 셈에 들어간다."""
    text = "\x1eabc|2026-01-01|kim|KAFKA-1 fix\na/A.java\nb/B.java\n\x1edef|2026-01-02|lee|merge\n"
    commits = _parse(text)
    assert [c.sha for c in commits] == ["abc", "def"]
    assert commits[0].paths == ["a/A.java", "b/B.java"]
    assert commits[1].paths == []


def test_hotspots_count_revisions_of_existing_files(facts: DomainFacts) -> None:
    """지금 없는 경로와 제외 경로는 세지 않는다. 핫스팟은 수정 횟수 순이다."""
    commits = [
        _commit("1", ["a/A.java", "gone/B.java", "target/C.class"]),
        _commit("2", ["a/A.java"], author="b"),
    ]
    known = {"a/A.java", "target/C.class"}
    def module_of(path: str, roots: list[str]) -> str:
        return path.split("/")[0] if roots else "."

    found = hotspots(commits, facts, known, module_of, [""], top=5)
    assert [(h.path, h.revisions, h.authors) for h in found] == [("a/A.java", 2, 2)]


def test_couplings_follow_the_code_maat_formula(facts: DomainFacts) -> None:
    """결합도는 함께 바뀐 횟수를 두 파일 수정 횟수의 평균으로 나눈 값이다."""
    known = {"a/A.java", "a/B.java", "a/C.java"}
    commits = [_commit(str(i), ["a/A.java", "a/B.java"]) for i in range(6)]
    commits += [_commit("x", ["a/A.java", "a/C.java"]) for _ in range(6)]
    found = couplings(commits, facts, known, top=5)
    pairs = {(c.left, c.right): (c.shared, c.coupling) for c in found}
    assert pairs[("a/A.java", "a/B.java")] == (6, 0.6667)
    assert ("a/A.java", "a/C.java") in pairs


def test_couplings_skip_oversized_changesets(facts: DomainFacts) -> None:
    """한 커밋이 너무 많은 파일을 바꾸면 결합의 근거로 쓰지 않는다."""
    known = {f"a/F{i}.java" for i in range(40)}
    commits = [_commit(str(i), sorted(known)) for i in range(10)]
    assert couplings(commits, facts, known, top=5, max_changeset=30) == []


def test_issue_keys_count_each_pattern(facts: DomainFacts) -> None:
    """패턴마다 몇 건인지 센다. 한 제목이 둘에 걸리면 둘 다 센다."""
    commits = [
        _commit("1", [], subject="KAFKA-1 fix"),
        _commit("2", [], subject="MINOR: cleanup"),
        _commit("3", [], subject="MINOR: KAFKA-2 both"),
        _commit("4", [], subject="no key"),
    ]
    keys = issue_keys(commits, facts.issue_patterns)
    assert keys.total_commits == 4
    assert keys.counts == {"jira": 2, "minor": 2}
