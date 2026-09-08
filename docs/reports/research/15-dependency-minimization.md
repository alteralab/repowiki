---
status: 실측 완료 (2026-09-09). uv 0.11.8 `pip compile`(linux x86_64, cp312), pip 26.2 `download --only-binary`, npm 10.9 `--package-lock-only`와 `npm ci`, ast-grep 0.45.3 kind 룰과 `outline`, dockerfile-parse 2.0.1, python-hcl2 8.1.4, PyPI JSON API, npm view, GitHub API. 원자료와 스크립트는 `15-scripts/`(요구 파일, 락, 휠 목록, ast-grep 룰과 샘플, heredoc 전처리). 라벨: [실측] 이 세션 로컬 실행, [웹] PyPI, npm, GitHub API, [대장] `docs/reference/dependency-docs.md` 인용, [unverified] 미측정
scope: PLAN.md 6판이 함의하는 모든 런타임 의존성(Python, 네이티브 휠, Node, 바이너리, 선택 항목, 테스트 전용)의 필요성 감사와 최소 집합 제안. 판정 기준은 목적(사람이 다이어그램으로 구조와 결합을 파악한다)과 하드 제약(air-gap, 줄 번호 인용, 증분 정확성)이다
---

# 15. 의존성 최소화 감사 (PLAN 6판)

## 0. 요약

사용자의 지침은 "좋아 보인다고 이것저것 섞으면 관리가 안 된다. 지속 가능한 시스템은 정말 필요한 것들로만 구성된다. 그러나 정말 써야 하는 도구는 쓴다"이다. 이 감사는 PLAN 6판이 함의하는 런타임 의존성 전부를 세고, 각 항목이 목적 또는 하드 제약에 닿는지, 이미 있는 것이나 표준 라이브러리가 대신할 수 있는지, 유지 위험이 얼마인지 실측으로 답한다.

핵심 수치 [실측]

| 측정 | 현행(PLAN 6판 함의) | 제안 최소 집합 | 차이 |
|---|---|---|---|
| Python 직접 의존 | 34 | 9 | -25 |
| Python 해석 패키지 수(linux x86_64, cp312) | 120 | 49 | -71 |
| 네이티브(플랫폼 특정) 휠 수 | 38 | 8 | -30 |
| 휠 총량(manylinux x86_64, cp312) | 153,520 KB (150 MB) | 42,624 KB (42 MB) | -111 MB |
| Node 락 패키지 수 | 161 | 153 | -8 |
| `node_modules` 크기 | 338,616 KB (331 MB) | 255,944 KB (250 MB) | -81 MB |
| 런타임 바이너리 | git, node, helm, kustomize, ast-grep(휠), cbm(조건부), tfparse(cffi+Go) | git, node, helm, kustomize, ast-grep(휠) | -2 |

판정 요약: 유지 9건(anthropic, ast-grep-cli, networkx, pydantic, PyYAML, python-hcl2, dockerfile-parse, mkdocs, mkdocs-material)과 Node 3건(mermaid 11.17.2, mermaid 11.13.0, jsdom), 바이너리 4건(git, node, helm, kustomize). 기존 것으로 교체 6건(LangGraph 스택, python-gitlab, typer+rich, jsonschema, tiktoken, tree-sitter 코어와 문법 휠 9종). 제거 7건(ast-grep-py, scikit-network 런타임 포함, mkdocs-llmstxt, mkdocs-panzoom-plugin, tree-sitter-hcl, tree-sitter-dockerfile, codelore). 스파이크 보류 4건(codebase-memory-mcp, tfparse, sigma+graphology, @mermaid-js/layout-elk). 테스트 전용으로 이동 4건(hanlint, zensical, scikit-network, code-maat).

tree-sitter 판정의 근거는 실측이다. ast-grep 0.45.3 kind 룰 16개로 Java와 Python 샘플에서 def 태그 21건과 ref 태그 32건을 range와 함께 뽑았다(§3). `outline`은 Java `record`를 빠뜨리고 Scala에서 빈 목록을 내므로 kind 룰이 정본이다.

## 1. 방법

1. PLAN 6판 §2.1, §2.7, §3, §5, §8과 대장(dependency-docs.md) "핀 정책"에서 런타임 의존성을 전수 추출했다. §11에서 v1 밖으로 낸 mcp, bm25s, kiwipiepy는 현행 집합에 넣지 않았다. 다만 §8 자산 manifest와 §10이 아직 "kiwipiepy 모델"과 "`repowiki query`(kiwipiepy 분절)"를 언급한다. 이 둘은 §11과 모순이므로 문구를 지워야 한다.
2. 현행 집합(A)과 제안 집합(B)을 각각 scratch `requirements.in`으로 만들고 `uv pip compile --python-version 3.12 --python-platform x86_64-manylinux_2_34`로 해석했다. 해석 결과 전부를 `pip download --only-binary=:all: --platform manylinux_2_34_x86_64 ... --python-version 3.12 --no-deps`로 받아 휠 수, 네이티브 휠 수, 총량을 쟀다. 두 집합 모두 sdist 없이 휠로만 받아졌다(air-gap 반입 가능).
3. 의존성 묶음(cluster)마다 단독 해석을 돌려 전이 의존 수와 네이티브 수, 휠 크기를 귀속시켰다(`15-scripts/clusters/`). 묶음끼리 겹치는 패키지(pydantic, httpx 계열, requests 계열)가 있으므로 묶음 합계는 전체보다 크다.
4. Node는 mermaid 두 판(11.17.2, GitLab 대상 11.13.0 alias)과 jsdom을 최소로, 거기에 sigma, graphology, @mermaid-js/layout-elk, hanlint를 더한 것을 현행으로 두고 `npm install --package-lock-only`와 `npm ci`로 패키지 수와 `node_modules` 크기를 쟀다.
5. ast-grep kind 룰로 def/ref 태그 추출을 Java와 Python 샘플에서 실행했고, python-hcl2 `parses_to_tree`와 ast-grep `hcl` 룰의 속성 스팬을 비교했으며, dockerfile-parse의 heredoc 동작을 확인했다.
6. 유지 위험은 대장을 우선 인용하고, 대장에 없는 패키지는 PyPI JSON API, npm view, GitHub API로 최신 판, 최근 12개월 릴리스 수, 라이선스, 기여자 분포를 확인했다.

