---
status: 실측 완료 (2026-09-08, macOS, git 2.50.1, ast-grep 0.45.1, serena 1.7.1, python 3.14, JDK 17) — "not measured" 항목은 미측정
scope: Apache 4개 레포(commons-cli · dubbo · kafka · airflow) 클론·크기·모듈·심볼·의존·이력·Serena·문서 실측
---

# Repo → Wiki pipeline: empirical profiling of 4 Apache repos

Date: 2026-09-08. Machine: macOS (Darwin 25.2), git 2.50.1, ast-grep 0.45.1, serena 1.7.1, python 3.14, JDK 17.
All work under `scratchpad/repos/`. Helper scripts in `scratchpad/scripts/`, edge CSVs in `scratchpad/edges-*.csv`, most-changed lists in `scratchpad/most-changed-*.txt`.

## 1. Clone cost (`git clone --filter=blob:none --single-branch`, run 4 in parallel)

| repo | clone wall | .git (blob:none) | worktree | files (excl .git) | full-clone .git (measured) |
|---|---|---|---|---|---|
| commons-cli | 2 s | 2.6 MB | 4.2 MB | 143 | 6.2 MB (3.3 s) |
| dubbo | 16 s | 31 MB | 62 MB | 4,847 | not measured |
| kafka | 23 s | 76 MB (96 MB after `fetch --tags`) | 174 MB | 7,540 | 271 MB (31 s) |
| airflow | 37 s | 230 MB | 438 MB | 13,908 | not measured |

Also: kafka `--depth 1` = 6.8 s, 20 MB .git. Nothing needed `--depth 1` fallback; blob:none was fast enough for all four. Note blob:none still downloads every blob at HEAD (for checkout), so worktree size ≈ full HEAD.

## 2. Size by language (script: `scripts/langstat.py`, 0–2 s per repo)

| repo | primary langs (files / lines) | src lines | test-vs-main (lines, primary lang) | src tokens chars/4 | src tokens tiktoken o200k (real) |
|---|---|---|---|---|---|
| commons-cli | Java 87 / 20.5k | 21k | Java test 10.7k / main 9.8k (52% test) | 209k | **183k** (4.59 chars/tok) |
| dubbo | Java 4,050 / 481k; XML 259 / 21k; Groovy 10; Proto 10 | 484k | Java test 176k / main 305k (37% test) | 4.6M | **3.77M** (4.90 chars/tok) |
| kafka | Java 6,178 / 1.56M; Scala 262 / 135k; Python 184 / 32k; MD 134 / 38k | 1.74M | Java test 892k / main 673k (**57% test**); Scala test 105k / main 30k | 19.8M | **16.2M** (4.88 chars/tok) |
| airflow | Python 7,844 / 1.62M; reST 1,739 / 265k; TS 1,097 / 156k; YAML 461 / 135k; JSON 433 / 119k; Go 65 / 17k | 1.83M | Python test 903k / main 719k (56% test); TS test 33k / main 122k | 18.1M | **15.9M** (4.52 chars/tok) |

Takeaways: chars/4 overestimates Java/Scala by ~20% (real ≈ chars/4.9) and Python by ~12%. Tests are >50% of source lines in kafka and airflow — excluding tests roughly halves LLM input. tiktoken over 6–9k files takes 7 s; fine.

"All text" tokens (including docs/config): commons-cli 272k, dubbo 4.9M, kafka 20.6M, airflow 25.3M (chars/4).

## 3. Build system & module structure

