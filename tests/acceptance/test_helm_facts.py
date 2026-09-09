"""SC-2b.1 수용 검사. Helm 저장소에서 색인된 선언과 참조가 픽스처와 같다.

이 파일은 봉인 경로에 있다. 구현 중에는 읽기 전용이고, 통과시키려고 여기를 고치지
않는다. 기대값이 명세와 어긋나 보이면 멈추고 사람에게 설명한다.

14건의 구성은 사람이 확정했다(2026-09-09).
  차트 메타 3건   name, version, appVersion 이 자리와 함께 나온다.
  의존 2건        Chart.yaml 의 dependencies 가 판과 저장소와 조건까지 나온다.
  values 키 3건   점 표기 경로와 값과 자리가 나온다.
  템플릿 참조 3건 템플릿의 `.Values.x.y`가 그 values 키에 이어진다.
  이미지 1건      repository 와 tag 를 짝지어 하나의 이미지로 낸다.
  계수 2건        선언되지 않은 values 키를 참조한 것이 엣지가 아니고, 자격증명 유사
                  키의 값이 산출물에 실리지 않는다(SC-2b.4).

렌더하지 않는다. 그 판단과 근거는 SPEC 의 SC-2b.1 이 담고 있다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from repowiki.pipeline.analyze_run import analyze_repo

FIXTURE = Path(__file__).parent / "fixtures" / "helm"


@pytest.fixture(scope="module")
def helm_facts(tmp_path_factory):
    """픽스처를 저장소 하나로 놓고 분석한다."""
    work = tmp_path_factory.mktemp("helm")
    shutil.copytree(FIXTURE, work, dirs_exist_ok=True)
    facts = analyze_repo(work).facts.helm
    assert facts is not None, "Chart.yaml 이 있는 저장소인데 helm 사실이 없다"
    return facts


def _chart(facts):
    assert len(facts.charts) == 1, f"차트가 {len(facts.charts)}개다"
    return facts.charts[0]


# --- 차트 메타 3건 ---------------------------------------------------------

@pytest.mark.parametrize(
    ("field", "value"),
    [("name", "mychart"), ("version", "1.2.3"), ("app_version", "v0.9.0")],
)
def test_chart_metadata_comes_with_its_place(helm_facts, field, value):
    chart = _chart(helm_facts)
    assert getattr(chart, field) == value
    assert chart.span.path == "mychart/Chart.yaml"
    assert chart.span.start_line >= 1


# --- 의존 2건 -------------------------------------------------------------

@pytest.mark.parametrize(
    ("name", "version", "condition"),
    [("redis", "18.1.0", ""), ("common", "2.x.x", "common.enabled")],
)
def test_chart_dependencies(helm_facts, name, version, condition):
    """의존은 차트 사이의 결합이다. 판과 저장소와 조건이 함께 있어야 뜻이 있다."""
    found = [d for d in helm_facts.dependencies if d.name == name]
    assert len(found) == 1, f"{name} 의존이 {len(found)}건이다"
    assert found[0].version == version
    assert found[0].condition == condition
    assert found[0].repository == "https://charts.bitnami.com/bitnami"
    assert found[0].span.path == "mychart/Chart.yaml"


# --- values 키 3건 --------------------------------------------------------

@pytest.mark.parametrize(
    ("key", "value"),
    [("image.repository", "nginx"), ("image.tag", "1.25"), ("service.port", "8080")],
)
def test_values_keys_are_dotted_paths_with_places(helm_facts, key, value):
    found = [v for v in helm_facts.values if v.key == key]
    assert len(found) == 1, f"{key} 가 {len(found)}건이다"
    assert found[0].value == value
    assert found[0].span.path == "mychart/values.yaml"


# --- 템플릿 참조 3건 -------------------------------------------------------

@pytest.mark.parametrize(
    "key", ["image.repository", "image.tag", "service.port"]
)
def test_templates_reference_values_keys(helm_facts, key):
    """이 값이 어디에 쓰이는가. 코드의 호출 그래프에 해당하는 자리다."""
    found = [u for u in helm_facts.uses if u.key == key]
    assert found, f"{key} 를 쓰는 템플릿이 없다"
    assert all(u.span.path == "mychart/templates/deployment.yaml" for u in found)


# --- 이미지 1건 -----------------------------------------------------------

def test_image_is_repository_and_tag_together(helm_facts):
    """이미지는 두 키가 짝을 이룬 것이다. 따로 두면 무엇이 실행되는지 안 보인다."""
    assert [(i.repository, i.tag) for i in helm_facts.images] == [("nginx", "1.25")]


# --- 계수 2건 -------------------------------------------------------------

def test_a_reference_to_an_undeclared_values_key_is_not_an_edge(helm_facts):
    """`.Values.notDeclared.anywhere`는 values.yaml 에 없다. 이으면 없는 것을 잇는 것이다."""
    declared = {v.key for v in helm_facts.values}
    assert [u.key for u in helm_facts.uses if u.key not in declared] == []
    assert any("선언되지 않은 values 키" in note for note in helm_facts.unresolved)


def test_credential_like_values_are_not_in_the_output(helm_facts):
    """SC-2b.4. 값이 있었다는 사실은 남기고 값은 지운다."""
    key = [v for v in helm_facts.values if v.key == "registryPassword"]
    assert key, "키 자체는 남아야 한다. 그 설정이 있다는 것이 사실이다"
    assert "s3cr3t-do-not-print" not in key[0].value
    assert key[0].value, "가렸다는 표시가 있어야 한다. 빈 값은 없었다는 뜻이 된다"


# 픽스처가 내야 하는 것의 전체 수. 사람이 산출을 열거해 확정했다(2026-09-10).
# 이름을 대는 검사만 있으면 군더더기가 들어와도 통과한다.
# `image`와 `service`는 안이 채워진 매핑이라 그 자체도 키다. 템플릿이 둘 다 쓴다.
TOTAL_CHARTS = 1
TOTAL_DEPENDENCIES = 2
TOTAL_VALUES = 6
TOTAL_USES = 3
TOTAL_IMAGES = 1


def test_the_fixture_yields_exactly_this_many_facts(helm_facts) -> None:
    """수가 늘면 없는 선언이나 없는 참조가 생긴 것이고, 줄면 사라진 것이다."""
    assert len(helm_facts.charts) == TOTAL_CHARTS
    assert len(helm_facts.dependencies) == TOTAL_DEPENDENCIES
    assert len(helm_facts.values) == TOTAL_VALUES
    assert len(helm_facts.uses) == TOTAL_USES
    assert len(helm_facts.images) == TOTAL_IMAGES


def test_no_two_values_share_a_key_in_one_chart(helm_facts) -> None:
    """한 차트 안에서 values 열쇠는 유일하다. 겹치면 참조가 어느 선언을 가리키는지 모른다."""
    seen = [(value.chart, value.key) for value in helm_facts.values]
    assert len(seen) == len(set(seen))