## 2. 의존성별 판정

판정 기호: KEEP(필수), DROP(제거), REPLACE(기존 의존성 또는 표준 라이브러리로 교체), SPIKE(스파이크 통과 전에는 런타임에 넣지 않음), TEST(테스트 전용 이미지로 이동).

### 2.1 Python 런타임

| 이름 | 역할(계획 참조) | 필수 근거 또는 대체 | 유지 위험 | 판정 |
|---|---|---|---|---|
| anthropic 1.4.0 | LLM 호출, `count_tokens` 하드 게이트, Bedrock Mantle, structured outputs (§3, §4) | 목적의 LLM층 전체와 토큰 게이트 제약이 이 SDK 하나에 걸린다. 전이 15개, 네이티브 2개(pydantic-core, jiter), 4.6 MB [실측] | 1.0.0(2026-08-20) httpx2 전환과 파라미터 제거가 있었으나 MIGRATION.md가 있고 `adapters/llm.py` 하나가 소유한다 [대장] | KEEP |
| ast-grep-cli 0.45.3 | 심볼, import, 진입점, 타입 근사, HCL 속성 스팬 (§2.7, §3) | 결정층의 핵심 추출기이고 줄 번호 인용의 원천이다. 단일 휠 7.8 MB, 전이 0 [실측] | 릴리스 잦음(ast-grep-py 기준 12개월 22회)이나 룰 YAML과 `--json` 형식의 breaking은 확인되지 않음 [대장]. 골든 룰 테스트로 판 올림을 잡는다 | KEEP |
| ast-grep-py 0.45.3 | 대장 핀 목록에 있으나 계획 본문은 CLI `--json=stream`만 쓴다 | 같은 파서를 두 번 싣는다(네이티브 휠 5.2 MB 추가). 어댑터 하나가 subprocess로 CLI를 부르면 충분하다 | 12개월 22회 릴리스, PyO3 ABI 휠 | DROP |
| networkx 3.6.1 | PageRank, HITS, SCC, Louvain (§2.3 `FileRank`, `ModuleGraph`) | 순수 Python 2.0 MB, 전이 0. 표준 계산을 직접 짜지 않는다(C-LIB-1) | 3.6 breaking은 무관 함수뿐 [대장] | KEEP |
| pydantic 2.13.5 | 상태 타입, structured outputs 스키마, frontmatter 검증 (§2.1, §2.4) | anthropic이 이미 끌고 오므로 한계 비용 0 [실측 cluster] | 2.12, 2.13의 validator와 discriminator 변경 [대장]. 모델 정의는 `pipeline/`과 `gate/frontmatter`에 모인다 | KEEP |
| PyYAML 6.0.3 | `compose_all` 마크로 YAML 스팬 (§2.7) | 줄 번호 인용의 원천. C 확장은 선택이며 순수 로더로도 동작한다 | 안정 [대장] | KEEP |
| python-hcl2 8.1.4 | Terraform 블록과 속성 스팬, 값 (§2.7) | `parses_to_tree()` 블록과 속성에 `meta.line/end_line`이 있다. 샘플에서 속성 8건 스팬이 ast-grep `hcl` 룰과 동일했다(§3.3) [실측]. 값(모듈 source, backend)은 HCL 의미 파싱이 필요해 ast-grep으로는 대체 불가 | 12개월 7회 릴리스, 8.1.3에서 오류 없이 파싱되던 입력의 결과가 바뀜 [대장]. 골든 픽스처 필수 | KEEP |
| tree-sitter-hcl 1.2.0 | 속성 스팬 보조 (§2.7) | python-hcl2 `parses_to_tree`가 속성 스팬을 이미 준다. 필요하면 ast-grep 내장 `hcl`이 두 번째 원천이다 [실측] | 2025-06-16 이후 릴리스 0, `tree-sitter~=0.24` 선언인데 계획은 0.26 핀 [웹] | DROP |
| dockerfile-parse 2.0.1 | Dockerfile 명령과 줄 스팬 (§2.7) | 순수 Python, 전이 0. heredoc 본문을 명령으로 오인하는 결함이 있으나 37줄 전처리로 정확한 스팬을 얻었다(§3.4) [실측] | 2023-07-18 이후 릴리스 0, 사실상 동결 [대장]. 동결은 breaking 없음을 뜻하기도 한다 | KEEP (heredoc 전처리를 `adapters/dockerfile.py`에 둔다) |
| tree-sitter-dockerfile 0.2.0 | heredoc 실패 시 폴백 (§2.7) | 위 전처리가 폴백을 대신한다 [실측] | 릴리스 0, `tree-sitter~=0.21` 선언 [웹] | DROP |
| tree-sitter 0.26.0 + 문법 휠 7종 + `data/tags.scm/` | def/ref 태그(aider 방식) (§2.7, §3) | ast-grep kind 룰이 같은 def/ref 태그를 range와 함께 낸다(§3.1, §3.2) [실측]. 파서를 두 벌(ast-grep 내장 tree-sitter, py-tree-sitter) 싣는 이유가 없다. 네이티브 휠 10개, 2.3 MB 감소 | py-tree-sitter 0.25와 0.26에서 연속 API 제거 [대장]. 문법 휠은 `tree-sitter~=0.21/0.22` 코어 호환을 선언하는데 계획은 0.26 핀이라 ABI 검증이 매번 필요하다. java 0.23.5(2024-12-21)와 kotlin 1.1.0(2025-01-09)은 12개월 릴리스 0 [웹] | REPLACE (ast-grep kind 룰) |
| scikit-network 0.33.5 | Leiden 도전자 (§3) | 목적에는 서브시스템 분할 하나가 필요하고 Louvain이 그것이다. Leiden은 평가에서 비교할 도전자다. numpy+scipy 51 MB, 네이티브 3개 [실측] | 12개월 릴리스 2회, BSD [웹] | TEST (`evals/` extra) |
| typer 0.27.2 + rich 15.0.0 | CLI (§2.2 `cli.py`) | 명령은 `analyze, write, bundle, site, system, structure, read, job next/submit`이고 실패는 종료 상태로 말한다(C-REPORT-5). argparse 서브파서로 충분하다. 전이 7개 감소 | typer 0.22에서 0.27까지 breaking 5회 [대장] | REPLACE (argparse) |
| jsonschema | frontmatter JSON Schema 게이트 (§6) | pydantic 모델이 `.schema/frontmatter.json`을 `model_json_schema()`로 내고 같은 모델로 검증한다. 스키마 파일은 외부 CI용 산출물로 남는다. 전이 6개, 네이티브 1개(rpds-py) 감소 | 안정 [웹] | REPLACE (pydantic) |
| tiktoken 0.14.0 | P-C와 게이트웨이 차단 시 로컬 토큰 추정 (§3, §4, §8) | 하드 게이트는 `count_tokens`다. 로컬 추정이 쓰이는 곳은 `RepoProfile` 토큰 추정(비용 예측)과 `count_tokens` 불가 시 p95 게이트뿐이며, P-C에서는 LLM 생성 자체가 지원 범위 밖이다(§1 비목표). 보정표를 `claude/tiktoken` 비율 대신 콘텐츠 종류별 `chars/claude_token` p50, p95로 두면 tiktoken과 `o200k_base` 캐시 파일, `TIKTOKEN_CACHE_DIR`이 모두 사라진다. 네이티브 3개, 2.6 MB 감소 | 안정 [대장]. 다만 대장이 "Claude 4.7+ 과소 계산"을 기록했으므로 tiktoken 자체가 보정 없이는 쓸 수 없는 추정기다 | REPLACE (chars/token 보정표). Phase 0 보정 시 chars 기반 p95/p50 폭이 tiktoken 기반보다 10%p 넘게 넓으면 재검토 [unverified] |
| python-gitlab[graphql] 8.5.0 | 그룹 프로젝트 열거, MR 목록, 선택적 MR 생성 (§2.8, §2.9) | 필요한 호출은 REST 3종(`groups/:id/projects?include_subgroups=true`, `projects/:id/merge_requests`, MR 생성)이다. anthropic이 가져오는 httpx2로 80줄 안팎의 `adapters/gitlab.py`가 된다. 현행은 httpx 1.x + httpx2 두 스택과 requests, gql, graphql-core를 함께 싣는다(전이 18개, 네이티브 4개) [실측] | LGPL-3.0(SBOM 표시 대상), 8.0.0 GraphQL breaking [대장] | REPLACE (httpx2 어댑터). LGPL 항목이 SBOM에서 사라진다 |
| langgraph 1.2.11 + langgraph-checkpoint-sqlite 3.1.1 + langchain-core 1.6.2 | 조율 그래프, Send 팬아웃, interrupt, 체크포인트 (§2.1, §5 Phase 0) | 계약은 (1) 멱등 LLM 호출, (2) 재개 id 불일치 시 명시 실패, (3) SQLite 체크포인트, (4) 상한 있는 동시성과 재생성 루프 2회다. asyncio.Semaphore, sqlite3 jobs 표, pydantic으로 약 300줄이며 계획이 이미 그 러너를 명시한다. 스택은 전이 41개, 네이티브 10개, 13.3 MB이고 그중 langsmith(텔레메트리 클라이언트, 12개월 145회 릴리스), sqlite-vec(벡터 확장, 미사용), ormsgpack, xxhash, uuid-utils(12개월 19회), zstandard, websockets, orjson, httpx 1.x가 딸려온다 [실측, 웹]. `LANGSMITH_TRACING=false`를 진입점에서 고정해야 하는 것 자체가 변경 증폭이다 | 1.x는 하위 호환 명시 [대장]. 그러나 체크포인터 3.x breaking은 [unverified] | REPLACE (asyncio + sqlite3 러너). Phase 0 하네스 세 시나리오는 그대로 자작 러너의 수용 테스트로 쓴다. 동률 시 LangGraph라는 §5의 tie-break는 의존 41개 차이를 무시하므로 뒤집어야 한다 |
| mkdocs 1.6.1 + mkdocs-material 9.7.7 | `file://`로 여는 정적 사이트 (§2.4, §3, 리서치 13) | 목적의 읽기 표면이고 `file://` 통과는 실측된 둘 중 하나다. 전이 29개, 네이티브 4개, 27 MB(babel 10 MB 포함) [실측] | Material EOL 2026-11-05 [대장]. 어댑터 `bundle/site_nav.py` 하나로 격리하고 Zensical을 CI에서 병행 빌드한다 | KEEP |
| mkdocs-llmstxt 0.5.0 | 사이트에서 llms.txt 생성 | repowiki가 §1 목표 6으로 `llms.txt`와 `llms-full.txt`를 직접 낸다. 같은 파일을 두 번 만든다. 전이 11개(bs4, markdownify, mdformat) [실측] | 12개월 3회 [웹] | DROP |
| mkdocs-panzoom-plugin 0.5.2 | Mermaid SVG 팬과 줌 (§0 사이트 행) | 가독성 사다리 (c)가 "가로 스크롤 없음"을 보장하므로 줌 없이 읽히는 것이 게이트다. 편의 기능이다 | 2024-08 시작, 12개월 3회, 단일 유지자 [unverified] [웹] | DROP |
| zensical 0.0.60 | Material 후계 병행 빌드 (§3) | 런타임이 아니라 회귀 감시다. 네이티브 휠 14 MB, 0.0.x 주간 릴리스 | 1.0 전 breaking 상시 [대장] | TEST (CI 병행 빌드 job) |
| hanlint 0.0.10 | 한국어 산문 린트 3층 중 하나 (§2.6) | 계획이 이미 "규칙 4개 복사"와 "오탐 0 전까지 경고"로 강등했다. 복사한 4개 규칙은 `gate/prose.py`의 정규식이 되고, hanlint는 그 규칙의 출처와 대조용 오라클이다. 런타임에 실을 이유가 없다 | 2026-08-27 생성, 1★, 12일에 6회 릴리스, 라이선스 표현식 `MIT AND CC-BY-SA-4.0 AND LicenseRef-KOGL-Type-1` [대장]. CC BY-SA 데이터가 배포물에 섞이면 SBOM 검토 대상이다 | TEST (오라클) + 규칙 4개는 자체 정규식 |
| tfparse 0.6.21 | Terraform 평가 그래프 스파이크 (§2.7, §5 Phase 2b) | 계획이 이미 스파이크 조건부다. cffi + Go 공유 라이브러리 17 MB, 네이티브 2개 [실측] | 12개월 3회, Apache-2.0 [웹] | SPIKE (기본 락 밖, `[terraform-eval]` extra) |
| import-linter 2.15 | 계층 계약 (§2.2) | 개발 도구다. rich, click, grimp를 끌고 오지만 dev 그룹에 있다 | 12개월 13회 [웹] | KEEP (dev 그룹) |

