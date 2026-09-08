"""git CLI 어댑터. 이 파일이 git을 아는 유일한 자리다(PLAN §8 2).

경계 계약: 읽기만 한다. 클론, 체크아웃, 커밋은 이 파일의 일이 아니다 — Phase 1의
분석은 이미 있는 작업본을 읽는다. git 저장소가 아니면 `head_sha`는 빈 문자열이고
`tracked_files`는 파일 시스템 훑기로 물러선다(그 사실을 반환값이 말한다).

사각: 서브모듈 안의 파일은 상위 저장소의 추적 목록에 없어 빠진다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel


class GitError(RuntimeError):
    """git 실행 실패."""


class RepoHead(BaseModel):
    """작업본의 현재 위치. `is_git`이 거짓이면 나머지 필드는 비어 있다."""

    is_git: bool
    head_sha: str = ""
    branch: str = ""


def _run(root: Path, args: list[str]) -> str:
    out = subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise GitError(f"git {' '.join(args)} 종료 상태 {out.returncode}: {out.stderr.strip()}")
    return out.stdout


def head(root: Path) -> RepoHead:
    """현재 커밋과 브랜치. git 저장소가 아니면 `is_git=False`를 낸다."""
    if not (root / ".git").exists():
        return RepoHead(is_git=False)
    sha = _run(root, ["rev-parse", "HEAD"]).strip()
    branch = _run(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    return RepoHead(is_git=True, head_sha=sha, branch=branch)


def tracked_files(root: Path) -> list[str]:
    """추적 파일 목록. git 저장소가 아니면 파일 시스템을 훑는다.

    반환 경로는 저장소 루트 기준 POSIX 상대 경로다.
    """
    if (root / ".git").exists():
        out = _run(root, ["ls-files", "-z"])
        return [p for p in out.split("\0") if p]
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
