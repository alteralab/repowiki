"""페이지 작업 저장소. SQLite 하나가 작업과 응답 저널을 소유한다(PLAN §4).

경계 계약: 세션 드라이버는 `lease`로 작업을 받고 `submit`으로 결과를 낸다. 낡은 식별자,
소유자가 다른 제출, 중복 제출은 조용히 무시하지 않고 예외로 말한다(C-REPORT-2).

**응답 저널이 중복 호출을 막는 장치다.** 제출은 두 단계다. (1) `journal`이 응답을 먼저
확정하고 (2) `finish`가 작업을 끝낸다. 둘 사이에서 프로세스가 죽어도 `recover`가 저널의
응답으로 작업을 마치므로 LLM을 다시 부르지 않는다. 원격 호출과 로컬 확정은 원자적일 수
없으므로, 저널 기록 이전 구간의 중복은 이 장치로도 막지 못한다 — 그 사실을 여기 적는다
(C-GATE-2, C-REPORT-4).

사각: 잠금은 SQLite 트랜잭션이 준다. 여러 프로세스가 같은 파일을 열면 잠금 대기가 생기고,
그 대기 시간은 이 모듈이 재지 않는다.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from pydantic import BaseModel

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    page_path     TEXT NOT NULL,
    payload       TEXT NOT NULL,
    input_hash    TEXT NOT NULL,
    state         TEXT NOT NULL,
    generation    INTEGER NOT NULL DEFAULT 0,
    leased_by     TEXT,
    leased_at     REAL,
    attempts      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS journal (
    job_id     TEXT NOT NULL,
    generation INTEGER NOT NULL,
    response   TEXT NOT NULL,
    written_at REAL NOT NULL,
    PRIMARY KEY (job_id, generation)
);
"""

STATE_PENDING = "pending"
STATE_LEASED = "leased"
STATE_DONE = "done"


class JobError(RuntimeError):
    """작업 규약 위반. 낡은 식별자, 소유자 불일치, 중복 제출."""


class Job(BaseModel):
    """작업 하나. `generation`은 재시도마다 오른다 — 낡은 제출을 가리는 값이다."""

    id: str
    page_path: str
    payload: str
    input_hash: str
    generation: int
    attempts: int


class JobStore:
    """SQLite 작업 저장소. 경로 하나를 소유하고 그 파일만 만진다."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, isolation_level="IMMEDIATE")
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, job_id: str, page_path: str, payload: str, input_hash: str) -> None:
        """작업을 넣는다. 같은 식별자를 두 번 넣으면 예외다."""
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if existing is not None:
                raise JobError(f"이미 있는 작업이다: {job_id}")
            conn.execute(
                "INSERT INTO jobs (id, page_path, payload, input_hash, state) VALUES (?, ?, ?, ?, ?)",
                (job_id, page_path, payload, input_hash, STATE_PENDING),
            )

    def lease(self, worker: str) -> Job | None:
        """대기 중인 작업 하나를 빌린다. 없으면 `None`."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE state = ? ORDER BY id LIMIT 1", (STATE_PENDING,)
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE jobs SET state = ?, leased_by = ?, leased_at = ? WHERE id = ?",
                (STATE_LEASED, worker, time.time(), row["id"]),
            )
            return Job(
                id=row["id"],
                page_path=row["page_path"],
                payload=row["payload"],
                input_hash=row["input_hash"],
                generation=row["generation"],
                attempts=row["attempts"],
            )

    def journal(self, job_id: str, generation: int, worker: str, response: str) -> None:
        """응답을 먼저 확정한다. 이 시점 이후로는 LLM을 다시 부르지 않는다."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise JobError(f"없는 작업이다: {job_id}")
            if row["state"] == STATE_DONE:
                raise JobError(f"이미 끝난 작업이다: {job_id}")
            if row["generation"] != generation:
                raise JobError(
                    f"낡은 세대다: {job_id} 제출 {generation}, 현재 {row['generation']}"
                )
            if row["leased_by"] != worker:
                raise JobError(f"빌린 사람이 아니다: {job_id} 소유자 {row['leased_by']}")
            already = conn.execute(
                "SELECT job_id FROM journal WHERE job_id = ? AND generation = ?",
                (job_id, generation),
            ).fetchone()
            if already is not None:
                raise JobError(f"이미 제출된 응답이다: {job_id} 세대 {generation}")
            conn.execute(
                "INSERT INTO journal (job_id, generation, response, written_at) VALUES (?, ?, ?, ?)",
                (job_id, generation, response, time.time()),
            )

    def finish(self, job_id: str) -> None:
        """저널에 응답이 있는 작업을 끝낸다."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response FROM journal WHERE job_id = ? ORDER BY generation DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobError(f"저널에 응답이 없다: {job_id}")
            conn.execute("UPDATE jobs SET state = ? WHERE id = ?", (STATE_DONE, job_id))

    def reject(self, job_id: str, reason: str) -> int:
        """게이트 실패로 되돌린다. 세대를 올려 낡은 제출을 가린다."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise JobError(f"없는 작업이다: {job_id} ({reason})")
            generation = row["generation"] + 1
            conn.execute(
                "UPDATE jobs SET state = ?, generation = ?, attempts = attempts + 1,"
                " leased_by = NULL, leased_at = NULL WHERE id = ?",
                (STATE_PENDING, generation, job_id),
            )
            return generation

    def recover(self) -> list[str]:
        """저널에 응답이 있는데 끝나지 않은 작업을 마친다. 재개의 첫 동작이다."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT j.id FROM jobs j JOIN journal r ON r.job_id = j.id"
                " AND r.generation = j.generation WHERE j.state != ?",
                (STATE_DONE,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            for job_id in ids:
                conn.execute("UPDATE jobs SET state = ? WHERE id = ?", (STATE_DONE, job_id))
        return ids

    def response_of(self, job_id: str, generation: int | None = None) -> str | None:
        """저널에 확정된 응답. `generation`을 주면 그 세대의 것만 본다.

        세대를 지정하는 것이 기본 쓰임이다. 게이트 실패로 다시 쓸 때 옛 세대의 응답을
        재사용하면 재생성이 아니라 같은 본문의 반복이 된다.
        """
        with self._connect() as conn:
            if generation is None:
                row = conn.execute(
                    "SELECT response FROM journal WHERE job_id = ?"
                    " ORDER BY generation DESC LIMIT 1",
                    (job_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT response FROM journal WHERE job_id = ? AND generation = ?",
                    (job_id, generation),
                ).fetchone()
        return row["response"] if row is not None else None

    def counts(self) -> dict[str, int]:
        """상태별 작업 수. 진행 판정의 정본은 이 표다(C-REC-1)."""
        with self._connect() as conn:
            rows = conn.execute("SELECT state, COUNT(*) AS n FROM jobs GROUP BY state").fetchall()
        return {row["state"]: row["n"] for row in rows}

    def pending_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE state != ? ORDER BY id", (STATE_DONE,)
            ).fetchall()
        return [row["id"] for row in rows]
