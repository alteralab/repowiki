---
status: 판정 완료 (2026-09-08) — 템플릿 실물 정독 기준 (agentic-project-tpl HEAD 0f5c6cb, 2026-08-30)
scope: repowiki를 agentic-project-tpl 위에 세울지의 이분법 판정
---

# agentic-project-tpl 채용 판정

**판정: 채용한다.** 부분 차용 없음 — 템플릿 전체를 `tpl_init.py`로 인스턴스화하고 그 운영 모델(15단계 루프)·게이트 체인·봉인·메모리 거버넌스를 그대로 따른다.

## 판정 근거 (현재형 사실)

| 템플릿이 요구하는 것 | repowiki의 실물 | 맞물림 |
|---|---|---|
| Python 프로젝트 (uv·uv.lock·ruff·pytest·pre-commit) | 결정층은 Python CLI (ast-grep·git·networkx·Anthropic SDK) | 그대로 맞는다 |
| altera-rules 표면 `common`·`lang/python`·`lang/bash` 상시 선언 | 사용자가 altera-rules 적용을 요구 — 같은 규약 저장소(rules-v0.10.0) | 선언 파일이 이미 있어 `/rules-install`이 실체화만 하면 된다 |
| 수용 테스트 봉인(`tests/acceptance` 읽기 전용, 사람 승인 단독 커밋) | 위키 생성기는 "생성물이 그럴듯하다"로 통과가 만들어지기 쉬운 부류 — 봉인이 정확히 그 경로를 닫는다 | 필요한 통제다 |
| `evals/regression` (에이전트 판단 회귀, 통과율 ~100%) | 생성 파이프라인의 LLM 단계(계획·페이지 작성·Mermaid 수리)는 에이전트 판단 결함이 코드 결함과 분리되어야 한다 | 템플릿의 evals 층이 그 자리다 (LEDGER식 근거율 측정도 여기 둔다) |
| `repo-memory/` → `openwiki/` (Node 22, npm 로컬 고정) | 개발 시점 도구이지 출하물이 아니다. 사내 반입 패키지에는 들어가지 않는다 | 개발 환경 요구(Node 22)는 이미 충족(node v22.17.0) |
| `docs/reports/research/`는 첫 리서치 보고 때 개설 | 리서치 보고 5편이 이미 있다 | 인스턴스화 직후 `docs/research/` → `docs/reports/research/`로 이동해 대장(repository-layout.md)에 맞춘다 |
| `memory/` 6구획, inbox 경유 승격 | Apache 레포 실측에서 나온 운영 지식(제외 글로브, 언어 서버 메모리)이 반복 재사용된다 | 승격 3문을 통과하는 항목이 실제로 생긴다 |

## 채용하지 않을 때 잃는 것

- 봉인·게이트 체인·전이 원장을 다시 짓게 된다 — 같은 지식의 두 번째 사본(C-DUP-2).
- 템플릿이 이미 openwiki를 repo-memory 생성기로 배선해 두었다. repowiki는 openwiki와 같은 문제를 푸는 도구라, 자기 저장소의 repo-memory를 openwiki로 만들어 두면 **Phase 3의 비교 대상(동일 저장소, 두 생성기)** 이 공짜로 생긴다.

## 비용과 처리

- `tpl_init.py`는 **대상 디렉토리가 비어 있어야** 한다(가드). 현재 `repowiki/docs/research/`가 있으므로: 리서치 파일을 임시로 옮기고 → 인스턴스화 → `docs/reports/research/`로 복귀. (PLAN Phase 0의 첫 절차)
- `altera-rules.yml`의 `rev: HEAD`는 인스턴스화 시 `rules-v0.10.0`으로 고정한다(템플릿 주석이 요구).
- 템플릿 RUNLOG가 미완인 항목 둘 — `gate_chain.sh` 완주(테스트 실물 필요), `.claude/skills/` 심링크 자동 노출 확인 — 은 repowiki가 첫 인스턴스로서 완주 기록을 남긴다.
- openwiki `--init`이 `CLAUDE.md` 심링크를 실파일로 덮는 문제는 템플릿 스킬(repo-memory-maintenance)이 복구 절차를 소유한다.

## 사각

- 템플릿은 2커밋·1주 된 초판이다. 그 자체의 결함은 repowiki 개발 중 발견되는 대로 템플릿 저장소로 되돌린다(템플릿 소유자는 사용자 본인). 이 프로젝트 안에서 템플릿 파일을 고치지 않는다 — 고치면 사본 드리프트다.
