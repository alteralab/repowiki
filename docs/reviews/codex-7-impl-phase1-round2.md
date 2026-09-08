# Codex 독립 검증 2차 (Phase 1 결정층, 2026-09-09) 원문

대상 커밋: `9413029`. 반영 결과는 `scripts/RUNLOG.md`의 "Codex 독립 검증 2차 보고와 반영"에 있다.

# Second independent verification report

Scope: commit `9413029` against prior review of `9242180`. No files were edited.

Important execution note: the workspace is fully read-only, so the requested `/tmp/v1` and `/tmp/v2` directories could not be created, and `uv` could not initialize its cache. I instead ran the same `analyze_repo()` pipeline twice in memory and hashed the exact `model_dump_json(indent=2)` bytes that `write_facts()` writes.

During verification, the checkout was externally advanced to commits `f9023dc` and `0471f6a`. All verdicts below are pinned to `9413029`; later commits are not credited.

## Main findings

### 1. Kafka’s module-edge drop is partly a new correctness loss

At `9413029`, `resolve_dotted(..., home=...)` treats the importing module as the target whenever it is among the owners of a shared package. That is not valid: package ownership does not establish ownership of the imported class.

Using uniquely declared fully qualified types as an independent oracle:

- Kafka shared-package imports:
  - 1,866 real cross-module imports became unresolved.
  - 349 real cross-module imports were hidden as self-imports.
- A declaration-aware resolver produces 119 Kafka module-edge pairs, versus the recorded 109.
- Ten real module pairs are missing; no extra pairs appeared in this comparison.
- Largest loss: `storage → storage/api`, supported by 74 imports.
- Other missing pairs include `connect/mirror → connect/mirror-client` (7), `core → storage/api` (4), and `core → metadata` (4).

Dubbo shows the same problem:

- 1,202 real cross-module imports became unresolved.
- 301 were hidden as self-imports.

Therefore, `159 → 109` is not honestly characterized as merely “ambiguity is now refused.” Some false first-wins edges were removed, but real edges were also lost.

### 2. Module-local type resolution introduces proven wrong edges

`resolve_type()` uses only simple name and module:

```text
module-local unique → repository-global unique → refuse
```

It does not inspect the reference’s imports, package, lexical scope, or qualified identity.

Against explicit Java imports and same-package declarations:

| Repository | References with an independently identifiable duplicate-name target | Correct | Wrong local declaration | Still lost |
|---|---:|---:|---:|---:|
| dubbo | 4,515 | 1,807 | 91 | 2,617 |
| kafka | 8,538 | 3,516 | 57 | 4,965 |

Examples of wrong resolution include:

- Kafka `Converter.java` imports `org.apache.kafka.common.header.Headers`, but the resolver selects same-module `org.apache.kafka.connect.header.Headers`.
- Kafka `Worker.java` imports `org.apache.kafka.connect.health.ConnectorType`, but the resolver selects a same-module REST `ConnectorType`.
- Dubbo compatibility sources import `org.apache.dubbo.common.URL`, but the resolver selects the same-module compatibility `URL`.

The exact totals are a conservative heuristic because nested types complicate FQN construction, but the cited explicit-import counterexamples are definitive.

### 3. Airflow decorator handling regressed

At `9413029`, the new ast-grep rule emits zero `entry.decorator` records. All 281 recorded Airflow entry points are `entry.main`.

A Python `ast` recount found 278 non-test decorators whose callable attribute is one of `get`, `post`, `put`, `delete`, or `patch`, including clear FastAPI routes such as:

- `login_router.post`
- `app.get`
- `asset_state_store_router.get`
- `asset_state_store_router.put`

Thus `699 → 281` is not simply “decorator false positives removed.” The three known `.get()`-inside-argument false positives disappeared, but legitimate route decorators disappeared with them.

## Prior 11 findings

