---
status: 실측 완료 (2026-09-09). 리서치 13과 같은 300페이지 한국어 샘플 위키(`13-scripts/gen_wiki2.py`, Mermaid 포함)를 Fumadocs 16.15.8 + Next.js 16.3.4로 오프라인 정적 export하고, (a) `file://`, (b) 루프백 `python3 -m http.server --bind 127.0.0.1` 두 조건에서 헤드리스 Chrome 152로 측정. 스크립트, 설정, JSON 원자료는 `17-scripts/`, 스크린샷 24장은 scratchpad `fuma-reverify/shots/`
scope: 리서치 13이 Fumadocs를 탈락시킨 유일한 사유(`file://` 불통)를 재확인하고, 서빙 없이 "로컬 루프백 서버"를 붙였을 때 Fumadocs가 리서치 13의 UX 소계 기준을 어떻게 통과하는지 같은 도구로 다시 잰다. 서빙(S3, GitLab Pages)은 여전히 범위 밖이다. 판정은 하지 않고 측정 결과만 적는다
---

# Fumadocs 재검증 (`file://`와 루프백 http.server)

## 0. 요약 숫자

| 항목 | 값 | 라벨 |
|---|---|---|
| 버전 | fumadocs-core, fumadocs-ui, @fumadocs/base-ui 16.15.8 (2026-09-07), fumadocs-mdx 15.4.0 (2026-08-27), next 16.3.4, react 19.2.8. 리서치 13과 동일 | [웹] npm registry |
| 오프라인 빌드 | `npm ci --offline` 4.3 s(캐시 웜), `next build` 9.3 s에서 12.0 s(4회), CPU 약 50 s, sandbox-exec로 루프백 외 egress 차단 | [실측] |
| 락, node_modules | 락 567 패키지(템플릿 그대로, serve와 cn 포함), `node_modules` 706,888 KB, 37,543 파일 | [실측] |
| 산출물 | 300페이지에 222,604 KB, 2,226 파일. HTML 304개, RSC `.txt` 1,510개 = 125,496 KB | [실측] |
| RSC `.txt` 제거 | 95,132 KB, 718 파일로 줄지만 사이드바 클릭이 전체 리로드로 바뀌고(`window` 마커 소실) `__next._tree.txt` 404가 난다. 리서치 13 결론 재현 | [실측] |
| `file://` | 불통. 기본 빌드는 페이지마다 `/_next/static` 15개에서 16개 실패, CSS 0, Mermaid 0/1, 다크 토글 무반응, 검색 0건, 첫 클릭이 `file:///docs/2-broker/`로 간다. `assetPrefix: './'`는 루트 `index.html` 한 장만 살리고 하위 페이지는 자기 디렉토리 기준으로 `./_next`를 찾아 16개 실패 | [실측] |
| 루프백 http.server | 통과. 탐색(사이드바 4단, 브레드크럼, 이전/다음, 우측 TOC 추적), 클라이언트 탐색 4홉 모두 소프트(536 ms에서 687 ms), 검색 9질의 중 8 적중(조사 붙은 `컴포넌트는`, `퍼거토리에서` 포함), Mermaid 3/3, 다크 토글이 Mermaid까지 다시 그림, 실패 요청 0(취소된 prefetch 5건 제외), axe 위반 3종(리서치 13과 동일) | [실측] |
| 콘솔 오류 | 모든 docs 페이지에서 React #418(hydration 불일치) 1건. 홈 `/`에는 없음. 리서치 13 빌드와 `serve`에서도 동일하게 나며 `next dev`에서는 안 난다. 원인 미확인 | [실측], 원인 [unverified] |
| UX 소계(리서치 13 rubric 10행) | 35 (사이드바 중복 항목을 고치면 36). Starlight 42, MkDocs 32, Zensical 30 | [실측] |
| 의존성 델타 | PLAN Node 최소 집합 직접 3, 락 153, 255,944 KB(리서치 15, linux x86_64) 대비 Fumadocs 빌더 단독 직접 18, 락 488, 700,116 KB. 합집합 직접 20, 락 527, 798,360 KB(macOS arm64) | [실측] |

