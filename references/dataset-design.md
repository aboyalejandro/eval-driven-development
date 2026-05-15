# Dataset design — shape, naming, coverage

Read `evaluator-selection.md` before this doc. The evaluator is the anchor: its schema name flows into the dataset name, the `--evaluator` flag in `edd-run`, and the coverage decisions below. A dataset without a pinned evaluator produces scores nobody can act on.

The dataset is the durable artifact every experiment scores against. Spend
the time to make it boring and stable; a noisy dataset poisons every score
that follows.

## Item shape

Minimum fields each item carries through the loop:

| Field | Source | Why |
|---|---|---|
| `id` | minted by `edd-build` | dedupes upserts |
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
edd-build ... --dry-run
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

## Scenario design: adversarial but realistic

The dataset should actively try to make the agent fail against its own prompt,
its skill contracts, and its evaluators — while staying within the range of
things a real user would actually ask.

**What this means in practice:**

- Don't default to the most basic, polished version of each question ("How are
  my articles doing?" → the agent handles this easily). Push harder: ask with
  ambiguous phrasing, incomplete context, or in a multi-turn session where the
  context shifts mid-conversation.
- Don't manufacture impossible edge cases either. "Analyze my articles from
  the year 1247" is a waste of a dataset slot — no real user asks this.
- Use the tension between the agent's stated capabilities and realistic user
  confusion. A user might ask "what are my top posts?" instead of the exact
  trigger phrase — does the skill still activate?
- Include scenarios where the agent SHOULD fail gracefully: out-of-scope asks,
  data that doesn't exist, ambiguous requests that need clarification. These
  validate the agent's guardrails, not just its happy-path behavior.
- Multi-turn sequences expose more failure modes than isolated questions.
  A follow-up that assumes context from the previous turn will break agents
  with weak session handling.

**Coverage planning**

Aim for ~100 items per dataset once the recipe stabilises. Default split,
tunable per topic:

| Bucket | % | Purpose |
|---|---|---|
| Happy path | 30 | establishes baseline pass rate — but write these as a real user would, not a test engineer |
| Wording variants | 20 | same intent, different phrasing — robustness against brittle trigger matching |
| Edge cases | 15 | empty data, missing context, nonexistent content — tests graceful degradation |
| Adversarial | 15 | questions that should confuse the agent: ambiguous scope, conflicting instructions, partial triggers |
| Multi-turn | 10 | follow-ups that depend on prior context — exposes session memory and context handling |
| Negatives | 10 | out-of-scope asks → graceful refusal |

Start at 10–20 items for the first dry run. Ramp once the recipe works.

## Filtering criteria for ingestion

`edd-build` keeps an item if:

1. The trace carries the `--branch-tag` (set by `edd run` as
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
