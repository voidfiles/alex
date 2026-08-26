# Summarization Batch Prompt Goal Loop

Paste the block below into `/goal` from the repository root.

```text
Objective: Improve the production summarization prompt stack in /home/alex/code/alex as one coherent, evidence-gated bundle.

Pipeline goal: produce dense, source-faithful, academically useful summaries that preserve document structure, central arguments, claims, evidence, caveats, key passages, and citation-worthy detail without unsupported inference or overcompression. The graph path should improve coverage without reducing faithfulness.

Target prompts:
chunk_summary, chunk_summary_with_graph, compression_summary, final_summary,
source_claim_extraction, graph_guided_summary, merged_summary,
merged_summary_repair, merged_summary_faithfulness_filter.

Fixed prompts:
Do not change fact_extraction, fact_coverage_judge, claim_extraction,
claim_verification, rubric_judge, or prompt_critic during this run.

Models:
Use two configurable critic models. Default critic A is openai/gpt-5.6-sol.
Critic B must be supplied by env/flag, for example an Anthropic high-reasoning
model when available. Use the highest practical critic token budget.

Method:
1. Record git status and active prompt versions.
2. Run a full-corpus baseline with fixed eval judges.
3. Build one prompt package containing the pipeline goal, production prompt roles,
   current prompt text, placeholders, active versions, and baseline failure evidence.
4. Ask critic A and critic B independently for a complete bundle proposal covering
   every target prompt. Each proposal must preserve placeholders and output contracts.
5. Synthesize the two proposals into one final bundle: keep improvements supported
   by both models, include unique improvements only when clearly justified by eval
   evidence, and reject changes that alter pipeline roles or placeholder sets.
6. Save new vNNN prompt versions only for changed prompts.
7. Evaluate the candidate bundle against the same corpus and fixed judges.
8. Promote all changed active.txt files only if mean paired blended delta is at least
   +0.02 and the candidate wins or ties on a strict majority of clean docs.
9. If the gate fails, keep candidate files for audit but leave active.txt unchanged.
10. Log critic outputs, synthesis output, prompt version maps, run artifacts, deltas,
    promotion/rejection reason, and final active versions.

Suggested command:
uv run alex improve-prompts \
  --critic-model-a openai/gpt-5.6-sol \
  --critic-model-b anthropic/claude-opus-5 \
  --critic-max-tokens 32000 \
  --min-delta 0.02

Forbidden:
Do not tune scoring weights, eval judge prompts, corpus files, model defaults,
chunking, graph settings, or Python behavior unless explicitly implementing the
batch-improvement workflow itself.
```