## 1. 배경과 방법

리서치 13은 넷 다 오프라인 빌드를 통과시킨 뒤 `file://` 한 항목으로 Fumadocs를 탈락시켰다(절대 경로 `/_next/`, `/docs/`). 사용자는 MkDocs 읽기 UX가 실사용에서 실망스러웠다고 했고, `127.0.0.1` 루프백 서버를 "여전히 로컬"로 볼지 검토 중이다. 그래서 두 조건을 같은 위키, 같은 도구로 다시 쟀다.

- 샘플: `13-scripts/gen_wiki2.py`의 fuma 타깃 출력 300페이지(scratchpad `docs-site/fuma-static/content`와 동일, diff 0). 두 군데를 손봤다. (1) `meta.json`의 `pages`에서 `"index"`를 뺐다(폴더 index.md는 Fumadocs가 폴더 노드로 쓰므로 다시 나열하면 `<folder>/index.md`로 가는 중복 항목이 생겨 prefetch 404 19건이 났다). (2) 루트 index.md의 링크에 `./`를 붙였다(리서치 13 행 10에서 이미 지적한 `createRelativeLink` 제약). 스크립트는 `17-scripts/fix_meta.py`, `fix_rootlinks.py`. favicon.ico를 `public/`에 넣었다(404 1건 제거). 본문, 사이드바 구조, 컴포넌트는 리서치 13 그대로다.
- 빌드: `17-scripts/build-offline.sh`. `npm ci --offline`과 `next build`를 리서치 13과 같은 `sandbox-exec -f sandbox-noegress.sb`(루프백 외 outbound 거부) 아래에서 돌렸다. 프록시는 `127.0.0.1:9`.
- 측정: 리서치 13의 `measure.mjs`를 경로만 바꿔 그대로 돌렸고(`report-fuma-loopback.json`), 추가 항목은 `extras.mjs`(`report-fuma-extras.json`), `file-diag.mjs`(`report-file-*.json`), `slimtest.mjs`, `hydra*.mjs`. Chrome 152 headless, 1440x900, 로드마다 새 컨텍스트.
- 서버: `python3 -m http.server 8002 --bind 127.0.0.1 -d out`. 표준 라이브러리만, Node 서버 없음. `/docs` -> `/docs/` 301, 디렉토리 index.html 서빙, gzip 없음, `text/plain`에 charset 없음.

## 2. 오늘의 버전과 지원 프레임워크

- npm `latest`: fumadocs-core 16.15.8, fumadocs-ui 16.15.8, @fumadocs/base-ui 16.15.8(2026-09-07), fumadocs-mdx 15.4.0(2026-08-27). 리서치 13(2026-09-09 실측)과 같은 판이므로 기존 빌드를 그대로 재사용할 수 있었고, 그래도 락에서 `npm ci`와 빌드를 다시 돌렸다 [웹] [실측].
- `fumadocs-core@17.0.0`이 2026-02-01에 존재하나 deprecated 메시지가 "Changesets CLI 버그로 잘못 발행, 쓰지 말 것"이다. 실제 최신 메이저는 16이다 [웹].
- peerDependencies: fumadocs-ui와 base-ui는 `next 16.x.x`, `react ^19.2.0`. fumadocs-core는 `next 16.x.x`, `react-router 7.x.x || 8.x.x`, `@tanstack/react-router 1.x.x`, `waku *`. fumadocs-mdx는 `next ^15.3.0 || ^16.0.0`, `vite 7.x.x || 8.x.x`. 전부 MIT [웹].
- 공식 문서(`https://www.fumadocs.dev/llms.txt`, `llms-full.txt` 654,980바이트, `17-scripts/fumadocs-llms.txt`에 사본)가 Manual Installation으로 나열하는 프레임워크: Next.js, React Router, TanStack Start, Waku, Astro(React island) [웹].
- Static Build 문서: Next.js는 `output: 'export'`, React Router는 `ssr: false` + `prerender()`, TanStack Start는 `spa.enabled` + `prerender`, Waku는 모든 페이지 `render: 'static'`. 어느 항목도 상대 자산 경로나 `file://`를 언급하지 않는다 [웹]. Vite 기반(React Router, TanStack Start)에서 Vite `base: './'`가 Fumadocs 라우팅과 검색 인덱스 fetch까지 상대화하는지는 이번에 빌드하지 않았다 [unverified].
- Next.js `assetPrefix` 문서: CDN용이며 `_next/static`만 바꾸고 `public/` 파일에는 영향이 없다고 적혀 있다. 상대 경로 지원은 문서에 없다 [웹].

