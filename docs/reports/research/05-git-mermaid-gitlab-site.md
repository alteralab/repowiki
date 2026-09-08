---
status: 조사 완료 — [verified locally] 실측(git 2.50.1, node 22, mermaid 11.17.2), [unverified] 미재현
date: 2026-09-08
scope: git 이력 채굴 · LLM Mermaid 검증 · GitLab self-hosted 반입 · 사이트 생성기
---

# Research: repo → Markdown wiki with Mermaid + git-history section

## A. Git history mining

### A1. Empirical numbers (apache/kafka trunk, 18,187 commits, `.git` 271 MB) [verified locally]
| Operation | Full clone | `--filter=blob:none` |
|---|---|---|
| clone `--single-branch` | 42.8 s (271 MB) | 10.1 s (56 MB, `--no-checkout`) |
| `git log --format=…` | 0.14 s | same |
| `git log --name-status --no-renames` | ~0.8 s | **0.84 s, zero blob fetches** |
| `git log --name-status` (default rename detection) | 1.1 s | **2 min 19 s** (lazy blob fetching) |
| `git log --numstat` | 14.6 s | fails/crawls without blobs |
| `git backfill` (git ≥ 2.49) | n/a | 40.9 s → 292 MB; then `--numstat` 14.7 s |
| `git shortlog -sn --no-merges` | 0.12 s | same |
| `git commit-graph write --reachable --changed-paths` | 1.3 s; `git log -- core/src/main/scala/kafka/server/` 0.085 s | same |

commons-cli (2,250 commits): blobless `--numstat` 33 s and aborted twice (`could not fetch <sha> from promisor remote`), vs 0.28 s full / 0.26 s after 2.6 s `git backfill`.

**`--numstat` needs blobs: yes.** `--name-only/--name-status` need tree diffs only — **but rename detection (on by default) pulls blobs; pass `--no-renames`** on blobless clones. `git backfill` (experimental, Git 2.49) exists for this.

| Mode | Full history? | `--numstat` | Notes |
|---|---|---|---|
| `--single-branch --no-checkout` | yes (one branch) | fast | only tags reachable from that branch: Kafka **2 tags vs 315 after `git fetch --tags`** |
| `--filter=blob:none` | yes | slow/flaky until backfill | best for metadata-only |
| `--filter=tree:0` | yes | very slow | CI-only |
| `--depth N` / `--shallow-since` | truncated | works in window | never fetch from shallow; breaks merge-base/tag reachability |
| `--filter=blob:limit=1m` | yes | big blobs lazy | good for repos with binaries |

Recommended: `git clone --filter=blob:none --no-checkout --single-branch URL && git fetch --tags && git backfill && git commit-graph write --reachable --changed-paths`.

### A2. Commands
```bash
git log --all --numstat --date=short --pretty=format:'--%h--%ad--%aN' --no-renames --after=2023-01-01 > repo.log   # code-maat git2
git log --format='%H%x09%aI%x09%aN%x09%ae%x09%s%x09%(trailers:key=Reviewers,valueonly,separator=;)' --no-merges
git shortlog -sne --no-merges --since="2 years ago" -- core/src/main/scala/kafka/server/
git shortlog -ns --group=trailer:reviewed-by
git log -M50% --diff-filter=R --name-status --format='%H %ad %s' --date=short
git log --numstat --format= --since="1 year ago" -- src/ | awk 'NF==3 && $1!="-" {a[$3]+=$1+$2} END{for(f in a) print a[f], f}' | sort -rn | head -50
git log --merges --first-parent --format='%H %s' v3.8.0..v3.9.0
git log --first-parent --format='%h %s' 3.8.0..3.9.0 | grep -oE '^([0-9a-f]+) (KAFKA-[0-9]+|MINOR|HOTFIX)'
```