| repo | build | modules |
|---|---|---|
| commons-cli | Maven, single module, parent `commons-parent:105` | 1 (no `<module>`) |
| dubbo | Maven multi-module; **119 pom.xml** (depth 1: 14, depth 2: 84, depth 3: 20) | root pom lists 62 `<module>` entries, **with duplicates from `<profiles>`** (e.g. `dubbo-plugin/dubbo-mcp` appears 2×) → must dedupe and walk nested poms |
| kafka | Gradle, `settings.gradle` `include(...)`, `build.gradle` 4,424 lines, `gradle/dependencies.gradle` | 65 subprojects |
| airflow | uv workspace (`[tool.uv.workspace].members`, 141 pyproject.toml, 107 under `providers/`, 88 provider dirs), pnpm/npm for UI (10 package.json, no root workspaces field) | ~150 members |

**kafka modules (65):** clients, clients:clients-integration-tests, connect:{api,basic-auth-extension,file,json,mirror,mirror-client,runtime,test-plugins,transforms}, coordinator-common, core, examples, generator, group-coordinator, group-coordinator:group-coordinator-api, jmh-benchmarks, metadata, raft, server, server-common, share-coordinator, shell, storage, storage:api, streams, streams:{examples,integration-tests,streams-scala,test-utils}, streams:upgrade-system-tests-{0110,10,11,20…43} (**29 near-empty version-compat modules — noise for a wiki**), tools, tools:tools-api, transaction-coordinator, trogdor, test-common:{test-common-internal-api,test-common-util,test-common-runtime}.

**dubbo top-level modules (deduped):** dubbo-common, dubbo-remoting, dubbo-rpc (→ api, dubbo, injvm, triple), dubbo-cluster, dubbo-registry, dubbo-configcenter, dubbo-config, dubbo-serialization, dubbo-compatible, dubbo-dependencies-bom, dubbo-metadata, dubbo-metrics, dubbo-test, dubbo-maven-plugin, dubbo-spring-boot-project/{actuator, autoconfigure, 3-autoconfigure, compatible, starters, dubbo-spring-boot, actuator-autoconfigure}, dubbo-plugin/{qos, qos-api, auth, reactive, security, spring-security, spring6-security, native, compiler, filter-cache, filter-validation, rest-jaxrs, rest-spring, rest-openapi, triple-servlet, triple-websocket, mutiny, plugin-loom, mcp}, dubbo-demo/{api, spring-boot, spring-boot-idl, mcp-server}, dubbo-distribution/{all, all-shaded, apache-release, bom, core-spi}.