### 2.2 네이티브 바이너리와 외부 도구

| 이름 | 역할 | 필수 근거 또는 대체 | 유지 위험 | 판정 |
|---|---|---|---|---|
| git | 클론, 이력 (§2.9) | 대체 없음. pygit2는 배제됐다 | 없음 | KEEP |
| node 22 | Mermaid 파서 게이트, 생성기 자산 빌드 (§1 제약) | Mermaid 문법 검증은 Mermaid 자신만 정확하다. mmdc는 Chromium이 필요해 기각됐다 | jsdom 30이 `^22.22.2`를 요구한다. 로컬 22.17.0에서도 `mermaid.parse`가 두 판 모두 동작했으나(§3.5) 이미지에는 22.22 이상을 박는다 [실측, 대장] | KEEP |
| helm 4.2.4 | 차트 렌더 (§2.7) | 렌더 없이는 Helm 레포의 객체와 엣지를 얻을 수 없다. 리서치 10의 119객체, 124엣지가 이 경로다 | Helm 4 메이저 [대장], 골든 렌더로 잡는다 | KEEP |
| kustomize 5.8.1 | overlay 빌드 (§2.7) | 위와 같다 | Helm 4 연동 변경 [대장] | KEEP |
| codebase-memory-mcp 0.10.8 | 타입 관계와 호출 엣지 (§2.3, §3) | 호출 엣지는 흐름 페이지 홉 정밀도에 닿으므로 목적과 관계있다. 그러나 계획이 이미 채택 조건(Jaccard 0.95, precision 0.85, recall 0.70)을 걸었고, 미채택 언어에서는 "정적 근사" 표기로 목적을 달성한다. 플랫폼별 38 MB 정적 바이너리 [웹] | MIT, 42.6k★, 2026-09-08 push. 릴리스 30회가 모두 12개월 안. 기여 분포 DeusData 1,638 대 차순위 53으로 bus factor 1 [웹] | SPIKE (테스트 이미지에서만 실행, `adapters/cbm.py` 하나로 격리, Phase 1 종료까지 미채택이면 계획에서 삭제) |
| tfparse 네이티브 | 위 표 참조 | | | SPIKE |
| code-maat 1.0.4 (Docker) | 이력 오라클 (§2.9) | 테스트 전용, 픽스처 CSV 1회 생성 | GPL-3.0, 배포 안 함 [대장] | TEST |
| codelore | 두 번째 이력 오라클 (§2.9) | 3★, GPL-3.0 [웹]. code-maat와 다를 때 사람이 판정해야 하므로 오라클이 늘수록 판정 비용만 는다. 목적 기여 없음 | 검증 안 된 신생 도구 | DROP |
| syft, cosign, podman | SBOM, 서명, `--network=none` 게이트 (§8) | CI 도구다 | 없음 | KEEP (CI 전용) |

