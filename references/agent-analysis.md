# Agent analysis — extracting what to evaluate

Do this before scenario design or evaluator selection. Reading the agent source first means your evaluators map to what the agent actually promises, not to a taxonomy you brought in from outside.

## What to read

In order of signal density:

1. **System prompt / instructions** — explicit output contracts, format rules, refusal policies
2. **Tools** — what each returns, when it should fire, what "empty result" means
3. **Skills / sub-agents** — trigger conditions, expected output shape per skill
4. **Output examples / demos** — what a passing response looks like in practice

## Extraction questions

For each source, ask:

**System prompt**
- What response shape does it prescribe? (sections, format, length)
- What does it refuse or redirect to the user?
- What must the response be grounded in — fetched data, retrieved context, session history?

**Tools**
- What does each tool return, and is it structured?
- When should tool X fire instead of tool Y?
- What should the agent do when the tool returns empty or errors?

**Skills / sub-agents**
- What user intents trigger this skill? (Use the trigger words verbatim as scenario seeds.)
- What is the exact output format this skill produces?
- What intents should *not* trigger it — adjacent asks that should fall through?

**Output examples**
- What specific data does the response cite? (titles, numbers, dates — anything that must come from a tool call)
- What structural sections appear consistently?

## Promise inventory

Translate the above into a flat table. One row per testable promise.

| Source | Promise | Failure mode | Evaluator type |
|--------|---------|--------------|----------------|
| System prompt | Response follows prescribed structure | Missing sections, wrong order | Format (LLM-judge) |
| Tool: `<name>` | Claims grounded in tool output, not training data | Hallucinated specifics | Grounding (LLM-judge) |
| Tool: `<name>` | Empty result → acknowledge, don't invent | Fabricated data | Recovery (LLM-judge) |
| Skill: `<name>` | Correct skill activates for its trigger intents | Wrong skill, no skill | Routing (LLM-judge or code) |
| Skill: `<name>` | Output matches skill's prescribed format | Partial or missing output shape | Format (LLM-judge) |
| System prompt | Off-topic asks declined or redirected | Out-of-scope answer given | Scope (LLM-judge) |

Add rows for every distinct promise you can extract. Remove rows where you can't describe the failure — those aren't testable yet.

## Baseline vs generated

**Baseline** — the promises that define the agent's core identity, stable across any diff:
- Pick 5–8 rows from the promise inventory that would make the agent useless if broken
- Write one scenario intent per row, store in `regressions.txt`
- Calibrate the evaluator for each before the first experiment
- Run on every change, regardless of what the diff touches

**Generated** — what Claude derives per diff:
- Read `git diff main...HEAD` → identify which promises the change touches
- Generate scenario instances for each touched promise (see `scenario-design.md`)
- The evaluator prompts can be drafted from the "Promise" and "Failure mode" columns directly
- Don't add to `regressions.txt` until the evaluator survives 2+ iterations without calibration drift

The distinction matters because baseline evaluators need calibration investment. Generated ones are cheap but ephemeral — promote them only after they prove stable.

## Anti-patterns

- **Skipping this step and using a taxonomy.** You end up with evaluators that don't map to what the agent actually does, and scenarios that test nothing real.
- **Treating all promises as baseline.** `regressions.txt` bloats; every run fires 30 evaluators; signal drowns in noise.
- **Extracting promises without reading the output format.** The scenario generates an answer in the wrong shape and the judge fires for the wrong reason.
