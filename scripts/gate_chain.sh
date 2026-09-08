#!/usr/bin/env bash
# 게이트 체인 — 결정적 검사 전부가 LLM·사람 판정보다 먼저 돈다.
# 순서와 금지의 정본: docs/policies/quality-gates.md
#
# 도구는 프로젝트 가상환경(uv + uv.lock)에서 실행한다 — 전역 도구는 머신 간
# 재현이 안 된다. 도구가 없는 단계는 조용히 넘어가지 않고 SKIP을 크게 표시한다 —
# 돌지 않은 게이트는 지켜진다는 착각을 만든다.
set -uo pipefail

fail=0
step() { printf '\n=== [%s] %s ===\n' "$1" "$2"; }
skip() { printf '>>> SKIP: %s — %s\n' "$1" "$2"; }

if [ -f pyproject.toml ] && command -v uv >/dev/null 2>&1; then
  RUN="uv run --quiet"
else
  RUN=""
  echo ">>> 주의: uv 또는 pyproject.toml 미감지 — 전역 도구로 실행한다 (재현성 없음. scripts/tpl_init.sh를 밟으라)"
fi
has() { $RUN "$1" --version >/dev/null 2>&1; }

step 1 "생성 규약 + 봉인 (pre-commit)"
if has pre-commit; then
  $RUN pre-commit run --all-files || fail=1
else
  skip "pre-commit" "미설치 — uv sync 후 재시도"
fi

step 2 "단위 테스트"
if has pytest && [ -n "$(find tests/unit -name 'test_*.py' -o -name '*_test.py' 2>/dev/null | head -1)" ]; then
  $RUN pytest tests/unit -q || fail=1
else
  skip "tests/unit" "pytest 미설치 또는 테스트 없음"
fi

step 3 "회귀 테스트 (보존 신호 — 실패는 동작 변경의 표시)"
if has pytest && [ -n "$(find tests/regression -name 'test_*.py' -o -name '*_test.py' 2>/dev/null | head -1)" ]; then
  $RUN pytest tests/regression -q || fail=1
else
  skip "tests/regression" "테스트 없음"
fi

step 4 "수용 테스트 (수용 판정은 이 단계만 센다)"
if has pytest && [ -n "$(find tests/acceptance -name 'test_*.py' -o -name '*_test.py' 2>/dev/null | head -1)" ]; then
  mkdir -p traces
  $RUN pytest tests/acceptance -q --junitxml=traces/acceptance.xml || fail=1
  step 5 "전이 원장"
  python3 scripts/transition_ledger.py traces/acceptance.xml || fail=1
else
  skip "tests/acceptance" "테스트 없음 — SPEC 성공 기준이 아직 테스트로 파생되지 않았다"
fi

step 6 "에이전트 회귀 평가 (evals/regression — 통과율 ~100%)"
if [ -x evals/run.sh ]; then
  evals/run.sh || fail=1
elif [ -n "$(find evals/regression -type f ! -name '.gitkeep' 2>/dev/null | head -1)" ]; then
  echo ">>> FAIL: evals/regression 에 케이스가 있는데 러너(evals/run.sh)가 없다" >&2
  fail=1
else
  skip "evals/regression" "케이스 없음 — 첫 에이전트 실패 때 승격 (eval-driven-improvement 스킬)"
fi

step 7 "커버리지 (관문 아님 — 안 덮인 곳 목록이 리뷰 단서)"
if has pytest && $RUN python -c 'import pytest_cov' 2>/dev/null; then
  $RUN pytest tests/unit tests/regression -q --cov=src --cov-report=term-missing:skip-covered --no-header || true
else
  skip "coverage" "pytest-cov 미설치"
fi

step 8 "변경부 뮤테이션 (점수 관문 금지 — 살아남은 뮤턴트를 개별로 본다)"
if $RUN python -c 'import mutmut' 2>/dev/null; then
  echo "mutmut run 은 수동/야간 실행을 권장한다: $RUN mutmut run && $RUN mutmut results"
else
  skip "mutmut" "미설치 (선택 단계)"
fi

printf '\n'
if [ "$fail" -ne 0 ]; then
  echo "gate_chain: 실패한 게이트가 있다. 위 출력에서 확인하라." >&2
  exit 1
fi
echo "gate_chain: 결정적 게이트 통과. 다음 층: 새 문맥 리뷰(반박 목표), 그다음이 사람이다."
