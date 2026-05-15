# Dataset design — shape, naming, coverage

The dataset is the durable artifact every experiment scores against. Spend
the time to make it boring and stable; a noisy dataset poisons every score
that follows.

## Item shape

Minimum fields each item carries through the loop:

| Field | Source | Why |
|---|---|---|
| `id` | minted by `build_dataset.py` | dedupes upserts |
| `user_message` | extractor (default: `trace.input.user_message`) | judge input |
| `assistant_response` | extractor (default: `trace.output.assistant_response`) | judge target |
| `source_trace_id` | `trace.id` | links back to the sim trace for re-scoring + UI deep-link |
| `trace_metadata` (optional) | `trace.metadata` | carries scenario-context (page, tenant, language) into the judge |

If your judge depends on intermediate state (tool calls, retrieved chunks,
context injected into the prompt), propagate it through the trace and copy
the relevant pieces in via a custom `--extractor`. The default extractor
keeps the contract minimal on purpose — extend, don't refactor.

## Trace shape and the extractor

The default extractor reads `trace.input.user_message` / `trace.output.assistant_response`. Most modern OTEL runtimes (Agno, LangChain, LlamaIndex via OpenInference) emit different keys:

```
trace.input["input.value"]   → user message
trace.output["output.value"] → assistant response
```

If you skip `--extractor` with an OpenInference-instrumented agent, the default extractor returns `None` for every item and the dataset ends up empty. Always do a `--dry-run` first to verify items extract cleanly:

```bash
python scripts/build_dataset.py ... --dry-run
```

Inspect the two sample items printed. If `user_message` and `assistant_response` are empty strings, you need a custom extractor. See `references/trace-inspection.md` for the pattern; the extractor is a plain Python callable — one function in a `.py` file, importable from the repo root.

`trace.metadata` (enriched fields like `tools_called`, `tool_count`) is copied into `item.trace_metadata` automatically when present. Judges in experiments read `tools_called` from the original trace via `metadata.tools_called` variable path — the dataset item carries it for reference, not for judge resolution.

## Naming convention

`<project-slug>-<topic>-<version>` — e.g. `edd-recovery-v1`, `edd-format-v3`.

- **project-slug** so multiple projects can share an Opik instance
- **topic** matches the evaluator family you're targeting (recovery, format,
  faithfulness)
- **version** bumps every time the *scenario shape* changes; a new version
  earns a new dataset, not an in-place rewrite. Experiments comparing
  prompt iterations need a frozen dataset to be meaningful.

## Coverage planning

Aim for ~100 items per dataset once the recipe stabilises. Default split,
tunable per topic:

| Bucket | % | Purpose |
|---|---|---|
| Happy path | 40 | establishes baseline pass rate |
| Wording variants | 20 | same intent, different phrasing — robustness |
| Edge cases | 15 | empty data, oversized inputs, malformed context |
| Conflicts | 10 | contradictory instructions vs branch prompt — priority |
| Negatives | 10 | out-of-scope asks → graceful refusal |
| Multilingual / context | 5 | extra locales or context injections relevant to the judge |

Start at 10–20 items for the first dry run. Ramp once the recipe works.

## Filtering criteria for ingestion

`build_dataset.py` keeps an item if:

1. The trace carries the `--branch-tag` (set by `cli.py run` as
   `sim-<branch>`).
2. The trace start time is within `--from`.
3. The extractor returns a dict (default extractor drops empty
   user/assistant strings).

Kept and dropped counts are logged before any write.

## Versioning

Bump the dataset name (`v1` → `v2`) when:

- Item shape gains or loses a field the judge reads
- The scenario coverage mix shifts materially
- The branch under test now exercises a different prompt section

Don't bump just because new items got added — additive growth within the
same shape is fine.

## Anti-patterns

- **Hand-curated golden outputs.** The judge scores against the agent's
  behavior, not against a baked-in answer. Use real sim traces.
- **One huge dataset across topics.** Per-topic datasets keep failures
  surgical and let optimization timelines stay legible.
- **Skipping the trace link.** Without `source_trace_id` the experiment
  scores get orphaned from the actual conversation — debugging is guesswork.
