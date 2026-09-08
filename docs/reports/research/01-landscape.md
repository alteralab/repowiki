---
status: 조사 완료 (2차 자료 포함, 각 표에 출처 명시)
date: 2026-09-08
scope: repo URL → wiki 생성 도구 지형 (DeepWiki, OSS 클론, 논문)
---

# Repo-URL → Wiki/Architecture-Doc Generators (DeepWiki-style): Research Report

Star counts pulled live from the GitHub REST API on 2026-09-08; "unknown" where not verifiable.

## 0. Executive summary

- **DeepWiki (Cognition)** is closed-source. Public: fixed page taxonomy (numbered Overview → subsystem sections → per-module pages, ≤30 pages standard / 80 enterprise), inline Mermaid, line-range citations, "Last indexed" stamp, 2-day refresh throttle, MCP server (`read_wiki_structure`, `read_wiki_contents`, `ask_question`), `.devin/wiki.json` steering file. Effort levels 0 / ~5-10 / ~20-40 ACUs per wiki. Internal pipeline not documented.
- Three OSS architectures: (a) RAG-over-chunks + LLM-planned XML outline (deepwiki-open 17.9k); (b) agentic tool loop with bounded read/grep/list (OpenDeepWiki 3.6k, OpenWiki 16.2k, Hermes code-wiki, Mintlify); (c) static dependency graph → hierarchical decomposition → recursive sub-agents (CodeWiki 1.7k ACL 2026; deepwiki-rs 1.7k; RepoDoc; MemDocAgent). Benchmarks (CodeWikiBench, MemDocAgent) rank (c) > (a).
- Cheapest proven importance ranking: **aider repo map** — tree-sitter `tags.scm` def/ref → file MultiDiGraph → personalized PageRank with identifier multipliers → binary search to token budget (§4.1).
- Recurring failures: hallucinated architecture from stale identifiers, big-file coverage skew, broken Mermaid, context overflow, refresh not re-pulling, bogus bug reports to maintainers. Shipped mitigations: citation-mandatory prompts with path validation, AST-validated graph → deterministic Mermaid compiler (gitdiagram), parser-in-the-loop Mermaid repair (GenAIScript, CodeWiki, OpenWiki, mermaid-fixer), evidence-versioned Claims (OpenWiki), memoized per-file summaries (CocoIndex), dependency-order traversal with shared memory (MemDocAgent).

## 1. Cognition DeepWiki — public facts

| Item | Detail | Source |
|---|---|---|
| Launch | 2025-04-25; 50,000+ public repos pre-indexed | https://cognition.com/blog/deepwiki |
| Compute cost | "$300K" — secondary reporting only | https://news.ycombinator.com/item?id=43859649 |
| MCP (2025-05-22) | `https://mcp.deepwiki.com/{sse,mcp}`; tools `read_wiki_structure`, `read_wiki_contents`, `ask_question` | https://cognition.com/blog/deepwiki-mcp-server |
| Steering file | `.devin/wiki.json`: `repo_notes[]` (≤10,000 chars, ≤100), `pages[]` (`title`,`purpose`,`parent`,`page_notes`); if present, exactly those pages | https://docs.devin.ai/work-with-devin/deepwiki |
| Page limit | 30 (80 enterprise) | same |
| Effort/cost | Low free; Medium ≈5-10 ACU; High ≈20-40 ACU | same |
| Refresh | "Last indexed <date> (<sha>)"; 2-day min window; weekly auto if badge in README | https://howworks.ai/blog/deepwiki-vs-greptile-vs-reading-it-yourself |
| Hallucination stance | "minimized through tuning"; snippets shown for verification | https://news.ycombinator.com/item?id=43796308 |

Observed page structure (deepwiki.com/AsyncFuncAI/deepwiki-open): numbered outline `1 Overview → 1.1 Getting Started, 1.2 Docker & CI/CD → 2 Backend Architecture → 2.1…2.6 → 3 RAG Pipeline → 4 Frontend → 5 API Reference → 6 Testing → 7 Glossary`. Overview: capability table, "System Data Flow" Mermaid, key components, deployment. Citations inline `[api/main.py64-72](url#L64-L72)` + per-section "Sources" list. Diagram nodes clickable.