### 2.3 Node

| 이름 | 역할 | 필수 근거 또는 대체 | 유지 위험 | 판정 |
|---|---|---|---|---|
| mermaid 11.17.2 | 사이트 벤더링과 파서 게이트 (§2.5) | 목적의 다이어그램 표면 | 11.13.0 라벨 파싱 수정 외 breaking 없음 [대장] | KEEP |
| mermaid 11.13.0 (`npm:mermaid@11.13.0` alias) | GitLab 저장소 뷰 판 파서 게이트 (§2.5) | 하드 제약(GitLab 렌더 동일성). 73 MB를 차지하지만 파서 게이트의 정본이다 [실측] | 대상 GitLab 판이 오르면 alias 하나만 바꾼다 | KEEP |
| jsdom 30.0.1 | Node에서 `mermaid.parse`용 DOM | 대체 없음(happy-dom은 미검증). 8.5 MB | Node 최소 판 상향 [대장] | KEEP |
| sigma 3.0.3 + graphology 0.26.0 | `graph.json` 대화형 페이지, 사다리 마지막 단 (§2.5) | 사다리 (a)(b)(c)를 dagre, ELK, 분할로 통과하면 필요 없다. 추가 패키지 6개, 4.3 MB [실측]. Phase 1의 4개 레포에서 마지막 단에 떨어지는 다이어그램이 하나도 없으면 목적에 기여하지 않는다 | sigma 12개월 15회, graphology 2025-01 이후 릴리스 0(정체) [웹] | SPIKE (Phase 1 사다리 결과로 결정) |
| @mermaid-js/layout-elk 0.2.3 + elkjs 0.12.0 | 사다리 두 번째 단 `layout: elk` (§2.5) | 첫 단(dagre) 실패 시에만 필요. `node_modules`에서 69.5 MB + 7.9 MB [실측] | elkjs 라이선스 `EPL-2.0 OR GPL-3.0-or-later` 이중 선택. SBOM에는 EPL-2.0으로 기록해야 §8 GPL 0건 규칙을 통과한다 [웹] | SPIKE (Phase 1 사다리 결과로 결정, 채택 시 SBOM 라이선스 선택 기록) |
| hanlint (npm) | Python 판과 중복 | 둘 중 하나도 런타임에 필요 없다(§2.1) | 위와 같다 | DROP |