### A3. Libraries
| Library | Notes | Verdict |
|---|---|---|
| `git` CLI subprocess | Kafka 18k commits `--numstat` 14.6 s; metadata 0.14 s | **default** |
| GitPython | subprocess per call, slow | glue only |
| pygit2 | fastest Python walk; diffstat slow (#894); install pinning pain | metadata walks |
| dulwich | pure Python, slower than pygit2 | fallback in locked-down envs |
| PyDriller | `ModifiedFile.complexity` via lizard; slowest | complexity half of churn×complexity on sampled files |
| commit-graph | always run after clone | ✔ |

### A4. Tools
code-maat (Clojure; `revisions/coupling/soc/age/entity-churn/main-dev/entity-ownership`; `-g` component grouping) — reference semantics, reimplement 3 analyses in Python; *Your Code as a Crime Scene* 2nd ed. (2024) — hotspot = change frequency × complexity (indentation proxy), temporal coupling, knowledge maps; hercules (heavy, burndown); git-of-theseus (survival chart); git-quick-stats (sanity); RefactoringMiner (Java, 40+ refactoring types, 99.6% precision); Githru (research); bus-factor (20 lines).

### A5. History content that earns its place
| Section | Computation |
|---|---|
| Module timeline | first commit touching each top-level dir (`--diff-filter=A`), rename bursts (`--diff-filter=R`) |
| Hotspots | revisions per file (12–24 mo) × LOC/indentation; top 10 per module |
| Temporal coupling | pairs co-changed in ≥k commits, coupling % = shared/avg(revs); filter commits touching >50 files |
| Ownership / bus factor | `git shortlog -sne -- dir`; main-dev share; 6-mo active authors; `Co-authored-by` trailers (squash hides) |
| Release → changelog | `git tag --sort=-creatordate`, `--first-parent` per tag, group by JIRA key |
| Issue/proposal links | Kafka: `KAFKA-\d+:`, `MINOR:`/`HOTFIX:`, `(KIP-\d+)`, `Reviewers:` trailers (10,835/18,187 subjects `KAFKA-`, 5,850 `MINOR`, 826 `KIP-`) [verified]; Spark `[SPARK-xxxx][COMP]`; Airflow: **no** issue numbers in titles today (CI hook rejects), older `[AIRFLOW-6107] [AIP-21]` |
| Activity trend | commits/year (Kafka 2023 1,474 · 2024 2,449 · 2025 2,184 · 2026 1,386 YTD) |

Link templates: JIRA `https://issues.apache.org/jira/browse/KAFKA-1234`; KIP index `https://cwiki.apache.org/confluence/display/KAFKA/Kafka+Improvement+Proposals`; PR `(#N)` → `https://github.com/apache/kafka/pull/N`.

### A6. Summarising 10k+ commits cheaply
1. Never feed raw commits. Kafka has only 42 merge commits (squash workflow) — use `--first-parent` + subjects (~60–80 tok/commit → 18k ≈ 1.2M tokens raw).
2. Bucket by release tag (`X.Y.0` only; quarter fallback) × top-level module (fast with commit-graph Bloom filters).
3. Map-reduce: map = per (module, release) summary from subjects + JIRA keys + file list (no diffs), pre-aggregated regex tables + ≤200 representative subjects; reduce = module timeline.
4. Diff-level only for events: rename bursts, hotspot top-5 commits, KIP commits.
5. Cost levers: Batch API −50%, prompt caching for stable prefix, `effort: low` for map stage. Rough Kafka: ~200 buckets × ~6k tokens ≈ 1.2M input.

## B. Mermaid diagrams generated by LLMs

### B1. Type × renderer
| Type | GitHub | GitLab self-hosted | MkDocs Material | Docusaurus | Obsidian |
|---|---|---|---|---|---|
| flowchart / classDiagram / sequenceDiagram / stateDiagram-v2 / erDiagram | ✔ | ✔ | ✔ themed | ✔ | ✔ |
| C4Context… | ✔ (v10+) | ✔ | works, not official | ✔ | ✔ |
| gitGraph, timeline | ✔ | ✔ | gitGraph not official | ✔ | ✔ |
| block-beta | mermaid ≥10.x/11 | GitLab 19.0+ | Material ≥9.5.34 | ✔ | ✔ |
| architecture-beta (v11.1+) | GitHub reported on 10.8.0 → likely no [unverified] | GitLab ≥19.0 | ✔ | ✔ | ✔ (11.13) |

GitHub **blocks `click` links** (strict securityLevel). GitLab: Mermaid 11 only from GitLab 19.0; `Cross-Origin-Resource-Policy` misconfig makes diagrams fail silently; char limit history 5,000 → 50,000. MkDocs Material: superfences; Mermaid 11 since 9.5.34. Mermaid defaults: `maxTextSize` 50,000, `maxEdges` 500, `securityLevel` strict, layout dagre (ELK optional). C4 experimental. architecture-beta needs iconify → won't render on GitHub/GitLab.

### B2. LLM syntax errors caught by real parser [verified locally, 36 cases]
| Pattern | Result | Prompt rule |
|---|---|---|
| `A[Broker (KafkaServer)]` | FAIL | always quote labels `A["…"]` |
| `start --> end` (`end` id) | FAIL | ids never `end`; label `["end"]` OK |
| `-->|fetch(offset)|` | FAIL | quote edge labels |
| quotes inside unquoted label | FAIL | `#quot;` inside quoted label |
| `class Cache<K,V>` | FAIL | generics `~K,V~` |
| stray fence inside diagram / prose after diagram | FAIL | one fence per diagram, nothing else |
| `participant end` | FAIL | reserved words |
| 600 edges | FAIL (limit 500) | ≤25 nodes, ≤60 edges |
| Korean/Unicode in quotes, `<br/>`, `%%{init}%%`, `classDef`/`:::`, `click` | OK | allowed |
| **Parses but wrong**: `subgraph End`, `A[Config; parse]`, `kafka.server.KafkaApis` as id, `default` id, `dev---ops` (`o` = circle edge), subgraph id == node id | OK | lint: ids `^[A-Za-z_][A-Za-z0-9_]*$`, no `;`/`.` in ids, subgraph id ≠ node id |

### B3. Validators [verified locally]
| Tool | Browser? | Accuracy | Notes |
|---|---|---|---|
| `mermaid.parse()` under **jsdom** | no | **matches real renderer** | 83 MB + 8 MB node_modules; 22 files in 0.97 s |
| `mmdc` | **yes** (Puppeteer/Chromium) | full render | `-p puppeteer-config.json` with system Chrome; Docker `minlag/mermaid-cli` |
| `@zabaca/mermaid-validate` | no (jsdom) | same, packaged CLI | not run |
| `@a24z/mermaid-parser` | no | **false positives** | do not use |
| `beautiful-mermaid` 1.1.3 | no | own parser, false positives; limited types | static SVG only, not validation |
| `mermaid-isomorphic` | yes (playwright) | full | same enterprise problem |
| `mermaid-py` | calls mermaid.ink (self-hostable via `MERMAID_INK_SERVER`) | — | network dependency |
| Kroki | server-side, self-hostable offline | full | GitLab can point at it |

Working script `scratchpad/mermaid-test/validate.mjs` (deps `npm i mermaid@11 jsdom dompurify`):
```js
import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { pretendToBeVisual: true });
globalThis.window = dom.window; globalThis.document = dom.window.document;
globalThis.DOMPurify = (await import('dompurify')).default(dom.window);
for (const k of ['navigator','HTMLElement','SVGElement','Element','Node','getComputedStyle','DocumentFragment'])
  if (!(k in globalThis)) globalThis[k] = dom.window[k];
const mermaid = (await import('mermaid')).default;
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', suppressErrorRendering: true });
function extract(p){ const s=readFileSync(p,'utf8'); if(!p.endsWith('.md')) return [{name:p,code:s}];
  const out=[]; const re=/```mermaid\s*\n([\s\S]*?)```/g; let m,i=0; while((m=re.exec(s))) out.push({name:`${p}#${++i}`,code:m[1]}); return out; }
let bad=0;
for (const f of process.argv.slice(2)) for (const {name,code} of extract(f)) {
  try { const r=await mermaid.parse(code,{suppressErrors:false}); console.log(`OK    ${name}  (${r.diagramType})`); }
  catch(e){ bad++; console.log(`FAIL  ${name}: ${String(e.message??e).split('\n').slice(0,3).join(' | ')}`); }
}
process.exit(bad?1:0);
```
Fix loop: validate → feed error back → re-validate (max 2) → fall back to bullet list.

### B4. Layout rules
15–25 nodes; split beyond 30–40; ≤3 nesting; subgraphs for real boundaries; `flowchart LR` for deps, `TB` for layers; `direction` in subgraph ignored when a node links outside; `%%{init: {"theme":"neutral"}}%%`; `classDef hot` for hotspots; `click` works in MkDocs/Docusaurus (`securityLevel: loose`), not GitHub — always emit a "Sources" link list under diagrams.

## C. GitLab self-hosted ingestion
| Need | Endpoint |
|---|---|
| Enumerate | `GET /groups/:id/projects?include_subgroups=true&archived=false&simple=true&per_page=100`; `/groups/:id/descendant_groups` |
| Metadata | `GET /projects/:id?statistics=true` → `default_branch`, `path_with_namespace`, `last_activity_at`, `statistics.repository_size`; id may be `group%2Fproject` |
| Languages | `GET /projects/:id/languages` → percentages [partially verified] |
| Tree | `GET /projects/:id/repository/tree?recursive=true&pagination=keyset&per_page=100` |
| File | `GET /projects/:id/repository/files/:urlenc_path?ref=` (base64), `/raw`, `/blame`; >10 MB files 5 req/min |
| Archive | `GET /projects/:id/repository/archive.tar.gz?sha=&path=` |
| Commits | `GET /projects/:id/repository/commits?ref_name=&since=&path=&with_stats=true&first_parent=true&trailers=true` |
| Tags / MRs | `/repository/tags?order_by=updated`; `/merge_requests?state=merged&order_by=merged_at` → `merge_commit_sha, squash_commit_sha, labels` |
| Wiki publish | `GET/POST /projects/:id/wikis` (`title`, `content`, `format=markdown`), `PUT/DELETE /wikis/:slug`, attachments; wiki also a git repo `….wiki.git`; `_sidebar` |
| Pages | job with `pages: true` publishing `public/` |
| Pagination | `per_page` ≤100; keyset via `Link: rel="next"`; >10,000 rows drops `x-total` |

```bash
git clone --filter=blob:none --no-checkout https://oauth2:$GITLAB_TOKEN@gitlab.example.com/group/proj.git
# CI: https://gitlab-ci-token:${CI_JOB_TOKEN}@…
```
```python
gl = gitlab.Gitlab(url, private_token=TOKEN, ssl_verify="/etc/ssl/corp-ca.pem", per_page=100)
for p in gl.groups.get(GROUP).projects.list(include_subgroups=True, archived=False, iterator=True): ...
proj.languages(); proj.repository_tree(recursive=True, ref=..., get_all=True); proj.files.get(file_path=".gitlab-ci.yml", ref=...).decode()
proj.wikis.create({"title": "Architecture/Overview", "content": md, "format": "markdown"})
```
`glab repo clone -g GROUP --include-subgroups --archived=false --paginate --preserve-namespace -- --filter=blob:none`.

Tokens: `read_api` + `read_repository` for reading; `api` needed to **write wiki**; clone `https://oauth2:<token>@…`; recommended: **group access token** for the 20 projects. Self-managed rate limits disabled by default (when on: 7,200 req/3,600 s; raw 300/min always on; 429 + `Retry-After`). Air-gapped: jsdom validator inside pre-built image with vendored node_modules; Kroki or `minlag/mermaid-cli` image mirrored; Bedrock PrivateLink `com.amazonaws.<region>.bedrock-runtime`; LiteLLM-style gateway.

GitHub side [verified]: `gh repo clone apache/kafka -- --filter=blob:none --no-checkout --single-branch`; `gh api repos/apache/kafka/languages` (bytes); GraphQL `languages(first:10,orderBy:{field:SIZE})`, diskUsage 312,193 KB. Permalinks: GitHub `…/blob/<sha>/path#L10-L40`; GitLab `…/-/blob/<sha>/path#L10-20` (**no second `L`**).

## D. Site generation
| Generator | Mermaid | Offline build & search | Notes |
|---|---|---|---|
| **MkDocs Material** | native superfences, Mermaid 11 since 9.5.34, dark mode | **privacy plugin** vendors CDN JS; **offline plugin** makes `file://` search work | mermaid2 plugin redundant/breaks dark mode |
| **Zensical** (Rust, Nov 2025) | built in | offline/search/tags native; reads `mkdocs.yml`; no `mike`; v0.0.x | write for Material now |
| Docusaurus 3 | `@docusaurus/theme-mermaid` | local search via `@easyops-cn/docusaurus-search-local` | React/MDX toolchain |
| VitePress | no native; plugins unmaintained | minisearch | — |
| mdBook | `mdbook-mermaid` copies js locally | elasticlunr | fully offline |
| Obsidian | native 11.13, `internal-link` class | app | toggle wikilinks off to emit MD links |
| GitLab Wiki | native per release | GitLab search | slugs spaces→hyphens, `/` → subdir |
| GitHub | native, no `click` | — | version lags |

Linking: plain **relative** Markdown links; citations `path/File.java:L10-L40` + permalink at analysed SHA; store `analyzed_commit` in frontmatter.

## Recommendations
1. Clone: `--filter=blob:none --no-checkout --single-branch` + `fetch --tags` + `backfill` + `commit-graph`. For the 20 internal repos just full-clone. Never `--depth` for history.
2. History: shell out to git (`--name-status --no-renames` ~1 s; `--numstat` once, 15 s Kafka; `-M --diff-filter=R --summary`); reimplement code-maat `revisions`, `coupling`, `main-dev`, `entity-ownership`; keep code-maat as test oracle.
3. History page: module timeline, top-10 hotspots per module, coupling pairs >30% / ≥5 shared, ownership & 6-mo active, changelog by JIRA/KIP/MR.
4. LLM budget: regex pre-aggregate, bucket tag × module, map-reduce ≤200 subjects, Batch API + cached prefix + low effort; diffs for <1% of commits.
5. Mermaid: restrict to flowchart/classDiagram/sequenceDiagram/stateDiagram-v2/erDiagram/timeline; prompt rules (quoted labels, safe ids, no `end`/`default`, ≤25 nodes, subgraph≠node ids, no `click` reliance); gate with jsdom `mermaid.parse`; reject `@a24z/mermaid-parser`/`beautiful-mermaid` as validators; `mmdc`/Kroki only for SVG output.
6. GitLab: group token (`read_api`,`read_repository`); enumerate via groups API; clone for history; publish wiki via API (`api` scope) and MkDocs Material site (`offline`+`privacy`) via `pages: true` job; vendor node_modules in runner image.
7. Site: MkDocs Material now, Zensical-compatible config; relative links + SHA permalinks.

Artifacts: scratchpad `mermaid-test/validate.mjs` + `cases/`, `cases2/`; `pc-test/` clones.