## 3. 오프라인 빌드 (`output: 'export'`)

| 실행 | `npm ci --offline` | `next build` real | 산출물 |
|---|---|---|---|
| 1회(리서치 13 컨텐츠 그대로) | 4.31 s, 461 패키지 추가 | 12.01 s (user 50.4 s) | 222,412 KB, 2,225 파일 |
| 2회(meta.json 수정) | 5.88 s | 9.60 s | 222,608 KB |
| 3회(루트 링크 수정) | 6.23 s | 9.30 s | 222,604 KB |
| 4회(favicon 추가, 최종) | 5.44 s | 9.61 s | 222,604 KB, 2,226 파일 |

- 락 567 패키지, `node_modules` 706,888 KB(37,543 파일). 그중 `next` 203,552 KB, `@next`(swc 바이너리) 98,848 KB, `mermaid` 85,484 KB [실측].
- 산출물 구성: HTML 304, RSC `.txt` 1,510개 125,496 KB(페이지마다 `__next._tree.txt`, `__next._full.txt`, `index.txt` 등 5개), `_next/` 6,088 KB, `api/search` 12,265,284바이트 단일 JSON, `llms.mdx/` 2,612 KB, `llms.txt` 41,807 B, `llms-full.txt` 2,370,205 B [실측].
- RSC `.txt` 제거 재확인: `llms*.txt`를 제외한 `.txt`를 지우면 95,132 KB, 718 파일. 루프백에서 사이드바 클릭 시 `window.__marker`가 사라져(전체 리로드) 소프트 탐색 false, `/__next._tree.txt?_rsc=` 404 3건. 리서치 13의 "92 MB 변형은 탐색이 리로드로 후퇴" 결론이 현재 판에서도 같다 [실측].
- 부수 관찰: `next dev`를 한 번 띄우자 Next 16이 프로젝트 루트에 `AGENTS.md`와 `CLAUDE.md`를 자동 생성했다(`agentRules: false`로 끌 수 있다는 로그). 정적 빌드에는 영향 없고 삭제했다 [실측].

## 4. `file://` 시도 (30분 한도)

`17-scripts/tools/file-diag.mjs`로 `out/index.html`, `out/docs/index.html`, `out/docs/3-replication/3-2-b/3-2-4/index.html` 세 장을 `--allow-file-access-from-files`로 열었다.

| 빌드 | 페이지 | CSS 적용 | Mermaid SVG | 다크 토글 | 검색 | 실패 요청 | 첫 클릭 |
|---|---|---|---|---|---|---|---|
| 기본(`output: 'export'`, `trailingSlash: true`) | 루트 | 0 | 0/0 | 무반응 | 0건 | 15 (`file:///_next/static/...`) | 없음 |
| 기본 | `/docs/` | 무스타일(body 배경 투명) | 0/1 | 무반응 | 0건 | 16 (`/_next/static`) | `file:///docs/2-broker/` (Chrome "파일에 액세스할 수 없음") |
| 기본 | 3.2.4 | 무스타일 | 0/1 | 무반응 | 0건 | 16 | 같음 |
| `assetPrefix: './'` | 루트 | 적용(배경 rgb(18,18,18)) | 0/0 | 동작(18 -> 245) | 0건 | 2 (`file:///docs/`, `file:///api/search`) | 없음 |
| `assetPrefix: './'` | `/docs/` | 무스타일 | 0/1 | 무반응 | 0건 | 16 (`<out>/docs/_next/static/...`) | 절대 경로 그대로 |
| `assetPrefix: './'` | 3.2.4 | 무스타일 | 0/1 | 무반응 | 0건 | 16 (`<out>/docs/3-replication/3-2-b/3-2-4/_next/...`) | 절대 경로 그대로 |

