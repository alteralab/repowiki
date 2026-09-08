# Codex 독립 검증 1차 (Phase 1 결정층, 2026-09-09) 원문

대상 커밋: `9242180 feat: 결정층 분석 파이프라인과 Mermaid 게이트`. 검증자는 파일을 고치지 않았다.
반영 결과는 `scripts/RUNLOG.md`의 "Codex 독립 검증 1차와 그 반영"에 있다.

The forwarded verification run completed. Here is the Codex verifier's report exactly as returned:

# Independent verification report

Scope: commit `9242180 feat: 결정층 분석 파이프라인과 Mermaid 게이트`. No files were edited.

## Findings

### Critical — deterministic output is not deterministic

1. **Package ownership is first-wins over nondeterministically ordered ast-grep output.**  
   [graph.py:47](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:47), especially line 53.

   `package_index()` uses `setdefault()`. Java packages commonly span multiple modules; whichever matching file ast-grep emits first becomes the package owner. Repeated analyses of the same checkouts produced:

   | Repository | RUNLOG module edges | Verification run 1 | Verification run 2 |
   |---|---:|---:|---:|
   | dubbo | 296 | 299 | 295 |
   | kafka | 159 | 164 | 129 |
   | kafka subsystems | 39 | 40 | 39 |

   This changes architecture facts and downstream subsystem grouping without an input change.

   **Minimal change:** build `package -> set[module]`; resolve an import only when ownership is unique or when the importing module provides an unambiguous module-local match. Otherwise record ambiguity. Sort all emitted records by a canonical tuple before folding.

2. **Global simple-name type resolution discards a large share of valid relations.**  
   [graph.py:111](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:111), [graph.py:120](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:120).

   Any production type name declared more than once is removed globally, even where the reference's module makes the target unique. Test declarations do **not** trigger this—the code correctly filters `is_test` at line 115—but duplicates across production files/modules do.

   Measured impact:

   | Repository | Duplicate names | Dropped refs to duplicate names | Uniquely recoverable in referencing module |
   |---|---:|---:|---:|
   | commons-cli | 3 | 86 | 0 |
   | dubbo | 160 | 7,416 | 2,937 |
   | kafka | 240 | 15,435 | 5,595 |
   | airflow | 364 | 3,474 | 1,128 |

   This materially depresses type edges, rankings, and flows. Simple type names also make distinct declarations indistinguishable in `TypeEdge.src/dst`.

   **Minimal change:** make the index multi-valued and resolve in order: exact module-local declaration, imported/package-qualified declaration, then repository-global unique declaration; refuse only if ambiguity remains. Use a qualified type identity such as module + path + name.

### High

3. **Owner assignment silently loses references outside all types and is unstable for equal ranges.**  
   [symbols.py:262](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/symbols.py:262), [symbols.py:283](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/symbols.py:283), [graph.py:128](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:128).

   Sorting by ascending span size is correct for ordinary nesting. However, equal-size/equal-range candidates retain ast-grep input order; the first is selected without detecting ambiguity. A reference outside every type gets `owner=None`, after which `type_edges()` silently skips it and does not increment `unresolved`. Thus the reported unresolved count understates loss.

   **Minimal change:** sort canonically by `(span length, start, end, qualified identity)` and return unresolved/ambiguous when the smallest enclosing range is tied. Count `owner=None` references that otherwise map to a supported edge kind.

4. **Mermaid degradation can still emit an over-limit diagram.**  
   [diagrams.py:65](/Users/angyojun/workspace/repowiki/src/repowiki/bundle/diagrams.py:65), lines 73–86.

   The shrinking loop stops at one node. If the header plus that node still exceeds `max_source_chars`, `_compile()` returns an invalid diagram, sometimes without a degradation reason. This contradicts the module's "meets the limit by degradation" safeguard claim and violates C-REPORT-4.

   **Minimal change:** after the loop, explicitly verify the limit. If one node cannot fit, return an empty/summary diagram that fits, or raise a typed compilation error. Never return an over-limit `Diagram`.

