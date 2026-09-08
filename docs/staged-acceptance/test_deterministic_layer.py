"""SPEC 성공 기준의 수용 판정. 기준 하나에 검사 하나로 대응한다.

이 층은 봉인 경로다. 구현 세션은 여기를 고치지 못하고, 변경은 사람 승인 단독 커밋으로만
들어온다. 검사는 명령 층에서 관측 가능한 것만 본다 — 내부 함수를 부르지 않는다.

픽스처는 `tests/fixtures/sample-repo`다. 다른 기계에서도 같은 결과가 나와야 하므로 큰
저장소를 쓰지 않는다. 그 저장소들에서의 실측은 `scripts/RUNLOG.md`가 기록한다.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "sample-repo"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _analyze(out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "repowiki.cli", "analyze", str(FIXTURE), "--out", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def facts(tmp_path_factory: pytest.TempPathFactory) -> dict:
    out = tmp_path_factory.mktemp("facts")
    result = _analyze(out)
    assert result.returncode == 0, result.stderr
    return json.loads((out / "facts.json").read_text(encoding="utf-8"))


def test_sc_1_1_analysis_finishes_with_status_zero(facts: dict) -> None:
    """SC-1.1 분석이 종료 상태 0으로 끝나고 사실을 낸다."""
    assert facts["profile"]["kind"] == "code"
    assert {m["id"] for m in facts["modules"]} == {"core", "clients", "pysvc"}


def test_sc_1_1_import_forms_resolve_to_the_declaring_module(facts: dict) -> None:
    """SC-1.1 평범한 임포트, 중첩 타입 임포트, 정적 임포트가 모두 선언 모듈에 닿는다.

    픽스처의 `core`는 `clients`를 세 형태로 임포트한다. 하나라도 놓치면 가중치가 준다.
    """
    edges = {(e["src"], e["dst"]): e["weight"] for e in facts["module_edges"]}
    assert edges == {("core", "clients"): 3}


def test_sc_1_1_external_import_makes_no_edge(facts: dict) -> None:
    """SC-1.1 저장소가 선언하지 않은 이름(`java.util.List`)은 엣지를 만들지 않는다."""
    names = {e["dst"] for e in facts["type_edges"]}
    assert "List" not in names


def test_sc_1_1_entry_points_exclude_argument_calls(facts: dict) -> None:
    """SC-1.1 라우트 데코레이터만 진입점이다. 인자 안의 호출은 아니다."""
    kinds = [e["kind"] for e in facts["entry_points"]]
    assert kinds == ["route"]


def test_sc_1_3_partition_is_deterministic(tmp_path: Path) -> None:
    """SC-1.3 같은 입력을 두 번 분석하면 사실이 바이트까지 같다."""
    first, second = tmp_path / "a", tmp_path / "b"
    assert _analyze(first).returncode == 0
    assert _analyze(second).returncode == 0
    digest_a = hashlib.sha256((first / "facts.json").read_bytes()).hexdigest()
    digest_b = hashlib.sha256((second / "facts.json").read_bytes()).hexdigest()
    assert digest_a == digest_b


def test_sc_1_5_every_diagram_passes_both_mermaid_parsers(facts: dict) -> None:
    """SC-1.5 모든 다이어그램이 사이트 판과 GitLab 판 파서를 통과한다."""
    payload = json.dumps([{"id": d["id"], "source": d["source"]} for d in facts["diagrams"]])
    result = subprocess.run(  # noqa: S603
        ["node", str(ROOT / "tools" / "mermaid_parse.mjs")],
        input=payload,
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    verdicts = json.loads(result.stdout)
    assert [v for v in verdicts if not v["ok"]] == []
    assert len(verdicts) == 2 * len(facts["diagrams"])


def test_sc_1_5_diagrams_stay_within_gitlab_limits(facts: dict) -> None:
    """SC-1.5 페이지당 소스 2,000자 이하, 50블록 이하."""
    assert len(facts["diagrams"]) <= 50
    for diagram in facts["diagrams"]:
        assert len(diagram["source"]) <= 2000, diagram["id"]


def test_sc_1_6_ladder_passes_for_every_structure_diagram(facts: dict, tmp_path: Path) -> None:
    """SC-1.6 L0과 L1이 1440px에서 교차 10 이하, 라벨 잘림 0, 가로 스크롤 없음."""
    if not CHROME.exists():
        pytest.skip("Chrome이 없다. 사다리 측정은 실제 렌더가 필요하다")
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts), encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "evals" / "ladder" / "measure.py"), str(facts_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "다음 단으로 갈 것 0개" in result.stdout, result.stdout


def test_sc_1_7_every_fact_carries_an_existing_span(facts: dict, tmp_path: Path) -> None:
    """SC-1.7 근거 span이 실재한다. 위반은 명령이 종료 상태로 말한다."""
    result = _analyze(tmp_path / "out")
    assert result.returncode == 0
    assert "근거 위반 0건" in result.stdout
    for symbol in facts["symbols"]:
        assert (FIXTURE / symbol["span"]["path"]).exists()


def test_sc_0_5_dependency_caps_hold() -> None:
    """SC-0.5 의존 상한 검사가 종료 상태 0으로 끝난다."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "depcheck.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sc_1_2_python_declarations_match_the_standard_library_oracle() -> None:
    """SC-1.2 파이썬 선언 추출이 표준 라이브러리 `ast`와 일치한다."""
    script = ROOT / "evals" / "oracles" / "python_ast_oracle.py"
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), str(FIXTURE), "10", "42"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "precision 1.0000" in result.stdout
    assert "recall 1.0000" in result.stdout


def test_sc_0_1_rule_surfaces_match_the_declaration() -> None:
    """SC-0.1 규약 표면 선언과 실체가 일치한다."""
    installer = Path.home() / "workspace" / "altera-rules" / "scripts" / "install_surfaces.py"
    if not installer.exists():
        pytest.skip("규약 저장소가 이 기계에 없다")
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(installer), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
