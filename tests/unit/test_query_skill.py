"""조회 스킬. 스크립트는 낱말이 든 절만 내고, 스킬은 위키와 함께 나간다(PLAN §2.10)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from repowiki.pipeline.write_run import QUERY_SKILL, emit_query_skill

SCRIPT = QUERY_SKILL / "scripts" / "search-wiki.sh"

_FULL = """<!-- areas/1-clients.md -->
---
type: area
title: "클라이언트"
sources: [{id: "E1", resource: "repo://clients/NetworkClient.java#L1-L9"}]
---

<details>
<summary>근거 소스 1개</summary>

- `clients/NetworkClient.java`
</details>

클라이언트 묶음의 머리말이다. NetworkClient 가 여기 있다.

## 무엇에 기대는가

NetworkClient 는 Selector 에 기댄다 [^E1]

### 실패

연결이 끊기면 재시도한다.

## 다른 절

여기에는 낱말이 없다.

---

<!-- areas/2-streams.md -->
---
title: "스트림즈"
---

스트림즈 머리말.

## 상태 저장소

RocksDBStore 가 있다.
"""


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd, check=False
    )


def test_only_sections_with_the_word_are_printed(tmp_path: Path) -> None:
    """낱말이 든 절만 낸다. frontmatter 는 절이 아니고, 쪽 사이 구분선도 절이 아니다."""
    full = tmp_path / "llms-full.txt"
    full.write_text(_FULL, encoding="utf-8")
    done = _run("networkclient", str(full))
    assert done.returncode == 0, done.stderr
    out = done.stdout
    assert "== areas/1-clients.md :: 근거 소스" in out
    assert "== areas/1-clients.md :: (쪽 머리)" in out
    assert "== areas/1-clients.md :: 무엇에 기대는가" in out
    assert "다른 절" not in out and "스트림즈" not in out
    assert "type: area" not in out  # frontmatter 는 내지 않는다
    assert "실패" not in out  # 하위 절도 절이다. 낱말이 없으면 안 낸다


def test_directory_argument_and_max_and_no_match(tmp_path: Path) -> None:
    """둘째 인자는 위키 디렉토리여도 된다. --max 를 넘으면 수만 말하고, 없으면 종료 1이다."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "llms-full.txt").write_text(_FULL, encoding="utf-8")
    done = _run("NetworkClient", str(wiki), "--max", "1")
    assert done.returncode == 0
    assert done.stdout.count("== ") == 1
    assert "절 3개 중 1개만 냈다" in done.stdout
    missing = _run("없는낱말", str(wiki))
    assert missing.returncode == 1 and missing.stdout == ""
    assert _run("x", str(tmp_path / "nowhere")).returncode == 2


def test_default_wiki_location_is_relative_to_the_script(tmp_path: Path) -> None:
    """스킬이 위키 옆에 놓이면 인자 없이 그 위키를 읽는다. 작업 디렉토리는 무관하다."""
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "llms-full.txt").write_text(_FULL, encoding="utf-8")
    skill = emit_query_skill(tmp_path)
    assert (skill / "SKILL.md").exists() and (skill / "scripts" / "search-wiki.sh").exists()
    done = subprocess.run(  # noqa: S603
        ["bash", str(skill / "scripts" / "search-wiki.sh"), "RocksDBStore"],
        capture_output=True,
        text=True,
        cwd="/",
        check=False,
    )
    assert done.returncode == 0
    assert "== areas/2-streams.md :: 상태 저장소" in done.stdout


def test_shards_are_read_as_one(tmp_path: Path) -> None:
    """원문이 조각으로 나뉘어 있으면 조각 전부를 읽고 인덱스는 건너뛴다."""
    shards = tmp_path / "wiki" / "llms-full"
    shards.mkdir(parents=True)
    head, tail = _FULL.split("\n---\n\n<!-- areas/2-streams.md -->")
    (shards / "01-areas.md").write_text(head, encoding="utf-8")
    (shards / "02-streams.md").write_text("<!-- areas/2-streams.md -->" + tail, encoding="utf-8")
    (shards / "index.md").write_text("- RocksDBStore 는 index 에도 있다\n", encoding="utf-8")
    done = _run("RocksDBStore", str(tmp_path / "wiki"))
    assert done.returncode == 0
    assert done.stdout.count("== ") == 1