### 2.4 계획에 남아 있는 잔여 언급

- §8 자산 manifest의 "kiwipiepy 모델", "임베딩 모델 revision"과 §10의 "`repowiki query`(kiwipiepy 분절)가 정본이다"는 §11(자체 검색 v1 밖)과 모순이다. 세 문구를 지운다.
- §8의 "tiktoken 캐시", "ormsgpack, xxhash, uuid-utils, sqlite-vec", "tfparse cffi", "sigma와 graphology", "tree-sitter 코어와 문법 휠 7종"은 위 판정에 따라 manifest에서 빠지거나 조건부로 옮긴다.
- §5 P-C의 환경 변수 `TIKTOKEN_CACHE_DIR`, `LANGSMITH_TRACING=false`는 사라지고 `REPOWIKI_TOKEN_GATE=local`만 남는다.

## 3. 실측 근거

### 3.1 ast-grep kind 룰로 def/ref 태그 (Java)

룰 16개(`15-scripts/astgrep-rules/`), 샘플 `OrderService.java`(30줄). `ast-grep scan --json=stream`에 `has: {field: name, kind: identifier, pattern: $NAME}`로 이름과 range를 함께 받는다. 출력 32건 중 발췌.

```
def.class      OrderService     L6-L26     ref.extends    BaseService      L6
def.field      repo             L7         ref.implements Runnable         L6
def.constructor OrderService    L10-L12    ref.implements AutoCloseable    L6
def.method     findOpen         L14-L18    ref.type       OrderRepository  L7, L10, L30
def.method     filterOpen       L20-L22    ref.call       findByCustomer   L15
def.method     run              L24        ref.call       check            L16
def.interface  Order            L28        ref.call       filterOpen       L17
def.enum       Status           L29        ref.new        Worker           L24
def.record     Worker           L30        ref.call       stream, filter, toList  L21
```

aider `java-tags.scm`이 내는 정의(class, interface, enum, method, constructor, field)와 참조(method_invocation, object_creation, superclass, super_interfaces, type_identifier)를 같은 이름과 줄로 얻는다. `outline --json=stream --items all`은 class, interface, enum과 멤버를 내지만 `record Worker`를 빠뜨리고 Java 멤버 `signature`가 비어 있다(리서치 02와 일치). 따라서 kind 룰이 정본이고 tree-sitter 두 번째 파서는 필요 없다.

### 3.2 같은 방식 (Python)

룰 5개, 샘플 `service.py`(25줄). 출력 21건.

```
def.class     OrderService   L5-L18    ref.extends  BaseService      L5
def.function  __init__       L8-L9     ref.type     OrderRepository  L8
def.function  find_open      L11-L14   ref.call     find_by_customer L12
def.function  close          L17-L18   ref.call     validate         L13
def.function  _filter_open   L20-L21   ref.call     Path, getcwd, exists  L18
def.function  main           L23-L25   ref.call     OrderService, OrderRepository  L24
```

`outline`도 Python은 class, field, method, function을 모두 냈다. Scala는 `outline`이 `items: []`를 내므로(§3.1과 같은 세션 실측) Scala는 kind 룰 경로만 있다.

### 3.3 HCL 속성 스팬: python-hcl2 대 ast-grep hcl

`main.tf`(20줄, backend, module, resource). `hcl2.parses_to_tree()`의 `block`과 `attribute` 노드 `meta.line/end_line`과 ast-grep `kind: attribute` 룰의 range가 8건 모두 같았다(bucket L3, key L4, source L9, version L10, cidr L11, ami L15, instance_type L16, tags L17-L19). tree-sitter-hcl이 더할 것이 없다.

### 3.4 Dockerfile heredoc

dockerfile-parse 2.0.1은 `RUN <<EOT ... EOT`의 본문 줄을 `APT-GET`, `EOT`, `KEY=VALUE`, `EOF2`라는 명령으로 오인한다 [실측]. 37줄짜리 전처리(`15-scripts/heredoc_prepass.py`)가 heredoc 본문을 소유 명령에 접고 원본 줄 번호를 되돌려 `RUN L3-L6`, `COPY L7-L9`, `RUN L10-L11`(줄 연속)을 정확히 냈다. 계획의 "heredoc 골든 케이스"는 이 전처리의 테스트가 되고 tree-sitter-dockerfile 폴백은 사라진다.

### 3.5 mermaid.parse 두 판 (jsdom, Node 22.17.0)

`mermaid@11.17.2`와 alias `mermaid-gitlab@npm:mermaid@11.13.0`을 같은 jsdom에서 초기화해 정상 flowchart는 `{"diagramType":"flowchart-v2"}`, 깨진 flowchart는 `suppressErrors: true`로 `false`를 두 판 모두 돌려줬다. 파서 게이트에 layout-elk는 필요 없다(렌더 전용).

### 3.6 Python 해석과 휠 측정