- 깨지는 것: (1) 자산 `/_next/static/*` 절대 경로, (2) `next/link` href `/docs/...` 절대 경로(HTML과 RSC payload 양쪽에 박힘), (3) 검색 인덱스 `/api/search` 절대 fetch, (4) RSC 탐색 fetch. 콘솔 오류는 `Failed to load resource: net::ERR_FILE_NOT_FOUND` 반복뿐이다 [실측].
- `assetPrefix: './'`는 빌드가 되고 `<script src="./_next/...">`로 찍히지만 상대 경로는 문서 위치 기준이라 루트 한 장에서만 맞는다. `trailingSlash: false`로 바꿔도 `docs/2-broker.html` 기준 `docs/_next`가 되므로 같은 문제다(추론, 빌드하지 않음) [unverified]. `basePath`는 하위 경로 호스팅용이고 상대값을 받지 않는다는 것은 이번에 실측하지 않았다 [unverified].
- 문서화된 방법 없음. 살리려면 리서치 13이 말한 대로 HTML과 1,510개 RSC `.txt`를 모두 다시 쓰는 후처리기가 필요하고, 그 뒤에도 `/api/search` fetch와 `next/link`의 클라이언트 라우터가 남는다 [실측 + 추론].

## 5. 루프백 http.server 측정 (`measure.mjs` + `extras.mjs`)

### 5.1 탐색

- 사이드바(`#nd-sidebar`): 루트 페이지에서 링크 47개(1단 9개 + 2단 37개 전부 노출, `defaultOpenLevel: 1`), 깊은 페이지에서 54개(현재 3단 폴더가 열려 3.2.1에서 3.2.6까지 추가). 현재 항목 `data-active`가 뷰 안에 있음(top 746 px, 사이드바 자동 스크롤). 리서치 13에서 지적한 "index 페이지가 폴더 링크와 자식으로 중복" 현상은 `meta.json` 수정으로 사라졌다 [실측].
- 브레드크럼: `extras.mjs`의 셀렉터(`nav[aria-label*=bread]`, `[class*=breadcrumb]`)는 못 찾았으나 스크린샷 `fuma-loopback-deep-desktop.png`에 "3. 복제와 리더 선출 > 3.2 리더 에포크"가 h1 위에 찍혀 있다. 리서치 13의 `hasBreadcrumb=false`도 같은 검출 실패였다 [실측 스크린샷].
- 이전/다음: 3.2.4에서 prev `/docs/3-replication/3-2-b/3-2-3/`, next `/docs/3-replication/3-2-b/3-2-5/` [실측].
- 우측 TOC(clerk): left 1,157 px, 링크 10개, 스크롤 추적(`요약` -> `설정 표`). heavy 페이지(`full: true`)는 설계상 TOC 없음. 리서치 13과 동일 [실측].
- 클라이언트 탐색 체인 index -> 2. 브로커 코어 -> 2.2 ReplicaManager -> 2.2.1 -> 3. 복제, 뒤로가기: 5회 모두 소프트(SPA) 탐색, 홉당 536 ms에서 687 ms, 홉마다 새 요청 3개에서 8개(RSC `.txt` 0에서 7개), 도착 페이지 Mermaid SVG 1, 1, 3, 2개. 4xx 0 [실측].
- 실패 요청: 4xx와 네트워크 오류 0. `net::ERR_ABORTED` 5건은 `/docs/...` prefetch가 라우터에 의해 취소된 것으로, 서버 로그에는 200으로 남는다 [실측].

### 5.2 검색 (Orama 정적 인덱스, 서버 라우트 없음)

`app/api/search/route.ts`의 `staticGET`이 빌드 시 `out/api/search`(12,265,284 B, `application/octet-stream`으로 서빙됨)를 내고, 클라이언트 `staticClient`가 첫 검색에서 1회 fetch한다. 서버 라우트는 필요 없다 [실측].