5. **Unsupported references are silently swallowed despite the extractor's fail-loud contract.**  
   [symbols.py:195](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/symbols.py:195), [graph.py:34](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:34), [java-ref-type.yml:3](/Users/angyojun/workspace/repowiki/src/repowiki/data/rules/java/java-ref-type.yml:3).

   The Java rule emits `ref.local_type`, but `_REF_TO_EDGE` recognizes `ref.type`, not `ref.local_type`. `_handler_for()` accepts every `ref.*`, so extraction does not fail; `type_edges()` then silently skips the unsupported message at line 126. `ref.call` is also accepted then silently omitted, although calls are intentionally unimplemented. This conflicts with the "unknown messages raise" docstring and C-REPORT-2/C-REPORT-4.

   **Minimal change:** align `ref.local_type` with the edge map and explicitly classify intentionally unsupported `ref.call` into a named unresolved/deferred count. Reject any other `ref.*`.

6. **Source-read failures are silently converted into zero line counts.**  
   [analyze_run.py:38](/Users/angyojun/workspace/repowiki/src/repowiki/pipeline/analyze_run.py:38), lines 43–47.

   An `OSError` is ignored; `build_profile()` then reports zero lines for that tracked source. This directly contradicts the file-level claim that failures are raised rather than replaced with empty facts.

   **Minimal change:** raise a typed error containing the relative path, or return a named partial-analysis result and make the CLI exit nonzero.

### Medium

7. **Python dotted-name collisions are silently first-wins.**  
   [graph.py:57](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:57), line 68.

   The pipeline currently supplies `git ls-files` order, and the non-git fallback is explicitly sorted, so this path is reproducible in current CLI runs. It is nevertheless order-dependent as a pure function and silently chooses the first module. Airflow contains **23 dotted names mapped by paths to multiple modules**.

   **Minimal change:** accumulate a set of owners and refuse ambiguous dotted names, using module-local resolution where possible. Sort inputs inside the function so its determinism does not depend on callers.

8. **Repeated `/src/main/` chooses the outermost source-set root.**  
   [structure.py:94](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/structure.py:94).

   `path.split(marker)[0]` uses the first occurrence. For `a/src/main/generated/src/main/java/X.java`, it derives `a`, not the closest enclosing source-set root.

   **Minimal change:** use `rsplit(marker, 1)[0]`, with the same handling for `/src/test/`.

9. **Flow selection is bounded but not fully deterministic, and its preference is opposite to the stated concern.**  
   [graph.py:271](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:271), especially line 279.

   It terminates: depth is capped at four and destinations are added to `seen`. The key `(dst_module != src_module, dst)` actually prefers **same-module** edges because `False < True`, not cross-module targets. Equal destinations retain input order, so different edge kinds/spans can change the chosen evidence.

   **Minimal change:** define the intended preference explicitly and sort by a complete canonical key, e.g. `(cross-module preference, dst module, qualified dst, kind, path, start, end)`.

10. **Entry-point owner lookup does not select the innermost enclosing type.**  
    [graph.py:262](/Users/angyojun/workspace/repowiki/src/repowiki/analyze/graph.py:262).

    It returns the first enclosing globally unique type. Nested classes can therefore attach an entry point to the outer type, and duplicate-name filtering can make an otherwise resolvable owner disappear.

    **Minimal change:** reuse the deterministic innermost-range resolver based on file-local, qualified declarations.

11. **Airflow's 699 entry points include demonstrable false positives.**  
    [py-entry-decorator.yml:5](/Users/angyojun/workspace/repowiki/src/repowiki/data/rules/python/py-entry-decorator.yml:5).

    The regex searches the entire decorator subtree, so `@click.option(... default=lambda: os.environ.get(...))` matches `.get(` and becomes a route. Three such `option` matches found in non-test sources. Many development/documentation CLI commands are also classified as product entry points; whether those are in scope is not represented.

    **Minimal change:** match the decorator callable/name node, not arbitrary descendant text, and represent or filter tooling/example scope separately.

## Parsing edge cases specifically requested

- `import static a.b.C.d;` becomes `a.b.C.d`; longest-prefix package resolution usually reaches `a.b`, but the member is not deliberately separated from the declaring class. Can resolve incorrectly if `a.b.C` is also a package key.
- `import a.b.*;` becomes `a.b`: the semicolon split and `.*` removal handle this input correctly.
- Requests explicit tests for both, including collision with a package named `a.b.C`.

## Test adequacy

The 13 unit tests are readable behavior-level tests, but cover narrow handcrafted examples. They pin basic exclusion counting, global ambiguity refusal, source-set discovery, and ordinary diagram degradation. They do **not** establish the contracts needed for SC-1.1, much less the rest of SC-1.