| 집합 | 직접 | 해석 | 네이티브 | 휠 총량 | 네이티브 목록 |
|---|---|---|---|---|---|
| A 현행 | 34 | 120 | 38 | 153,520 KB | ast_grep_cli, ast_grep_py, cffi, charset_normalizer, jiter, markupsafe, multidict, numpy, orjson, ormsgpack, propcache, pydantic_core, pyyaml, regex, rpds_py, scikit_network, scipy, sqlite_vec, tfparse, tiktoken, tomli, tree_sitter(코어 1 + 문법 9), uuid_utils, watchdog, websockets, xxhash, yarl, zensical, zstandard |
| B 최소 | 9 | 49 | 8 | 42,624 KB | ast_grep_cli, charset_normalizer, jiter, markupsafe, pydantic_core, pyyaml, regex, watchdog |

A에만 있는 71개: aiosqlite, annotated-doc, ast-grep-py, attrs, backoff, beautifulsoup4, cffi, deepmerge, distro, gql, graphql-core, hanlint, httpcore, httpx, jsonpatch, jsonpointer, jsonschema, jsonschema-specifications, langchain-core, langchain-protocol, langgraph, langgraph-checkpoint, langgraph-checkpoint-sqlite, langgraph-prebuilt, langgraph-sdk, langsmith, markdown-it-py, markdownify, mdformat, mdformat-tables, mdurl, mkdocs-llmstxt, mkdocs-panzoom-plugin, multidict, numpy, orjson, ormsgpack, propcache, pycparser, python-gitlab, referencing, requests-toolbelt, rich, rpds-py, scikit-network, scipy, shellingham, soupsieve, sqlite-vec, tenacity, tfparse, tiktoken, tomli, tree-sitter와 문법 9종, typer, uuid-utils, wcwidth, websockets, xxhash, yarl, zensical, zstandard. B에만 있는 것은 없다.

크기 상위: scipy 34.5 MB, tfparse 17.0 MB, numpy 16.3 MB, zensical 14.2 MB, babel 10.0 MB, mkdocs-material 9.1 MB, ast-grep-cli 7.8 MB, scikit-network 7.8 MB, zstandard 5.4 MB, ast-grep-py 5.2 MB.

묶음별 귀속(단독 해석, 겹침 포함)

| 묶음 | 해석 | 네이티브 | 휠 KB | 비고 |
|---|---|---|---|---|
| langgraph + checkpoint-sqlite + langchain-core | 41 | 10 | 13,277 | httpx 1.x와 httpx2 두 스택, langsmith, sqlite-vec 포함 |
| python-gitlab[graphql] | 18 | 4 | 1,931 | REST만이면 7, 1, 841 |
| typer + rich | 7 | 0 | 1,754 | |
| tree-sitter + 문법 9종 | 10 | 10 | 2,268 | 전부 네이티브 |
| scikit-network | 3 | 3 | 58,665 | numpy, scipy |
| tfparse | 3 | 2 | 17,261 | cffi |
| mkdocs-llmstxt | 11 | 0 | 683 | |
| zensical | 10 | 4 | 17,080 | |
| tiktoken | 7 | 3 | 2,602 | + `o200k_base` 캐시 파일 [unverified 크기] |
| jsonschema | 6 | 1 | 600 | rpds-py |
| mkdocs-panzoom-plugin | 17 | 3 | 5,519 | 거의 mkdocs 공유분, 플러그인 자체는 작다 |
| ast-grep-py | 1 | 1 | 5,161 | |
| anthropic | 15 | 2 | 4,614 | pydantic 포함 |
| mkdocs-material | 29 | 4 | 27,105 | babel 10 MB |
| python-hcl2 | 3 | 1 | 994 | lark, regex |
| networkx | 1 | 0 | 2,020 | |

### 3.7 Node 측정

| 집합 | 락 패키지 | 설치 package.json 수 | `node_modules` |
|---|---|---|---|
| 현행(mermaid 2판 + jsdom + sigma + graphology + layout-elk + hanlint) | 161 | 172 | 338,616 KB |
| 최소(mermaid 2판 + jsdom) | 153 | 160 | 255,944 KB |

차이 8개: @mermaid-js/layout-elk(69,464 KB), elkjs(7,864 KB), sigma(1,208 KB), graphology(2,724 KB), graphology-types, graphology-utils, events, hanlint(1,048 KB). 최소 집합 안에서는 mermaid 85,484 KB, mermaid 11.13.0 alias 72,584 KB, jsdom 8,544 KB가 대부분이다. 두 번째 Mermaid는 GitLab 렌더 동일성이라는 하드 제약의 비용이다.

## 4. 제안 최소 런타임 집합

Python 직접 의존 9개(`15-scripts/py-minimal/requirements.in`)

```
anthropic==1.4.0        # LLM, count_tokens, Bedrock Mantle
ast-grep-cli==0.45.3    # 심볼, import, 진입점, HCL 속성 스팬
networkx==3.6.1         # PageRank, HITS, SCC, Louvain
pydantic==2.13.5        # 상태, 출력 스키마, frontmatter
PyYAML==6.0.3           # compose_all 마크
python-hcl2==8.1.4      # Terraform 블록과 속성 스팬, 값
dockerfile-parse==2.0.1 # Dockerfile 스팬 (heredoc 전처리는 어댑터)
mkdocs==1.6.1           # 정적 사이트
mkdocs-material==9.7.7  # 정적 사이트 테마 (EOL 2026-11-05, 어댑터 격리)
```

표준 라이브러리가 맡는 것: argparse(CLI), asyncio와 sqlite3(러너, 체크포인트, jobs 표), hashlib(`PageInput` 해시), json, tomllib, subprocess(어댑터 안에서만), re(산문 정규식), difflib(충실성 diff).

네이티브 휠 8개(모두 위 9개의 전이): ast-grep-cli, pydantic-core, jiter, PyYAML, regex, markupsafe, watchdog, charset-normalizer.

Node 3개: mermaid 11.17.2, mermaid 11.13.0(alias), jsdom 30.0.1. Node 22.22 이상.

