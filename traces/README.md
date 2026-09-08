# traces/

실행 증거의 자리.

- `transitions.jsonl` — 전이 원장. `scripts/transition_ledger.py`가 수용 테스트
  결과를 acceptance 트리 해시와 함께 적재하고, 해시 변경을 동반한 실패→통과
  전이를 표시한다. **지우지 않는다** — 원장이다.
- `runs/` — 작업 실행 로그·트레이스 요약이 실제로 쌓일 때 개설.
