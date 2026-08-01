# EVALS INSTRUCTIONS

## OVERVIEW

`evals/` mixes source evaluation inputs with generated model artifacts. Treat it
as experiment state: preserve corpus/facts/lineage carefully, and avoid
normalizing generated run output unless the task is about that artifact.

## STRUCTURE

```text
evals/
|-- corpus/          # Source documents used for scoring
|-- facts/           # Cached extracted reference facts
|-- lineage/         # JSONL prompt-improvement history
|-- runs/            # Standard eval-summary artifacts, often large/generated
|-- claim_graph/     # Historical graph eval artifacts
|-- merged_summary/  # Historical merged-summary artifacts
|-- prompt_bundles/  # Bundle-improvement candidates and evidence
|-- reports/         # Generated Markdown/SVG reports
|-- goal_logs/       # Prompt-loop session logs
`-- workflow_ideas/  # Logged-only non-prompt ideas
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Change scored documents | `evals/corpus/` | Corpus edits change every comparison baseline. |
| Inspect cached answer keys | `evals/facts/` | Filenames encode source hash/model/version. |
| Trace prompt iterations | `evals/lineage/*.jsonl` | Append-only history for prompt and bundle runs. |
| Compare summary runs | `evals/runs/` | Standard and graph-enhanced run artifacts. |
| Generate reports | `evals/reports/`, `alex eval-report` | Reports read stored artifacts. |
| Follow prompt-loop logs | `evals/goal_logs/` | Human-readable command/evidence trails. |

## CONVENTIONS

- Live eval commands call LLMs and are not CI checks.
- Prefer explicit `--run-id` values for reproducible comparisons.
- Keep parent and candidate runs paired on the same docs, facts, judges, and
  prompt overrides before interpreting deltas.
- For summary prompt promotion, use a local/manual gate: probe first, then full
  corpus only if the probe passes. Require mean delta `>= +0.0200`, majority
  paired docs win/tie, no faithfulness delta `< -0.0100`, and no newly failed
  eval document before changing `active.txt`.
- A probe pass requires the mean of `n >= 3` same-config probe runs, not a
  single run. Measured 2026-07-04: identical config swung book-doc coverage by
  9/37 facts and blended by ~0.05 between runs (generation-side variance), so
  single-run deltas below that scale are noise.
- A numeric gate pass additionally requires a mechanism check before
  promotion: inspect run artifacts (selected subgraph, document graph,
  repair/meta files) to confirm the treatment actually fired and the delta is
  attributable to it. Measured 2026-07-04: an n=3 mean cleared the gate for a
  treatment whose code path provably never executed differently from baseline.
- Answer keys switched from fact_extraction v002 to v003 on 2026-07-04 (junk
  exclusions: piracy/boilerplate/bibliography meta-facts). Runs before and
  after that date are NOT coverage-comparable. Clean-key baseline runs:
  `evals/runs/exp-cleankey-baseline-{full-2,book-2,book-3}.json` (book n=3
  means: blended 0.7069, coverage 0.5299, faithfulness 0.9620).
- Model defaults switched from Claude (haiku-4-5/sonnet-5/opus-5) to GPT-5.6
  (luna/terra/sol) on 2026-08-01, including the eval judge and fact extractor.
  Runs judged before and after that date are NOT comparable: answer keys re-key
  on the extractor (sol vs opus-5) and the judge changed. The A/B evidence for
  the swap lives in `evals/runs/gpt56-{base,cand}-*.json` (Claude judges both
  arms; base-1/2 complete at 0.784/0.776, cand-1 complete at 0.792; base-3 and
  cand-2/3 lost to API-credit exhaustion — the user accepted the partial
  evidence). `gpt56-newstack-*` starts the new all-GPT baseline lineage; run a
  full n=3 new-stack baseline before the next prompt-tuning campaign.
- `evals/lineage/*.jsonl` is append-only audit history; do not rewrite it to
  make a result cleaner.
- `evals/workflow_ideas/*.jsonl` is for logged-only ideas discovered during
  prompt work; writing there does not authorize pipeline changes.
- Generated runs can be numerous and deep. Avoid broad formatting, cleanup, or
  search/replace across all run artifacts.

## ANTI-PATTERNS

- Do not edit corpus files while claiming a prompt-only improvement.
- Do not change judge prompts, scoring weights, model defaults, graph settings,
  or chunking to make a candidate win.
- Do not compare a graph run against a no-graph run without naming that as an
  A/B of pipeline settings.
- Do not treat `eval-report` as a live eval; it aggregates existing artifacts.
- Do not delete failed or losing candidate artifacts unless the user explicitly
  asks for cleanup.

## COMMANDS

```bash
just eval
uv run alex eval-summary --docs <doc.md> --prompt <name>=<version> --run-id <run_id>
uv run alex eval-summary --no-graph --run-id <run_id>
uv run alex eval-summary --no-coverage-repair --run-id <run_id>
uv run alex eval-judges --fail-under 0.85
uv run alex eval-report --output-dir evals/reports/latest
```

## NOTES

- `summary_eval.py` continues per document when one document fails; inspect
  errored docs before trusting mean scores.
- `improve-prompt` and `improve-prompts` require `--promote` before `active.txt`
  changes; candidate versions remain for audit even when rejected.
- Existing worktree changes under this directory may be generated artifacts from
  active experiments. Do not revert them without explicit direction.
