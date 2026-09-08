---
status: 실측 완료 (2026-09-08) — Fumadocs 16.15.8 스캐폴드·정적 export·오프라인 빌드, MkDocs Material 9.7.7 privacy/offline/llmstxt 빌드. [unverified] 표기 항목 미확인
scope: 위키 사이트 생성기 선정(Fumadocs vs MkDocs Material vs Starlight 등), 테마, DeepWiki UX 대응, "Ask the docs" 2차 단계 설계
---

# repowiki docs-site evaluation — Fumadocs vs alternatives

오프라인 실행은 `HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:9`로 egress 차단.

## 1. Fumadocs hands-on
스캐폴드: `npx create-fumadocs-app@latest fuma-static --template "+next+fuma-docs-mdx+static" --search orama --pm npm --no-git -y` (정적 export 전용 템플릿 존재; `--ai-chat openrouter|llmgateway|inkeep` 옵션).

| 항목 | 결과 |
|---|---|
| 버전/라이선스 | fumadocs-core 16.15.8, fumadocs-mdx 15.4.0, `fumadocs-ui`=`@fumadocs/base-ui`, next 16.3.4, react 19.2.8, tailwind 4.3.3, mermaid 11.17.2, zbsearch 4.0.0. 전부 MIT(zbsearch Apache-2.0) |
| (a) 정적 export | 동작. 21페이지 → 69 라우트(HTML + RSC `.txt`, `/api/search` JSON, `/llms.txt`, `/llms-full.txt`, `/llms.mdx/docs/**/content.md`, OG PNG) |
| (b) Mermaid | 클라이언트 렌더, CDN 없음. `remarkMdxMermaid`(fence → `<Mermaid>`) + 클라이언트 컴포넌트. 헤드리스 DOM에 `<svg class="statediagram">` 확인. 함정: 플러그인을 호출하지 않고 전달. mermaid가 node_modules +83 MB, 청크 ~700 KB |
| (c) llms.txt | 정적 export에서 기본 생성. **단 LLM 텍스트는 처리된 MDAST라 mermaid fence가 `<Mermaid chart=…/>` JSX로, accordion도 JSX로 남는다.** `page.data.getText('raw')`로 원문 변형 가능. "Open" 메뉴가 chatgpt.com/claude.ai/cursor.com을 가리켜 air-gap에서 죽은 링크 |
| (d) 정적 검색 | `createFromSource(source).staticGET` JSON 인덱스(21p 262 KB, **301p 4.16 MB**), 엔진 zbsearch. **한국어: 템플릿의 `language: 'english'`로 0건, `language: 'multilingual'`(Intl.Segmenter)로 주문 19건·컴포넌트 18건** |
| (e) 오프라인 빌드 | `npm ci --offline --cache` 4.4 s exit 0; node_modules **537 MB**(mermaid 포함 689 MB), 캐시 555 MB, `npm-cache.tgz` **224 MB**; 21p `next build` 5.2 s, `out/` 11 MB; **301p: 7.7 s, `out/` 210 MB**(페이지마다 300개 사이드바 트리가 HTML과 RSC에 인라인, 페이지 HTML 354 KB). **self-managed GitLab Pages 기본 최대 사이트 크기 100 MB**(https://docs.gitlab.com/administration/pages/) |
| (f) Google Fonts | 템플릿이 `next/font/google` Inter → 오프라인 빌드 **하드 실패**(`Failed to fetch Inter`). 해결: import 제거 + 시스템 폰트 스택(Pretendard, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR) 또는 `next/font/local` |
| MDX 취약성 | `.mdx` 산문에 `Map<K, V>` → 빌드 전체 실패; `{name}` → prerender 실패. `.md`는 빌드되나 **raw HTML 제거**(`List<T>`→"List", `<details>` 제거). → repowiki는 `.md`를 내고 코드성 토큰은 백틱 |

## 2. Fumadocs 테마/레이아웃
프리셋(디스크 확인): aspen, black, catppuccin, dusk, emerald, neutral, ocean, purple, ruby, shadcn, solar, vitepress. import: `@import 'tailwindcss'; @import 'fumadocs-ui/css/<preset>.css'; @import 'fumadocs-ui/css/preset.css';` 폭 `--fd-layout-width`. 레이아웃: docs, notebook, flux, glass, home. `meta.json` `pages`로 순서; **네이티브 번호 매김 없음**(제목에 번호, DeepWiki와 같은 모양). 커뮤니티 테마 의존할 것 없음(`fumadocs-ui-template` 2026-08-03 아카이브). **판정: 기본 테마 교체는 불필요.** 채택 시 `neutral.css`(또는 `vitepress.css`), `--fd-layout-width: 1600px`, 다이어그램 페이지 `full: true`, `sidebar.defaultOpenLevel: 1`, `tableOfContent.style: 'clerk'`, Google font 제거, 외부 "Open" 링크 교체.

## 3. 대안 비교
| 도구 | 정적 | Mermaid | llms.txt | 오프라인 빌드 | 검색/한국어 | 300p | 유지 |
|---|---|---|---|---|---|---|---|
| **MkDocs Material 9.7.7** | native | superfences; mermaid.min.js는 unpkg → **`privacy` 플러그인이 `assets/external/`로 내려받음(검증)** | `mkdocs-llmstxt` 0.5.0(pawamoy, ISC): llms.txt + llms-full.txt + 페이지별 `.md`(검증) | egress 차단 빌드는 **exit 0이지만 CDN URL이 조용히 남음**; 온라인 1회 빌드의 `.cache/plugin/privacy`(4.2 MB) 동봉 시 완전 self-host. `theme.font: false`. 빌드 0.4–3 s, venv 126 MB | lunr `search.lang: ko`, 한국어 인덱스 확인 | 양호 | **9.7.0(2025-11-11)부터 유지보수 모드, EOL 2026-11-05** |
| **Zensical 0.0.60**(Rust) | native | unpkg | **없음 [unverified]**; mkdocs-llmstxt 미이식 | `offline` 이식, **`privacy` 없음** | 자체 엔진, `ko` 로케일 | 미시험 | 알파 |
| **Fumadocs 16.15.8** | 동작 | 번들 | 내장(JSX 섞임) | 폰트 수정 후 동작; Node + 224 MB 캐시 | zbsearch, `multilingual` 필요 | **210 MB** | 활발, Next 16 주기 종속 |
| Docusaurus 3.10.2 | SPA+prerender | `@docusaurus/theme-mermaid` | `docusaurus-plugin-llms` 0.6.0 | 시스템 폰트 | `docusaurus-search-local`(lunr ko) | 양호 | 활발 |
| Astro Starlight 0.42.0 | native | `astro-mermaid` 2.1.0(클라이언트) | `starlight-llms-txt` 0.11.0 | 시스템 폰트, Pagefind | Pagefind(CJK 확장 빌드) | 양호 | 활발 |
| VitePress 1.6.4/2.0 alpha | native | `vitepress-plugin-mermaid` 2024-09 정체, v1만 | `vitepress-plugin-llms` 1.13.5 | Inter 로컬 | MiniSearch | 양호 | v2 알파 |
| Nextra 4.6.1 | export + Pagefind | 내장 | 없음 | [unverified] | Pagefind | 양호 | 느림 |
| Mintlify | Enterprise self-host(K8s+DB)만 | — | native | — | — | — | 제외 |

순위(air-gap 정적 > LLM 노출 > 읽기 UX > Python 유지): **1. MkDocs Material(9.7.x 핀) + privacy/offline/llmstxt**, 2. Starlight, 3. Fumadocs, 4. Docusaurus, 5. Zensical(privacy·llms.txt 대기).

## 4. DeepWiki 읽기 UX 대응 (deepwiki.com/apache/kafka: 59페이지 9섹션)
| DeepWiki 요소 | Fumadocs | MkDocs Material |
|---|---|---|
| 번호 사이드바(≤3레벨, `/{n}-{slug}`) | `meta.json` 순서 + 번호 제목 | `nav:` 번호 제목, `navigation.sections/indexes` |
| "Relevant source files"(커밋 고정 링크 35–40개, 접힘) | `<Accordion>`(`.mdx`만) | `pymdownx.details`(`??? "Relevant source files"`) plain `.md` |
| 인용 칩(`path.ext` + `12-34` → `blob/<sha>/path?plain=1#L12-L34`) | 백틱 라벨 링크 | 동일 |
| 다이어그램 | `remarkMdxMermaid` + 클라이언트 | superfences + privacy; glightbox 확대 |
| 우측 TOC | 내장(clerk) | `toc.follow` |
| "Last indexed: 5 September 2026 (940c10)" | `<Callout>` | admonition(git-revision 플러그인은 `offline`과 불가) |
| Ask Devin, MCP(`read_wiki_structure`, `read_wiki_contents`, `ask_question`) | §5 | §5 |

## 5. "Ask the docs" 2차 단계
사실: `llms-full.txt`는 llmstxt.org 규격 밖의 관례. Fumadocs AI 검색은 CLI 추가(`npx @fumadocs/cli add ai/…`), Vercel AI SDK `useChat` + `/api/chat` POST 핸들러 → **`output: 'export'`에서 불가**. 브라우저→Anthropic 직접 호출은 `dangerouslyAllowBrowser`로 키 노출. Orama Answer Engine은 Cloud 필요. Pagefind Node API는 색인 빌드 전용.

최소 설계(정적 사이트에 서버 없음):
1. **repowiki가 LLM 표면을 직접 낸다**: `llms.txt`(규격형 인덱스, 페이지 목적 포함), `llms-full.txt`(원문 Markdown, mermaid fence 유지 — Fumadocs의 JSX화 텍스트보다 낫다), `wiki/` 트리. `CLAUDE.md`/`AGENTS.md`에 "아키텍처 위키: `wiki/llms.txt`부터 읽고 링크를 따라가며 `path:lines`로 인용" 한 줄. Claude Code는 Read/Grep/Glob으로 답한다. 인프라 0.
2. **선택, 로컬 MCP `repowiki-mcp`**(FastMCP ~150줄, `.mcp.json` 프로젝트 스코프): `read_wiki_structure`, `read_wiki_contents(page)`, `search(query,k)` = **`bm25s` 0.3.11** + 사용자 분절기(**`kiwipiepy`** 형태소 + ASCII 정규식; bm25s 기본 `\b\w\w+\b`는 조사를 붙여 둔다), 임베딩 없음, 생성 시점 색인. `ask`는 두지 않는다(호출하는 에이전트가 LLM).
3. **소형 사내 서비스가 허용될 때**: FastAPI `POST /ask` = BM25 top-k → Anthropic 호환 게이트웨이 → `path:lines` 인용 스트리밍; 정적 사이트에 "Ask" 패널(MkDocs: 소형 JS). SSO 쿠키 인증, HTML에 공유 키 금지.

## 6. 권고
**Fumadocs가 아니라 MkDocs Material을 유지하고, 위키 출력은 생성기 독립으로 둔다.**
1. air-gap: MkDocs 압승 — Python 휠 + 4 MB privacy 캐시(mermaid·폰트 self-host 검증; `theme.font: false`). Fumadocs는 Node 22 + Next 16 + 224 MB 캐시 + 폰트 패치, 300페이지 210 MB vs Pages 기본 100 MB.
2. LLM 노출: repowiki가 `llms.txt`/`llms-full.txt`를 직접 쓰면 동률; `mkdocs-llmstxt`도 검증됨.
3. 읽기 UX: Fumadocs가 테마 없이도 앞선다(스크린샷). Material은 `navigation.sections`, 번호 제목, `pymdownx.details`, 다크 팔레트로 ~80%.
4. Python 팀 유지: MkDocs.
주의: Material은 EOL 2026-11-05 → `mkdocs-material==9.7.7` wheelhouse 핀 + `.cache/plugin/privacy` 동봉(캐시 없는 오프라인 빌드는 깨진 CDN 링크를 조용히 낸다). 콘텐츠는 plain Markdown + mermaid fence + YAML frontmatter + 상대 링크로 유지해 Zensical(설정 호환)이나 Starlight/Fumadocs로 재빌드 가능하게 둔다. UX를 air-gap 비용보다 우선하는 결정이 내려지면 검증된 Fumadocs 레시피는 `fuma-static/`에 있다(정적 템플릿, `remarkMdxMermaid`, `multilingual`, Google 폰트 제거, `.md` 출력) + Pages 크기 한도 상향.

## 산출물 — scratchpad `docs-site/`
`fuma-static/`(21p 앱 + `out/` 11 MB), `fuma-offline-ci/`, `npm-cache/`(555 MB), `npm-cache.tgz`(224 MB), `gen_wiki.py`, `search-test.mjs`, `build1–9*.log`, `dom-2-2.html`, `shot-*.png`, `mkdocs-test/`(Material 9.7.7 + privacy + offline + llmstxt 빌드).