| 질의 | 적중(상한 60) | 첫 결과 ms | 1위 |
|---|---|---|---|
| 컴포넌트 | 60 | 389 | Apache Kafka 아키텍처 위키 |
| 컴포넌트는 | 60 | 365 | 2.4.2 핵심 자료구조(본문 "이 컴포넌트는 브로커 기동 시...") |
| 퍼거토리 | 60 | 347 | 7.3.1 책임과 경계(본문 "퍼거토리에서 강제로 완료") |
| 퍼거토리에서 | 60 | 368 | 같음 |
| 복제 관리자 | 60 | 381 | 루트, 2위 2.2 ReplicaManager 복제 관리자 |
| 복제 관리자가 | 60 | 389 | 같음 |
| ReplicaManager | 60 | 464 | 루트, 2위 2.2 |
| 리더 에포크 캐시가 절단 지점을 결정한다 | 60 | 570 | 3.2.4 오류 처리, 문장 그대로 스니펫. Enter -> `/docs/3-replication/3-2-b/3-2-4/` |
| ㅋㅍ(초성) | 0 | 없음 | 없음 |

리서치 13(`serve`)의 356 ms에서 565 ms와 같은 대역이다. 조사가 붙은 질의도 어간 질의와 같은 결과를 낸다 [실측].

### 5.3 Mermaid, 다크 모드, 무게, 접근성

- Mermaid 1440 px, heavy 페이지 3개: 3,791/3,791 px(컨테이너 1,091 px, 가로 스크롤), 1,226/1,226 px(가로 스크롤), 333 px. 글자 16 px. 1920 px에서도 원 크기(컨테이너 1,102 px). 문서 자체 가로 스크롤 없음(docScrollWidth 1,425 = 뷰포트) [실측].
- CSS `[data-mermaid] svg { max-width: 100%; height: auto }` 오버레이: 25노드 그래프가 1,075 px(28%)로 줄고 유효 글자 4.5 px, 가로 스크롤 없음. 곧 MkDocs와 Starlight의 "축소, 줌 필요" 상태가 된다. 원 크기 + 가로 스크롤과 축소 중 하나를 고르는 문제이지 둘 다는 안 된다 [실측].
- 클릭 줌 오버레이(리서치 13의 40줄 컴포넌트): 열림, 휠 2회에 121%, 오버레이 안 SVG 4,588 px, Esc로 닫힘 [실측].
- 다크 토글(`aria-label="Toggle Theme"`): body 배경 rgb(245,245,245) -> rgb(18,18,18), html class `light` -> `dark`, Mermaid 노드 채움 rgb(255,255,222) -> rgb(71,73,73)로 3개 모두 다시 렌더. 다크 링크 대비 15.71:1 [실측].
- 무게(gzip 없음, http.server 그대로): heavy 페이지 전송 3,077 KB(문서 242 KB, JS 2,156 KB 36개, CSS 77 KB, fetch 602 KB 26개). 리서치 13의 `serve` gzip 값 749 KB와 비교하려면 압축 차이를 감안해야 한다. 로컬 루프백이라 load 71 ms, FCP 48 ms, 3 SVG 411 ms로 시간은 리서치 13과 같다 [실측].
- axe(WCAG 2 A/AA, light): index color-contrast 24, scrollable-region-focusable 1, svg-img-alt 1. deep 43/1/1. heavy 36/2/1. 리서치 13과 같은 3종. 헤딩 건너뜀 1(아코디언 제목 h3가 첫 h2 앞) [실측].
- 모바일 390 px: 드로어 `#nd-sidebar-mobile` 319 px, 링크 46에서 53. SVG는 원 크기로 컨테이너 341 px 안에서 가로 스크롤 [실측].

### 5.4 콘솔 오류: React #418

- 모든 docs 페이지 로드에서 `Minified React error #418`(서버 HTML과 클라이언트 불일치, 트리 재생성) 1건. 홈 `/`에는 없다. 리서치 13이 만든 `docs-site/fuma-static/out`을 `serve`로 띄워도 같고, 이번 빌드를 `serve`로 띄워도 같다. `next dev`(SSR 즉석 렌더)에서는 안 난다. Mermaid 컴포넌트를 서버 렌더 `<pre>` 스텁으로 바꿔 다시 빌드해도 그대로다. 서버 HTML과 hydration 후 DOM의 요소 경로 diff는 클라이언트 전용 노드 5개가 앞에 붙는 인덱스 이동만 보여 위치를 못 잡았다 [실측]. 원인은 [unverified]. 사용자 관측 영향: 이번 측정의 탐색, 검색, 토글은 모두 이 오류가 있는 상태에서 통과했다.