| # | Finding | Status | Evidence checked |
|---:|---|---|---|
| 1 | Nondeterministic package ownership/output | **Fixed** | Two complete in-memory analyses produced identical serialized hashes: dubbo `02d251…d22994` twice; kafka `43083a…f8686a` twice. Counts also matched both runs. Canonical scan ordering is at `analyze_run.py:76-81`; indices and emitted edges are sorted in `graph.py`. |
| 2 | Global simple-name type resolution drops recoverable edges | **Partial** | Type edges increased to dubbo 10,742 and kafka 41,342, confirming recovery. But `graph.py:153-168` uses only module-local/global uniqueness. Explicit-import comparison found 91 wrong dubbo and 57 wrong kafka selections, plus thousands still lost. Qualified identities remain absent. |
| 3 | Owner tie instability and uncounted ownerless refs | **Partial** | `graph.py:211-213` now counts `no_owner`; kafka reports 37. Ordinary nested ownership works. But `symbols.py:268-287` sorts only by range size and silently selects the first equal-range candidate. Upstream canonical order makes CLI output stable but does not detect ambiguity. |
| 4 | Single oversized Mermaid node can exceed limit | **Fixed** | `diagrams.py:73-87` degrades to the header and records a reason. `flowchart LR` alone passed both configured parsers as `flowchart-v2`. Unit test checks size but not parsing. |
| 5 | `ref.local_type`/`ref.call` silently swallowed | **Fixed** | `graph.py:202-207` explicitly counts them. Reproduced counts: dubbo calls 61,350/local types 24,871; kafka calls 163,780/local types 54,833. Unknown `ref.*` raises at `graph.py:208-210`. |
| 6 | Source read errors become zero lines | **Fixed** | `_line_counts()` raises `SourceReadError` with the path at `analyze_run.py:40-53`. No test pins this contract. |
| 7 | Python dotted-name collision is first-wins/order-dependent | **Fixed for determinism; correctness caveat** | `python_index()` sorts inputs and retains owner sets at `graph.py:64-80`; reversal test exists. Shared-name resolution is deterministic. The questionable `home` policy applies equally to Python and can still hide cross-module imports. |
| 8 | Repeated source set chooses outer root | **Fixed** | `structure.py:94-101` uses `rsplit(marker, 1)`. Unit test covers repeated `src/main`; repeated `src/test` remains untested. |
| 9 | Flow preference reversed and tie-breaking incomplete | **Partial** | `graph.py:376-388` now prefers cross-module hops and adds a mostly canonical key. There are no flow tests. The key omits `span.end_line`, so pure-function permutation can still choose different evidence for otherwise tied candidates. Simple-name owner keys also conflate unrelated types. |
| 10 | Entry-point owner not innermost | **Partial** | `_owner_type_at()` minimizes range size at `graph.py:351-363`. Equal-sized enclosing candidates are silently resolved lexicographically instead of treated as ambiguous, and the result remains only a simple name. No test covers this function. |
| 11 | Airflow decorator false positives | **Regressed** | Rule at `py-entry-decorator.yml:5-12` produces zero decorator entries. Airflow’s 281 entries are all `main`; Python AST finds 278 non-test route-like callable decorators. The false positives were removed by removing all positives. |

Summary: 5 fixed, 5 partial, 1 regressed.

## Determinism and reproduced measurements

Complete repeated runs at `9413029`:

| Repository | SHA-256, run 1/run 2 | Files | Modules | Subsystems | Symbols | Type edges | Module edges | Entries | Flows | Diagrams |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dubbo | `02d251…d22994` / same | 4,841 | 84 | 11 | 30,397 | 10,742 | 225 | 15 | 10 | 17 |
| kafka | `43083a…f8686a` / same | 7,540 | 70 | 40 | 67,380 | 41,342 | 109 | 104 | 10 | 21 |

These reproduce the RUNLOG table exactly and establish CLI-pipeline determinism for those inputs, though not correctness.

Function-level permutation is pinned for:

- Package index input reversal
- Python path input reversal
- Type-reference input reversal

Not pinned for flows, full `analyze_repo`, equal-range ownership, or diagram edge ties.

## Canonical sort semantics

The canonical sort in `analyze_run.py:76-81` does more than presentation ordering:

- It determines which equal-range type wins owner assignment.
- It determines entry-point order, flow IDs, and which flows survive the limit.
- It stabilizes downstream graph insertion order and score ties.

This is deterministic but converts unresolved semantic ambiguity into a reproducible arbitrary choice. The changed comment also says “Codex 5차 검증 지적,” which is mutable review history rather than a self-contained reason.

## Diagram empty-degradation path

The empty degradation source is `flowchart LR`, not an empty string. It is valid Mermaid:

- Site parser: pass, `flowchart-v2`
- GitLab parser: pass, `flowchart-v2`

The limit gate also passes it. However, the oversized-node test checks only limits, not the actual two-version parse gate.

## ResolutionCounts

The categories are mutually exclusive because processing stops at the first applicable branch:

1. test references excluded
2. deferred call
3. deferred local type
4. unsupported message raises
5. no owner
6. ambiguous/unknown
7. successful self-edge or emitted edge

