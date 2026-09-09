"""작업 저장소의 단위 검사.

여기서 고정하는 것은 세대의 뜻이다. 세대가 낡은 제출을 가리고, 그 가림이 없으면
다시 쓰기가 옛 본문으로 되돌아간다.
"""

from __future__ import annotations

from repowiki.adapters.jobs import JobStore


def _store(tmp_path, job_id: str = "a") -> JobStore:
    store = JobStore(tmp_path / "jobs.sqlite")
    store.add(job_id, "x.md", "{}", "hash")
    return store


def test_a_finished_job_can_be_reopened_for_a_better_plan(tmp_path) -> None:
    """사실 층이 바뀌면 끝난 쪽도 다시 써야 한다. 세대를 올려야 저널이 가려진다.

    상태만 되돌리면 `recover`가 그 세대의 응답을 보고 곧바로 다시 끝냄으로 만든다.
    kafka 열 쪽을 근거 예산 수정 뒤에 다시 쓰려다 실제로 그렇게 막혔다(2026-09-10).
    """
    store = _store(tmp_path)
    job = store.lease("w1")
    assert job is not None
    store.journal("a", job.generation, "w1", "옛 본문")
    store.finish("a")
    assert store.state_of("a") == "done"

    generation = store.reopen("a")
    assert generation == job.generation + 1
    # 저널에 그 세대의 응답이 없으므로 `recover`가 되살리지 않는다.
    assert store.recover() == []
    again = store.lease("w2")
    assert again is not None and again.generation == generation
    # 옛 세대의 응답은 남아 있고 새 세대의 것은 아직 없다.
    assert store.response_of("a", job.generation) == "옛 본문"
    assert store.response_of("a", generation) is None


def test_reopening_without_bumping_the_generation_would_be_undone(tmp_path) -> None:
    """`recover`의 계약을 뒤집어 확인한다. 같은 세대의 응답이 있으면 끝냄으로 되돌린다.

    이것이 `reopen`이 세대를 올려야 하는 까닭이다.
    """
    store = _store(tmp_path)
    job = store.lease("w1")
    assert job is not None
    store.journal("a", job.generation, "w1", "본문")
    store.finish("a")

    with store._connect() as conn:  # noqa: SLF001 - 계약을 뒤집어 보는 검사다
        conn.execute("UPDATE jobs SET state = 'pending' WHERE id = 'a'")
    assert store.recover() == ["a"]
    assert store.state_of("a") == "done"
