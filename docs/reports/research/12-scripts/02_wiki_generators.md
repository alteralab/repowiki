# Multi-repo handling in code-wiki / documentation generators (subagent research, 2026-09-08)

## A. AI code-wiki generators
| Tool | Unit = single repo? | Multi-repo / org / system mode | Cross-repo relations | Sources |
|---|---|---|---|---|
| DeepWiki (Cognition, public) | Yes; deepwiki.com/<org>/<repo> | None found; "Add repo" one at a time; "free public version of Devin Wiki and Devin Search" | None documented; LLM-generated | https://cognition.com/blog/deepwiki ; https://deepwiki.com/ |
| Devin Wiki / DeepWiki for private repos | Yes; `.devin/wiki.json` per repo; max 30 pages (80 enterprise) | Repos indexed one at a time; enterprise "organizations" scope access; `bulk-index-repositories` v2 API exists; wiki scoping across repos not documented | Not documented; Devin Search cross-repo scope UNVERIFIED | https://docs.devin.ai/work-with-devin/deepwiki ; https://docs.devin.ai/work-with-devin/ask-devin ; https://docs.devin.ai/onboard-devin/index-repo ; https://docs.devin.ai/enterprise/getting-started/organizations ; https://docs.devin.ai/api-reference/v2/repositories/bulk-index-repositories |
| AsyncFuncAI/deepwiki-open | Yes | No; issue #66 "Deepwiki that bridges Multiple Github Repositories?" (2025-05-08) open, unanswered | N/A; LLM+RAG | https://github.com/AsyncFuncAI/deepwiki-open ; https://github.com/AsyncFuncAI/deepwiki-open/issues/66 |
| Google Code Wiki | Yes; "for each one [repository]" (announced 2025-11-13) | None; Gemini CLI extension for private repos forthcoming | LLM (Gemini) diagrams; no cross-repo | https://developers.googleblog.com/introducing-code-wiki-accelerating-your-code-understanding/ ; https://codewiki.google/ |
| langchain-ai/openwiki | Code mode = current repo (`openwiki --init`) | Two modes: code (one repo) and personal "brain" (connectors: MCP, Notion, Slack, Gmail, X, web, HN, LangSmith, local git repos). No multi-repo code mode | LLM agent; "Standard Markdown links between concept documents"; connectors deterministic fetchers | https://github.com/langchain-ai/openwiki |
| CodeWiki (arXiv 2510.24428) | Yes; repository-level, 7 langs | No | Hybrid: Tree-sitter dependency graph (deterministic) + LLM recursive decomposition; 68.79% vs DeepWiki 64.06% on CodeWikiBench | https://arxiv.org/abs/2510.24428 |

## B. Docs platforms with explicit multi-repo support
| Tool | Multi-repo mode | Cross-repo relations | Sources |
|---|---|---|---|
| Swimm | Workspace = many repos; "flows spanning across multiple repositories" with snippets/tokens/paths | Deterministic code coupling; CI check only for current repo | https://docs.swimm.io/features/multi-repo-content/ |
| Mintlify | Enterprise "multi-repository deployments": per-source Git connection + docs.json, combined into one site; agent references any repo with GitHub App | Deterministic config; root-relative links | https://www.mintlify.com/docs/deploy/multi-repo ; https://www.mintlify.com/docs/deploy/monorepo ; https://mintlify.com/docs/agent |
| Antora | playbook content.sources = git URLs + branches | Deterministic resource IDs version@component:module:family$file | https://docs.antora.org/antora/latest/playbook/configure-content-sources/ ; https://docs.antora.org/antora/latest/page/resource-id-coordinates/ |
| Backstage TechDocs | per entity, aggregated in catalog | `backstage.io/techdocs-ref` | https://backstage.io/docs/features/techdocs/ ; https://backstage.io/docs/features/techdocs/creating-and-publishing |
| Docusaurus | community plugin docusaurus-plugin-remote-content | URL list | https://github.com/rdilweb/docusaurus-plugin-remote-content |
| GitHub Copilot | Knowledge bases sunset 2025-11-01 -> Copilot Spaces (multi-repo context) | context only | https://github.blog/changelog/2025-08-20-sunset-notice-copilot-knowledge-bases/ ; https://docs.github.com/en/copilot/concepts/context/spaces |
| Sourcegraph Cody | Enterprise @-mention repositories | Q&A only | https://raw.githubusercontent.com/sourcegraph/docs/main/docs/cody/core-concepts/context.mdx |
| Atlassian Compass | component catalog, declared relationships | deterministic; compass.yml details UNVERIFIED (404) | https://support.atlassian.com/compass/docs/what-is-compass/ |

## C. Architecture / C4 diagram generators
| Tool | From code? | Static vs LLM | Sources |
|---|---|---|---|
| Structurizr on-prem | Java component finder per codebase; workspace extension for landscapes | deterministic | https://docs.structurizr.com/onpremises ; https://docs.structurizr.com/dsl/cookbook/workspace-extension/ ; https://docs.structurizr.com/java/component |
| IcePanel | manual C4; YAML/JSON imports | manual | https://docs.icepanel.io/core-features/model-imports.md |
| Multiplayer.app | runtime OpenTelemetry traces (2024 GA); current status UNVERIFIED | deterministic telemetry | https://www.multiplayer.app/blog/multiplayer-launches-ga-with-new-system-architecture-observability-features/ |
| Eraser Eraserbot / DiagramGPT | repo per "monitor" | LLM | https://docs.eraser.io/docs/eraserbot |
| CodeSee | acquired by GitKraken 2024-05-14; site 404 | static (historical) | https://www.gitkraken.com/blog/gitkraken-acquires-codesee |
| Swark | VS Code folder -> Mermaid | LLM | https://github.com/swark-io/swark |
| GitDiagram | one GitHub repo | LLM AST -> deterministic Mermaid compile | https://github.com/ahmedkhaleel2004/gitdiagram |

## Key findings
1. Every AI code-wiki generator surveyed is per-repository; none documents an org/system-level wiki or cross-repo relations.
2. Multi-repo aggregation exists only in deterministic docs platforms (Swimm, Mintlify Enterprise, Antora, TechDocs, Compass) where links are declared.
3. System-level diagrams spanning repos come from DSL/manual tools (Structurizr, IcePanel) or runtime telemetry (Multiplayer); LLM diagrammers are single-repo.