def test_bad_counts_are_usage_errors(tmp_path: Path) -> None:
    """`--max nope` 나 `0` 을 awk 에 넘기면 조용히 아무것도 안 낸다. 인자 오류는 종료 2다."""
    full = tmp_path / "llms-full.txt"
    full.write_text(_FULL, encoding="utf-8")
    for flag, value in (("--max", "nope"), ("--max", "0"), ("--max", "-1"), ("--lines", "x")):
        assert _run("NetworkClient", str(full), flag, value).returncode == 2, (flag, value)


def _wiki(root: Path, name: str, body: str) -> Path:
    """시스템 뿌리 아래 위키 하나. 번들이 내는 것과 같은 파일들이다."""
    import json

    wiki = root / name / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "llms-full.txt").write_text(body, encoding="utf-8")
    (wiki / "llms.txt").write_text(f"# {name}\n", encoding="utf-8")
    (wiki / "index.md").write_text(f"# {name}\n", encoding="utf-8")
    (wiki / ".manifest.json").write_text(
        json.dumps({"name": name, "description": f"{name} 위키", "analyzed_commit": "a" * 40, "pages": 1}),
        encoding="utf-8",
    )
    return wiki


def test_system_root_searches_every_wiki_and_names_them(tmp_path: Path) -> None:
    """뿌리에 system/llms.txt 가 있으면 그 위키 전부를 훑고 절마다 어느 위키인지 앞에 붙인다."""
    from repowiki.pipeline.system_run import discover, write_system

    _wiki(tmp_path, "kafka", _FULL)
    _wiki(tmp_path, "flink", _FULL.replace("NetworkClient", "JobManager"))
    members = discover(tmp_path)
    assert [m.name for m in members] == ["flink", "kafka"]
    assert members[0].path == "flink/wiki"
    system, count = write_system(tmp_path, "platform")
    assert count == 2
    llms = (system / "llms.txt").read_text(encoding="utf-8")
    # 링크는 system/ 안의 파일 기준이라 한 단계 올라간다.
    assert "- [flink](../flink/wiki/llms.txt): flink 위키" in llms
    index = (system / "index.md").read_text(encoding="utf-8")
    assert "| kafka | kafka 위키 | 1 | `aaaaaaaaaaaa` | [kafka/wiki/index.md](../kafka/wiki/index.md) |" in index
    done = _run("JobManager", str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert "== flink/wiki/areas/1-clients.md :: 무엇에 기대는가" in done.stdout
    assert "kafka/" not in done.stdout
    both = _run("Selector", str(tmp_path))
    assert "== flink/wiki/areas/1-clients.md" in both.stdout and "== kafka/wiki/areas/1-clients.md" in both.stdout


def test_single_wiki_root_has_a_system_index_too(tmp_path: Path) -> None:
    """위키가 하나여도 system/index.md 는 있다. 처음부터 있는 자리에 줄이 더해지는 구조다."""
    from repowiki.pipeline.system_run import write_system

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "llms-full.txt").write_text(_FULL, encoding="utf-8")
    (wiki / ".manifest.json").write_text(
        '{"name": "solo", "description": "혼자", "analyzed_commit": "b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0", "pages": 2}',
        encoding="utf-8",
    )
    system, count = write_system(tmp_path)
    assert count == 1
    assert "solo 시스템 인덱스" in (system / "index.md").read_text(encoding="utf-8")
    # 위키 하나인 뿌리에서 검색하면 접두어 없이 낸다.
    done = _run("NetworkClient", str(tmp_path))
    assert done.returncode == 0 and "== areas/1-clients.md ::" in done.stdout


def test_empty_root_writes_no_system_index(tmp_path: Path) -> None:
    """구성원이 없으면 인덱스를 쓰지 않는다. 빈 인덱스는 길을 잘못 안내한다."""
    from repowiki.pipeline.system_run import write_system

    system, count = write_system(tmp_path)
    assert count == 0 and not system.exists()


