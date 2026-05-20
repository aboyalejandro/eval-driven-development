# Eval-Driven Agent PR Process

How to create a PR on the agent repo using EDD findings. Run this when moving from one hypothesis to the next.

## When to do this

After completing a hypothesis cycle (run → dataset → experiment → read scores), open a PR on the agent repo proposing the prompt or logic change that the next hypothesis will test. The PR is the change under test — EDD measures its effect.

## Steps

### 1. Read the hypothesis doc

Load `docs/DEMO_BRANCH.md`. Identify:
- Current hypothesis (H2, H3, etc.)
- Target file in the agent repo
- Specific behavior to change

### 2. Fetch the target file

```bash
gh api repos/aboyalejandro/substack-author-agent/contents/<path> --jq '.content' | base64 -d
```

### 3. Create a branch on the agent repo

```bash
SHA=$(gh api repos/aboyalejandro/substack-author-agent/git/refs/heads/main --jq '.object.sha')
gh api repos/aboyalejandro/substack-author-agent/git/refs \
  --method POST \
  --field ref="refs/heads/<topic>" \
  --field sha="$SHA"
```

Branch name = hypothesis topic = `<topic>` (e.g. `url-clarification`). Same tag used in EDD traces.

### 4. Push the file change

Get the file SHA:
```bash
gh api repos/aboyalejandro/substack-author-agent/contents/<path> --jq '.sha'
```

Encode and push:
```bash
CONTENT=$(python3 -c "import base64; print(base64.b64encode(open('/tmp/new_file.py','rb').read()).decode())")
gh api repos/aboyalejandro/substack-author-agent/contents/<path> \
  --method PUT \
  --field message="fix: <one-line description>" \
  --field content="$CONTENT" \
  --field sha="<file-sha>" \
  --field branch="<topic>"
```

### 5. Create the PR

```bash
gh pr create \
  --repo aboyalejandro/substack-author-agent \
  --head <topic> \
  --base main \
  --title "<short title>" \
  --body "$(cat <<'EOF'
## Context
<hypothesis statement>

## Prior findings
<scores from previous experiment>

## Change
<diff of what changed and why>

## H<N> Hypothesis
<what improvement is expected>

## Test Plan
- [ ] Emit scenarios via `edd run scenarios.txt`
- [ ] Build dataset `<project>-<topic>-v1`
- [ ] Run experiment with relevant evaluator
- [ ] Compare score vs prior baseline
EOF
)"
```

### 6. Update session state

Edit `.edd/session.json` — update `branch_tag` and `dataset_name` for the new hypothesis:

```json
{
  "mode": 2,
  "aggression": 2,
  "project": "substack-author-agent",
  "branch_tag": "<topic>",
  "dataset_name": "<project>-<topic>-v1"
}
```

### 7. Prepare scenarios

Copy or rewrite `scenarios.txt` for the new hypothesis. Each line: plain message or JSON `{"message": "...", "evaluators": ["..."]}`.

Regenerate per-session — don't carry over scenarios from the previous hypothesis.

## Key invariants

- Branch name on both repos = topic = tag. One readable identity across agent branch, trace tag, dataset, experiment.
- PR description carries the hypothesis and prior scores — that context disappears from the PR once merged unless it's in the body.
- `docs/H<N>.md` captures what happened after the experiment. The PR proposes the change before.
- Never reuse the same dataset name across hypotheses — version-bump (`v2`) if item shape changes.
