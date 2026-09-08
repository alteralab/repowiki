# repowiki PLAN

> 상태: **초안 4판**, 작성 2026-09-09. 3판(`docs/plan-history/PLAN-v3.md`)에 incumbent 편향 감사(리서치 14, 30개 항목)와 의존 문서 대장(`docs/reference/dependency-docs.md`)을 반영했다. "3판과 같다"는 절은 그 파일의 같은 번호 절을 가리킨다. 사이트 생성기 행은 재검증(리서치 13) 결과가 올 때까지 잠정이다. 근거는 리서치 `01–14`(현재 `docs/research/`, Phase 0 뒤 `docs/reports/research/`). 라벨: [실측] 이 세션의 로컬 실행, [코드] 대상 저장소 정독, [웹] 문서와 이슈, [it] syntopicon KB, [문면] 벤더 문서, [14] 편향 감사 판정.
> 진행 상태는 이 문서가 적지 않는다. 정본은 `scripts/gate_chain.sh` 출력과 `tests/acceptance/` 통과 여부, 게이트 완주 기록은 `scripts/RUNLOG.md`다(C-REC-1).

## 0. 한 줄 정의와 판정

**repowiki**는 GitLab 그룹 또는 저장소 URL을 받아 레포 종류(코드, Helm, Terraform, k8s, CI)를 가리고, 모듈 분해, 모듈과 타입 수준의 결합, 진입점과 교차 모듈 흐름, 변경 핫스팟, 레포 사이의 관계(시스템 그래프)를 결정적으로 추출한 뒤, LLM이 그 사실 위에서만 Markdown+Mermaid 위키를 쓰게 하는 Python CLI다. 목적은 하나다. **새 코드베이스(레포 하나 또는 여럿으로 된 시스템)를 처음 보는 사람이 다이어그램으로 구조와 결합을 파악한다.** 1차 대상은 Apache 오픈소스(레포 4개 + SkyWalking 13개 레포 시스템), 2차 대상은 사내 self-hosted GitLab 프로젝트 20개(오프라인 반입).

