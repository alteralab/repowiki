---
status: 조사 완료 — 코드 직접 정독 (clone HEAD b5d2407 v0.5.0 / OKF spec HEAD ad30107)
date: 2026-09-08
scope: langchain-ai/openwiki 차용 목록, Google OKF 채택 판정
---

# OpenWiki and OKF: research report

## 0. Identity check — both exist, description accurate
| Claim | Verdict | Evidence |
|---|---|---|
| OpenWiki inspired by DeepWiki | True — launch post cites DeepWiki, AutoWiki, Karpathy's LLM Wiki | https://www.langchain.com/blog/introducing-openwiki-an-open-source-agent-for-repo-documentation (2026-07-01) |
| general-purpose memory for agents | True — "OpenWiki Brains" personal mode 2026-07-10 | https://www.langchain.com/blog/introducing-openwiki-brains-general-purpose-wiki-memory-for-agents |
| uses Google's OKF | True — OpenWiki 0.2 (2026-07-16) adopted OKF; 0.5.0 emits OKF v0.2. OKF published by Google Cloud Data Cloud team | https://www.langchain.com/blog/openwiki-0-2-adds-okf-support ; https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing (2026-06-13) |

| Repo | Stars | Lang | License | Created | Last push |
|---|---|---|---|---|---|
| langchain-ai/openwiki | 16,236 | TypeScript | MIT | 2026-06-22 | 2026-09-08 |
| GoogleCloudPlatform/open-knowledge-format | 344 | HTML/Python | Apache-2.0 | 2026-08-11 | 2026-08-21 |
| GoogleCloudPlatform/knowledge-catalog (`okf/` frozen) | 9,112 | TS | Apache-2.0 | 2026-05-04 | 2026-09-08 |

Namesakes: `vercel-labs/openwiki` (138, no OKF), `kdsz001/OpenWiki` (Rust desktop), `AIDotNet/OpenDeepWiki`. Ports: `openwiki-cc`, `openwiki-skills`, `pi-openwiki`, `okf-rs`.
Clones: scratchpad `repos/openwiki-langchain`, `repos/okf-spec`, `repos/openwiki-vercel`.

## 1. OpenWiki (langchain-ai) code reading
- 168 source files, 53,775 lines TS in `src/`, 52,233 lines tests. Node ≥22, `deepagents` 1.13.2 + LangChain 1.x, Ink TUI, MCP SDK, zod, yaml; `mermaid` + `jsdom` optional peers.
- Modes: `code` (writes `openwiki/` in repo), `personal` (`~/.openwiki/wiki`).
- Dogfood wiki: 21 concept pages across `architecture/ concepts/ integrations/ operations/ testing/ workflows/` + `quickstart.md`.

Module map (`src/`): prompts `agent/prompts/code.ts` (103), `agent/repository-prompts.ts` (231 planner+worker), `agent/prompt.ts` (202), `claims/guidance.ts`; lifecycle `generation/repository-run.ts` (1668), `run-state.ts` (`.run.json`), `page-jobs.ts`, `page-manifest.ts`; runtime `agent/index.ts` (2313), `docs-only-backend.ts` (sandbox FS writes only under `/openwiki`), `okf-middleware.ts`, `wiki-finalizer.ts` (299), `wiki-link-validator.ts` (514); Claims `claims/core/*`, `claims/evidence/repository/resolver.ts` (815); OKF `okf/frontmatter.ts` (854), `index-sync.ts`, `generated-provenance.ts`, `claim-sources.ts`, `claims-verification.ts`; Mermaid `mermaid/validate.ts` (237), `fences.ts`, `dom-shim.ts`; ingestion `ingestion/code-mode.ts` (AGENTS.md injection + CI); integrations `integrations/mcp/server.ts` (generation lifecycle MCP), installers for Codex/Claude Code/OpenCode/Cursor, `integrations/openwiki/SKILL.md`; visualizer `visualize/*`; evals `evals/ledger/`, `evals/deepswe/`.

