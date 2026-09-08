"""git 이력 어댑터. 로그를 읽어 커밋과 바뀐 파일을 낸다(PLAN §2.9).

경계 계약: 읽기만 한다. 명령은 `git log --name-only --no-renames --since=<개월>.months`
하나이고 blobless 클론에서도 돈다(kafka 실측 0.3초). 줄 단위 churn은 이 명령으로 얻을 수
없다 — 그것은 풀 클론이 필요하고, air-gap 반입 조건에서 쓸 수 없다고 계획이 이미 판정했다.

사각: `--no-renames`라 파일을 옮기면 옛 경로와 새 경로가 서로 다른 엔티티로 세어진다.
그 사실은 페이지가 표기한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel

_SEPARATOR = "\x1e"
_FIELD = "|"


class Commit(BaseModel):
    """커밋 하나와 그 커밋이 바꾼 파일 목록."""

    sha: str
    date: str
    author: str
    subject: str
    paths: list[str]


class GitHistoryError(RuntimeError):
    """git 이력 읽기 실패."""


def read_log(root: Path, months: int) -> list[Commit]:
    """최근 `months`개월의 커밋을 낸다. 새 것이 앞이다."""
    pretty = f"{_SEPARATOR}%H{_FIELD}%ad{_FIELD}%an{_FIELD}%s"
    out = subprocess.run(  # noqa: S603
        [
            "git",
            "log",
            "--name-only",
            "--no-renames",
            f"--since={months}.months",
            f"--pretty=format:{pretty}",
            "--date=short",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise GitHistoryError(f"git log 종료 상태 {out.returncode}: {out.stderr.strip()[:300]}")
    return _parse(out.stdout)


def _parse(text: str) -> list[Commit]:
    """로그 원문을 커밋 목록으로 판다. 순수 함수라 픽스처로 시험한다."""
    commits: list[Commit] = []
    for chunk in text.split(_SEPARATOR):
        if not chunk.strip():
            continue
        head, _, body = chunk.partition("\n")
        fields = head.split(_FIELD, 3)
        if len(fields) != 4:
            continue
        paths = [line.strip() for line in body.splitlines() if line.strip()]
        commits.append(
            Commit(
                sha=fields[0], date=fields[1], author=fields[2], subject=fields[3], paths=paths
            )
        )
    return commits
