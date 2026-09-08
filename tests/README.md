# tests/

세 구획의 지위가 다르다.

| 구획 | 지위 | 쓰기 권한 |
|---|---|---|
| `unit/` | 구현과 함께 진화하는 검사 | 자유 |
| `regression/` | 현재 동작을 기대값으로 굳힌 테스트(특성화·생성 테스트)의 자리. **보존용이지 수용 판정용이 아니다** — 기대값의 출처가 대상 자신이라 옳음을 증명하지 못한다 | 자유 (단, 수용 판정에서 제외) |
| `acceptance/` | SPEC 성공 기준에서 파생, **사람 승인분만**. 수용 판정은 이 구획만 센다 | **봉인** — 구현 중 읽기 전용. 변경은 사람 승인 단독 커밋(`ACCEPTANCE_UNSEAL=1`)만 |

봉인 강제: `.claude/settings.json`(세션) + `scripts/seal_check.sh`(커밋).
실행: `scripts/gate_chain.sh`. 결과 원장: `traces/transitions.jsonl`.