### Pipeline (code mode)
**No AST, no tree-sitter, no LSP, no embeddings, no vector DB.** Discovery purely agentic (`ls/glob/grep/read_file`, `rg --files`).
1. `beginRepositoryRun` — source fingerprint (sha256 over tracked+untracked non-ignored files + `git rev-parse HEAD`), Claims preflight; `--update` returns `noop` or per-page **update windows** (pages grouped by `gitHead` in `openwiki/.page-manifest.json`, `changedPaths` from `git diff --name-only <baseline>..HEAD` + working tree + untracked).
2. Planner → `submitRepositoryPlan`: ordered queue of `PageJob {path,title,purpose,seedPaths,relatedPages,instructions}` in `openwiki/.run.json`.
3. Loop: fresh page-worker agent per page → `submitRepositoryPage` with sparse Claim decisions; durable only after Markdown + Claims + verification + manifest written; failed workers roll back.
4. `finishRepositoryRun` → deterministic finalizer: `mermaid` → `index_sync` → `link_validation` → `claims_sources` → `generated_provenance`. Source drift at finish handed to next `--update`.
No chunking/ranking; planner decides taxonomy; `seedPaths` are starting points.

### Grounded Claims
Sidecar `openwiki/.claims/<page>.json` = `{schemaVersion, pageVersion: sha256, claims:[{id, statement, evidence:[{resource:"repo://src/x.ts#L40-L82", version:"repo-lines-v1:sha256:<hash>:<base64 anchors>"}]}]}`. Resolver encodes content hash of cited span + first/last line hashes + 3 context lines each side for relocation. Stale claims force the page into next update. Projected into OKF frontmatter `sources: [{id, resource}]`, `verified: [{by: openwiki/0.4.3, at}]`. **Markdown body has no inline line citations.**

