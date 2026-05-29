# Eval fundamentals — the theory this framework operationalizes

Distilled from Anthropic, **["Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)** (published 2026-01-09, retrieved 2026-05-29). This is the *why* behind the pipeline. Load it when you need to justify a grader choice, a scoring convention, or a scenario-design call — not for mechanics (those live in the per-step references).

The article's fundamentals are constant across agent types; this framework is one concrete operationalization of them. Where a concept maps to a framework artifact, the mapping is called out inline.

## What an eval is

An **evaluation** gives an AI an input, then applies **grading logic** to its output to measure success. Three rungs of complexity:

- **Single-turn** — one prompt, one response, one grader.
- **Multi-turn** — an agent loop (tool calls + reasoning) updates an environment; grading checks the resulting state (e.g. unit tests on the artifact the agent produced).
- **Agent evals** — tools across many turns, mutating state, mistakes compounding. Frontier models also find valid solutions a static grader didn't anticipate — so grade outcomes, not paths (see below).

→ This framework runs **automated** evals: scenarios fire at the agent, traces land in Opik, graders score them — no real users, reproducible, runnable per branch.

## Three grader types — combine them

Great eval design **chooses the right grader per dimension** and combines types. Don't reach for an LLM judge when a regex will do.

| Grader | Methods | Strengths | Weaknesses |
|---|---|---|---|
| **Code-based** | string/regex match, binary tests, static analysis, outcome verification, tool-call verification, transcript stats (turns, tokens) | fast, cheap, objective, reproducible, easy to debug | brittle to valid variations, no nuance, weak on subjective tasks |
| **Model-based** (LLM-as-judge) | rubric scoring, NL assertions, pairwise comparison, reference-based, multi-judge consensus | flexible, scalable, captures nuance, handles open-ended output | non-deterministic, costlier than code, **needs calibration against human labels** |
| **Human** | SME review, structured annotation | ground truth, catches what automation misses | slow, expensive — use judiciously for validation |

**The rule: deterministic graders where possible, LLM graders where necessary, human graders to validate.**

→ Model-based graders are this framework's **Opik LLM-as-judge evaluators** (`scope-evals` → `create_evaluator`). Code-based graders are the **deterministic code metrics** (`scripts/metrics/`, registered as `user_defined_metric_python` rules). Pick the type per dimension in `evaluator-selection.md` Step 0 (the "deterministic vs subjective" note is exactly this choice).

## Two rules for graders

- **Grade what the agent produced, not the path it took.** Checking for a specific tool-call sequence is too rigid — agents find valid approaches the designer didn't anticipate, and you punish creativity. Grade the outcome/state. (Tool-call *presence* is fair game; tool-call *ordering* usually isn't.)
- **Make graders bypass-resistant.** Passing should require genuinely solving the task, not exploiting a loophole in the grader.

## Capability vs regression evals

| Kind | Asks | Target pass rate | Framework artifact |
|---|---|---|---|
| **Capability / quality** | "What can this agent do well?" | starts **low** — a hill to climb | session `scenarios.txt` (diff-specific, higher aggression) |
| **Regression** | "Does it still handle what it used to?" | **~100%** — a drop means something broke | `regressions.txt` (stable baselines, one per core promise) |

Capability evals **graduate** into the regression suite once the agent passes them reliably: "Can we do this at all?" becomes "Can we still do this?" — which is exactly why `regressions.txt` is committed and persists across sessions while `scenarios.txt` is regenerated per diff.

## Non-determinism — a green run isn't proof

Agent behavior varies run to run; each task has its own success rate. Two metrics capture this:

- **pass@k** — probability of ≥1 success in *k* attempts. Rises with *k*. pass@1 is the bar when first-try matters (most coding).
- **pass^k** — probability **all** *k* trials succeed. Falls with *k*. The bar for customer-facing agents where users expect reliability every time.

→ Practical consequence here: one passing trace per scenario is weak signal. Run multiple **instances** per intent (`scenario-design.md`), and treat a single green score-table as necessary, not sufficient. See `failure-modes.md` for judge-noise vs real-regression.

## Zero→one roadmap (the parts that change how you work here)

- **Source realistic tasks from the failures you actually see** — production incidents and bug reports make the best eval items, not invented edge cases.
- **Define unambiguous, robust success criteria** — if you can't state what score 1 means in one sentence, the dimension isn't ready (`evaluator-selection.md` Step 0).
- **Stable, isolated harness** — each trial starts clean; shared state (leftover files, git history, cached data) causes correlated failures or inflated scores. Mirror production: don't inject context by concatenating into the user message (see root `CLAUDE.md` key constraints).
- **Read the transcripts.** You can't trust a grader you haven't watched. When a task fails, the transcript tells you whether the agent erred or the grader rejected a valid solution. This is why the inner loop surfaces traces for inline review before scaling.
- **Watch for saturation.** An eval at 100% tracks regressions but gives no room to improve. When `scenarios.txt` goes green, graduate it to `regressions.txt` and raise aggression on the next capability set.

## Where automated evals fit

Automated evals are one method, not the whole picture. A complete view also uses **production monitoring** (real behavior, but reactive and no ground truth), **A/B testing** (real outcomes, but slow and deploy-gated), **user feedback** (real signal, but sparse/noisy), and **systematic human review**. Automated evals trade up-front + maintenance cost for fast, reproducible, pre-deployment iteration — and can create false confidence if they drift from real usage. Keep them honest by sourcing from real failures and reading transcripts.

## See also

- [`evaluator-selection.md`](evaluator-selection.md) — turn the grader-type choice into a concrete Opik rule
- [`scenario-design.md`](scenario-design.md) — capability vs regression in practice; intent/instance; aggression levels
- [`score-reading.md`](score-reading.md) — score-table mechanics + the binary scoring convention
- [`failure-modes.md`](failure-modes.md) — red judge → real-vs-noise (the non-determinism check)
