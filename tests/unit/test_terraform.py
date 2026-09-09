"""Terraform 사실의 단위 검사.

여기서 고정하는 것은 소유자 판정이다. 참조가 어느 블록에 속하는지가 틀리면 위키가
블록 사이의 결합을 한 파일로 뭉쳐 보여 준다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from repowiki.pipeline.analyze_run import analyze_repo


def _facts(text: str):
    work = Path(tempfile.mkdtemp())
    (work / "main.tf").write_text(text, encoding="utf-8")
    return analyze_repo(work).facts.terraform


def test_a_block_without_an_address_still_owns_its_references() -> None:
    """`terraform`과 `moved` 같은 블록은 선언이 아니지만 그 안의 참조에 소유자가 있다.

    없으면 서로 다른 블록의 관계가 한 파일 노드로 뭉치고 블록 수준의 결합이 사라진다.
    """
    facts = _facts(
        'variable "x" { type = string }\n\n'
        "terraform {\n  experiments = [var.x]\n}\n"
    )
    edges = [(e.src, e.kind, e.dst) for e in facts.edges]
    assert ("terraform", "var", "var.x") in edges
    assert not [e for e in edges if e[0].endswith(".tf")]


def test_such_a_block_is_not_reported_as_a_declaration() -> None:
    """소유자일 뿐 선언이 아니다. 선언으로 내면 위키가 없는 선언을 있다고 말한다."""
    facts = _facts(
        'variable "x" { type = string }\n\n'
        "terraform {\n  experiments = [var.x]\n}\n"
    )
    assert [b.address for b in facts.blocks] == ["var.x"]


def test_a_labelled_owner_keeps_its_label() -> None:
    """`check "healthy"`와 `check "ready"`는 다른 자리다. 라벨이 그것을 가른다."""
    facts = _facts(
        'variable "x" { type = string }\n\n'
        'check "healthy" {\n  assert {\n    condition = var.x != ""\n'
        '    error_message = "bad"\n  }\n}\n'
    )
    assert [e.src for e in facts.edges] == ["check.healthy"]