## 6. llms.txt와 페이지별 Markdown

- Fumadocs 문서 방식: `app/llms.txt/route.ts`(`llms(source).index()`), `app/llms-full.txt/route.ts`, `app/llms.mdx/docs/[[...slug]]/route.ts`가 라우트 핸들러이고 `revalidate = false`로 정적 export 때 파일로 떨어진다. `/docs/x.md` 단축 URL은 `next.config`의 `rewrites()`인데 정적 export에는 서버가 없어 적용되지 않는다 [웹] [실측 404].
- 루프백 서빙 확인: `/llms.txt` 200 `text/plain` 41,807 B, `/llms-full.txt` 200 2,370,205 B, `/llms.mdx/docs/2-broker/2-2-replicamanager/2-2-1/content.md` 200 `text/markdown` 11,851 B. `/docs/.../2-2-1.md`와 `.../index.md`는 404 [실측].
- repowiki 자체 파일 덮어쓰기: `out/llms.txt`, `out/llms-full.txt`를 임의 내용으로 바꾼 뒤 같은 서버에서 200으로 서빙되고 UTF-8 바이트가 그대로 돌아온다. 정적 디렉토리라 당연한 결과이고, Fumadocs가 만든 두 파일은 덮어쓰거나 라우트를 지우면 된다 [실측].
- 주의: `http.server`는 `text/plain`에 charset을 안 붙인다. 브라우저에서 `/llms.txt`를 직접 열면 한글이 깨져 보일 수 있다(curl과 에이전트 Read는 바이트라 무관). 브라우저 표시는 이번에 확인하지 않았다 [unverified].
- 페이지별 Markdown 품질: `content.md`에 `<CalloutContainer>`, `<Accordions>`, `<Mermaid chart=...>` JSX가 남고 ```` ```mermaid ```` 펜스는 0개다. remark-directive 변환 결과가 그대로 나오기 때문이고 리서치 13 행 9에서 지적한 것과 같다. `remark-llms`의 `output` 옵션으로 되돌릴 수 있다고 문서에 적혀 있으나 시험하지 않았다 [웹] [unverified]. 페이지 상단 "Copy Markdown"과 "Open" 메뉴는 매 페이지 있다 [실측].

## 7. 유지보수 신호

Fumadocs (`fuma-nama/fumadocs`, 기본 브랜치 `dev`) [웹, GitHub API 2026-09-09]:
- 최근 12개월(2025-09-09 이후) 기본 브랜치 커밋 1,773.
- 기여자 98명, 총 5,439 커밋 중 fuma-nama 5,222(96.0%), 2위 12. bus factor 1.
- npm 안정판 릴리스 최근 12개월: fumadocs-core 137회(15.7.11에서 16.15.8), fumadocs-mdx 64회. 메이저 15(2025-01-29), 16(2025-10-22).
- open issue 0, open PR 1, 스타 13,099, MIT, 마지막 push 2026-09-08.

Next.js [웹]:
- 현재 메이저 16.x Active LTS(2025-10-21), 15.x Maintenance LTS(2025-10-21부터). 정책: 다음 메이저가 나오면 이전 메이저는 Maintenance로 가고 첫 릴리스 후 2년간 critical 버그와 보안 패치만 받는다(`nextjs.org/support-policy`).
- 안정판 릴리스 최근 12개월 83회(15.5.3에서 16.3.4).
- GitHub 보안 권고(npm `next`) 최근 12개월 35건(high 16건), 발행일 9일에 몰림(2025-12-03, 12-11, 12-12, 2026-01-27, 01-28, 03-17, 04-10, 05-11, 07-22). 최신 묶음 2026-07-22 9건은 `< 16.2.11` 대상이라 16.3.4는 포함되지 않는다. 즉 고정 이미지라면 대략 1개월에서 2개월 간격으로 패치 묶음이 온다. 정적 export는 Node 서버가 없으므로 이 권고 중 어느 것이 빌드 도구로서의 Next에 해당하는지는 건별로 봐야 한다 [unverified].

## 8. 의존성 델타 (air-gap 이미지)

| 집합 | 직접 | 락 패키지 | `node_modules` | 플랫폼 | 출처 |
|---|---|---|---|---|---|
| PLAN Node 최소(mermaid 11.17.2, mermaid 11.13.0 alias, jsdom 30.0.1) | 3 | 153 | 255,944 KB | linux x86_64 | 리서치 15 [실측] |
| Fumadocs 빌더 단독(serve, cn 제외) | 18 (deps 11, devDeps 7) | 488 | 700,116 KB (36,421 파일) | macOS arm64 | [실측] `17-scripts/fuma-only.json` |
| 합집합(PLAN 최소 + 빌더) | 20 | 527 | 798,360 KB (39,242 파일) | macOS arm64 | [실측] `17-scripts/union.json` |
| 리서치 13 템플릿 락 그대로 | 20 | 567 | 706,888 KB | macOS arm64 | [실측] |

- 합집합에서 큰 것: next 203,552 KB, @next swc 98,848 KB, mermaid 85,484 KB, mermaid 11.13.0 72,584 KB, jsdom 8,544 KB. mermaid 11.17.2는 두 집합이 공유하므로 합집합이 단순 합보다 작다 [실측].
- 락 패키지는 +374(153 -> 527), `node_modules`는 약 +542 MB(플랫폼이 달라 swc 바이너리 크기가 다르므로 근사). 직접 의존성 18개 중 7개는 타입과 빌드 도구(@types 4종, postcss, tailwindcss, typescript)라 런타임 SBOM에서 dev 그룹으로 뺄 수 있다 [실측 + 추론].
- 빌드 시간은 MkDocs 3.7 s(리서치 13) 대비 9.3 s에서 12.0 s. CPU는 약 50 s로 병렬 워커 9개를 쓴다 [실측].

## 9. 통과/불통과와 비교표

### 9.1 Fumadocs 조건별

| 항목 | (a) `file://` | (b) 루프백 `http.server` |
|---|---|---|
| CSS, JS 로드 | 불통 (15에서 16 실패/페이지) | 통과 |
| 사이드바 탐색 -> 3.2.4 | 불통 (첫 클릭 `file:///docs/...`) | 통과 (4홉 소프트, 뒤로가기 포함) |
| Mermaid 렌더 | 불통 (0/1) | 통과 (3/3, 원 크기 + 가로 스크롤, 줌 오버레이) |
| 다크 토글 | 불통 | 통과 (Mermaid 재렌더 포함) |
| 검색 | 불통 (0건) | 통과 (정적 인덱스 12.3 MB 1회 fetch, 한국어 조사 질의 적중) |
| 실패 요청 0 | 불통 | 통과 (4xx 0, 취소 prefetch 5건 별도) |
| 콘솔 오류 0 | 불통 | 불통 (React #418 1건/페이지, 기능 영향 미관측) |
| llms.txt, llms-full.txt, content.md | 해당 없음 | 통과 |
| `assetPrefix: './'` 우회 | 루트 1장만 통과, 나머지 불통 | 해당 없음 |

### 9.2 UX 소계 (리서치 13 rubric 10행, 행당 1에서 5)

| 행 | MkDocs Material 9.7.7 | Zensical 0.0.60 | Starlight 0.42 | Fumadocs 16.15.8 (리서치 13, `serve`) | Fumadocs 16.15.8 (이번, `http.server`) |
|---|---|---|---|---|---|
| 25노드 그래프 가독성 1440 px | 3 | 2 | 3 | 4 | 4 (3,791 px 원 크기, 가로 스크롤, 줌 121%) |
| 사이드바 3단, 번호, 현재 경로 | 4 | 4 | 4 | 3 | 3, 중복 항목 제거 반영 시 4 |
| 우측 TOC 추적, 브레드크럼 | 4 | 3 | 3 | 4 | 4 (TOC 추적, 브레드크럼 스크린샷 확인) |
| 한국어 검색 | 2 | 2 | 5 | 4 | 4 (조사 질의 4종 추가 적중, 초성 0) |
| 페이지 무게 | 2 | 2 | 5 | 3 | 3 (gzip 없이 3,077 KB, 압축 조건 다름) |
| 다크 모드 Mermaid, 링크 대비 | 3 | 3 | 5 | 4 | 4 (15.71:1) |
| axe | 3 | 2 | 5 | 2 | 2 (같은 3종) |
| Markdown 복사, LLM 파일, 갱신일 | 3 | 2 | 3 | 4 | 4 |
| 순수 `.md` 충실성 | 5 | 5 | 5 | 3 | 3 (`./` 링크, JSX 잔존) |
| 소계(시간 행 제외) | 32 | 30 | 42 | 35 | 35 (사이드바 4로 보면 36) |

리서치 13의 점수를 그대로 가져왔고 Fumadocs 열만 이번 측정으로 다시 채웠다. 다른 셋은 재측정하지 않았다.

### 9.3 델타

| 항목 | PLAN 현행(MkDocs) | Fumadocs |
|---|---|---|
| Node 직접 | 3 | 20 (합집합) |
| Node 락 | 153 | 527 |
| `node_modules` | 255,944 KB | 798,360 KB |
| 빌드 real | 3.7 s | 9.3 s에서 12.0 s |
| 300페이지 산출물 | 59 MB (리서치 13) | 222,604 KB, 그중 RSC `.txt` 125,496 KB(지우면 탐색 후퇴) |
| 뷰어 조건 | `file://` | 루프백 서버 필수 |

## 10. [unverified] 목록

1. React #418 hydration 오류의 원인과 사용자 가시 영향(깜빡임 여부).
2. Vite 기반 프레임워크(React Router, TanStack Start, Waku, Astro)에서 Fumadocs가 상대 자산 경로로 `file://`를 통과하는지. 문서에 언급 없음, 빌드 안 함.
3. `trailingSlash: false` + `assetPrefix: './'` 조합, `basePath` 상대값 거부.
4. `remark-llms`의 `output` 옵션이 `content.md`의 JSX를 Markdown으로 되돌리는지.
5. `http.server`의 charset 없는 `text/plain`이 브라우저에서 한글을 깨뜨리는지.
6. Next.js 보안 권고 35건 중 정적 export 빌드 도구 용도에 실제로 해당하는 건수.
7. `node_modules` 크기 비교는 플랫폼이 다르다(리서치 15 linux x86_64 대 이번 macOS arm64). 이미지 플랫폼에서 다시 재야 한다.
8. MkDocs, Zensical, Starlight는 이번에 재측정하지 않았다. 비교표의 세 열은 리서치 13 값이다.

## 11. 판단 (측정이 보여주는 범위)

`file://`에서는 Fumadocs가 리서치 13과 같은 이유로 여전히 불통이고, `assetPrefix: './'`는 루트 한 장만 살린다. 루프백 `python3 -m http.server`를 붙이면 리서치 13이 잰 모든 UX 항목(탐색, 검색, Mermaid, 다크, 실패 요청 0)을 통과하고 소계는 35(중복 항목 수정 반영 시 36)로 MkDocs 32보다 높고 Starlight 42보다 낮다. 그 대가로 뷰어가 서버 프로세스 하나를 띄워야 하고, 콘솔에 원인 미확인 hydration 오류가 페이지마다 1건 남으며, air-gap 이미지의 Node 락은 153에서 527, `node_modules`는 약 250 MB에서 약 800 MB로 늘고, 산출물은 300페이지에 217 MB(RSC payload 125 MB 포함)가 된다. 한국어 검색은 조사가 붙은 질의를 포함해 모두 적중했고, llms.txt와 페이지별 Markdown은 정적 파일로 서빙된다. bus factor 1과 Next.js의 1개월에서 2개월 간격 보안 패치 묶음은 리서치 13 그대로다.