### Mermaid validation
`mermaid/validate.ts`: real `mermaid.parse` under jsdom shim; fallback heuristic (reserved `end`, `;`/`<>` in labels). Invalid fences degraded to ```` ```text ```` + `<!-- openwiki: mermaid parse failed ... -->`. CI installs `mermaid@11.16.0 jsdom@29.1.1`. Guidance in `skills/mermaid-diagrams/SKILL.md`.

### Storage / agent access
Plain files in `openwiki/` (md + `.claims/*.json` + `.page-manifest.json` + `.last-update.json` + transient `.run.json`), committed via PR/MR. Agents read via **file reads** — managed block injected into `AGENTS.md`/`CLAUDE.md`: `<!-- OPENWIKI:START --> ... optional just-in-time context, not required startup reading ... <!-- OPENWIKI:END -->`. **No "ask the wiki" MCP**; the MCP server exposes generation lifecycle only (`openwiki_begin/submit_plan/next_page/inspect_page_claims/submit_page/finish`). `openwiki visualize` graph + static export. Cron CI example `examples/openwiki-update.gitlab-ci.yml` opens MR via GitLab API (`GIT_DEPTH: "0"` required).

### Key prompts (verbatim excerpts)
Planner (`agent/repository-prompts.ts:44-90`): "Design the smallest complete repository-specific information architecture that helps a coding agent understand and safely change the system. Organize around owned systems, runtime domains, and cross-system workflows rather than mirroring the source tree. Use hierarchical paths … /openwiki/architecture/, /concepts/, /workflows/, /operations/, /integrations/, /testing/ … Include /openwiki/quickstart.md." "Explore before submitting the plan. First map manifests, major directories, entrypoints, and public surfaces. Then trace representative end-to-end control and data flows … avoid exhaustive file-by-file inventory."
Page worker (`:129-190`): "You own exactly ${job.path}. … Research deeply enough to explain the important responsibilities, entrypoints, mechanisms/control flow, relationships, state/lifecycle, invariants/failures, extension points, configuration/operations, and focused tests … Do not turn the page into a source-file inventory." "The page MUST begin with valid OKF concept frontmatter: type / title / description / tags. Do not author generated, verified, sources, timestamp …"
Claims (`claims/guidance.ts`): "Atomic means one coherent, independently falsifiable idea … materiality test: if the proposition were false, would it meaningfully change a reader's architectural model, implementation decision, operational expectation, or safe change plan? If not, omit it."
System (`agent/prompts/code.ts`): "Ground every important claim in source files, tests, existing docs, or git evidence you have inspected." "Do not read .env files." "Directory index.md files are generated deterministically after the run."
Diagram: "A stale diagram is a stale claim, not existing structure to preserve."

### Evals
`evals/ledger/`: replays git checkpoints, classifies claims supported/stale/invented/unverified (sample 88-91% supported, 2-3% hallucinated). `evals/deepswe/`: paired Codex runs with/without wiki (harness only).

## 2. OKF — what it is
- Google Cloud Data Cloud/BigQuery leads; v0.1 2026-06-13, v0.2 `SPEC.md` (1006 lines) https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md ; Apache-2.0; formalizes Karpathy's LLM Wiki gist.
- **Early draft**: v0.1→v0.2 breaking renames (`timestamp`→`generated.at`, body `# Citations`→frontmatter `sources`, §13.1); repo 4 weeks old, 6 commits; 2026-08-21 timestamps require UTC offset. Dataplex Knowledge Catalog ingest/export via `kcmd`.
- Core (§3-9): bundle = dir tree of `.md`; reserved `index.md` (no frontmatter except root `okf_version: "0.2"`), `log.md`. Concept = `.md` + YAML frontmatter, **only `type` required**; recommended `title`, `description`, `resource`, `tags`; types producer-defined; unknown keys preserved. Optional: `sources: [{id, resource, title, author, usage_count, last_modified}]`, `generated: {by, at}`, `verified: [{by, at}]` (trust tier: none→unverified, non-human→machine-confirmed, `human:<id>`→human-reviewed), `status: draft|stable|deprecated`, `stale_after`. Actor `<producer>/<version>`, `human:<id>`, `process:<id>`. Per-claim attribution = footnotes `[^id]`. Links = **standard markdown** (bundle-absolute recommended) — no `[[wikilinks]]`; untyped relations. Conventional headings `# Schema/# Examples/# Computation`. `type: Attested Computation` (§10) irrelevant to code wikis. No JSON Schema, no registry.
- Ecosystem: `scaccogatto/okf-skills` 378, `serradura/okf` 154 (Ruby CLI/MCP), `jyjeanne/okf-rs` 96 (**tree-sitter + LSP code→OKF generator with MCP**), `Awesome-OKF` 102, `oak-invest/kiso` 39, `aws-samples/sample-okf-llm-wiki` 26, `zosmaai/pi-llm-wiki` 561. "OKF-compatible" mostly = "frontmatter with `type`".
- Google's own reference agent prompt says "Never start a link with `/` (that breaks GitHub rendering)" — contradicting SPEC §6.1.

## 3. Borrow list
**Borrow**
1. Page taxonomy + planner prompt (`quickstart.md` + `architecture/ concepts/ workflows/ operations/ integrations/ testing/`, organized around owned systems not source tree, `relatedPages` at plan time).
2. Plan → per-page fresh worker → deterministic finalizer (indexes, link validation, mermaid, provenance) — resumable, LLM kept out of deterministic work.
3. Mermaid parse-and-degrade (real parser under jsdom; degrade to text fence with error comment) + label-safety rules.
4. Change-window update model: per-page `{gitHead, sourceFingerprint, pageVersion}` manifest; `git diff --name-only <baseline>..HEAD` per cohort; re-plan only affected pages.
5. Claims sidecar (simplified): `repo://path#Lx-Ly` + content-hash/context-anchor versions as staleness detector. Skip the sparse-reconciliation MCP protocol.
6. Frontmatter conventions: `type`, `title`, `description` (retrieval-oriented), `tags` (English even when prose localized), `generated`, `sources`.
7. AGENTS.md / CLAUDE.md managed block (`<!-- X:START/END -->`) pointing agents at the wiki as optional JIT context.
8. `INSTRUCTIONS.md` user-authored never-regenerated brief per repo.
9. LEDGER-style eval: replay git checkpoints, measure supported/stale/invented claim rates.

**Don't borrow**: DeepAgents/LangChain runtime, Ink TUI, 13-provider auth (~7k lines); personal-brain connectors; pure-agentic discovery without structural pre-pass (Apache-scale needs deterministic module graph/entrypoints first — cf. `okf-rs`); generation-lifecycle MCP as first step; full Claims reconciliation day one; OKF `sources` as the only citation surface (human GitLab readers want inline file/line links — do both); "Ask the wiki" MCP (OpenWiki has none; see `serradura/okf`, `okf-rs` `okf-mcp` for reference).

## 4. OKF verdict
| Criterion | OKF v0.2 | MD+frontmatter, `[[wikilinks]]` | DeepWiki-Open | llms.txt |
|---|---|---|---|---|
| GitLab wiki render | frontmatter shown in a box (harmless); std links OK; Mermaid v11 | same box; `[[Page]]` only in GitLab *wiki* | JSON/XML app model, needs own UI | one file |
| MkDocs | frontmatter → templates; `/abs` links break → use relative | needs wikilinks plugin | n/a | n/a |
| Agent retrieval | `description/tags/type` filters; `index.md` progressive disclosure; freshness fields | same minus standard names | importance + relatedPages ideas | entry index only |
| Ecosystem | 3 months; validators, one Rust generator, MCPs; no Obsidian/MkDocs native | mature | app mature | widely adopted |
| Stability | breaking renames within 5 weeks | stable de facto | n/a | stable |
| Lock-in | ~zero (MD+YAML, 1 required key) | zero | high | zero |
| License | Apache-2.0 | – | MIT | CC |

**Recommendation: adopt partially — OKF core (frontmatter schema + reserved `index.md`/`log.md` + standard-markdown links), not full v0.2 conformance, not data-analytics parts.** Cost near zero; buys interop with growing ecosystem and LangChain/Google alignment. Treat as convention validated by our own ~50-line check, not a dependency. Use **relative** links (as Google's reference agent does).

Keep: `type` (fixed vocabulary: `architecture-overview`, `module`, `workflow`, `data-model`, `operations`, `integration`, `testing`, `quickstart`), `title`, `description`, `tags`; `generated: {by: "<tool>/<version>", at}`; `verified: [{by: "human:<id>", at}]`; `sources: [{id, resource: "repo://path#L10-L40"}]` + `[^id]` footnotes + producer extension `commit`; `status`, `stale_after` optional; `index.md` per dir (deterministic, no frontmatter), root `log.md`, `okf_version: "0.2"` in root index. Body: own skeleton (Overview / Responsibilities / Key flows + Mermaid / Data & state / Configuration / Failure modes / Tests / Related).
Skip: `Attested Computation`, `runtime/parameters/executor/attester`, `usage_count/usage_window`, `resource` as canonical asset URI. Also emit llms.txt-style root index (`quickstart.md`).

## Sources
OpenWiki repo/blogs/X posts; https://antaoalmada.dev/posts/OpenWiki-and-OKF-Agent-Wikis/ ; OKF SPEC.md, Google Cloud blog, knowledge-catalog okf/, MarkTechPost 2026-06-16, GitBook explainer, HN 48643541 / 48810399; okf-skills, serradura/okf, okf-rs, Awesome-OKF, kiso, agent-wiki; Karpathy gist; deepwiki-open; vercel-labs/openwiki; GitLab Markdown docs; MkDocs meta-data; llmstxt.org.
