# Summarization Prompt Goal Loop

Paste the block below into `/goal` from the repository root.

```text
Objective: Improve summarization prompt quality in /home/alex/code/alex through a bounded, evidence-driven loop.

Default target prompt: chunk_summary_with_graph, unless I explicitly provide another.
Default min delta: 0.02.
Max outer iterations: 6.
Stop after 2 consecutive quick-probe failures or 2 consecutive full-corpus gate failures.

Allowed changes:
- Prompt versions created by `uv run alex improve-prompt`.
- `src/alex/prompts/<target_prompt>/active.txt`, only after a full-corpus gate pass.
- Eval artifacts/logs under `evals/`.

Forbidden changes:
- Do not edit Python pipeline code, tests, corpus files, judge prompts, scoring weights, model defaults, chunking, graph settings, or command behavior.
- If workflow changes look useful, append them to `evals/workflow_ideas/<target_prompt>.jsonl` and do not act on them.

Start:
1. `cd /home/alex/code/alex`.
2. Record `git status --short` in the session log. Do not revert existing changes.
3. Create `evals/goal_logs/<UTC_TIMESTAMP>-<target_prompt>.md`.
4. Inspect the active target prompt and existing versions.
5. Choose the quick probe doc: use the lowest-blended doc from the latest relevant full-corpus run if available; otherwise use the smallest `.md` in `evals/corpus/`.

Loop:
1. Note the current line count of `evals/lineage/<target_prompt>.jsonl`.
2. Run:
   `uv run alex improve-prompt <target_prompt> --iterations 1 --docs <quick_doc> --min-delta 0.02`
3. Read the new lineage record. Escalate only if it has a candidate version, clean paired delta, `rejected_reason == null`, and mean delta >= 0.02.
4. Log command, parent, candidate, quick doc, deltas, rejection reason, and a hypothesis for why it went well or failed.

Full-corpus validation:
1. Run parent unless a matching artifact from this loop can be reused:
   `uv run alex eval-summary --prompt <target_prompt>=<parent_version> --run-id <loop_id>-i<NN>-full-parent`
2. Run candidate:
   `uv run alex eval-summary --prompt <target_prompt>=<candidate_version> --run-id <loop_id>-i<NN>-full-candidate`
3. Compute paired per-doc blended deltas, excluding errored docs.
4. Pass only if mean paired delta >= 0.02 and the candidate wins or ties on a strict majority of paired docs.
5. After the pair, log a hypothesis for why the candidate generalized or failed.

Promotion:
- If full gate passes, set `src/alex/prompts/<target_prompt>/active.txt` to the candidate version with a trailing newline.
- If full gate fails, leave `active.txt` unchanged and keep the candidate version for audit.
- After promotion, use the candidate full-corpus run as the next baseline.
- After failure, choose the next quick doc from the largest regression or lowest candidate score.

Workflow idea log:
Append non-prompt ideas as JSONL to `evals/workflow_ideas/<target_prompt>.jsonl`:
{"timestamp":"...","target_prompt":"...","iteration":1,"evidence":["..."],"workflow_change":"...","why_it_might_help":"...","status":"logged_only_do_not_act"}

Final verification:
- If `active.txt` changed, run:
  `uv run pytest tests/test_prompt_templates.py tests/test_prompt_improvement.py -q`
- Final response must report final active version, candidates tried, run artifacts, promotions/rejections, log paths, and tests.
```
