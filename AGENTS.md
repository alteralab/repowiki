# AGENTS.md

이 파일은 항상 로드된다. 짧게 유지한다 — 절차는 `skills/`가 정본이고,
여기는 가리키기만 한다.

## 먼저 읽기

1. `SPEC.md` — 목표·제약·성공 기준.
2. `repo-memory/quickstart.md` (= `openwiki/quickstart.md`) — 현재 코드베이스.
   없으면 repo-memory-maintenance 스킬로 생성한다.
3. `skills/using-project-skills/SKILL.md` — 작업에 맞는 스킬 선택.
4. `docs/operating-model.md` — 한 작업의 수명 15단계. 작업은 이 루프를 따른다.

## 상시 규칙

- `tests/acceptance/`는 구현 중 **읽기 전용**이다. 테스트가 명세와 어긋나
  보이면 통과시키려고 코드를 깎지 말고, **멈추고 설명하라**.
- 정직하게 풀 수 없다고 판단되면 사람을 호출하고 종료하라.
- `repo-memory/`(openwiki 출력)는 생성물이다 — 손으로 고치지 않는다. 내용이
  틀렸으면 소스나 `openwiki/INSTRUCTIONS.md`를 고쳐 재생성한다.
- 병합 전 `scripts/gate_chain.sh` 통과. 게이트 정본: `docs/policies/quality-gates.md`.
- 게이트를 다 지난 산출물을 사람이 거절하면 사유를 `REJECTIONS.md`에 남긴다.

## 지식의 자리

- 승인된 인간 지식 → `docs/` · 코드베이스 사실 → `repo-memory/` ·
  큐레이션된 학습 → `memory/` (inbox 경유, `docs/policies/memory-governance.md`).