바이너리 4개: git, node, helm 4.2.4, kustomize 5.8.1(SHA256 고정).

테스트 전용 이미지 또는 dev 그룹(런타임 SBOM 밖): pytest, ruff, import-linter, code-maat(Docker, GPL), hanlint(오라클), zensical(병행 빌드), scikit-network(Leiden 도전자), syft, cosign, podman.

스파이크(통과 전에는 락과 manifest에 없음): codebase-memory-mcp(`adapters/cbm.py`), tfparse(`[terraform-eval]` extra), sigma+graphology(사다리 마지막 단), @mermaid-js/layout-elk(사다리 두 번째 단, SBOM에 EPL-2.0 선택 기록). LangGraph는 Phase 0 하네스의 도전자로만 남고 기본은 자작 러너다.

제거: ast-grep-py, tree-sitter와 문법 휠 9종, `data/tags.scm/`, tree-sitter-hcl, tree-sitter-dockerfile, typer, rich, jsonschema, tiktoken, python-gitlab, langgraph 스택, mkdocs-llmstxt, mkdocs-panzoom-plugin, hanlint(런타임), codelore.

## 5. 지속 가능성 규칙

1. 상한. 런타임 Python 직접 의존 10개 이하, Node 직접 의존 3개 이하, 바이너리 4개 이하, 네이티브 휠 10개 이하. 상한을 넘기는 추가는 같은 수만큼 제거를 동반한다.
2. 서드파티 하나에 어댑터 하나. `adapters/` 파일 목록이 곧 서드파티 목록이다(`llm.py`, `astgrep.py`, `git.py`, `helm.py`, `kustomize.py`, `gitlab.py`, `node.py`, `site.py`, `hcl.py`, `dockerfile.py`). `.importlinter`가 `adapters/` 밖의 `anthropic`, `subprocess`, `httpx2`, `mkdocs`, `hcl2`, `dockerfile_parse` 임포트를 막는다. 교체는 그 파일 하나를 바꾼다.
3. 파서는 한 벌. 코드 파싱은 ast-grep 내장 tree-sitter 하나다. 같은 문법의 두 번째 파서(py-tree-sitter, language-pack)는 넣지 않는다.
4. HTTP 스택은 한 벌. anthropic이 가져오는 httpx2가 유일한 클라이언트다. requests나 httpx 1.x를 요구하는 라이브러리는 그 자체로 추가 불가 사유다(mkdocs-material의 requests는 사이트 빌드 한정이며 런타임 코드가 임포트하지 않는다).
5. 추가 검사 목록(add-a-dep checklist). PR 본문에 여덟 항목을 적지 않으면 리뷰하지 않는다.
   1. 목적 문장 또는 하드 제약 중 어디에 닿는지 한 줄.
   2. 표준 라이브러리와 기존 의존성으로 해 본 결과(코드 줄 수와 실패 지점). 시도 없이 "편하다"는 사유는 반려.
   3. `uv pip compile` 전후 차이: 해석 수, 네이티브 수, 휠 KB(`15-scripts/clusters/` 방식).
   4. 유지 신호: 최신 판과 날짜, 12개월 릴리스 수, 상위 기여자 분포, SPDX 라이선스, 네이티브 여부, 12개월 breaking.
   5. 어댑터 파일 이름과 `.importlinter` 계약 갱신.
   6. 골든 테스트(판 올림 시 diff가 나는 출력)와 `--network none` 설치 확인.
   7. 퇴출 경로: 빼면 무엇이 바뀌는지, 대체가 무엇인지.
   8. `dependency-docs.md` 행과 락 변경을 같은 커밋에.
6. 판 올림은 한 패키지씩, 골든셋 재통과 뒤에만(대장 "올리는 방법" 유지).
7. 분기마다 이 감사를 다시 돌린다. `15-scripts/py-*/requirements.in`을 현재 락과 비교해 상한 초과와 미사용 의존(임포트 0건)을 `.report.json`이 아니라 RUNLOG에 남긴다.

## 6. 미검증과 한계

- chars/token 보정표가 tiktoken 기반 보정표보다 p95 폭이 넓은지 여부 [unverified]. Phase 0 보정에서 잰다. count_tokens가 하드 게이트이므로 이 폭은 비용 예측 정밀도에만 영향을 준다.
- ast-grep kind 룰의 태그 수가 aider `tags.scm`과 kafka, airflow 규모에서 동일한지는 샘플 2개로만 확인했다 [unverified 규모]. Phase 1 골든셋(레포당 30파일 사람 라벨)이 그 판정 자리다.
- codebase-memory-mcp의 오프라인 색인과 정밀도는 계획대로 스파이크 대상이며 이 감사는 크기와 기여 분포만 확인했다.
- mkdocs-panzoom-plugin 유지자 수는 PyPI 메타데이터만 보았다 [unverified].
- `o200k_base.tiktoken` 캐시 파일 크기는 재지 않았다(제거 대상이므로).
- 휠 측정은 linux x86_64 cp312 한 플랫폼이다. aarch64와 UBI9(glibc 2.34)는 같은 절차를 CI에서 돌린다.

## 7. 추가 측정: 최소 집합 + LangGraph

사용자가 조율기를 LangGraph로 확정했으므로(자작 러너 대신 프레임워크), §4의 최소 9개에 langgraph 1.2.11, langgraph-checkpoint-sqlite 3.1.1, langchain-core 1.6.2를 더한 집합 C를 같은 절차(uv pip compile, linux x86_64 manylinux_2_34, cp312, pip download --only-binary)로 쟀다. 원자료는 `15-scripts/py-minimal-langgraph/`(requirements.in, requirements.txt, wheels.tsv, lg_net_probe.py).

