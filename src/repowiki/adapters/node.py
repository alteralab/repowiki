"""Node 어댑터. Mermaid 파서 게이트를 부르는 유일한 자리다(PLAN §8 2).

경계 계약: `parse_diagrams`는 다이어그램 소스를 받아 판별로 통과 여부를 낸다.
Mermaid 문법의 정본은 Mermaid 자신이라 파싱을 흉내 내지 않는다(C-LIB-1).
Node나 자산이 없으면 `NodeError`를 올린다 — 통과로 물러서지 않는다(C-REPORT-2).

사각: `parse`는 문법 수용만 본다. 렌더 결과(SVG 생성, 라벨 보존)는 이 함수가 못 본다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel

SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "mermaid_parse.mjs"


class NodeError(RuntimeError):
    """Node 실행 실패."""


class ParseResult(BaseModel):
    """한 다이어그램에 대한 한 판의 판정."""

    id: str
    version: str
    ok: bool
    diagram_type: str | None = None
    error: str | None = None


class DiagramSource(BaseModel):
    """파싱할 소스 하나."""

    id: str
    source: str


def parse_diagrams(sources: list[DiagramSource], cwd: Path | None = None) -> list[ParseResult]:
    """Mermaid 두 판으로 소스를 파싱한다. 빈 입력이면 빈 목록을 낸다."""
    if not sources:
        return []
    payload = json.dumps([s.model_dump() for s in sources])
    root = cwd or SCRIPT.parent.parent
    if not SCRIPT.exists():
        raise NodeError(f"Mermaid 게이트 스크립트가 없다: {SCRIPT}")
    out = subprocess.run(  # noqa: S603
        ["node", str(SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    if out.returncode != 0:
        raise NodeError(f"node 종료 상태 {out.returncode}: {out.stderr.strip()[:400]}")
    return [ParseResult(**item) for item in json.loads(out.stdout)]
