"""조율 하네스. SPEC SC-0.3의 세 시나리오를 재현한다.

이 검사들은 수용 층으로 올릴 후보다. 봉인 경로(`tests/acceptance`)의 변경은 사람 승인
단독 커밋만 허용하므로, 승인 전까지 회귀 층에 둔다.

시나리오 (a) 강제 종료 주입, (b) 순서 뒤섞인 재개와 낡은 제출, (c) 게이트 실패 루프.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repowiki.adapters.jobs import Job, JobError, JobStore
from repowiki.pipeline.graph import MAX_ATTEMPTS, GraphState, build_graph


def _store(tmp_path: Path, count: int = 3) -> JobStore:
    store = JobStore(tmp_path / "jobs.sqlite")
    for index in range(count):
        store.add(f"job-{index}", f"modules/m{index}.md", "facts", f"hash-{index}")
    return store


def _ok_gate(_body: str) -> tuple[bool, None]:
    return True, None


def test_crash_before_journal_may_call_again_but_loses_nothing(tmp_path: Path) -> None:
    """저널 기록 전에 죽으면 다시 부른다. 그 한계를 계약으로 고정한다."""
    store = _store(tmp_path, count=1)
    job = store.lease("w1")
    assert job is not None
    # 응답을 받았지만 저널을 쓰기 전에 프로세스가 죽었다고 본다.
    store.reject(job.id, "강제 종료")
    assert store.counts()["pending"] == 1
    assert store.response_of(job.id) is None


def test_crash_after_journal_does_not_call_again(tmp_path: Path) -> None:
    """저널에 응답이 있으면 재개는 그것으로 끝낸다 — 중복 호출 0."""
    store = _store(tmp_path, count=1)
    job = store.lease("w1")
    assert job is not None
    store.journal(job.id, job.generation, "w1", "본문")

    calls: list[str] = []

    def writer(target: Job) -> str:
        calls.append(target.id)
        return "다시 쓴 본문"

    graph, saver = build_graph(writer, _ok_gate, tmp_path / "checkpoint.sqlite")
    with saver as checkpointer:
        app = graph.compile(checkpointer=checkpointer)
        state = GraphState(repo="r", store_path=str(tmp_path / "jobs.sqlite"), worker="w1")
        result = app.invoke(state, {"configurable": {"thread_id": "t1"}})

    assert calls == []
    assert result["llm_calls"] == 0
    assert store.counts()["done"] == 1
    assert store.response_of("job-0") == "본문"


def test_resume_completes_every_page_exactly_once(tmp_path: Path) -> None:
    """강제 종료를 흉내 낸 뒤 재개하면 남은 페이지만 쓰고 누락이 없다."""
    store = _store(tmp_path, count=5)
    first = store.lease("w1")
    assert first is not None
    store.journal(first.id, first.generation, "w1", "본문-0")

    calls: list[str] = []

    def writer(job: Job) -> str:
        calls.append(job.id)
        return f"본문-{job.id}"

    graph, saver = build_graph(writer, _ok_gate, tmp_path / "checkpoint.sqlite")
    with saver as checkpointer:
        app = graph.compile(checkpointer=checkpointer)
        state = GraphState(repo="r", store_path=str(tmp_path / "jobs.sqlite"), worker="w1")
        result = app.invoke(state, {"configurable": {"thread_id": "t1"}})

    assert sorted(calls) == ["job-1", "job-2", "job-3", "job-4"]
    assert result["llm_calls"] == 4
    assert store.counts() == {"done": 5}
    assert store.pending_ids() == []


def test_stale_generation_and_foreign_worker_fail_loudly(tmp_path: Path) -> None:
    """낡은 세대, 다른 소유자, 중복 제출은 조용히 지나가지 않는다."""
    store = _store(tmp_path, count=1)
    job = store.lease("w1")
    assert job is not None
    new_generation = store.reject(job.id, "게이트 실패")
    again = store.lease("w2")
    assert again is not None
    assert again.generation == new_generation

    with pytest.raises(JobError, match="낡은 세대"):
        store.journal(job.id, job.generation, "w2", "낡은 응답")
    with pytest.raises(JobError, match="빌린 사람이 아니다"):
        store.journal(job.id, again.generation, "w1", "남의 응답")

    store.journal(job.id, again.generation, "w2", "본문")
    with pytest.raises(JobError, match="이미 제출된 응답"):
        store.journal(job.id, again.generation, "w2", "두 번째 제출")


def test_unknown_job_id_fails(tmp_path: Path) -> None:
    """없는 식별자로 제출하면 실패한다."""
    store = _store(tmp_path, count=1)
    with pytest.raises(JobError, match="없는 작업"):
        store.journal("job-없음", 0, "w1", "본문")


def test_gate_failure_loop_stops_at_limit(tmp_path: Path) -> None:
    """게이트가 계속 실패해도 상한에서 멈추고 사유를 남긴다."""
    store = _store(tmp_path, count=1)
    attempts: list[str] = []

    def writer(job: Job) -> str:
        attempts.append(job.id)
        return "나쁜 본문"

    def failing_gate(_body: str) -> tuple[bool, str]:
        return False, "인용 없음"

    graph, saver = build_graph(writer, failing_gate, tmp_path / "checkpoint.sqlite")
    with saver as checkpointer:
        app = graph.compile(checkpointer=checkpointer)
        state = GraphState(repo="r", store_path=str(tmp_path / "jobs.sqlite"), worker="w1")
        result = app.invoke(state, {"configurable": {"thread_id": "t1"}})

    assert len(attempts) == MAX_ATTEMPTS
    assert result["exhausted"] == ["job-0"]
    assert store.counts() == {"done": 1}


def test_source_read_failure_is_explicit(tmp_path: Path) -> None:
    """소스를 못 읽으면 줄 수 0으로 물러서지 않고 멈춘다."""
    from repowiki.analyze import domain
    from repowiki.pipeline.analyze_run import SourceReadError, _line_counts

    facts = domain.load()
    with pytest.raises(SourceReadError, match="없는파일.py"):
        _line_counts(tmp_path, ["없는파일.py"], facts)


def test_finished_job_is_not_resurrected_by_a_bad_submit(tmp_path: Path) -> None:
    """이미 끝난 작업을 되돌리지 않는다. 되돌리면 통과한 페이지가 취소된다."""
    store = _store(tmp_path, count=1)
    job = store.lease("w1")
    assert job is not None
    store.journal(job.id, job.generation, "w1", "본문")
    store.finish(job.id)
    with pytest.raises(JobError, match="이미 끝난 작업은 되돌리지 않는다"):
        store.reject(job.id, "게이트 실패")
    assert store.counts() == {"done": 1}