Large repos: HN reports on LLVM — "over-emphasizes large single files while missing distributed components", omitted InstCombine/GlobalISel/TableGen (https://news.ycombinator.com/item?id=45002092). MemDocAgent measured ~50% source-file retrieval overlap and ~13% cross-page inconsistency in DeepWiki output (https://arxiv.org/abs/2605.14563).

## 2. OSS clones and alternatives

| Tool | Stars | Lang | License | Last push | Core approach | AST/LSP | RAG | Mermaid validation | Large-repo/cost | GitLab self-hosted | Output |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AsyncFuncAI/deepwiki-open | 17,915 | Py+TS | MIT | 2026-09-03 | LLM plans XML outline; per-page RAG | text only | FAISS 350w/100 overlap, top_k 20 | none server-side | skip files >81,920 tok; 8-12 / 4-6 pages | `oauth2:<token>@host` clone | web app + md/json export |
| AIDotNet/OpenDeepWiki | 3,579 | C#+TS | MIT | 2026-08-27 | agent loop; catalog tool + budgeted Read/Grep/List | text | no | unknown | `DocumentSourceToolBudget` read≤240 lines, list≤20, grep≤12 | any git URL | web, MCP, chat |
| FSoft-AI4Code/CodeWiki (ACL 2026) | 1,677 | Py | MIT (README; no LICENSE file) | 2026-09-07 | tree-sitter dep graph → topo → LLM clustering → recursive agents | yes, 10 langs, Tarjan SCC | no | yes, after each editor write | `--max-token-per-module` 36,369, leaf 16,000, depth 2-3; leaf pruning >400 | local path | `docs/` md + `module_tree.json` |
| langchain-ai/openwiki | 16,236 | TS | MIT | 2026-09-08 | DeepAgents planner → durable page-job queue → per-page worker → Claims with evidence `repo://path#L40-L82` + version | text (agent tools) | no | yes; failing fences → `text` fence w/ repair note | resumable `.run.json`; only stale-Claim pages regenerate | GitLab CI template | `openwiki/` md (OKF v0.2), AGENTS.md pointer |
| sopaco/deepwiki-rs (Litho) | 1,714 | Rust | MIT | 2026-08-14 | preprocess → research agents → C4 docs → verify | own extractors 12+ langs | no | JS sandbox + LLM repair (mermaid-fixer) | agent memory chunks | local | md |
| ahmedkhaleel2004/gitdiagram | 15,966 | TS | MIT | 2026-09-07 | LLM emits size-bounded JSON graph AST; server validates paths; deterministic AST→Mermaid compiler | tree only | no | by construction | rejects oversized inputs; cost endpoint | GitHub only | single diagram |
| bb-boy680/open-zread | 39 | TS | MIT | 2026-07-16 | 3-layer map: topology → most-imported signatures → on-demand AST | web-tree-sitter 14 langs | no | unknown | 100k LOC in ~5k tokens (claim); AST-hash cache | unknown | `Wiki/` md |
| OpenBMB/RepoAgent | 1,038 | Py | Apache-2.0 | 2024-12 (inactive) | Python AST + Jedi ref graph → topo order; pre-commit hook | Python only | add-on | n/a | git-diff incremental | local | md per file |
| potpie-ai/potpie | 5,715 | Py | Apache-2.0 | 2026-09-08 | tree-sitter → Neo4j graph → agents | yes | yes | n/a | graph queries | GitHub | CLI/MCP |
| DeusData/codebase-memory-mcp | 42,636 | C | MIT | 2026-09-08 | tree-sitter 162 langs → SQLite property graph → 15 MCP tools | yes | bundled | n/a | Linux kernel 2.1M nodes ~3 min | local | MCP |
| yamadashy/repomix | 28,241 | TS | MIT | 2026-09-07 | pack repo; `--compress` keeps signatures | compress only | no | n/a | per-file token counts | `--remote` | single file |
| coderamp-labs/gitingest | 15,404 | Py | MIT | 2026-09-02 | digest (summary, tree, content) | no | no | n/a | token summary | custom domains since v0.1.5 | text |
| cocoindex | 11,505 | Rust | Apache-2.0 | 2026-09-08 | incremental dataflow, per-file structured extraction, memo by content | no | no | unknown | 80-90% fewer LLM calls on edit | local | md + Mermaid |
| Google Code Wiki | closed | — | — | preview 2025-11 | regen per commit; diagrams; Gemini chat | unknown | unknown | unknown | unknown | no | web |
| Swimm | closed | — | — | active | deterministic static analysis → LLM only at generation | proprietary | no | unknown | static index | enterprise | docs in repo |
| Mintlify autodoc | closed | — | — | 2026 | analyze → JSON plan → parallel subagents → reconciliation | unknown | no | unknown | 70→45 min per large project | GitHub | site |
| Sourcegraph Cody | — | — | — | active | BM25 + SCIP; **dropped embeddings** | SCIP | removed | n/a | native index | yes | IDE |
| Hermes code-wiki skill | — | skill | — | 2026 | cap 8-10 modules by import freq+LOC, depth ≤3, `.codewiki-state.json` SHA | no | no | fence-balance + file-existence | scope caps | local | md tree |

### Pipeline details
- **deepwiki-open** (`api/services/wiki/prompts.py`): clone with token in URL (masked in logs) → `repo.json` exclusions → skip >81,920 tok → 350-word chunks → structure prompt returns `<wiki_structure>` XML (sections, pages with importance/relevant_files/related_pages) → page prompt requires `<details>Relevant source files</details>` ≥5 files, "Based ONLY on RELEVANT_SOURCE_FILES", `Sources: [path:start-end]()`. Gaps: one generic RAG query per page (#447), refresh reuses stale clone (#371), Mermaid errors only in browser (#437), embedder overflow (#468).
- **OpenDeepWiki**: CatalogTool/DocTool/GitTool wrapped by `DocumentSourceToolBudget`; separate `WIKI_CATALOG_*` vs `WIKI_CONTENT_*` model bindings.
- **CodeWiki**: `dependency_analyzer/` per-language tree-sitter; `topo_sort.py` Tarjan SCC; `leaf_selection.py` classes/structs, free functions when OOP <20%; prune >400; `cluster_modules.py` path-prefix batches; sub-agent only if module spans >1 file, depth<max, tokens ≥ leaf×depth; every write runs `validate_mermaid_diagrams`. Results 68.79% vs DeepWiki 64.06%; C/C++ 53.24%.
- **OpenWiki**: planner (read-only + `submit_plan`) → ordered durable page queue → non-delegating worker per page → `submit_page` with Claims; `--update` rechecks Claim evidence versions. Source drift mid-run invalidates plan.
- **gitdiagram**: LLM never writes Mermaid; JSON graph AST validated (IDs, connectivity, size, every path exists) → deterministic compiler with escaping.

## 3. Failure modes → mitigations

| Failure | Evidence | Mitigation seen |
|---|---|---|
| Hallucinated architecture / stale names | LibreOffice "Buck" build system; OpenWrt maintainer warning | static analysis first (Swimm); Claims w/ evidence (OpenWiki); "Do not infer" prompt; verify-before-diagram (Hermes); Verifier agent (DocAgent) |
| Big-file coverage skew | LLVM omissions | reference-graph ranking (aider PageRank, open-zread, CodeWiki entry points) |
| Cross-page inconsistency | MemDocAgent ~50% overlap, ~13% inconsistency; Mintlify contradictions | plan-first outline; dependency-order + shared memory; reconciliation sweep |
| Broken Mermaid | deepwiki-open #437; gitdiagram #29; GenAIScript blog | parser-in-loop repair; probelabs/maid lint `--fix`; AST compiler; prompt rules (labels ≤4 words, quote specials) |
| Context overflow | deepwiki-open #468; PR #273 | size skip; dir-grouped chunking; token thresholds + recursion; tool budgets; 3-layer map; page cap |
| Cost blowups | Devin 20-40 ACU; MemDocAgent loops | memoization (CocoIndex); incremental (RepoDoc −77% tokens); no-op skip; cheap model for bodies |
| Stale docs | 2-day window; refresh bug #371 | git-hook/CI diff-driven; provenance stamps; Claims re-verification |
| Maintainer externalities | bogus bug reports (HN) | "Last indexed"+SHA; link every claim; steering file |
| Non-deterministic maps break caching | aider #1874 | stable sort keys; refresh modes |

## 4. Aider repo map (verified from `aider/repomap.py`)
1. Tags via `tags.scm` (`name.definition.*`→def, `name.reference.*`→ref); Pygments backfill when no refs; diskcache by path+mtime.
2. `nx.MultiDiGraph` nodes=files; edge referencer→definer weight `mul*sqrt(num_refs)`; mul: ×10 mentioned, ×10 snake/camel & len≥8, ×0.1 `_`-private, ×0.1 defined in >5 files, ×50 referencing file in chat; def-only idents get 0.1 self-edge.
3. Personalization `100/num_files` for chat/mentioned files → `nx.pagerank(G, weight="weight")`.
4. Distribute rank over out-edges to `(definer_file, ident)`; sort by `(rank, key)` desc for determinism.
5. Binary search prefix to `map_tokens` budget (default 1,024; ×8 without chat files) within 15%.
6. Zero LLM calls. Standalone reimpl: https://github.com/pdavis68/RepoMapper.

Papers: RepoAgent https://arxiv.org/abs/2402.16667 · DocAgent https://github.com/facebookresearch/DocAgent · CodeWiki https://arxiv.org/abs/2510.24428 · MemDocAgent https://arxiv.org/abs/2605.14563 (completeness +15.9%, inconsistency −75.5%) · RepoDoc https://arxiv.org/abs/2604.26523 · Codebase-Memory https://arxiv.org/abs/2603.27277 · Agentless https://arxiv.org/html/2407.01489 · Sourcegraph dropped embeddings https://sourcegraph.com/blog/how-cody-understands-your-codebase.

## 5. Design lessons
1. Rank before you read (tree-sitter def/ref + PageRank); never file size as proxy.
2. Derive outline from dependency graph, LLM only names/clusters (CodeWiki recipe: topo → entry points → leaf selection → clustering, 36k/16k token thresholds, depth ≤3).
3. Generate in dependency order with shared memory, not N independent RAG calls.
4. Citations as hard contract; validate paths mechanically; store evidence versions per claim.
5. Never trust LLM Mermaid: compile from validated AST (gitdiagram) or parser-in-loop repair; degrade to `text` fence.
6. Budget every tool (read ≤240 lines, list ≤20, grep ≤12, call caps).
7. Skip/split deterministically; structural pass first, full source only for covered modules.
8. Incremental updates from day one: per-file/symbol hashes, run manifest with SHA, regenerate only changed pages; refresh must actually fetch.
9. Resumable, per-page durable runs.
10. Cap and steer page count; steering file (`.devin/wiki.json`, `INSTRUCTIONS.md`); mirror DeepWiki numbering.
11. Provenance on every page (Last indexed + SHA, generated/verified stamps, Sources list).
12. Split models by role; pre-run cost estimate; live meter.
13. Prefer graph/keyword retrieval over embeddings for Ask.
14. GitLab self-hosted = host + project path + token; never write token into cache keys or links.
15. Plain Markdown files + sidecar JSON tree first; web UI/MCP layered on top.

Caveats: Sourcegraph blog and Miraheze page returned 403 (claims from secondary excerpts); CodeWiki LICENSE file absent per API; "$300K" is secondary reporting.
