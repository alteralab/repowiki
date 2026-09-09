"""SC-2b.2 수용 검사. Terraform 저장소에서 픽스처의 사실 16건을 모두 낸다.

이 파일은 봉인 경로에 있다. 구현 중에는 읽기 전용이고, 통과시키려고 여기를 고치지
않는다. 기대값이 명세와 어긋나 보이면 멈추고 사람에게 설명한다.

16건의 구성은 사람이 확정했다(2026-09-09).
  선언 7건  블록 종류 일곱이 각각 자리와 함께 나온다.
  엣지 6건  선언과 선언 사이의 관계 여섯이 나온다.
  계수 3건  엣지가 아닌 것이 조용히 사라지지 않는다.

행동 층위로 적는다. 입력은 `.tf` 파일 하나이고 관측하는 것은 `facts.terraform`이다.
어느 함수가 무엇을 돌려주는지는 여기서 말하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repowiki.pipeline.analyze_run import analyze_repo

FIXTURE = Path(__file__).parent / "fixtures" / "terraform"


@pytest.fixture(scope="module")
def terraform_facts(tmp_path_factory):
    """픽스처를 저장소 하나로 놓고 분석한다. git 저장소가 아니어도 분석은 돈다."""
    work = tmp_path_factory.mktemp("tf")
    (work / "main.tf").write_text(
        (FIXTURE / "main.tf").read_text(encoding="utf-8"), encoding="utf-8"
    )
    result = analyze_repo(work)
    facts = result.facts.terraform
    assert facts is not None, "Terraform 파일이 있는 저장소인데 terraform 사실이 없다"
    return facts


# --- 선언 7건 -------------------------------------------------------------

@pytest.mark.parametrize(
    ("kind", "address"),
    [
        ("provider", "provider.aws"),
        ("local", "local.name"),
        ("variable", "var.region"),
        ("module", "module.network"),
        ("resource", "aws_instance.web"),
        ("data", "data.aws_ami.ubuntu"),
        ("output", "output.web_ip"),
    ],
)
def test_each_block_kind_is_declared_with_its_address(terraform_facts, kind, address):
    """블록 종류 일곱이 각각 참조가 쓰는 주소 형태로 나온다."""
    found = [b for b in terraform_facts.blocks if b.address == address]
    assert len(found) == 1, f"{address} 선언이 {len(found)}건이다"
    assert found[0].kind == kind
    assert found[0].span.path == "main.tf"
    assert found[0].span.start_line >= 1


# --- 엣지 6건 -------------------------------------------------------------

@pytest.mark.parametrize(
    ("src", "kind", "dst"),
    [
        ("module.network", "source", "../modules/network"),
        ("module.network", "var", "var.cidr"),
        ("aws_instance.web", "data", "data.aws_ami.ubuntu"),
        ("aws_instance.web", "module", "module.network"),
        ("aws_instance.web", "var", "var.instance_type"),
        ("output.web_ip", "resource", "aws_instance.web"),
    ],
)
def test_declaration_to_declaration_edges(terraform_facts, src, kind, dst):
    """선언 하나가 다른 선언을 쓰는 자리가 엣지로 나온다."""
    found = [
        e for e in terraform_facts.edges if e.src == src and e.kind == kind and e.dst == dst
    ]
    assert found, f"{src} --{kind}--> {dst} 엣지가 없다"
    assert all(e.span.path == "main.tf" for e in found)


# --- 계수 3건 -------------------------------------------------------------

def test_loop_and_meta_names_are_not_edges(terraform_facts):
    """`count`, `each`, `path`는 선언이 아니다. 엣지로 내면 없는 결합을 그린다."""
    heads = {e.dst.split(".", 1)[0] for e in terraform_facts.edges if e.kind != "source"}
    assert not (heads & {"count", "each", "path", "self", "terraform"})
    assert any("선언이 아닌 머리" in note for note in terraform_facts.unresolved)


def test_references_that_reach_no_declaration_are_not_edges(terraform_facts):
    """`dynamic` 블록의 반복 이름처럼 선언에 닿지 않는 참조는 엣지가 아니다."""
    known = {b.address for b in terraform_facts.blocks}
    dangling = [e for e in terraform_facts.edges if e.kind != "source" and e.dst not in known]
    assert dangling == []
    assert any("선언에 닿지 않는 참조" in note for note in terraform_facts.unresolved)


# 픽스처가 담은 참조의 수. 사람이 파일을 읽고 센 값이다(2026-09-09).
#   var.region, var.cidr, data.aws_ami, var.instance_type, module.network,
#   var.count_hint, local.name, each.key, var.disks, ebs_block_device.value,
#   aws_instance.web
# 이 값을 구현이 낸 수에서 가져오면 검사가 자기 자신을 비교하게 된다.
REFERENCES_IN_FIXTURE = 11


def test_nothing_disappears_silently(terraform_facts):
    """엣지가 된 것과 계수로 남은 것의 합이 픽스처가 담은 참조 수와 같다.

    이것이 이 사실 층의 가장 중요한 계약이다. 못 푼 참조를 조용히 버리면 위키를 읽는
    사람은 그 저장소에 그런 관계가 없다고 읽는다(C-REPORT-2).
    """
    counted = sum(
        int(note.rsplit(" ", 1)[-1].removesuffix("건")) for note in terraform_facts.unresolved
    )
    references = [e for e in terraform_facts.edges if e.kind != "source"]
    assert counted > 0, "픽스처는 세어야 할 것을 일부러 담고 있다"
    assert len(references) + counted == REFERENCES_IN_FIXTURE
