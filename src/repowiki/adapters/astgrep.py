"""ast-grep CLI 어댑터. 이 파일이 ast-grep을 아는 유일한 자리다(PLAN §8 2).

경계 계약: `scan`은 저장소 경로를 받아 룰 매치를 스트림으로 낸다. 매치는 이름 붙은
형태(`AstMatch`)로만 나가고 사전형은 경계를 넘지 않는다(C-PY-1). ast-grep이 없거나
0이 아닌 상태로 끝나면 `AstGrepError`를 올린다 — 조용히 빈 결과를 내지 않는다(C-REPORT-2).

사각: 룰 파일의 문법 오류는 ast-grep이 stderr로만 말하므로 여기서 원문을 그대로
예외 메시지에 싣는다. 매치의 정확성은 이 어댑터가 판정하지 않는다(Phase 1 골든셋의 일).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel

RULES_CONFIG = Path(__file__).resolve().parent.parent / "data" / "sgconfig.yml"


class AstGrepError(RuntimeError):
    """ast-grep 실행 실패. 원문 stderr를 담는다."""


class AstMatch(BaseModel):
    """룰 매치 하나. 줄 번호는 1부터 세고 양 끝을 포함한다(ast-grep은 0부터 센다)."""

    rule_id: str
    message: str
    path: str
    start_line: int
    end_line: int
    text: str
    name: str | None = None


def _to_match(payload: dict, root: Path) -> AstMatch:
    rng = payload["range"]
    meta = payload.get("metaVariables", {}).get("single", {})
    name = meta.get("NAME", {}).get("text") if isinstance(meta, dict) else None
    path = Path(payload["file"])
    rel = path.relative_to(root) if path.is_absolute() else path
    return AstMatch(
        rule_id=payload["ruleId"],
        message=payload.get("message", payload["ruleId"]),
        path=rel.as_posix(),
        start_line=rng["start"]["line"] + 1,
        end_line=rng["end"]["line"] + 1,
        text=payload.get("text", ""),
        name=name,
    )


def scan(root: Path, targets: list[str] | None = None) -> Iterator[AstMatch]:
    """저장소를 훑어 룰 매치를 낸다.

    `targets`가 있으면 그 하위 경로만 본다. 반환은 지연 이터레이터라 대형 저장소에서도
    전체 매치를 메모리에 쌓지 않는다.
    """
    args = [
        "ast-grep",
        "scan",
        "--config",
        str(RULES_CONFIG),
        "--json=stream",
        *(targets or ["."]),
    ]
    proc = subprocess.Popen(  # noqa: S603
        args,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.stdout is None:  # pragma: no cover - Popen 계약상 발생하지 않는다
        raise AstGrepError("ast-grep stdout을 열지 못했다")
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        yield _to_match(json.loads(line), root)
    proc.wait()
    if proc.returncode != 0:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise AstGrepError(f"ast-grep 종료 상태 {proc.returncode}: {stderr.strip()}")


def version() -> str:
    """설치된 ast-grep 판. 분석기 판 해시(PLAN §2.9 항목 9)의 입력이다."""
    out = subprocess.run(  # noqa: S603
        ["ast-grep", "--version"], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()