Required missing tests before treating SC-1.1 as met:
- Repeated identical analysis of a fixture with one package shared across modules must produce byte-identical facts.
- Package ambiguity must refuse rather than select the first ast-grep record.
- Duplicate production type names must resolve module-locally when unique and refuse when still ambiguous.
- A same-named test type must not invalidate a production type.
- Nested/equal-range/outside-type owner assignment, including unresolved counting.
- Python dotted-name collision with reversed input order.
- Repeated `/src/main/` and `/src/test/`.
- Static Java import and wildcard/double-semicolon import.
- Flow tie-breaking under permuted edge order, same-module versus cross-module preference, cycle termination, and maximum depth.
- A one-node Mermaid plan whose label alone exceeds the character limit.
- `ref.local_type`, intentionally unsupported `ref.call`, and unknown `ref.*`.
- Read failure must produce explicit failure rather than zero lines.
- Airflow-style decorator containing `.get(` inside its arguments must not become a route.
- End-to-end CLI behavior for zero diagrams, parser failure, partial read failure, and output reproducibility.

`tests/acceptance/` is empty, so SPEC's stated 1:1 acceptance mapping does not exist. SC-0 and SC-1 are therefore unverified by the project's own definition. SC-1.2–SC-1.7 also remain explicitly unmeasured in RUNLOG.

## Rule and boundary compliance

- **Subprocess ownership:** compliant — all subprocess calls confined to `adapters/{astgrep,git,node}.py`.
- **Analyze purity:** mostly pure, but `analyze/domain.py` reads YAML from the filesystem; the "analyze is pure" boundary doesn't hold literally.
- **Third-party boundary:** noncompliant with SPEC — `yaml` imported by `analyze/domain.py` and `pipeline/analyze_run.py`, `networkx` by `analyze/graph.py`, despite third-party imports being restricted to `adapters/`.
- **Machine absolute paths:** none embedded in reviewed implementation/data/tests.
- **Named boundary types:** major cross-layer payloads use Pydantic models; dynamic lookup indices remain dictionaries (reasonable); `_busiest_modules()` lacks parameter typing but not a material boundary defect.
- **Silent failure:** present in line-count reads, unsupported reference messages, ambiguous package/Python module ownership, and ownerless references.
- **C-REPORT-4:** violated by fail-loud comments in `symbols.py`/`analyze_run.py` and by the Mermaid degradation claim. Also, `languages.yml:2` claims unknown extensions are counted as `other`, but `build_profile()` simply omits them.
- **V-COMMENT-1:** several new docstrings rely on mutable `PLAN §...` locations rather than stating the contract locally; not self-contained under the verification rubric.
- **SC-1.7 provenance:** the model does not demonstrate "every fact has a span or is marked rendered." `Module`, `Subsystem`, and `FileRank` lack evidence spans/rendered provenance, so SC-1.7 cannot currently pass as written.

## Measurement verification

Read-only restrictions prevented `uv` cache initialization, pytest capture, and writing `/tmp/x`. Codex instead invoked the analysis functions directly in-memory, exercising git, ast-grep, extraction, graph construction, rankings, flows, and diagram compilation without writing files.

Stable counts reproduced exactly for files/modules/symbols/type edges/entry points/flows/diagrams:
- commons-cli: 143 / 1 / 795 / 223 / 0 / 0 / 3
- dubbo: 4,841 / 84 / 30,397 / 8,963 / 15 / 5 / 17
- kafka: 7,540 / 70 / 67,380 / 37,744 / 104 / 10 / 21
- airflow: 13,939 / 164 / 27,562 / 6,748 / 699 / 4 / 20

Module-edge counts did **not** reproduce and varied between identical runs (see finding 1). The 61/61 Mermaid claim is therefore evidence for parser acceptance of that particular run, not reproducibility. Kafka's 70 modules is plausible relative to the ~65 Gradle-module prior research; airflow's 699 entry points is inflated by confirmed decorator false positives; commons-cli's zero entry points is plausible for a library repo with no detected product `main`/framework route.

## Verdict

The deterministic layer is **not yet sound enough to serve as the sole factual foundation for the LLM layer**: identical inputs currently produce different module edges and subsystem facts, and global simple-name resolution silently drops thousands of recoverable type relations. The single highest-value fix is to replace every first-wins/global-simple-name index with a canonical, multi-owner, scope-aware resolver — module/package-local first, globally unique second, explicit ambiguity otherwise — and test byte-identical output under permuted extraction order.
