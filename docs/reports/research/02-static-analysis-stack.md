---
status: 조사 완료 — [L] 로컬 실측, [W] 웹 출처, [U] 미검증
date: 2026-09-08
scope: ast-grep / Serena(LSP) / tree-sitter / SCIP / Joern 등 코드 분석 스택 선정
---

# Code-analysis stack research report

Legend: **[L]** verified locally (ast-grep 0.45.1, Serena 1.7.1.dev0), **[W]** cited web source, **[U]** unverified.

## TL;DR
- **ast-grep 0.45 = Tier-0 symbol extractor.** 28 built-in languages (Java, Kotlin, Scala, Python, TS/TSX, Go, C/C++, C#, Rust, Ruby, PHP, Bash, YAML, JSON, Markdown, HCL…) [L]. `--json=stream` on all commands; `outline` command (0.44+) gives per-file class/function/member digests. Apache Polaris (616 Java + 450 py + 13 kt, ~100k Java LOC): `ast-grep outline --json=stream .` **0.13 s**; `run -k method_declaration` over all Java **0.04 s** [L]. Caveats: patterns brittle (`class $N {…}` misses `public class A extends B`) → use `kind:` rules; `outline` drops members when given a directory and never fills Java member `signature` [L] → get signatures from `run -k method_declaration`.
- **Serena headless works but is an LSP orchestrator, not a batch indexer.** `serena project index` calls `textDocument/documentSymbol` per file → `.serena/cache/<lang>/document_symbols.pkl` [L, `cli.py:788-840`]. Pyright cold start ≈ 5 s for 1-file project [L]; a user reported ~11 h indexing 7,749 LLVM files [W issue #890]; JDT.LS default `-Xmx3G`, JDK 21+ [L]. Python API exists (`Project`, `LanguageServerManager`, `SolidLanguageServer.request_references/request_document_symbols/request_full_symbol_tree`) and HTTP `start-project-server` `POST /query_project` [L]. Use as **Tier 1** for reference graphs on selected symbols only.
- **Module dependency graph without compiling:** import statements via ast-grep (`import_declaration`, `import_from_statement`, `import_statement`, Go `import_declaration`) mapped to modules by build-file boundaries — 7,324 Java imports in 0.04 s [L]. SCIP needs a compiling build [W]. Joern `javasrc2cpg` works on uncompiled Java but JVM-heavy [W]. **CodeQL free CLI not licensed for private code** [W]. GitHub stack-graphs **archived 2025-09-09** [W].
- **Aider repo-map** = tree-sitter `*-tags.scm` → NetworkX MultiDiGraph → `nx.pagerank(personalization=…)` → binary search on token budget [W]; reproducible with `tree-sitter-language-pack` (371 grammars, `get_tags_query()`) [W].

## 1. ast-grep 0.45.1
Languages [L]: Bash, C, Cpp, CSharp, Css, Dart, Elixir, Go, Haskell, Hcl, Html, Java, JavaScript, Json, Kotlin, Lua, Markdown, Nix, Php, Python, Ruby, Rust, Scala, Solidity, Swift, Tsx, TypeScript, Yaml. Rejected: sql, toml, zig, ocaml, groovy, protobuf, dockerfile, vue, svelte. Custom languages via compiled `.so` in `sgconfig.yml` `customLanguages` [W].

Pattern syntax: `$VAR`, `$$$VAR`, `$_`; rule files with atomic (`pattern|kind|regex|nthChild|range`), relational (`inside|has|follows|precedes`), composite (`all|any|not|matches`); `constraints`, `transform`, `message` (interpolated → surfaces captured names in `scan --json`) [W/L].

JSON output [L]: `run --json=stream` → `text, range{byteOffset,start,end}, file, lines, charCount, language, metaVariables{single,multi}` (metaVariables only for patterns, not `-k`). `scan --json` adds `ruleId, severity, message, note, labels`.

`outline` [L/W]: `ast-grep outline [--json=stream] [--items auto|structure|exports|imports|all] [--type class,enum] [--match REGEX] [--pub-members] PATHS`. JSON `{path, language, items:[{role, symbolType, name, range, signature, astKind, isImport, isExported, members:[…]}]}`. Built-in outline rules for c, cpp, csharp, go, java, javascript, kotlin, markdown, php, python, ruby, rust, swift, typescript; **Scala → nothing** [L]. Directory input → `members` omitted; file input → members present but Java member `signature` empty [L].

Performance: TypeScript/src 10.8 s → 0.975 s after optimisations [W]; respects `.gitignore`; `--no-ignore vcs` [L]. Limits: no type resolution, no cross-file. Bindings: `ast-grep-py` (PyO3) `SgRoot(src,"python").root().find_all(kind=…|pattern=…)`; `@ast-grep/napi` [W].

Verified rules [L]:
```yaml
id: java-method
language: java
rule: { kind: method_declaration, has: { field: name, pattern: $NAME } }
message: "method $NAME"
---
id: java-types
language: java
rule: { any: [ {kind: class_declaration}, {kind: interface_declaration}, {kind: enum_declaration}, {kind: record_declaration} ] }
---
id: javadoc
language: java
rule: { kind: block_comment, precedes: { any: [ {kind: method_declaration}, {kind: class_declaration} ] } }
---
id: spring-route
language: java
rule:
  kind: method_declaration
  has: { kind: modifiers, has: { kind: annotation, pattern: "@$KIND($$$ARGS)",
         has: { kind: identifier, regex: "^(Get|Post|Put|Delete|Patch|Request)Mapping$" } } }
```
```bash
ast-grep run -l py -k function_definition,class_definition,import_statement,import_from_statement --json=stream .
ast-grep run -l py -p '@$APP.$METHOD($PATH)
def $F($$$): $$$' --json=stream .          # FastAPI/Flask routes
ast-grep run -l ts -k function_declaration,class_declaration,interface_declaration,lexical_declaration,import_statement --json=stream .
ast-grep run -l ts -p '$R.$M($PATH, $$$H)' --json=stream .   # Express/Nest
ast-grep run -l go -k function_declaration,method_declaration,type_declaration,import_declaration --json=stream .
ast-grep run -l go -p 'http.HandleFunc($P, $H)' --json=stream .
ast-grep run -l java -p 'public static void main(String[] $A) { $$$ }' --json=stream .
```

## 2. Serena 1.7.x
MIT; LSP backend (solidlsp) or JetBrains backend. Tools: `get_symbols_overview`, `find_symbol` (name-path `Class/method[0]`), `find_referencing_symbols`, `find_declaration`, `find_implementations`, `get_diagnostics_for_file`, `search_for_pattern`, memories [L].

Language servers: Java → Eclipse JDT.LS (auto-download vscode-java VSIX + JRE 21 + Lombok + Gradle, or upstream-JDTLS mode offline; JDK 21+; `jdtls_xmx` 3G) [L `eclipse_jdtls.py:66-166`]; Python → pyright (alt basedpyright/ty/pyrefly/jedi); TS → typescript-language-server; Go → gopls (**manual**); C/C++ → clangd (wants `compile_commands.json`); Kotlin → pre-alpha official LS; Scala → Metals (imports build on first use, `indexing_timeout: 180`); Rust → rust-analyzer (manual); + ~40 others [W].

Headless [L]: `serena project create [--index] PATH`, `serena project index [--language X] [--timeout F] PATH`, `index-file`, `health-check`. Index does **not** precompute references. HTTP: `serena start-project-server` → `GET /heartbeat`, `POST /query_project {project_name, tool_name, tool_params_json}` (read-only tools). Python API: `serena.project.Project.load`, `create_language_server_manager()`, `SolidLanguageServer.request_document_symbols / request_full_symbol_tree / request_dir_overview / request_references / request_referencing_symbols / request_definition / request_implementing_symbols / request_workspace_symbol` — not documented public API [U stability]. Config `.serena/project.yml`, global `tool_timeout: 240`.

Cost: pyright 1 file 5.0 s [L]; LLVM 7,749 files ~11 h [W #890]; Java Maven multi-module ~800 files, tools timed out 600 s (older v0.1.4) [W #937]; JDT.LS 299-project Maven import ~2 GB heap [W eclipse.jdt.ls#982]. Kafka-specific numbers **[U] not found**.

Verdict: targeted Tier-1 only — start LS once, `request_references` for top-N ranked symbols, stop.

## 3. Cross-file graph alternatives
| Tool | Langs | Needs build? | Output | Notes |
|---|---|---|---|---|
| tree-sitter + language-pack 1.16.2 (MIT) | 371 grammars; tags for Java/Kotlin/Scala/Py/TS/Go/C++ | no | DIY | `get_parser`, `get_tags_query`, `QueryCursor(query).captures(node)` [W]; `tree-sitter-languages` unmaintained |
| SCIP (Apache-2) | scip-java (Maven/Gradle/Bazel; Kotlin "less mature"; Scala via SemanticDB), scip-python (venv), scip-typescript (npm install), scip-go, scip-clang… | **yes** | `index.scip` → `scip print --json`, `expt-convert` → SQLite | best true cross-file for JVM if build compiles [W] |
| stack-graphs | Java/JS/Py/TS | no | Rust | **archived 2025-09-09** — avoid |
| Kythe | C++/Go/Java | yes | graphstore | heavy Bazel — avoid |
| universal-ctags (GPL-2) | ~50+ [U] | no | JSON Lines | no refs; covers Scala/Groovy |
| Joern (Apache-2) | c2cpg, javasrc2cpg (JavaParser, no compile), jimple2cpg, kotlin2cpg, gosrc2cpg, jssrc2cpg, pysrc2cpg… | no | `joern-export --repr ast|cfg|pdg|all --format dot|graphml|neo4jcsv` | JDK 19; multi-GB heap; ≥16 GB for >500k LOC — Tier 2 |
| CodeQL | many | yes | SARIF | **license forbids non-OSS codebases without GHAS** — not usable for GitLab projects |
| jdeps | Java classes | yes | text/dot | good package graph if build exists |
| JavaParser / Spoon | Java | no (Spoon noclasspath default) | AST | |
| grimp / import-linter (BSD-2) | Python | importable pkg | Graph API | |
| pydeps / pyan3 | Python | importable / no | JSON, dot | pyan3 "superficial" |
| dependency-cruiser / madge (MIT) | JS/TS | node_modules preferred [U] | json/dot/mermaid | |
| ts-morph | TS | tsconfig | API | Tier-2 precision |
| `go list -e -json -deps ./...` / goda | Go | toolchain, no build | JSON / dot | cheap and exact — Tier 0 when toolchain exists |
| Gradle `projects`/`dependencies`, Maven `dependency:tree -DoutputType=json` | JVM | resolves deps (network) | text/json | static alternative: parse `settings.gradle(.kts)` `include`, `pom.xml <modules>` |

Assessment: for a **module** dependency graph, import-statement graph (ast-grep) + static build-file parsing beats everything: zero build, sub-second, all target languages, modules = units architecture docs talk about. Precision loss (wildcard imports, reflection, DI) acceptable for docs. SCIP = upgrade path when a build is available; Joern only for call/data-flow on uncompilable Java.

## 4. Aider repo-map standalone
1. `get_tags(file)`: `<lang>-tags.scm` (aider ships 31 under `queries/tree-sitter-language-pack/`; kotlin/scala/typescript/php only in legacy `queries/tree-sitter-languages/`) [L]; `@name.definition.*`→def, `@name.reference.*`→ref; Pygments `Token.Name` fallback; diskcache keyed by path+mtime.
2. `nx.MultiDiGraph`; edge referencer→definer weight `mul*sqrt(num_refs)`; mul ×50 chat file, ×10 mentioned, ×10 ≥8 chars snake/camel, ×0.1 `_`-prefix, ×0.1 defined in >5 files.
3. `nx.pagerank(G, weight="weight", personalization=…, dangling=…)`, personalize `100/len(chat_files)`; `filter_important_files()` (README, LICENSE, pom.xml, build.gradle, package.json, pyproject, Dockerfile, `.github/workflows/*.yml`, `.gitlab-ci.yml`, Jenkinsfile, tsconfig, k8s yaml, openapi…) prepended [W special.py].
4. Binary-search tags to `map_tokens` within 15%; render with `grep-ast` `TreeContext`.

Example queries: Java `(class_declaration name: (identifier) @name.definition.class)`, `(method_invocation name: (identifier) @name.reference.method …)`; Python `(function_definition name: (identifier) @name.definition.function)`, `(call function: [(identifier) @name.reference.call (attribute attribute: (identifier) @name.reference.call)])`.

Recipe: `pip install tree-sitter tree-sitter-language-pack networkx`; `Query(get_language("java"), get_tags_query("java"))`; for batch docs, personalize on entry-point files instead of chat files **[U adaptation]**; per-file importance = PageRank ⊕ import fan-in ⊕ git churn [U heuristic].

## 5. Size / tokens / packing
- scc (MIT, Go): `scc --by-file --format json`, per-file complexity, fastest; tokei; cloc (GPL-2, slowest). None installed locally → pick scc.
- Tokens: tiktoken `o200k_base` for relative budgeting; Anthropic `count_tokens` free but rate-limited (5k/10k/20k RPM by tier), **Claude 4.7+/Fable tokenizer ~30% more tokens than earlier** — count with the model you use [W]. Rule: tiktoken locally, `count_tokens` once per final prompt.
- repomix `--compress --style json` (tree-sitter skeletons, ~70% cut, `--token-count-tree`); gitingest `ingest()` → (summary, tree, content). Neither adds structure beyond ast-grep.

## 6. Entry points / frameworks / config surfaces
- Java/Kotlin: `public static void main`; `@SpringBootApplication` + `SpringApplication.run`; `@RestController/@Controller` + `@*Mapping`; `@EnableScheduling` + `@Scheduled`; `@KafkaListener` [U]; picocli `@Command/@Option`.
- Python: `if __name__ == "__main__"`; FastAPI `@app.get…`, `APIRouter`; Flask `@app.route`; Django `urlpatterns`; click `@click.command/group` + `[project.scripts]`.
- TS/JS: Express `app.get/post`, `express.Router()`; NestJS `@Controller/@Get/@Module`, `NestFactory.create`; `package.json` `bin`/`scripts`.
- Go: `func main()` in `package main`; `http.HandleFunc`, `NewServeMux`; gin `r.GET`; cobra `cobra.Command`, `cmd/`.
- Config surfaces: `pom.xml <modules>`, `build.gradle(.kts)` + `settings.gradle(.kts)` `include`, `gradle/libs.versions.toml`, `pyproject.toml`, `package.json`/`tsconfig.json`, `go.mod`, `Cargo.toml`, `Dockerfile`/compose, `helm/`, `k8/`, `.github/workflows`, `.gitlab-ci.yml`, `Jenkinsfile`, `application.yml|properties`.
- Apache layouts [L]: Kafka (Gradle) `bin/ config/ docs/ core/ clients/ connect/ streams/ storage/ raft/ metadata/ server/ tools/`; Spark (Maven+sbt) `bin/ sbin/ conf/ core/ sql/ mllib/ python/`; Flink `flink-*`; Airflow `airflow-core/ providers/ task-sdk/ chart/`; Polaris `polaris-core/ api/ persistence/ runtime/ helm/ k8/`. Module = directory containing a build file.

## 7. Comparison table
| Tool | Languages | Install | Build? | Cross-file | Output | Speed | License |
|---|---|---|---|---|---|---|---|
| ast-grep | 28 (+custom) | pip/brew/npm single binary | no | no | JSON stream | 0.04–0.13 s / 100k LOC [L] | MIT |
| tree-sitter + pack | 371 | pip | no | DIY tags | own | fast | MIT |
| Serena | 40+ via LS | uvx; LS auto/manual download | JVM: LS imports build | **yes** | pickle/JSON/HTTP | 5 s … hours | MIT |
| universal-ctags | ~50+ [U] | brew | no | no | JSON Lines | fast | GPL-2 |
| SCIP | JVM/Py/TS/Go/C++ | coursier/npm/go | **yes** | yes | protobuf | build time | Apache-2 |
| Joern | C/C++/Java/Kotlin/Py/JS/Go… | JDK 19 | no | CPG | dot/graphml | slow, multi-GB | Apache-2 |
| CodeQL | many | download | yes | yes | SARIF | slow | **OSS-only w/o GHAS** |
| jdeps | Java classes | JDK | yes | package | text/dot | fast | GPL+CE |
| grimp/pydeps | Python | pip | importable | module | API/JSON | fast | BSD-2 |
| dependency-cruiser/madge | JS/TS | npm | node_modules pref. | module | json/dot/mermaid | fast | MIT |
| go list / goda | Go | toolchain | no | package | JSON/dot | fast | BSD/MIT |
| scc/tokei/cloc | any | brew | no | – | json | very fast | MIT/MIT/GPL-2 |
| repomix/gitingest | any | npm/pip | no | – | xml/md/json | fast | MIT |

## 8. Recommended stack
**Tier 0 — always, no build, seconds**
1. File tree + scc → language routing.
2. Build-file discovery → module list (settings.gradle include, pom modules, go.mod, pyproject, package.json workspaces) + aider important-files.
3. `ast-grep outline --json=stream <files>` (pass files, not dirs) for Java/Kotlin/Py/TS/Go/C++/C#/Rust/Ruby/PHP/Swift; fallback `run -k …` for Scala (`class_definition`, `object_definition`, `trait_definition`, `function_definition` [U]) and for full signatures.
4. Docstrings/Javadoc via `precedes`/`nthChild` rules.
5. Import graph via `-k import_*` → module DAG with NetworkX; external deps by prefix.
6. Entry points/frameworks via §6 patterns.
7. Ranking: aider-style PageRank over tags graph (or import graph + symbol fan-in) ⊕ git churn; personalize on entry points and build roots.
8. tiktoken budgeting; `count_tokens` on final prompt.

**Tier 1 — opt-in per repo (minutes; JDK 21 / gopls / node)**
- Serena: `serena project create --index`, Python API or `start-project-server` → references for top-K (100–300) ranked symbols. `jdtls_xmx` ≥ 4G for Kafka-class [U]; upstream-JDTLS mode in corporate network. Skip Kotlin (pre-alpha LS); Scala/Metals best-effort.
- Go: `go list -e -json -deps ./...` → Tier 0 when toolchain exists.

**Tier 2 — heavy, when a compiling build exists (CI)**
- SCIP indexers → `scip print --json` / SQLite. Joern for uncompilable legacy. Never CodeQL on GitLab projects.

## 9. Unverified
JDT.LS on Kafka; Serena per-symbol ref cost at scale on Java; ctags language count; `@KafkaListener` citation; dependency-cruiser without node_modules; exact Scala node kinds; whether outline `signature` empty for all languages.

## 10. Sources (abridged)
ast-grep docs (languages, pattern-syntax, rule-config, sgconfig, custom-language, py-api, js-api, outline blog, optimize blog, releases); Serena README/docs/CHANGELOG, issues #890 #937; eclipse.jdt.ls #982 #3202; tree-sitter-language-pack; py-tree-sitter QueryCursor; SCIP docs; stack-graphs; Kythe; ctags JSON; Joern docs; CodeQL LICENSE.md; jdeps; JavaParser; Spoon; ArchUnit; grimp; import-linter; pydeps; pyan; dependency-cruiser; madge; ts-morph; go list; goda; Gradle/Maven docs; aider repomap.py/special.py/queries; grep-ast; networkx pagerank; scc/tokei/cloc; tiktoken; Anthropic token-counting; repomix; gitingest; Spring/picocli/FastAPI/Flask/Django/click/Express/NestJS/net-http/gin/cobra docs.

Local artifacts: scratchpad `sgtest/`, `polaris-outline.jsonl`, `serena-py/.serena/`.