def test_duplicate_names_and_linked_duplicates_are_refused(tmp_path: Path) -> None:
    """같은 이름 둘, 또는 링크로 두 번 잡히는 같은 위키는 인덱스가 될 수 없다."""
    import os

    import pytest

    from repowiki.pipeline.system_run import SystemIndexError, discover

    _wiki(tmp_path, "a", _FULL)
    _wiki(tmp_path, "b", _FULL)
    (tmp_path / "b" / "wiki" / ".manifest.json").write_text(
        (tmp_path / "a" / "wiki" / ".manifest.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(SystemIndexError, match="이름 'a'"):
        discover(tmp_path)
    (tmp_path / "b").rename(tmp_path / "c")
    os.symlink(tmp_path / "a", tmp_path / "b")
    with pytest.raises(SystemIndexError, match="같은 위키"):
        discover(tmp_path)


def test_removing_the_last_wiki_removes_the_stale_index(tmp_path: Path) -> None:
    """마지막 위키가 사라지면 인덱스도 사라진다. 낡은 인덱스는 없는 길을 안내한다."""
    import shutil

    from repowiki.pipeline.system_run import write_system

    _wiki(tmp_path, "a", _FULL)
    system, count = write_system(tmp_path)
    assert count == 1 and (system / "llms.txt").exists()
    shutil.rmtree(tmp_path / "a")
    system, count = write_system(tmp_path)
    assert count == 0 and not (system / "llms.txt").exists() and not (system / "index.md").exists()


def test_broken_index_entry_fails_loudly(tmp_path: Path) -> None:
    """인덱스가 가리키는 위키에 원문이 없으면 일부만 훑고 성공하지 않는다."""
    from repowiki.pipeline.system_run import write_system

    _wiki(tmp_path, "a", _FULL)
    _wiki(tmp_path, "b", _FULL)
    write_system(tmp_path)
    (tmp_path / "b" / "wiki" / "llms-full.txt").unlink()
    done = _run("NetworkClient", str(tmp_path))
    assert done.returncode == 2 and "b/wiki" in done.stderr


def test_manifest_drops_credentials_from_the_remote() -> None:
    """원격 주소의 토큰은 산출물에 남지 않는다."""
    from repowiki.bundle.emit import Frontmatter, Generated
    from repowiki.models import RepoFacts, RepoProfile
    from repowiki.pipeline.write_run import _manifest

    profile = RepoProfile(
        root_name="x", kind="code", head_sha="c" * 40,
        remote_url="https://user:s3cret@gitlab.example/g/x.git", file_count=1, languages={},
    )
    facts = RepoFacts.model_construct(profile=profile)
    head = Frontmatter(type="area", title="t", description="d", generated=Generated(by="repowiki/0", at="2026-09-10T00:00:00+00:00"), analyzed_commit="c" * 40)
    member = _manifest([("areas/x.md", head)], facts, "2026-09-10T00:00:00+00:00")
    assert "s3cret" not in member.remote_url and "user" not in member.remote_url


def test_foreign_system_files_are_never_overwritten(tmp_path: Path) -> None:
    """사람이 써 둔 system/index.md 는 repowiki 의 표식이 없다. 덮어쓰지도 지우지도 않는다."""
    import pytest

    from repowiki.pipeline.system_run import SystemIndexError, write_system

    _wiki(tmp_path, "a", _FULL)
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "index.md").write_text("# 내가 쓴 시스템 문서\n", encoding="utf-8")
    with pytest.raises(SystemIndexError, match="repowiki 가 만든 파일이 아니다"):
        write_system(tmp_path)
    assert (tmp_path / "system" / "index.md").read_text(encoding="utf-8") == "# 내가 쓴 시스템 문서\n"


def test_index_links_that_escape_the_root_are_refused(tmp_path: Path) -> None:
    """`../../밖` 처럼 뿌리를 벗어나는 링크는 읽지 않는다."""
    _wiki(tmp_path, "a", _FULL)
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "llms.txt").write_text(
        "# x\n<!-- repowiki system index -->\n\n- [a](../../outside/wiki/llms.txt): 밖\n", encoding="utf-8"
    )
    done = _run("NetworkClient", str(tmp_path))
    assert done.returncode == 2 and "안전하지 않다" in done.stderr