| 판정 | 결론 | 근거 |
|---|---|---|
| `agentic-project-tpl` | **채용** (전체) | 리서치 04 |
| OKF | **repowiki OKF 호환 프로필**: 필수 `type` + 고정 `title/description/tags/generated/sources/status` + `verified`, `stale_after`; 프론트매터 JSON Schema로 CI 검증 | 리서치 03, [14] |
| altera-rules | **적용**: `rev: rules-v0.10.0`, 표면 `common`, `lang/python`, `lang/bash`, `review` | 규약 저장소 정독 |
| 조율 | **LangGraph 잠정 유지, Phase 0에서 측정 게이트**: kill -9 재개, 다중 interrupt 순서 뒤섞임, 게이트 루프의 3시나리오 하네스로 자작 러너(asyncio + SQLite jobs + Pydantic, 약 300줄)와 비교한다. 조용한 페이지 누락이나 LLM 재실행이 있으면 교체 | syntopicon 재감사, [14] #8 |
| 다이어그램 | **Mermaid 11 유지**, 게이트에 GitLab의 실제 한도(페이지당 소스 2,000자, 50블록) 추가, 노드 상한은 교차 수와 문자 수 실측으로 확정, ELK는 선택 프로필, D2와 대화형 뷰어는 같은 그래프 JSON의 2차 산출 | [14] #1, #2 |
| 심볼, 타입, 호출 | ast-grep 0.45.3 kind 룰 유지(`outline`과 동수 검증), 문법은 언어별 휠 벤더링, 호출 엣지는 codebase-memory-mcp 스파이크(정밀도 ≥0.85면 채택) | [14] #3 |
| 랭킹, 서브시스템 | PageRank(권위 축) + 역방향 PageRank/HITS(허브 축), RRF 융합; 서브시스템은 빌드 트리 우선, 초과 그룹만 networkx Louvain + 비연결 분할 + 허브 고정, scikit-network Leiden은 도전자. **networkx Leiden은 CPU에 없다** | [14] #4, #5 |
| 이력 | git CLI 유지, `-c core.commitGraph=false` 삭제, blobless에서는 핫스팟 = 수정 횟수, 오라클은 code-maat(Docker 테스트 전용) + codelore | [14] #6 |
| 토큰 | `count_tokens`가 예산 계기이자 하드 게이트, tiktoken은 모델×콘텐츠별 보정표(p95)로만 | [14] #7 |
| 산문 | fluent-korean 조항(프롬프트) + 자체 정규식 + hanlint(강등, 30문장 픽스처 오탐 0일 때만 차단) | [14] #10 |
| 사이트 | **잠정**: 읽기 UX 1순위 재검증(리서치 13) 결과로 확정. 콘텐츠는 생성기 독립(Markdown + fence + frontmatter + 상대 링크) | 리서치 11, 13 |
| 설정, 인프라 레포 | Serena와 ast-grep이 아니다. PyYAML `compose_all`(줄 번호), Helm `helm template` + `# Source:` 매핑, Terraform은 python-hcl2 `parses_to_tree`/`hq` + tfparse, Dockerfile은 dockerfile-parse, properties는 자체 파서 | 리서치 10, [14] #12 |
| 멀티 레포 | `SystemGraph`: 다섯 증거 계열, span 없는 엣지 금지 | 리서치 12 |
| 2차 질의 | **1차 인터페이스 = CLI(`repowiki query`, `structure`, `read`) + `SKILL.md` + `AGENTS.md`**, MCP는 `mcp==2.2.0` `MCPServer` stdio로 2차. 검색은 bm25s 기본, 하이브리드(KURE-v2 벤더링)는 50문항 qrels에서 R@5 +0.08 이상일 때만 | [14] #11, #15 |
| 시크릿 | `.netrc`가 아니다. `GIT_ASKPASS` + 환경 변수, 가능하면 credential helper | [14] #17a |
| v1 밖 | Claims 사이드카, 이력 LLM 요약, 소유권과 릴리스 페이지, DeepWiki 비교와 LEDGER, Serena/LSP, Vale, D2 출력, 사이트 내 Ask 서비스 | §11 |

## 1. 목표, 비목표, 제약 (SPEC.md의 원천)
3판과 같다. 추가: 목표 3의 인용 게이트는 span 실재뿐 아니라 **줄 번호를 주는 파서**를 전제한다(§2.7). 제약에 "GPL 라이브러리는 동봉하지 않는다(leidenalg, igraph, infomap, graph-tool, code-maat 소스). 테스트 전용 Docker 실행만 허용"을 더한다.

## 2. 아키텍처

