"""구조 계산의 단위 검사. 입력은 경로 목록이고 판정은 순수 함수가 한다."""

from __future__ import annotations

import pytest

from repowiki.analyze.domain import DomainFacts, is_test
from repowiki.analyze.structure import (
    build_modules,
    detect_kind,
    module_of,
    module_roots,
    source_paths,
)
from repowiki.models import RepoKind


@pytest.fixture
def facts() -> DomainFacts:
    return DomainFacts(
        extensions={".java": "java", ".py": "python"},
        analyzed_languages=["java", "python"],
        exclude_globs={"**/target/**": "빌드 산출물", "**/node_modules/**": "서드파티"},
        test_markers=["/src/test/", "/tests/"],
        build_files=["pom.xml", "pyproject.toml"],
        kind_markers={"helm": ["Chart.yaml"]},
    )


def test_gradle_source_set_becomes_module(facts: DomainFacts) -> None:
    """빌드 파일이 없는 Gradle 하위 프로젝트도 소스 세트로 모듈이 된다."""
    paths = ["core/src/main/java/A.java", "clients/src/main/java/B.java", "build.gradle"]
    roots = module_roots(paths, facts)
    assert "core" in roots
    assert "clients" in roots
    assert module_of("core/src/main/java/A.java", roots) == "core"


def test_longest_ancestor_wins() -> None:
    """중첩 모듈에서는 가장 긴 조상이 소유한다."""
    roots = ["", "a", "a/b"]
    assert module_of("a/b/src/main/java/X.java", roots) == "a/b"
    assert module_of("a/other/X.java", roots) == "a"
    assert module_of("z/X.java", roots) == "."


def test_excluded_paths_are_counted_with_reason(facts: DomainFacts) -> None:
    """제외는 버리는 것이 아니라 사유별로 세는 것이다."""
    kept, excluded = source_paths(["src/A.java", "target/A.class", "target/B.class"], facts)
    assert kept == ["src/A.java"]
    assert sum(excluded.values()) == 2
    assert any("빌드 산출물" in reason for reason in excluded)


def test_kind_detection_marks_mixed(facts: DomainFacts) -> None:
    """표식이 둘이면 mixed다."""
    assert detect_kind(["pom.xml"], facts) is RepoKind.CODE
    assert detect_kind(["main.tf"], facts) is RepoKind.TERRAFORM
    assert detect_kind(["pom.xml", "main.tf"], facts) is RepoKind.MIXED


def test_module_counts_split_main_and_test(facts: DomainFacts) -> None:
    """테스트 소스는 제외가 아니라 분리다."""
    paths = ["core/src/main/java/A.java", "core/src/test/java/ATest.java"]
    roots = module_roots(paths, facts)
    modules = build_modules(paths, roots, {p: 10 for p in paths}, facts)
    core = next(m for m in modules if m.id == "core")
    assert core.file_count == 2
    assert core.main_file_count == 1
    assert is_test("core/src/test/java/ATest.java", facts) is True


def test_nested_source_set_picks_innermost_root(facts: DomainFacts) -> None:
    """소스 세트가 두 번 나오면 안쪽이 모듈 뿌리다."""
    path = "a/src/main/generated/src/main/java/X.java"
    roots = module_roots([path], facts)
    assert "a/src/main/generated" in roots
    assert module_of(path, roots) == "a/src/main/generated"


def test_top_level_build_output_is_excluded(facts: DomainFacts) -> None:
    """최상위 빌드 산출물도 제외된다. 글로브가 맨 앞 구획을 놓치면 안 된다."""
    kept, excluded = source_paths(["target/A.class", "a/target/B.class", "src/A.java"], facts)
    assert kept == ["src/A.java"]
    assert sum(excluded.values()) == 2


def test_build_file_inside_resources_is_not_a_module(facts: DomainFacts) -> None:
    """리소스 안의 빌드 파일은 템플릿이다. Maven 아키타입이 pom.xml을 통째로 담는다."""
    paths = [
        "quickstart/src/main/resources/archetype-resources/pom.xml",
        "quickstart/src/main/resources/archetype-resources/src/main/java/X.java",
        "quickstart/pom.xml",
    ]
    roots = module_roots(paths, facts)
    assert "quickstart" in roots
    assert not any("archetype-resources" in root for root in roots)
