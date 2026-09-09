"""저장소 구조: 종류 감지, 프로파일, 모듈 경계. 전부 순수 계산이다(C-DEPTH-3).

입력은 추적 파일 목록과 파일 크기 조회 함수이고, 출력은 이름 붙은 형태다.
파일을 직접 열지 않는다 — 여는 것은 호출자(파이프라인 노드)의 일이다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import PurePosixPath

from repowiki.analyze.domain import DomainFacts, excluded_by, is_test, language_of
from repowiki.models import LanguageStat, Module, RepoKind, RepoProfile


def detect_kind(paths: list[str], facts: DomainFacts) -> RepoKind:
    """저장소 종류를 감지한다. 표식이 둘 이상이면 `MIXED`다(PLAN §2.7)."""
    found: set[RepoKind] = set()
    names = [PurePosixPath(p).name for p in paths]
    if "Chart.yaml" in names and any("/templates/" in p for p in paths):
        found.add(RepoKind.HELM)
    if any(p.endswith(".tf") and ".terraform/" not in p for p in paths):
        found.add(RepoKind.TERRAFORM)
    if any(n in ("kustomization.yaml", "kustomization.yml") for n in names):
        found.add(RepoKind.K8S)
    if any(n in facts.build_files for n in names):
        found.add(RepoKind.CODE)
    if len(found) > 1:
        return RepoKind.MIXED
    if not found:
        return RepoKind.CODE
    return found.pop()


def source_paths(paths: list[str], facts: DomainFacts) -> tuple[list[str], dict[str, int]]:
    """분석 대상 소스와 제외 집계를 낸다. 제외는 사유별로 센다(C-GATE-4)."""
    kept: list[str] = []
    excluded: Counter[str] = Counter()
    for path in paths:
        glob = excluded_by(path, facts)
        if glob is not None:
            excluded[f"{glob} ({facts.exclude_globs[glob]})"] += 1
            continue
        kept.append(path)
    return kept, dict(excluded)


def build_profile(
    root_name: str,
    head_sha: str,
    paths: list[str],
    line_counts: dict[str, int],
    facts: DomainFacts,
    remote_url: str = "",
) -> RepoProfile:
    """언어별 파일과 줄 수를 센다. `line_counts`는 호출자가 읽어 넘긴다."""
    kept, excluded = source_paths(paths, facts)
    stats: dict[str, LanguageStat] = {}
    for path in kept:
        language = language_of(path, facts)
        if language is None:
            continue
        stat = stats.setdefault(language, LanguageStat(files=0, lines=0, main_files=0))
        stat.files += 1
        stat.lines += line_counts.get(path, 0)
        if not is_test(path, facts):
            stat.main_files += 1
    return RepoProfile(
        root_name=root_name,
        kind=detect_kind(paths, facts),
        head_sha=head_sha,
        remote_url=remote_url,
        file_count=len(kept),
        languages=stats,
        excluded=excluded,
    )


_SOURCE_SET = "/src/"
_RESOURCES = "/resources/"


def _inside_resources(path: str) -> bool:
    """리소스 디렉토리 안인가. 그 안의 빌드 파일과 소스 세트는 모듈이 아니라 템플릿이다.

    Maven 아키타입이 `src/main/resources/archetype-resources/`에 pom.xml과 소스 트리를
    통째로 담는다(kafka streams/quickstart 실측).
    """
    return _RESOURCES in f"/{path}/"


def module_roots(paths: list[str], facts: DomainFacts) -> list[str]:
    """모듈 뿌리를 정한다. 근거는 둘이고 합집합을 쓴다.

    (1) 빌드 파일이 있는 디렉토리(Maven, npm, pyproject, go.mod).
    (2) `src/main` 또는 `src/test` 소스 세트를 가진 디렉토리. Gradle 하위 프로젝트는
        자기 빌드 파일이 없을 수 있어 (1)만으로는 한 덩어리가 된다(kafka 실측).

    루트는 항상 포함한다 — 어느 뿌리에도 안 걸리는 파일의 소속처다.
    """
    roots = {""}
    for path in paths:
        pure = PurePosixPath(path)
        if pure.name in facts.build_files and not _inside_resources(path):
            roots.add(pure.parent.as_posix().lstrip("."))
        # 소스 세트가 경로에 두 번 나오면 안쪽이 이긴다. 바깥을 고르면 생성 소스가
        # 상위 모듈로 흡수된다(`a/src/main/generated/src/main/java/X.java`).
        for marker in (f"{_SOURCE_SET}main/", f"{_SOURCE_SET}test/"):
            if marker in path:
                head = path.rsplit(marker, 1)[0]
                # 리소스 안의 소스 세트는 모듈이 아니라 템플릿이다. Maven 아키타입이
                # `resources/archetype-resources/src/main/...`을 담는다(kafka 실측).
                if head and head != path and not _inside_resources(head):
                    roots.add(head)
                break
    return sorted(roots)


def module_of(path: str, roots: list[str]) -> str:
    """파일이 속한 모듈. 가장 긴 조상 뿌리가 이긴다."""
    best = ""
    for root in roots:
        if not root:
            continue
        if path == root or path.startswith(f"{root}/"):
            if len(root) > len(best):
                best = root
    return best or "."


def build_modules(
    paths: list[str],
    roots: list[str],
    line_counts: dict[str, int],
    facts: DomainFacts,
) -> list[Module]:
    """모듈별 언어 분포와 파일 수를 센다. 빈 모듈은 내지 않는다(C-SPEC-1)."""
    by_module: dict[str, Module] = {}
    lang_count: dict[str, Counter[str]] = defaultdict(Counter)
    for path in paths:
        language = language_of(path, facts)
        if language is None:
            continue
        module_id = module_of(path, roots)
        module = by_module.setdefault(
            module_id, Module(id=module_id, build_file=_build_file_of(module_id, paths, facts))
        )
        module.file_count += 1
        if not is_test(path, facts):
            module.main_file_count += 1
        lang_count[module_id][language] += line_counts.get(path, 0)
    for module_id, counts in lang_count.items():
        by_module[module_id].languages = dict(counts.most_common())
    return [m for _, m in sorted(by_module.items()) if m.file_count > 0]


def _build_file_of(module_id: str, paths: list[str], facts: DomainFacts) -> str | None:
    prefix = f"{module_id}/" if module_id and module_id != "." else ""
    for name in facts.build_files:
        candidate = f"{prefix}{name}"
        if candidate in paths:
            return candidate
    return None
