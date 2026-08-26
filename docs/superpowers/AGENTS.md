# SUPERPOWERS DOC INSTRUCTIONS

## OVERVIEW

This directory holds prompt-loop playbooks, design specs, and implementation
plans for the summarization/claim-graph system. These docs constrain workflow
and architecture; they are not runtime artifacts.

## STRUCTURE

```text
docs/superpowers/
|-- plans/    # Dated work plans
|-- prompts/  # Goal-loop prompts and operating procedures
`-- specs/    # Design constraints and architecture notes
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Prompt-improvement loop | `prompts/summarization-prompt-goal-loop.md` | Single-prompt bounded loop. |
| Batch prompt loop | `prompts/summarization-batch-prompt-goal-loop.md` | Bundle/multi-prompt workflow. |
| Chunk-first graph architecture | `specs/2026-06-19-chunk-first-claim-graph-design.md` | Source-grounded graph sequencing and non-goals. |
| Historical implementation context | `plans/` | Dated plans; check code before assuming still current. |

## CONVENTIONS

- Keep these docs concrete: commands, paths, gates, artifacts, and explicit
  forbidden changes are more useful than general strategy prose.
- Dated plans are snapshots. If implementation has drifted, update wording to
  distinguish historical plan from current behavior.
- Prompt-loop instructions should preserve auditability: status log, run IDs,
  paired deltas, promotion/rejection reason, and final verification.
- Summary pipeline docs should treat `summary_graph/manifest.json` as an
  additive diagnostics index for generated graph runs. Do not imply it replaces
  `summary.md`, `summary_evidence.md`, wrapper navigation, or existing
  `summary_graph/` artifacts.
- Architecture specs should state non-goals when a tempting implementation path
  would compromise the repo’s current design.

## ANTI-PATTERNS

- Do not use prompt-loop docs to authorize Python pipeline, tests, corpus,
  judge, scoring, model, chunking, graph-setting, or command changes during a
  prompt-only loop.
- Do not propose graph extraction from generated chunk summaries; specs require
  raw source/chunk text as the graph source.
- Do not replace raw chunk text with graph-only context for generation.
- Do not add graph/vector database infrastructure to this local pipeline without
  revising the design spec first.
- Do not change the public `alex summary INPUT OUTPUT_PATH` workflow from docs
  alone; update code, README, and tests together if that contract changes.

## COMMANDS

```bash
uv run alex improve-prompt <prompt_name> --iterations 1 --docs <doc.md>
uv run alex eval-summary --prompt <prompt_name>=<version> --run-id <run_id>
uv run alex eval-summary --prompt final_summary=<version> --prompt merged_summary=<version> --no-coverage-repair --run-id <run_id>
uv run pytest tests/test_prompt_templates.py tests/test_prompt_improvement.py -q
```

## NOTES

- The key architectural invariant is chunk-first, source-grounded claim graph
  extraction before chunk summary generation.
- Live eval gates are local/manual and require provider credentials; CI should
  stay limited to deterministic lint, typecheck, and tests.
- Non-prompt workflow ideas from prompt loops belong in
  `evals/workflow_ideas/<target_prompt>.jsonl`, logged only unless separately
  requested.
