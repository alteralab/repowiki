# agentic-project-tpl

에이전트와 함께 일하는 프로젝트의 시작 뼈대다. 핵심 원칙은 지식과 책임의 분리다 —
안정된 인간 지식(docs), 생성된 저장소 지식(repo-memory), 큐레이션된 운영 메모리(memory),
반복 워크플로(skills), 결정적 도구(scripts·tools), 품질 게이트(tests·evals)를 가른다.
여기에 LLM 생성 코드 검증 배선(수용 테스트 봉인·게이트 체인·원장)이 얹혀 있다.

전체 구조를 첫날 다 만들지 않는다 — 지금 쓰는 것만 개설되어 있고, 확장 자리와
개설 조건은 [repository-layout.md](docs/reference/repository-layout.md)가 소유한다.

## 인스턴스화 절차

```sh
# 1. 템플릿 루트에서 초기화 도구 하나로 끝낸다 (복사 포함)
cd ~/workspace/agentic-project-tpl
scripts/tpl_init.py ~/workspace/<프로젝트> <프로젝트명>
#   → 복사(.git·자기 자신 제외) · git init · 프로젝트명 치환 · 심링크 검증/복구
#     · uv sync(uv.lock 고정 — 커밋 대상) · pre-commit install. 남은 수동 단계도 출력.

# 2. SPEC.md 작성 — TODO 마커를 채운다. 목표·비목표·제약·성공 기준이 최소다.

# 3. 생성 규약 설치: Claude Code에서 /rules-install
#    (altera-rules.yml에 common·lang/python·lang/bash가 이미 선언돼 있다 —
#     동봉 도구가 그 표면의 적용 대상이다. 제품 언어 표면은 이때 추가)

# 4. repo-memory 생성 (Node.js 22+ — .nvmrc 참조)
npm install --save-dev openwiki   # 프로젝트 로컬 + package-lock.json에 버전 고정 — 커밋
npx openwiki --init               # 저장소 루트에 openwiki/ 생성 (repo-memory 심링크 대상)
```

도구는 전역 설치를 쓰지 않는다 — 파이썬 도구는 `uv.lock`, openwiki는
`package-lock.json`이 정확 버전을 고정하고, `gate_chain.sh`도 가상환경
(`uv run`)으로 실행한다. 다른 머신에서는 clone 후 `uv sync && npm ci`로 같은
도구 집합이 재현된다.

**openwiki --init 직후 반드시 할 것**: openwiki는 루트의 `AGENTS.md`·`CLAUDE.md`에 위키
포인터를 써넣는다. 이 템플릿의 `CLAUDE.md`는 `AGENTS.md`로의 심링크이므로,
openwiki가 이를 실파일로 덮어썼으면 내용을 `AGENTS.md`에 병합하고 심링크를 복구한다:
`ln -sf AGENTS.md CLAUDE.md`. 절차 정본은
[repo-memory-maintenance 스킬](skills/repo-memory-maintenance/SKILL.md).

## 무엇이 들어 있나

| 자리 | 역할 |
|---|---|
| `SPEC.md` | 목표·제약·성공 기준·품질 게이트. 프로젝트 헌법 |
| `AGENTS.md` (`CLAUDE.md`→심링크) | 상시 로드 진입점. 얇게 유지 — 절차는 스킬이 정본 |
| `docs/` | 사람이 승인한 안정 지식 (운영 모델·정책) |
| `repo-memory/` → `openwiki/` | 생성된 코드베이스 지식. openwiki가 만들고 갱신한다. **손편집 금지** |
| `skills/` | 반복 워크플로 6종 — 정본 (`.claude/skills/`는 자동 노출용 심링크) |
| `scripts/sealed_paths.txt` | 봉인 경로의 단일 원천 — 세션·커밋 훅이 함께 읽는다 |
| `.claude/settings.json` | 세션 봉인 훅 배선 (Claude Code 어댑터) |
| `scripts/` | 게이트 체인·봉인 검사·전이 원장 (결정적 도구) |
| `tests/` | `unit`(자유) · `regression`(보존용) · `acceptance`(사람 승인, 봉인) |
| `memory/` | 큐레이션 장기 메모리 — 6구획 상비, 쓰기는 inbox 경유만 |
| `evals/` | 에이전트 동작 검증 — `regression/` 상비, 통과율 ~100% 유지 |
| `tools/` `traces/` | README만 — 하위는 첫 실물이 생길 때 연다 |
| `REJECTIONS.md` | 게이트 통과 후 사람이 거절한 사유의 원장. 같은 사유 3회 → 게이트 후보 |

## 설계 원칙

- 결정적 게이트가 LLM·사람 판정보다 앞에 선다.
- 판정 근거(수용 테스트)는 에이전트의 쓰기 권한 밖에 둔다.
- 코드를 쓴 에이전트가 그 코드의 수용 판정 근거를 만들지 않는다.
- 커버리지·뮤테이션 절대 수치를 출하 관문으로 걸지 않는다.
- 반복 실패는 회귀로, 반복 거절 사유는 게이트로 승격한다.

근거와 금지의 정본: [docs/policies/quality-gates.md](docs/policies/quality-gates.md)