### 2.1 그래프 하나, 노드는 얇다
3판의 도해와 같다(결정층 노드 4개, LLM 노드 2개, 게이트와 번들). 조율 프레임워크는 §0의 측정 게이트를 통과한 쪽이다. 어느 쪽이든 지켜야 할 계약: (1) `write_page`의 LLM 호출은 interrupt 뒤에 두거나 멱등이어야 한다(LangGraph interrupt는 노드를 처음부터 재실행한다). (2) 재개 id 불일치는 조용히 무시되지 않고 실패해야 한다(langgraph #8836). (3) `LANGSMITH_TRACING=false`를 진입점에서 고정한다. (4) 동봉 네이티브 휠은 `ormsgpack`, `xxhash`, `uuid-utils`, `sqlite-vec` 넷이다.

### 2.2 계층과 경계 계약
3판과 같다. `adapters/`에 `cbm`(codebase-memory-mcp subprocess, 스파이크 통과 시)과 `tfparse`가 추가된다.

### 2.3 데이터 모델
3판과 같다. 바뀐 것:
- `TypeGraph`: 기본은 ast-grep 정적 근사. codebase-memory-mcp 스파이크가 통과하면 INHERITS/IMPLEMENTS/CALLS 엣지를 이 모델에 채우고 `resolution: static|cbm` 필드로 출처를 남긴다.
- `FileRank`: `authority`(PageRank, aider 승수), `hub`(역방향 PageRank 또는 HITS), `fused`(RRF k=60). churn은 융합하지 않고 다이어그램 시각 채널로만 쓴다.
- `ModuleGraph.subsystems`: `source: build-tree|louvain|sknetwork-leiden|instructions`를 기록한다.
- 모든 facts의 span은 파서가 준 줄 번호에서만 나온다. YAML은 `compose_all` 노드 마크, HCL은 `parses_to_tree` 블록 메타 또는 tree-sitter-hcl, properties는 자체 파서, Dockerfile은 `structure.startline/endline`.
- `TokenCalibration`: 모델 id × 콘텐츠 종류별 `claude/tiktoken` p50과 p95 비율. `data/calibration.json`으로 벤더링.

### 2.4 출력 번들
3판과 같다. 추가: `.schema/frontmatter.json`(CI 검증), 선택 `wiki.base`(Obsidian Bases), 채택 생성기의 nav 파일 자동 생성, `llms-full.txt`는 상한(2 MB)을 두고 초과 시 섹션별 분할. 정적 사이트에는 같은 검증 그래프 JSON을 읽는 **대화형 그래프 페이지 하나**(sigma 3 + graphology, 벤더링 약 30 kB)를 둔다. GitLab과 GitHub Markdown 안에서는 스크립트가 돌지 않으므로 그곳의 1차 산출은 여전히 정적 Mermaid다.

### 2.5 다이어그램
- 소스 언어는 Mermaid 11 다섯 종(flowchart, classDiagram, sequenceDiagram, stateDiagram-v2, erDiagram) + timeline. 게이트는 jsdom `mermaid.parse`다(Langium 파서 `@mermaid-js/parser`는 이 다섯 종을 다루지 않는다).
- **GitLab 실제 한도를 게이트에 넣는다**: 페이지당 Mermaid 소스 2,000자, 50블록 초과 시 클릭 렌더로 바뀐다. 검증은 대상 GitLab이 번들한 판(18.11–19.3은 11.13.0, 19.4+는 11.16.1)과 최신 11.17.2 둘 다로 돌린다.
- 노드 상한 15/25는 2025–26 연구 근거가 없다. Phase 1에서 4개 레포의 L1마다 문자 수와 교차 수(dagre vs ELK)를 재서 상한을 확정한다. `layout: elk`는 GitLab 19.2+와 정적 사이트(로더 벤더링)에서만 선택 프로필이다.
- LLM은 라벨과 그룹 이름만 제안한다(3판과 같다).

### 2.6 산문 규범
3판과 같되 hanlint를 강등한다. 세 층: fluent-korean 핵심 조항(프롬프트), 자체 정규식(엠대시, 이모지, 이중 피동, 명사형 종결), hanlint 0.0.10(버전 핀, 규칙 4개를 복사해 fork-ready). hanlint는 30문장 픽스처(번역투 10, 정상 10, 식별자 포함 10)에서 오탐 0일 때만 차단 규칙이 되고, 그전에는 경고다. arm64 import 테스트를 둔다(kiwipiepy CoNg 커널은 x86-64 전용).

### 2.7 레포 종류와 분석기
3판의 감지 규칙은 같다. 파서가 바뀐다.

| kind | 파서 | span 출처 | 하지 않는 것 |
|---|---|---|---|
| YAML 전반(Chart, values, k8s, kustomize, CI) | PyYAML 6.0.3 **`compose_all`**(`CSafeLoader`) | 노드 `start_mark`/`end_mark` | `safe_load_all`(마크를 버린다) |
| Helm 렌더 | `helm template`(v3.22 또는 v4.3 계열 확인 후 핀) → 원문에서 `# Source: <chart>/templates/<file>`를 먼저 파싱 → `compose_all` | 템플릿 파일(키 grep 스팬) + `values.yaml` 스팬. 렌더 사실은 `rendered: true` 표시 | 템플릿에 ast-grep, 렌더 줄→템플릿 줄 매핑(존재하지 않는다) |
| Terraform | python-hcl2 8.1.4 `parses_to_tree()`(블록 `meta.line/end_line`) 또는 `hq --with-location`; 속성 스팬은 tree-sitter-hcl/ast-grep hcl; 평가 그래프(count/for_each, 모듈 소스)는 **tfparse 0.6.21**(`allow_downloads=False`) 스파이크 통과 시 | 위 | `hcl2.load(with_meta=True)`(8.x에서 no-op, 이슈 #291), `terraform graph` |
| Dockerfile | dockerfile-parse 2.0.1(`structure.startline/endline`) + heredoc 골든 케이스; 실패 시 tree-sitter-dockerfile | 위 | ast-grep |
| `.properties` | 자체 40줄 파서(`key, value, line`, 연속 줄 처리) | 위 | jproperties(줄 정보 없음) |
| Spring 설정 조인 | ast-grep java `@ConfigurationProperties` + 위 파서 | 위 |, |
| code | ast-grep 0.45.3 kind 룰(`outline`과 ±2% 동수면 outline으로 교체), tree-sitter 0.26 API(`Query(lang, src)`, `QueryCursor`) + 언어별 휠(java 0.23.5, python 0.25.0, typescript 0.23.2, go 0.25.0, javascript 0.25.0, kotlin 1.1.0, scala 0.26.2) + aider `tags.scm` 벤더링 | ast-grep range | tree-sitter-language-pack(지연 다운로드, ABI 불일치 위험) |

게이트: `InfraGraph`와 `ConfigSurface`의 모든 사실은 `path:Lx-Ly`를 갖거나 `rendered: true`여야 한다.

### 2.8 시스템 수준
3판과 같다.

### 2.9 갱신과 이력
3판과 같되 명령에서 `-c core.commitGraph=false`를 뺀다. blobless 클론에서 핫스팟은 수정 횟수 기준이고, 줄 단위 churn은 풀 클론이거나 상위 20개 파일을 `git backfill`(2.54+ 경로 인자)한 경우에만 낸다. `--no-renames`가 개명된 파일의 이력을 둘로 가른다는 한계를 페이지에 표기한다. 오라클: code-maat v1.0.4를 Docker에서 정확한 기본값(`--min-revs 5 --min-shared-revs 5 --min-coupling 30 --max-changeset-size 30`, coupling = shared/avg(revs))으로 풀 클론에서 1회 돌려 픽스처 CSV를 커밋하고, codelore를 2차 오라클로 둔다.

### 2.10 2차 질의
- **1차 인터페이스는 CLI + 스킬**: `repowiki structure`, `repowiki read <page>`, `repowiki query <text>`와 `skills/repowiki/SKILL.md`, `AGENTS.md` 관리 블록. Bash가 되는 에이전트(Claude Code, Codex, Cursor)에서 컨텍스트 비용이 0에 가깝다.
- **MCP는 2차**: `mcp==2.2.0`의 `MCPServer`(스펙 2026-07-28), stdio, 같은 세 연산. `FastMCP`는 SDK 2.x에서 제거됐다.
- 검색: bm25s 0.3.11 + kiwipiepy 분절이 기본. Phase 4에서 50문항 한국어 qrels(개념 25, 식별자 25)로 R@5와 MRR을 재고, 하이브리드(KURE-v2 2026-08-17 또는 bge-m3 벤더링, RRF)는 개념 문항 R@5가 +0.08 이상 오르고 식별자 문항이 후퇴하지 않을 때만 채택한다. 그 전에 SQLite FTS5 trigram을 세 번째 lexical 다리로 시험한다.

## 3. 기술 스택 선정 (버전은 `docs/reference/dependency-docs.md`와 락 파일이 정본)

| 역할 | 채택 | 감사 판정 [14] | 결정 측정 |
|---|---|---|---|
| 심볼, import, 진입점 | ast-grep-cli 0.45.3 kind 룰 | KEEP, `outline` 재측정 | 3개 레포 동수 ±2% |
| 타입 관계, 호출 엣지 | ast-grep 정적 근사 → codebase-memory-mcp 0.10.8(MIT, 단일 C 바이너리, SQLite) 스파이크 | RE-MEASURE | kafka 오프라인 색인, 호출 지점 200개 vs scip-java 0.13 정답, 정밀도 ≥0.85 |
| def/ref 태그 | tree-sitter 0.26 + 언어별 휠 7종 + `tags.scm` | REPLACE(문법 출처) | kafka와 airflow 태그 수 동일, `--network none` 설치 |
| 랭킹 | PageRank 권위 + 역PageRank/HITS 허브, RRF | KEEP+ | 문서화된 모듈 목록 대비 precision@15, MRR |
| 서브시스템 | 빌드 트리 → networkx `louvain_communities`(seed, 비연결 분할, 허브 고정); scikit-network 0.33.5 Leiden 도전자 | REPLACE(기제) | MoJoFM/ARI vs 문서화 모듈, 시드 안정성 |
| 모듈 경계 | 빌드 파일 파서 | KEEP |, |
| 클론, 이력 | metadata 모드, `git log --name-only --no-renames --since=24.months`(kafka 0.27 s) | KEEP+ |, |
| 이력 오라클 | code-maat Docker + codelore | KEEP+ | 상위 20 집합 일치 |
| 토큰 | `count_tokens`(무료, 별도 5k RPM 풀) 하드 게이트 + tiktoken 0.14 보정표 p95 | REPLACE(정책) | `calibrate_tokens.py` 모델×종류 ≥30표본 |
| YAML/HCL/Dockerfile/properties | §2.7 | REPLACE 3건 | span 게이트 |
| Helm/kubectl | 핀된 바이너리 | KEEP+ |, |
| Mermaid 검증 | mermaid 11.17.2 + 11.13.0(GitLab 판) + jsdom 30.0.1 | KEEP+ | 2,000자, 50블록 게이트 |
| 산문 | fluent-korean + 정규식 + hanlint 0.0.10(강등) | KEEP(강등) | 30문장 오탐 0 |
| 검색 | bm25s 0.3.11 + kiwipiepy 0.23.2 | RE-MEASURE | 50문항 qrels |
| MCP | mcp 2.2.0 `MCPServer` | REPLACE | inspector 스모크 |
| GitLab | python-gitlab 8.5.0 `[graphql]`(읽기 fan-out은 GraphQL `Repository.blobs(paths)`, 쓰기는 REST) | KEEP+ | 요청 수 REST 대비 |
| 사이트 | 잠정(리서치 13) | 제외 | 읽기 UX 실측 |
| 조율 | LangGraph 1.2.11 잠정 | RE-MEASURE | 3시나리오 하네스 |
| LLM | anthropic 1.4.0(httpx2), Opus 5, adaptive thinking, `fallbacks: "default"`, 캐싱(Opus 5 최소 512토큰), Batches(1시간 TTL), structured outputs | KEEP+ | 인용 A/B(§4) |
| 패키징 | OCI + wheelhouse(`uv pip install --no-index --find-links --require-hashes`) | KEEP+ | `podman run --network=none` |
| 시크릿 | `GIT_ASKPASS` + 환경 변수 | REPLACE |, |

## 4. LLM 층 설계
3판과 같다. 추가:
- **노드별 effort**: plan과 맵 단계 `low/medium`, `write_page` `high/xhigh`.
- **페이지 브리프는 mid-conversation system message**(Opus 5, 베타 헤더 없음)로 넣어 캐시된 prefix를 보존한다.
- **Batches는 1시간 TTL 캐시**와 함께 쓴다. **Bedrock 경로에는 Batches와 Files API가 없다.** Bedrock은 온라인 전용 경로로 문서화한다.
- **인용 A/B(Phase 3, 20페이지)**: 자유 서술 `path:Lx-Ly` + 게이트 vs 심볼 span을 custom-content document 블록으로 주고 네이티브 citations(유효 포인터 보장, `cited_text` 무과금, Batches 호환, structured outputs와 비호환)을 쓰는 방식. 무효 span 비율, 페이지당 인용 수, 토큰으로 정한다.
- 맵 단계 모델: Opus 5 `low` vs Sonnet 5, 수용된 페이지당 비용으로 정한다.

## 5. 단계별 계획

| Phase | 산출물 | 완료 판정 |
|---|---|---|
| **0 기반** | 템플릿, altera-rules, `.importlinter`, SPEC.md, `docs/bootstrap.md`, **조율 하네스**, **토큰 보정표** | `install_surfaces.py --check` 0건; `gate_chain.sh` 완주; 참조 갱신 0건; 조율 하네스 3시나리오 결과가 RUNLOG에 있고 조용한 페이지 누락 0인 쪽을 채택; `calibration.json`에 모델×종류 6개 이상, 각 ≥30표본 |
| **1 결정층(code)** | facts + L0/L1/L2 | 4개 레포 종료 0; 선언 골든셋 recall과 precision ≥0.98; `outline` 동수 판정 기록; 서브시스템 MoJoFM이 빌드 트리 단독 이상; 랭킹 precision@15 기록; L1마다 Mermaid 문자 수와 교차 수 기록으로 상한 확정; 페이지당 Mermaid 소스 ≤2,000자 게이트 통과; codebase-memory-mcp 스파이크 결과(정밀도, 오프라인 여부) 기록 |
| **2 이력** | hotspot, coupling | code-maat와 codelore 상위 20 집합 일치; kafka <60 s; 이슈 키 파싱 실측 ±1%p |
| **2b 설정, 인프라** | helm/terraform/k8s/ci 분석기 | bdp-eks-charts 119객체, 124엣지 재현; aws-infra 16/16; **모든 사실에 span 또는 `rendered: true`**; tfparse 스파이크(모듈 소스 2, backend 3이 `--network none`에서 정확한 줄로 해석); 자격증명 키 노출 0 |
| **3 LLM층 + 게이트** | `wiki/` | 게이트 100%; 페이지당 인용 ≥3; 흐름 ≥5; 사람 표본 판정 ≥95%; 인용 A/B 결과 기록; hanlint 30문장 오탐 0 확인 뒤 차단 전환 |
| **4 사이트, 증분, 갱신, 질의** | 사이트, `--update`, MR, `changes/`, CLI+SKILL.md, MCP, 검색 | 소스 무변경 = LLM 0; 변이 세트 ≥9/10; 이해도 ≥4/5; 연속 갱신 3회 `changes/` 일치; 사이트 산출물 외부 URL 0; 대화형 그래프 페이지 렌더; 50문항 qrels 결과 기록; MCP inspector 스모크 |
| **5 GitLab, 패키징** | 20개 일괄, OCI(UBI9 타깃 포함), tarball | P-A/P-B/P-C 통과; `podman run --network=none` CI 게이트; 네이티브 휠 4종 포함 lock 전체 빌드; syft CycloneDX SBOM; 라이선스 목록에 LGPL 표시, GPL 0건 |
| **6 시스템** | `system/` | SkyWalking 비텍스트 엣지 ≥30, 스팟체크 ≥9/10; 사내 20개 거짓 엣지 0(class ≤3); 링크백 100% |

## 6. 게이트와 평가
3판과 같다. 추가 게이트: Mermaid 소스 문자와 블록 한도, span-or-rendered, 프론트매터 JSON Schema, `count_tokens` 하드 게이트, GitLab과 채택 생성기와 Obsidian의 렌더 라운드트립 테스트(공통 문법 주장의 유일한 실측).

## 7. 기각한 선택지 (현재형 사유)
3판의 표에 더한다.

| 선택지 | 기각 사유 |
|---|---|
| networkx Leiden | CPU 구현이 없다(백엔드 스텁) [실측] |
| leidenalg, igraph, infomap, graph-tool 동봉 | GPL |
| tiktoken을 그대로 예산 계기로 | Claude 4.7+ 토크나이저가 30% 더 많은 토큰을 내고, 벤더 문서가 tiktoken을 쓰지 말라고 적는다 |
| tree-sitter-language-pack 1.x | 문법 지연 다운로드, `manylinux_2_34` 전용, ABI 불일치 위험 |
| python-hcl2 `with_meta` | 8.x에서 동작하지 않는 스텁 |
| jproperties | 줄 정보 없음 |
| `FastMCP` | mcp SDK 2.x에서 제거 |
| `.netrc` | 평문이고 git 문서가 권하지 않는다 |
| stack-graphs, tree-sitter-graph, scip-syntax 참조 | 아카이브 또는 휴면 |
| GitNexus | PolyForm Noncommercial |
| `anthropic-tokenizer`, `gitoxide-py` | 출처 미검증, 어휘 구세대 |
| 사이트 결정을 air-gap 비용 1순위로 | 목적(읽기 UX)이 1순위이고 air-gap은 통과/불통과 제약이다(사용자 판정, §12) |

## 8. 사내 반입 패키징
3판과 같다. 추가: 네이티브 휠 `ormsgpack`, `xxhash`, `uuid-utils`, `sqlite-vec`; 언어별 tree-sitter 휠 7종; `tfparse`(cffi); `o200k_base.tiktoken` 파일 동봉; UBI9 `python-312` Dockerfile 타깃(RHEL 정책 대비, 고객 확인 항목); syft SBOM + cosign attest; `podman run --network=none` 설치와 실행 게이트; helm과 kubectl 바이너리 SHA256 고정.

## 9. 실측 프로파일
3판에 더한다: kafka blobless `git log` 0.27 s(0 fetch), `--name-status -M` 145.7 s, `--numstat` 44.1 s [14]; networkx 3.6.1 `leiden_communities` NotImplementedError [실측]; python-hcl2 8.1.4 `with_meta` 출력 동일 [실측]; PyYAML `compose` 노드 마크 확인 [실측].

## 10. 알려진 사각
3판에 더한다: `--no-renames`의 엔티티 분열; blobless에서 줄 churn 불가; tfparse 평가값은 원문이 아니라 표현식 인용은 tree-sitter-hcl로; hanlint 오탐률은 사내 문체에서 P-B에 처음 측정; codebase-memory-mcp의 kafka 규모 오프라인 색인 미검증; o200k→Opus 5 과소 계산 비율은 보정표가 처음 확정한다.

## 11. v1 밖으로 낸 것
3판에 더한다: D2 SVG 2차 출력(TALA 오픈소스화, 렌더는 Kroki나 사전 렌더만), 하이브리드 검색(qrels 임계 미달 시), Fumadocs 레시피(사이트 판정에 따라), 시간 감쇠 결합 지표(2025–26 문헌 미조사).

## 12. 실행 규약 (사용자 지시, 2026-09-08)
3판과 같다(버전 고정, 문서 우선 구현, C-/V- 분리 검증, kb-query, 비용보다 정확성). 의존 문서 대장 `docs/reference/dependency-docs.md`가 llms.txt 유무(10개 호스트 제공)와 미러 목록을 소유한다.

## 13. 이번 판에서 정정한 사실 (감사 14)
1. networkx에 CPU Leiden 구현은 없다.
2. GitLab은 18.11부터 Mermaid 11.13.0을 렌더하고 19.2부터 ELK를 지원한다. 실제 한도는 페이지당 소스 2,000자와 50블록이다.
3. python-hcl2 8.x `with_meta=True`는 줄 메타를 내지 않는다.
4. `git log -c core.commitGraph=false`는 효과가 없고, blobless 클론에서 `--numstat`은 air-gap에서 쓸 수 없다.
5. tiktoken은 Claude 4.7+ 계열 토큰을 체계적으로 과소 계산한다.
