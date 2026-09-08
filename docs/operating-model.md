# 운영 모델

한 작업의 수명 15단계다. 마지막 단계가 다음 작업의 시작을 강화하므로
사슬이 아니라 루프다.

| # | 단계 | 이 저장소에서 |
|---|---|---|
| 1 | 목표·제약·성공 기준 읽기 | `SPEC.md` |
| 2 | 최소 상시 지침 읽기 | `AGENTS.md` (CLAUDE.md 심링크로 자동 로드) |
| 3 | 현재 코드베이스 파악 | `repo-memory/quickstart.md` (= openwiki 출력) |
| 4 | 스킬 선택 | `skills/using-project-skills/` |
| 5 | 수직 슬라이스 분해 | 계획 단계 (전용 planner 에이전트는 미개설) |
| 6 | 근거 수집 | 소스·git·repo-memory·`.claims/` 앵커 |
| 7 | 최소 일관 변경 | 구현 — `tests/acceptance/` 봉인 하에 |
| 8 | tests 실행 | `scripts/gate_chain.sh` 1~5단계 |
| 9 | evals 실행 | `scripts/gate_chain.sh` 6단계 (`evals/run.sh`; 케이스 없으면 SKIP 표시) |
| 10 | 리뷰·감사 | 새 문맥 리뷰(반박 목표, 기준은 정확성·명시 요구사항 한정) → 사람 |
| 11 | 반복 실패 → 회귀 | `tests/regression/` (코드) · `evals/regression/` (에이전트 판단) |
| 12 | 학습 후보 → inbox | `memory/inbox/` |
| 13 | 큐레이터 승격 | `policies/memory-governance.md`의 3문 |
| 14 | repo-memory 갱신 | `openwiki --update` (repo-memory-maintenance 스킬) |
| 15 | 결정 기록 | `docs/decisions/` (첫 ADR 때 개설) |

루프 밖의 상시 규칙 하나: 게이트를 다 지난 산출물을 사람이 거절하면 사유를
`REJECTIONS.md`에 남기고, 같은 사유 3회에 게이트 승격을 판정한다.
