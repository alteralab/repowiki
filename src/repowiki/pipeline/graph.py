"""조율 그래프. 결정층과 LLM 층이 같은 상태 기계 안에 있다(PLAN §2.1).

경계 계약: `build_graph`는 페이지를 쓰는 호출자(`page_writer`)를 주입받아 그래프를 낸다
(C-STATE-3). 세션 드라이버는 `interrupt`를 쓰고 API 드라이버는 SDK를 부르지만, 둘 다
같은 상태 기계를 지난다 — 실행 모델이 하나여야 재개와 로그를 보는 자리가 하나다.

계약 넷(PLAN §2.1):
1. 페이지 호출은 응답 저널 뒤에 두어 재개가 다시 부르지 않는다(`adapters/jobs.py`).
2. 재개 식별자 불일치는 명시적 실패다.
3. 상태는 pydantic 타입, 체크포인트는 SQLite.
4. 게이트 실패 재생성은 2회까지다.

사각: 이 모듈은 조율만 본다. 페이지 내용의 옳고 바름은 게이트가 판정한다.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from repowiki.adapters.jobs import Job, JobStore

MAX_ATTEMPTS = 2


def silence_telemetry() -> None:
    """트레이싱 전송을 끈다. 진입점에서 한 번 부른다(PLAN §1 제약)."""
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


class PageResult(BaseModel):
    """한 페이지의 결과. 게이트 통과 여부와 사유를 함께 담는다."""

    job_id: str
    body: str
    passed: bool
    reason: str | None = None


class GraphState(BaseModel):
    """그래프 상태. 사전형이 아니라 이름 붙은 형태다(C-PY-1)."""

    repo: str
    store_path: str
    worker: str = "session"
    results: list[PageResult] = Field(default_factory=list)
    exhausted: list[str] = Field(default_factory=list)
    llm_calls: int = 0


PageWriter = Callable[[Job], str]
PageGate = Callable[[str], tuple[bool, str | None]]


def _run_one(store: JobStore, job: Job, writer: PageWriter, gate: PageGate, worker: str) -> PageResult:
    """작업 하나를 쓴다. 저널을 먼저 쓰고 그다음에 끝낸다."""
    body = store.response_of(job.id, job.generation)
    if body is None:
        body = writer(job)
        store.journal(job.id, job.generation, worker, body)
    store.finish(job.id)
    passed, reason = gate(body)
    return PageResult(job_id=job.id, body=body, passed=passed, reason=reason)


def build_graph(
    writer: PageWriter,
    gate: PageGate,
    checkpoint_path: Path,
):
    """상태 기계를 만든다. 체크포인터는 SQLite 파일 하나가 소유한다."""
    silence_telemetry()

    def write_pages(state: GraphState) -> dict:
        store = JobStore(Path(state.store_path))
        store.recover()
        results = list(state.results)
        exhausted = list(state.exhausted)
        calls = state.llm_calls
        while True:
            job = store.lease(state.worker)
            if job is None:
                break
            had_response = store.response_of(job.id, job.generation) is not None
            result = _run_one(store, job, writer, gate, state.worker)
            if not had_response:
                calls += 1
            if result.passed:
                results.append(result)
                continue
            if job.attempts + 1 >= MAX_ATTEMPTS:
                exhausted.append(job.id)
                results.append(result)
                continue
            store.reject(job.id, result.reason or "게이트 실패")
        return {"results": results, "exhausted": exhausted, "llm_calls": calls}

    graph = StateGraph(GraphState)
    graph.add_node("write_pages", write_pages)
    graph.add_edge(START, "write_pages")
    graph.add_edge("write_pages", END)

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    saver = SqliteSaver.from_conn_string(str(checkpoint_path))
    return graph, saver