| 측정 [실측] | B 최소 | C 최소 + LangGraph | 차이 |
|---|---|---|---|
| 직접 의존 | 9 | 12 | +3 |
| 해석 패키지 | 49 | 72 | +23 |
| 네이티브 휠 | 8 | 15 | +7 |
| 휠 총량 | 42,624 KB | 51,464 KB (50 MB) | +8,840 KB |

C의 네이티브 휠 15개: ast_grep_cli, charset_normalizer, jiter, markupsafe, orjson, ormsgpack, pydantic_core, pyyaml, regex, sqlite_vec, uuid_utils, watchdog, websockets, xxhash, zstandard. B 대비 추가된 7개는 orjson, ormsgpack, sqlite_vec, uuid_utils, websockets, xxhash, zstandard이고 전부 LangGraph 스택의 전이다. 추가 23개 중 크기 상위는 zstandard 5,416 KB, orjson, websockets, uuid-utils 순이다.

(a) httpx 1.x와 httpx2의 공존 [실측]. 락에 `httpx==0.28.1`과 `httpx2==2.12.0`, `httpcore==1.0.9`와 `httpcore2==2.12.0`이 함께 들어간다. 배포 이름과 임포트 이름이 다르므로(`httpx`, `httpx2`) 해석 충돌은 없고 두 스택이 공존한다. httpx 0.28.1을 끄는 쪽은 langchain-core(`httpx<1.0.0,>=0.23.0`)와 langgraph-sdk(`httpx>=0.25.2`)이고, httpx2를 끄는 쪽은 anthropic과 langsmith(`httpx2<3,>=2`)다. 따라서 §5 규칙 4(HTTP 스택 한 벌)는 LangGraph 채택과 함께 "런타임 코드는 httpx2만 임포트한다. httpx 1.x는 langchain-core 전이로만 존재한다"로 고쳐 적는다.

(b) langsmith는 langchain-core의 하드 의존이다 [실측]. `langchain_core-1.6.2` METADATA의 `Requires-Dist: langsmith<1.0.0,>=0.3.45`에 extra나 marker가 없다. 제외할 수 있는 extra는 없고, langsmith가 다시 requests, requests-toolbelt, zstandard, websockets, xxhash, orjson, uuid-utils, distro, httpx2를 무조건 끈다. langsmith의 선택 extra(otel, pytest, vcr, 각종 에이전트 프레임워크)는 지정하지 않으면 설치되지 않으므로 OpenTelemetry는 락에 없다.

(c) sqlite-vec는 langgraph-checkpoint-sqlite 3.1.1의 하드 의존이다 [실측]. `Requires-Dist: sqlite-vec>=0.1.6`과 `aiosqlite>=0.20`, `langgraph-checkpoint<5.0.0,>=4.1.0`에 조건이 없다. 벡터 저장을 쓰지 않아도 네이티브 휠이 들어온다.

(d) 텔레메트리 차단과 임포트 시 네트워크 [실측]. 추적 여부는 `langsmith.utils.tracing_is_enabled()`가 정하고 순서는 (1) 컨텍스트 변수, (2) 진행 중인 run tree, (3) 전역 fallback(`langsmith.configure(enabled=False)`가 `_GLOBAL_TRACING_ENABLED`를 설정), (4) 환경 변수 `TRACING_V2` 또는 `TRACING`을 `LANGSMITH_`와 `LANGCHAIN_` 접두사로 읽어 값이 문자열 `true`일 때만 켜짐이다. 즉 `LANGSMITH_TRACING`, `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING_V2`, `LANGCHAIN_TRACING` 어느 것도 `true`가 아니면 꺼져 있고 기본값은 꺼짐이다. langgraph 자체가 읽는 환경 변수는 `LANGGRAPH_STRICT_MSGPACK`, `LANGGRAPH_DEFAULT_RECURSION_LIMIT`, `LANGGRAPH_DELTA_MAX_SUPERSTEPS_SINCE_SNAPSHOT`, `LANGGRAPH_AES_KEY` 넷뿐이며 텔레메트리 관련은 없다.

소켓 `connect`와 `getaddrinfo`를 막은 프로브(`lg_net_probe.py`, macOS arm64, 같은 판)로 langgraph, langchain_core, langsmith, SqliteSaver를 임포트하고 `StateGraph` + `SqliteSaver` + `interrupt` + `Command(resume=)` 왕복을 돌린 결과.

| 조건 | 임포트 시 네트워크 시도 | 실행과 1.5초 대기 후 시도 |
|---|---|---|
| 추적 변수 전부 미설정 | 0 (콜드 임포트 2.84초) | 0 |
| `LANGSMITH_TRACING=true` + API 키 (양성 대조) | 0 | 3 (`api.smith.langchain.com` getaddrinfo) |
| `LANGSMITH_TRACING=false` + API 키 | 0 | 0 |

결론: 임포트 시 네트워크 호출은 없고, 실행 시에도 추적 변수를 `true`로 두지 않는 한 호출이 없다. 계획의 `LANGSMITH_TRACING=false` 고정은 유효하며, 진입점에서 `langsmith.configure(enabled=False)`를 함께 호출하면 환경 변수 상속(CI, 개발자 셸의 `LANGCHAIN_TRACING_V2=true`)까지 막는다. P-C의 `.report.json` `network_calls: 0`은 그대로 최종 증거다. 프로브는 macOS에서 돌렸으므로 Linux 이미지 안에서의 동일 결과는 Phase 5 P-C 게이트가 확인한다 [unverified 플랫폼].

§4 제안 집합의 갱신: Python 직접 의존 12개(9 + LangGraph 3), 네이티브 휠 15개. §5 규칙 1의 상한은 "Python 직접 의존 12개 이하, 네이티브 휠 15개 이하"로 조정하고, 규칙 2의 어댑터 목록에 `pipeline/graph.py`가 LangGraph를 소유한다는 항목을 더한다(`adapters/` 밖에서 `langgraph` 임포트 금지는 §2.2 계약 그대로).
