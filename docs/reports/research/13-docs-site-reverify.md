---
status: 실측 완료 (2026-09-09) — 동일 300페이지 한국어 샘플 위키를 MkDocs Material 9.7.7, Zensical 0.0.60, Fumadocs 16.15.8, Starlight 0.42.0으로 오프라인 빌드하고 헤드리스 Chrome으로 측정. 보고서 전문 `13-scripts/report.html`(artifact https://claude.ai/code/artifact/cfae4c4b-4c2f-479a-8fca-0a0c3fb4ffed), 원자료 `report-*.json`, 스크린샷은 scratchpad `docs-site/shots/`
scope: 읽기 UX 1순위, air-gap 빌드와 `file://` 동작은 통과/불통과, 유지보수 3순위로 사이트 생성기 재판정
---

# 사이트 생성기 재검증 (읽기 UX 1순위, 서빙 없음)

## 판정
**MkDocs Material 9.7.7**(offline 플러그인, self-host Mermaid, mkdocs-panzoom-plugin). **Zensical**이 같은 `docs/` 트리로 같은 UX와 같은 `file://` 통과를 내는 후계로 검증됐다.

**결정 측정은 `file://`이지 air-gap이 아니다.** 이전의 "air-gap 비용 때문에 MkDocs"라는 논거는 틀렸다. 넷 다 벤더링 뒤 egress 0으로 빌드된다(Fumadocs 10.4 s, Starlight 5.0 s, MkDocs 3.7 s, Zensical 2.3 s). 오히려 MkDocs가 우회가 가장 많았다(`font: false`, 테마 번들이 unpkg를 하드코딩해 `privacy.assets_exclude: unpkg.com/*` + `extra_javascript`로 mermaid 직접 로드, iframe-worker shim을 `extra.polyfills`로 벤더링).

파일시스템에서 열었을 때: MkDocs와 Zensical은 탐색, Mermaid, 다크, 검색이 끝까지 동작하고 실패 요청 0. Starlight는 `astro-relative-links`(마지막 릴리스 2024-12) + `build.format: 'file'`이 필요하고 그 뒤에도 Pagefind가 죽는다(절대 경로 `/pagefind/`). Fumadocs는 HTML과 RSC에 `/_next/`, `/docs/` 절대 경로가 박혀 그대로 실패한다.

**HTTP로 서빙하면 읽기 UX는 Starlight가 1위다**(UX 소계 Starlight 42, Fumadocs 35, MkDocs 32, Zensical 30). 페이지당 324 KB vs MkDocs 1,114 KB(페이지마다 mermaid.min.js 3.4 MB 즉시 로드). 한국어 검색은 MkDocs lunr가 조사를 못 다뤄 `컴포넌트`, `퍼거토리` 0건, Starlight와 Fumadocs는 전부 적중하고 구 검색이 정확 페이지로 간다. axe 위반 0. 서빙이 범위에 들어오면 판정은 Starlight로 바뀌며 전환 비용은 `gen_wiki2.py`의 emitter뿐이다.

다이어그램 가독성은 셋 다 "18–28%로 축소, 줌 필요"로 동률(MkDocs 688/3,791 px, Starlight 1,060/3,728 px). Fumadocs만 원 크기 + 가로 스크롤. MkDocs의 줌은 유지되는 플러그인이고 Starlight와 Fumadocs는 약 40줄 오버레이를 직접 썼다.

## 유지보수
Material EOL 2026-11-05(57일, 그때까지 critical/security만). Zensical 0.0.60 알파, privacy/llmstxt/panzoom 없음, 1.0 일정 없음, 그러나 동일 트리 빌드와 `file://` 통과. Fumadocs bus factor 1(사람 커밋 약 5,300 중 5,222), Next 16/React 19.2 필수, `@fumadocs/base-ui`는 별도 Base-UI 빌드. Starlight는 Astro 코어 팀, 0.x 마이너 breaking 월 1회 수준, Astro 메이저 12–15개월(7.0은 6.0 뒤 3.5개월).

Fumadocs 300페이지 산출 217 MB(RSC `.txt`; 92 MB로 줄이면 탐색이 전체 리로드로 후퇴, 검증).

## 산출물
스크린샷 48장 + drawer/zoom/search/file:// 샷(`{mkdocs|fuma|starlight|zensical}-{index|deep|heavy}-{light|dark}-{desktop|mobile}.png`), `report-*.json`, `tools/`. 미검증: Zensical panzoom과 breadcrumbs, Starlight `file://` 다크 토글, `search.separator` 한국어 완화.