They are not represented as a complete accounting total:

- `ResolutionCounts.total()` excludes `deferred_calls` and `deferred_local_types`.
- Successful self-relations and emitted edges are not counted.
- Test exclusions are not counted.
- `ambiguous` conflates local ambiguity and global ambiguity.

The six RUNLOG lines are explicit, but `total()` should not be interpreted as all non-emitted references.

## RUNLOG judgment

Accurate:

- Repeated dubbo/kafka output is byte-stable.
- Type-edge totals increased.
- Module-edge totals are reproducible.
- The explicit unresolved/deferred counts are real.
- The oversized diagram path now respects its character limit.

Overstated or misleading:

- “11 findings all fixed” is false: five are partial and the decorator fix regressed.
- “Module edges fell because ambiguous package ownership is no longer guessed” omits real-edge loss.
- “Airflow 699 → 281 = decorator false-positive removal” is false; all detected decorators were removed.
- “Module-local resolution revived edges” is numerically true but omits proven wrong-target edges.
- “Four repositories confirmed identical SHA” was not evidenced in the committed tests or durable artifacts; I independently confirmed only dubbo and kafka under the available target state.
- “Evidence violations 0 means SC-1.7 is satisfied” remains an overclaim because `Module`, `Subsystem`, and `FileRank` still lack spans/rendered provenance.
- The RUNLOG claims the fix followed the review’s module-local→global sequence, but the original recommendation also required imported/package-qualified resolution and qualified identities; those parts were not implemented.

## Tests

Commit `9413029` contains 29 unit and 6 regression tests.

Execution under the read-only environment:

- Unit: all 29 target tests are represented; the subsequently checked workspace ran 30/30 after an external follow-up commit.
- Regression: all 6 reached setup but could not execute because `tmp_path` could not create a directory. This was an environment restriction, not a product assertion failure.
- Direct parser check passed for the empty Mermaid degradation source.

Contracts now pinned:

- Package and Python index order independence
- Shared-package `home` behavior
- Module-local type preference
- Test declaration exclusion
- Explicit resolution categories
- Unknown reference failure
- Type-edge ordering
- Nested `src/main`
- Ordinary innermost owner
- Ownerless extraction
- Oversized diagram size limit
- Static/wildcard Java import normalization

Still missing:

- End-to-end byte-identical `facts.json`
- A declaration-aware shared-package import oracle
- Same-module name collision against an explicitly imported external type
- Equal-range owner ambiguity
- Repeated `src/test`
- Static-import collision with a package named like the declaring class
- Source-read failure
- Every flow contract: permutation, cross-module preference, cycle, depth
- Entry-point innermost/equal-range behavior
- Airflow-style `.get()` argument false positive
- Positive FastAPI route-decorator fixture
- Oversized degradation through both Mermaid parsers
- CLI partial-read failure and zero-diagram behavior

Implementation-detail assertions:

- Direct equality against the internal index shapes (`dict[str, set[str]]`, list length) pins representation more than externally observable behavior.
- The test asserting `home` wins a shared package pins the defective policy itself.
- Explicit `ResolutionCounts` fields are reasonable report-level behavior, but should be supplemented with an accounting invariant.

Under C-TEST-1, existing affected tests were generally revised rather than duplicated, which is compliant. C-TEST-2 and C-TEST-3 show no material violation. The main testing problem is missing behavioral oracles, especially the lack of a positive decorator case and the shared-package test that canonizes incorrect behavior.

Under V-COMMENT-1, changed comments/docstrings containing `PLAN §...`, “Codex 5차 검증 지적,” and embedded one-off kafka/dubbo measurements are not self-contained stable explanations. The canonical-sort comment is also factually incomplete because sorting does not merely order output; it arbitrates equal-range owners.

## Verdict

**No.** The output is now reproducible for dubbo and kafka, but the deterministic layer is not sound enough to be the LLM layer’s factual foundation. It deterministically loses real module edges, creates wrong type edges, and drops all Airflow decorator entry points.

The single highest-value remaining fix is a declaration-aware, qualified resolver shared by imports and type references: resolve exact FQN/import and same-package lexical scope first, then module-local only when semantically justified, then repository-global unique, otherwise report ambiguity. Type and owner identities must include module/path/qualified name rather than simple name.

The most serious RUNLOG overstatement is that the kafka module-edge drop is wholly a correctness improvement. It is not: at `9413029`, at least ten real Kafka module pairs and 2,215 declaration-identifiable cross-module import occurrences are hidden or unresolved.
