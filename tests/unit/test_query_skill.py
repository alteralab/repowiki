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
