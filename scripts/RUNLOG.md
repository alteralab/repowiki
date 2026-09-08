# 게이트 실행 기록

여기 없는 게이트는 돌지 않은 게이트다. 새 게이트를 넣는 커밋은 위반·무위반
표본에서 발화한 기록을 여기 함께 남긴다.

## 동봉 게이트의 완주 실적 (템플릿 출하 시점)

| 게이트 | 표본 | 결과 |
|---|---|---|
| `hooks/seal_acceptance.py` | acceptance 경로 쓰기 | 차단 (exit 2, 사유 stderr) ✅ |
| 〃 | src 경로 쓰기 | 통과 ✅ |
| 〃 | acceptance + `ACCEPTANCE_UNSEAL=1` | 통과 ✅ |
| `seal_check.sh` | src+acceptance 혼합 스테이징 | 실패 (exit 1) ✅ |
| 〃 | acceptance 단독 | 통과 ✅ |
| 〃 | 혼합 + UNSEAL | 통과 ✅ |
| `transition_ledger.py` | 최초 기록 (fail 1, pass 1) | 기록 ✅ |
| 〃 | acceptance 변경 + fail→pass | **flag 1건** ✅ |
| 〃 | 변경 없음 + 결과 동일 | flag 없음 ✅ |
| `gate_chain.sh` 6단계 (evals) | 케이스 없음 | SKIP 표시 ✅ |
| 〃 | 케이스 있음 + 러너 없음 | 실패 (exit 1) ✅ |
| 〃 | `evals/run.sh` 존재 | 실행 ✅ |

봉인을 `sealed_paths.txt` 단일 원천으로 개정한 뒤 재완주:

| 게이트 | 표본 | 결과 |
|---|---|---|
| `hooks/seal_acceptance.py` (개정판) | 봉인 경로 쓰기 | 차단 (exit 2) ✅ |
| 〃 | 비봉인 경로 · UNSEAL | 통과 ✅ |
| 〃 | 봉인 목록 부재 | **차단 (exit 2)** — 조용한 통과 금지 ✅ |
| `seal_check.sh` (개정판) | 혼합 · 단독 · UNSEAL | 실패/통과/통과 ✅ |
| 〃 | 봉인 목록 부재 | 실패 (exit 1) ✅ |

도구 로컬화(uv.lock·npx) 및 tpl_init 도입 뒤:

| 게이트/도구 | 표본 | 결과 |
|---|---|---|
| `tpl_init.sh` | 심링크 2개 고의 파손 + 신규 복사본 | git init·이름 치환·심링크 복구·uv.lock 생성·훅 설치 ✅ |

`tpl_init`을 파이썬 CLI(`tpl_init.py`, argparse·stdlib 전용)로 교체한 뒤 재완주 —
복사 단계 내장(.git·자기 자신 제외), 구판 sh 삭제:

| 표본 | 결과 |
|---|---|
| --help · 인자 부족 · 잘못된 이름 · 비어 있지 않은 대상 · 비템플릿 루트 | 각각 0·2·1·1·1 종료, 사유 출력 ✅ |
| 정상 경로 | 자기 자신 미복사·템플릿 이력 0커밋·심링크 보존·이름 치환·uv.lock·훅 설치, 첫 커밋 봉인 통과, gate_chain 완주 ✅ |
| `seal_check.sh` | 인스턴스 첫 커밋(.gitkeep 포함 전체) | .gitkeep 면제로 통과 ✅ — 면제 전에는 항상 실패했다 |
| `gate_chain.sh` (uv run 경유) | 초기화 직후 인스턴스 | pre-commit 통과, 나머지 SKIP 크게 표시 ✅ |
| altera-rules 자기 적용 | scripts/ 전체 (ruff base·shellcheck·ast-grep) | ruff·shellcheck 클린, ast-grep 매핑 오검출 2건 지목형 면제 ✅ |

비고: `gate_chain.sh`는 테스트 실물이 없는 상태에서는 완주할 수 없다 —
첫 수용 테스트를 세운 뒤 완주 기록을 여기 남기라.
`.claude/skills/`의 심링크 스킬이 Claude Code에서 자동 노출되는지는 첫 인스턴스
세션에서 확인하라(사용자 전역 스킬에서 검증된 패턴이나 프로젝트 층 완주 기록은
아직 없다) — 확인되면 이 줄을 지우고 결과를 남기라.
