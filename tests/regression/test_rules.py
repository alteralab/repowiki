"""룰이 무엇을 잡고 무엇을 안 잡는지 고정한다.

룰 파일은 데이터라 단위 검사로 감쌀 수 없다. 실제 ast-grep을 픽스처에 돌려 기대값을
줄 번호로 못 박는다. 룰을 넓히거나 좁히면 이 검사가 먼저 깨진다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repowiki.adapters.astgrep import scan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _messages(relative: str) -> list[tuple[str, int]]:
    root = FIXTURES.parent.parent
    target = (FIXTURES / relative).relative_to(root).as_posix()
    return sorted((m.message, m.start_line) for m in scan(root, [target]))


@pytest.fixture(scope="module")
def python_matches() -> list[tuple[str, int]]:
    return _messages("python/decorators.py")


def test_route_decorators_are_entry_points(python_matches: list[tuple[str, int]]) -> None:
    """`@app.get`과 `@router.post`는 라우트 진입점이다."""
    entries = [line for message, line in python_matches if message == "entry.decorator"]
    assert entries == [9, 14]


def test_argument_call_is_not_an_entry_point(python_matches: list[tuple[str, int]]) -> None:
    """인자 안의 `.get(`은 라우트가 아니다. 데코레이터의 호출 대상만 본다."""
    entries = [line for message, line in python_matches if message == "entry.decorator"]
    assert 19 not in entries
    assert 24 not in entries