**airflow:** airflow-core, task-sdk, airflow-ctl, dev/breeze, devel-common, chart, shared/* (14 libs), providers/* (88 dirs; nested namespaces `providers/apache/*`, `providers/common/*`, `providers/microsoft/*`). Largest providers by non-test py lines: google 132k, amazon 66k, common 29k, microsoft 21k, apache 20k, cncf 14k, fab 11k, standard 10k.

## 4. Entry points (ast-grep, `--json=compact`)

| probe | commons-cli | dubbo | kafka | airflow | time |
|---|---|---|---|---|---|
| `public static void main($$$) { $$$ }` (java) | 0 | 11 (6 are `dubbo-compiler` generators + demo apps; 1 in a test) | 72 (MetadataShell, examples/*Demo, many `*Config.main` that print docs) | – | 0.04 / 0.17 / 0.46 s |
| grep `static void main(` files | 0 | 26 | 162 | – | – |
| `@SpringBootApplication` / `@RestController` / `@Configuration` / `@Component` | 0 | 6 / 1 / 88 / 17 | 0 / 0 / 0 / 0 | – | 0.9 s dubbo, 2.9 s kafka (7 patterns) |
| `bin/` CLI scripts | – | none | 45 (`kafka-*.sh`, `connect-*.sh`) | `[project.scripts] airflow = airflow.__main__:main`; 154 `scripts/` files w/ `__main__` | – |
| `if __name__ == "__main__": $$$` | – | – | – | 235 (scripts 154, dev 33, airflow-core 15) | 0.57 s |
| FastAPI routes `@$R.get($$$)` etc. | – | – | – | get 166, post 47, put 13, delete 28, **patch 9,967 (bogus)**, route 1 | 2.7 s (6 patterns) |
| Scala `def main($$$): Unit = $$$` | – | – | 5 | – | – |

Notes:
- ast-grep `main` count (72) < grep (162) for kafka because the pattern requires exact `public static void` order/no annotations; `static void main` alone matched 72 too, so the rest are Scala/`throws`-less variants? Not fully diagnosed — for entry-point detection use a `kind: method_declaration` rule with `has: {kind: identifier, regex: ^main$}` instead of a text pattern.
- `@$R.patch(...)` matched **9,906 `@mock.patch`** in tests. Route detection must constrain `$R` to router/app names (real counts: `router.get` 29, `app.get` 15, `task_instances_router.get` 10, `assets_router.get` 10, …) and skip test paths.
- Real route concentration: `airflow-core/src/airflow/api_fastapi/core_api/routes/public` (69), `execution_api/routes` (31), `core_api/routes/ui` (27).

## 5. Symbol extraction with ast-grep — counts and gotchas

| pattern | commons-cli | dubbo | kafka | grep baseline (kafka) |
|---|---|---|---|---|
| `class $NAME { $$$ }` | 27 | 668 | **170** | 7,691 class-decl lines |
| `public class $NAME { $$$ }` | 13 | 558 | 2,174 | |
| `class $NAME extends $B { $$$ }` | 2 | 59 | 52 | |
| `interface $NAME { $$$ }` | 0 | 32 | **42** | 696 |
| `enum $NAME { $$$ }` | 0 | 9 | 51 | 261 |
| `record $NAME($$$) { $$$ }` | 0 | 0 | 33 | 337 |
| YAML rule `kind: class_declaration|interface_declaration|enum_declaration|record_declaration` (`scripts/java-types.yml`) | – | – | **class 7,697 / interface 690 / enum 299 / record 336 = 9,022; 6,104 top-level (col 0)** | matches grep within 1% |
| `public $T $M($$$) { $$$ }` methods | 254 | 8,412 | 12,421 | |

Timing: text patterns ~0.2 s (commons-cli), 1.5 s (dubbo), 4.7 s (kafka, 10 patterns); the kind-based YAML scan over all of kafka = **1.1 s**. ast-grep uses all cores (1000%+ CPU).

Python (airflow): `def $F($$$): $$$` 43,742 + `async def` 1,938 = 45,680, but `kind: function_definition` = **62,931**. The gap is return-type-annotated defs (`def f() -> T:`) which the text pattern does not match. `class $C: $$$` 4,853 + `class $C($$$B): $$$` 5,224 = 10,077 = kind count exactly. 45,429 of 72k decls (63%) live in test paths.

Gotchas (Java): text patterns are *exact structural* matches — any modifier (`public/final/abstract`), annotation, generic `<T>`, `extends`, `implements`, or `throws` makes the pattern miss. `$$$` is needed for bodies and arg lists. `class $NAME` without a body parses as a class_declaration and matched only 414. Use `kind:` rules (optionally with `has:`/`regex:` constraints) for enumeration; use text patterns only for very specific shapes. `sg` alias prints a deprecation banner to stderr — call `ast-grep`. `--json=compact` output includes `metaVariables.single.NAME.text` and `range`, which is enough to build a symbol index without a language server.

## 6. Import → module dependency edges (`scripts/depedges.py`, regex on `import`, main sources only)

| repo | files | imports parsed | internal edges | time |
|---|---|---|---|---|
| commons-cli | 87 | 633 | 0 (single module) | 0.0 s |
| dubbo | 4,050 | 22,332 | 143 | 0.4 s |
| kafka | 6,440 (java+scala) | 40,980 | 86 | 0.6 s |
| airflow | 7,833 | 27,610 | 397 (310 unresolved) | 0.6 s |

ast-grep equivalent: `import $P;` over kafka = 78,917 matches in 0.85 s; `from $M import $$$` over airflow = 38,323 in 0.68 s. Regex is sufficient and simpler for imports; ast-grep adds nothing here.

Top-10 edges (CSV: `scratchpad/edges-<repo>.csv`, columns src_module,dst_module,import_count):

- **kafka:** streams→clients 1,796; connect→clients 1,102; server→clients 1,038; tools→clients 816; metadata→clients 772; group-coordinator→clients 531; core→clients 503; raft→clients 445; storage→clients 431; jmh-benchmarks→clients 308; (metadata→server-common 308; core→server-common 254). `clients` is the hub — everything depends on it.
- **dubbo:** dubbo-rpc→dubbo-common 1,110; dubbo-registry→dubbo-common 814; dubbo-config→dubbo-common 730; dubbo-remoting→dubbo-common 631; dubbo-cluster→dubbo-common 603; dubbo-rpc→dubbo-remoting 517; dubbo-metrics→dubbo-common 309; dubbo-cluster→dubbo-rpc 272; dubbo-plugin/dubbo-qos→dubbo-common 252; dubbo-metadata→dubbo-common 235.
- **airflow:** dev→dev/breeze 540; providers/google→providers/common/compat 323; airflow-core→task-sdk 217; providers/amazon→providers/common/compat 167; providers/amazon→airflow-core 162; providers/amazon→task-sdk 114; providers/google→airflow-core 99; providers/cncf/kubernetes→airflow-core 98; providers/edge3→airflow-core 97; providers/fab→airflow-core 94.

Bonus: kafka already ships **authoritative dependency rules** in `checkstyle/import-control*.xml` (18 files, 1,982 lines, 77 `<subpackage>` blocks in the main one) — a wiki can cite these directly.

## 7. Git history

| metric | commons-cli | dubbo | kafka | airflow |
|---|---|---|---|---|
| commits (single branch) | 2,250 | 8,900 | 18,187 | 40,856 |
| date range | 2002-06 → 2026-09 | 2011-10 → 2026-09 | 2011-08 → 2026-09 | 2014-10 → 2026-09 |
| unique authors | 77 | 730 | 1,643 | 4,355 |
| merge commits | 53 | 497 | 42 | 1,116 |
| tags via `--single-branch` | 15 | 74 | **2** (0.8.0-beta1, 2013!) | 9,288 (per-provider tags) |
| tags after `git fetch --tags` (5 s) | – | – | 315 (latest 4.4.0-rc0 2026-08-21, 4.3.1) | – |
| commits/yr (recent) | 2024: 438, 2025: 282 | 2023: 1,468, 2024: 720, 2025: 455 | 2024: 2,449, 2025: 2,184 | 2024: 4,858, 2025: 7,565 |
| top committers | Gary Gregory 829 (+135 as "Gary D. Gregory" — **needs identity merge**), dependabot 274, Henri Yandell 216 | dependabot 1,096, william.liangf 1,074, ken.lj 1,004, Albumen Kevin 906 | Matthias J. Sax 746, Ismael Juma 716, Jason Gustafson 655, Guozhang Wang 540, David Jacot 462 | Jarek Potiuk 5,059, Kaxil Naik 2,081, Maxime Beauchemin 1,029, Amogh Desai 957, Ash Berlin-Taylor 948 |
| JIRA key in subject | CLI-\d+ 7.9% | DUBBO-\d+ 11.0% | **KAFKA-\d+ 61.5%**, MINOR: 32.2%, KIP-\d+ 4.5% | AIRFLOW-\d+ 10.1% (pre-2020 only) |
| `(#NNN)` PR ref in subject | 14.8% | 58.1% | 72.2% | 86.9% |
| avg files/commit (last 5000) | – | 8.8 | 6.8 | 6.5 |
| test-only / docs-only commits (last 5000) | – | 5.2% / 1.1% | 20.2% / 5.9% | 5.5% / 9.5% |

Top most-changed files (`--name-only --no-renames`; full lists in `most-changed-*.txt`):
- kafka: build.gradle 888, core/.../KafkaApis.scala 798, KafkaConfig.scala 532, ReplicaManager.scala 512, TestUtils.scala 507, KafkaApisTest.scala 464, docs/upgrade.html 454, StreamThread.java 426, KafkaServer.scala 417, gradle/dependencies.gradle 415, …, checkstyle/import-control.xml 312, KafkaConsumer.java 342, KafkaAdminClient.java 310.
- airflow: .pre-commit-config.yaml 1,076, airflow/www/views.py 1,032 (deleted path), setup.py 999, README.md 827, airflow/models.py 729, pyproject.toml 726, ci.yml 693, Dockerfile.ci 681, Dockerfile 619, models/taskinstance.py 576. Historical paths dominate because the tree was reorganized (airflow/ → airflow-core/src/airflow/) — churn must be mapped through renames or restricted to a date window.
- dubbo: dubbo-dependencies-bom/pom.xml 1,006, pom.xml 739, ServiceConfig.java 237, ReferenceConfig.java 216, RegistryProtocol.java 164, RegistryDirectory.java 155, CommonConstants.java 143.
- commons-cli: pom.xml 328, src/changes/changes.xml 296, 3 GitHub workflow files 188/179/152, Option.java 111, HelpFormatter.java 98, CommandLine.java 87, DefaultParser.java 82.

### blob:none + git log: measured behavior (important)

| command on blob:none clone | result |
|---|---|
| `git log --name-only` (default, rename detection on) | **Triggers lazy blob fetches** (rename similarity needs content). commons-cli: 12 s, +66 blobs. kafka full history: 1 m 13 s; airflow: 2 m 20 s; dubbo: 1 m 27 s. Also emitted `fatal: ... is in the commit graph file but not in the object database ... could not fetch ... from promisor remote` errors (output still produced). |
| `git -c core.commitGraph=false log --name-only --no-renames` | **0 fetches**, 0 errors. commons-cli 0.04 s, dubbo 0.9 s, kafka 1.9 s, airflow 3.0 s. |
| `git log --raw --no-renames` | same, 0.07 s on commons-cli (+ a few tree objects) |
| `git log --numstat` (any renames setting) | needs every historical blob → one promisor round-trip per object. commons-cli **>9 min, killed** (full clone: 0.26 s). kafka `-200`: 1 m 14 s; `-2000`: 45 s (after warm-up), pack grew 331k→414k objects. **Not viable** on blob:none. |
| full clone kafka `--numstat` | 14.5 s for whole history; `-2000` 2.3 s; `--name-only` 1.2 s |

Recommendation: clone blob:none for speed, use `--name-only --no-renames -c core.commitGraph=false` for churn (file-touch counts), and skip line-level numstat or do it only from a full clone (kafka full clone is just 31 s / 271 MB — cheaper than any partial numstat). Add `git fetch --tags` (5 s) because `--single-branch` drops tags on release branches (kafka).

## 8. Serena (headless) — 15 min budget, ~12 min used

- `serena project index <dir>` auto-creates `.serena/project.yml` but **prompts interactively** ("Enable typescript (2.25%)? [y/N]") when it detects secondary languages → hung until killed (10 min lost). Headless fix: `serena project index <dir> --language java < /dev/null` (or pre-write project.yml).
- With that, commons-cli indexed in **56 s wall**, of which ~27 s was the first-time download of Eclipse JDT.LS (`~/.serena/language_servers/static/EclipseJDTLS`, **378 MB**, bundles its own JRE 21) and ~25 s the JDT.LS startup + indexing of 87 files. Exit code 0; JDT.LS process terminated cleanly. Memory: not measured (process was gone before sampling).
- Output: `commons-cli/.serena/cache/java/document_symbols.pkl` + `raw_document_symbols.pkl` (2.0 MB total), `project.yml`, `project.local.yml`. The pickles depend on the `solidlsp` package (not loadable from a plain python; must be read inside serena's venv).
- kafka/dubbo: **not measured** (timebox). Expectation: JDT.LS on a 65-module Gradle build will trigger a Gradle import (serena disables the wrapper by default: "Gradle wrapper disabled") — likely minutes and >2 GB heap; a Maven project (dubbo, 119 poms) will attempt m2e import. Practical only as an optional enrichment, not on the critical path. ast-grep `kind:` rules gave a full type/method inventory of kafka in ~1 s with zero setup, which covers most wiki needs.

## 9. Existing documentation inventory

| repo | README | docs | design/ADR | ASF files |
|---|---|---|---|---|
| commons-cli | 579 words | none (site generated from `src/site`, `src/changes/changes.xml` is the changelog) | none; 2 package-info.java | NOTICE.txt, LICENSE.txt, .asf.yaml (notifications, JIRA link/label), SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, RELEASE-NOTES.txt |
| dubbo | 618 words | `docs/` 1 md file (44 KB); 9 READMEs total | none in-repo (docs live on dubbo.apache.org); 5 package-info | NOTICE, LICENSE, .asf.yaml (GitHub wiki+issues enabled), SECURITY.md, CONTRIBUTING.md, licenseCheck.sh |
| kafka | 1,692 words | `docs/` 5.3 MB, 168 files, **112 md** (3.6 MB is images): design/, implementation/, streams/, operations/, security/, configuration/, getting-started/ | `docs/design/design.md` (12,192 words), `docs/streams/architecture.md` (1,665 words); **255 unique KIP-\d+ references** in code/docs; 73 package-info.java; 18 READMEs; `checkstyle/import-control*.xml` | NOTICE, LICENSE, LICENSE-binary, NOTICE-binary, licenses/, .asf.yaml (jira@ notifications), SECURITY.md, CONTRIBUTING.md, release/ |
| airflow | 4,923 words | 118 `docs/` dirs; airflow-core/docs 57 MB (rst: core-concepts, howto, database-erd-ref, migrations-ref, configurations-ref); `contributing-docs/` 10 MB, 49 rst incl. `17_architecture_diagrams.rst`, `31_task_execution_architecture.rst` (+ diagram-as-code .py) | `airflow-core/adr/lang-sdk`, `go-sdk/adr/000{1..5}-*.md`; **44 unique AIP-\d+ refs**; **AGENTS.md / CLAUDE.md (5,060 words, symlinked) and `.claude/skills/*`** already present | NOTICE, LICENSE (+119 per-provider LICENSE / 118 NOTICE), .asf.yaml (github_rulesets), GOVERNANCE.md, COMMITTERS.rst, CONTRIBUTING.rst, RELEASE_NOTES.rst |

## 10. Operational gotchas observed

1. **Lazy blobs + rename detection**: any `git log --name-only/--stat/--numstat` without `--no-renames` silently fetches blobs one promisor round-trip at a time (minutes) and, with the auto-written commit-graph, prints `fatal: ... commit graph file but not in the object database` errors. Use `-c core.commitGraph=false --no-renames`, or full-clone for numstat.
2. **Tags**: `--single-branch` on kafka yielded 2 tags (2013); release tags live on `x.y` branches → `git fetch --tags` needed (5 s, +20 MB).
3. **Author identity split** (e.g. "Gary Gregory" vs "Gary D. Gregory"; dubbo "william.liangf" vs "liangfei0201"); no `.mailmap` in any of the four repos. dependabot is the #1 or #2 committer in commons-cli and dubbo — filter bots.
4. **Test weight**: kafka Java test lines 892k vs main 673k; airflow py test 903k vs main 719k; 63% of airflow declarations are in tests. Largest source file is a test (`GroupMetadataManagerTest.java` 1.5 MB, `SharePartitionTest.java` 0.8 MB, `KafkaApisTest.scala` 0.7 MB). Exclude `src/test`, `tests/`, `*Test.java` early.
5. **Generated code**: kafka generates Java from 260 `*/resources/common/message/*.json` schemas via `generator/` at build time (not committed → the wiki will see `ApiMessage` types referenced but not defined); airflow commits generated artifacts: `airflow-core/src/airflow/ui/openapi-gen/` (1.4 MB, `*.gen.ts` = 29,959 lines), `generated/` (provider_metadata.json 0.6 MB), `ts-sdk/src/generated`, `go-sdk/.../genmodels/gen`, `v2-rest-api-generated.yaml`. dubbo has `dubbo-compiler/.../gen` (protoc plugin sources, not output). No `.gitattributes linguist-generated` markers anywhere → need our own exclusion list.
6. **Vendored code**: `airflow-core/src/airflow/_vendor`, `providers/google/.../_vendor` (each has vendor.md). None in kafka/dubbo.
7. **Symlinks**: airflow has 6 (CLAUDE.md → AGENTS.md, `.github/skills/*` → `.claude/skills/*`, `gradle.properties` in java-sdk examples); harmless but walkers must not double-count.
8. **Big/odd files**: `airflow/uv.lock` 3.3 MB, `ui/pnpm-lock.yaml` 324 KB, `chart/values.schema.json` 0.7 MB, docs GIFs 0.8 MB; kafka 7 `.jks` keystores, 47 png. Exclude lockfiles, images, keystores, `*.md5sum`.
9. **Non-UTF8**: 0 files in all four (source/config only). CRLF: 2 files in airflow, 0 elsewhere.
10. **Module-list noise**: kafka's 29 `streams:upgrade-system-tests-*` modules and `jmh-benchmarks`; dubbo's `<profiles>` duplicates and `dubbo-distribution`/`dubbo-demo`/`dubbo-dependencies-bom` (pure packaging); airflow's `dev/*`, `*-tests` workspace members. Need a "packaging/test/benchmark" classification of modules.
11. **Path churn**: airflow moved `airflow/` → `airflow-core/src/airflow/` and kafka is migrating `core` Scala → Java (core/src/main still 53 Scala vs 16 Java); history-based hotspots point at dead paths unless rename-followed within a bounded window.
12. **ast-grep patterns are brittle** (see §5); the `sg` alias is deprecated; `@$R.patch` traps on `mock.patch`.
13. **serena interactive prompt** blocks headless runs; JDT.LS download is 378 MB on first use; pickled cache needs serena's own Python env to read.
14. **macOS has no `timeout`** — scripts wrapping long tools need `scripts/run_timeout.py` (or `gtimeout`).
15. zsh globbing: unquoted `--include=*.java` fails with "no matches found"; quote it in scripts.

## Not measured (timebox)
- Serena on kafka/dubbo (JDT.LS memory/heap, Gradle/Maven import time).
- Full clone times for dubbo/airflow; `--numstat` on airflow/dubbo.
- Peak RSS of ast-grep / tiktoken runs.

## Artifacts
- `scripts/langstat.py` — per-language files/lines/chars/test-split/big-file/non-UTF8 report (JSON).
- `scripts/tokcount.py` — tiktoken (o200k/cl100k) token counts for source extensions.
- `scripts/gitstats.sh <repo> <jira-regex>` — commits, range, tags, committers, per-year, subject-pattern shares.
- `scripts/depedges.py <repo> java-maven|java-gradle|python <out.csv>` — module import edges.
- `scripts/java-decls.yml`, `scripts/java-types.yml`, `scripts/py-decls.yml` — ast-grep kind-based inline rules.
- `scripts/run_timeout.py` — timeout wrapper for macOS.
- `edges-{commons-cli,dubbo,kafka,airflow}.csv`, `most-changed-*.txt`, `repos/langstat-*.json`, `repos/clone-times.txt`, `repos/serena-cli*.log`.
