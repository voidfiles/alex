# Pull-quote matching experiment — 2026-10-04

This report records the development round. The subsequent
[expanded benchmark](EXPANDED_BENCHMARK.md) evaluates all 169 sources, including
the 94 test sources left unused here, with fresh generations and fixed prompts.

The evaluation now rewards finding the human-selected pull quote among multiple
source-grounded candidates. Extra valid quotes do not lower agreement, and exact
matches receive a large bonus. Four new prompt revisions and one earlier revision
were compared with the baseline: **none passed development, so `v001` remains
active**. This is a scoring improvement and an unsuccessful prompt-tuning round;
it does not establish an improvement in extraction quality.

## Evaluation contract

Only the complete original source, rendered from its saved Markdown to readable
text, goes to the extractor. Reference quotes, curator identities, referring-post
metadata, and validation labels are withheld. Sources are independently acquired
documents, not the posts displaying the selected quotation. No source truncation,
quote-centered windows, or generated source text are used.

The new scorer, `best-pull-quote-match/v2`, evaluates each returned quote
individually and takes its highest score:

```text
match score = 0.50 × source-word-position F1
            + 0.25 × exact source-word-position match
            + 0.25 × exact reference-text match
```

The span metrics use normalized source-word positions. Exact text preserves case
and punctuation while allowing whitespace to reflow. Matching both the complete
reference passage and its text scores **1.0**. Complete span agreement with an
editorial or typographic difference scores **0.75**. Without either exact match,
partial agreement scores below **0.5**. Human excerpts containing edits or omission
markers can therefore have different text from a faithfully copied source passage.

Adding other source-valid quotes, including overlapping candidates or more than
the requested count, cannot reduce agreement. Several separate quotes cannot
jointly claim an exact match. Precision, recall, and exact-match diagnostics belong
to the best individual quote; total reference coverage and quote count are separate
diagnostics. A whole-article quotation has low precision rather than full credit.

Every segment must still match the original rendered source verbatim and appear
in source order within its quote. Invalid JSON, rewritten text, and reordered
segments fail validation; those generations remain in the denominator with zero
score. Extra quotes are exempt from quantity and cross-quote overlap limits,
not source validation. The interactive `alex quotes` command retains those limits.
There is no LLM judge.

This contract and the five-candidate request were fixed before the new benchmark
calls. Historical `source-span-f1/v1` results in [RESULTS.md](RESULTS.md) used a
different scorer, corpus, and quote count and are not directly comparable.

## Repeated development comparison

The [combined dataset](quotebacks_dataset/README.md) has 169 sources, with **35
development cases**: the original 10 Simon Willison cases and 25 newly collected
Quotebacks cases. Every version used three independent generations per source,
giving **105 generations per version**. Only development predictions and labels
were used to revise prompts.

Fixed settings: `openai/gpt-6-luna`, five requested quotes, 8,192 output tokens,
reasoning effort `None`, the same system prompt, and `markdown-it-py` 4.2.0.
The source corpus and scoring contract stayed unchanged throughout this round.
Dataset SHA-256:
`7ec80cdd0f38fc212dbc3b3250608a97ad92fed6f4c699f8d0f7e4693f19ffac`.

| Version | Selection change | Match score | Change | Exact text / 105 | Exact span / 105 | Errors / 105 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v001 | Baseline: informative, memorable, self-contained passages | **0.2850** | — | **10** | **17** | 2 |
| v003 | Earlier revision: specific observations, significance and lessons | 0.1876 | −0.0974 | 3 | 9 | 4 |
| v006 | Whole paragraphs, complete examples, broad editorial interest | 0.2449 | −0.0401 | 6 | 15 | 6 |
| v007 | Varied shortlist: insights, comparisons, explanations, advice and voice | 0.2165 | −0.0685 | 7 | 14 | 2 |
| v008 | Concrete lessons, limitations and secondary details; stronger copying checks | 0.1956 | −0.0894 | 5 | 14 | 4 |
| v009 | Smaller baseline extension: distinct ideas, useful details and natural boundaries | 0.2172 | −0.0678 | 6 | 14 | 5 |

The gate requires an improvement of at least 0.02 in mean match score, a majority
of paired sources winning or tying, no newly failed source, and no per-source
validity regression. Comparisons average the three generations for each source.
Candidate wins/ties/losses were 7/9/19 (`v003`), 8/12/15 (`v006`), 7/12/16
(`v007`), 6/12/17 (`v008`), and 7/12/16 (`v009`). Every candidate had a negative
mean change and introduced failures on sources that the baseline handled.

Development artifact inspection showed why a broadly sensible rubric can lose
reference agreement. The whole-paragraph preference in `v006` combined adjacent
material beyond some reference boundaries: the Matt Webb case fell from **0.8143
to 0.3633**. It helped other sources: the Sense of Doubt case
`qb-sensedoubt-blogspot-com-3e1d350148f2` rose from **0.1124 to 0.9167**. Those gains
did not offset the losses. Longer outputs also introduced more non-verbatim
segments. Broader selection rubrics continued to miss specific human choices,
such as Tom Critchlow's selected reporting-process detail in
`qb-tomcritchlow-com-857b80a894c8`. These observations concern development only.

The [promotion decision](round2/promotion_decision.json) retains `v001`. No
candidate advanced to test, leaving **94 fresh new test sources** unused in this
round. The combined manifest also includes 40 previously evaluated Simon test
sources; those would not constitute a fresh confirmation. No held-out quality
improvement is claimed.

## Evidence and verification

[benchmark_summary.json](round2/benchmark_summary.json) contains complete metrics,
paired source deltas, configuration, source-case lists, prompt hashes, raw-run
hashes, costs, and the gate decision. Raw runs preserve full provider responses,
validated predictions, source offsets, errors, and usage:

- [v001](../runs/quote_extraction/20261004-v2-v001-dev-r3.json)
- [v003](../runs/quote_extraction/20261004-v2-v003-dev-r3.json)
- [v006](../runs/quote_extraction/20261004-v2-v006-dev-r3.json)
- [v007](../runs/quote_extraction/20261004-v2-v007-dev-r3.json)
- [v008](../runs/quote_extraction/20261004-v2-v008-dev-r3.json)
- [v009](../runs/quote_extraction/20261004-v2-v009-dev-r3.json)

All **630 generations** are counted once. Recorded cost was **$0.6157**, with
2,007,063 input tokens and 1,066,960 output tokens. Cost uses recorded provider
usage/pricing, not a billing reconciliation. Runs with validation failures return
a nonzero CLI status after saving their complete artifact; they remain included.

Verification: **81 focused offline tests pass**, as does the separate lightweight
CLI-help import test. Scoped Ruff and formatting checks pass, and strict MyPy
passes for the three changed source modules. Tests cover
exact matches retaining full credit with extra/overlapping quotes, the requested
count being exceeded, exact text outranking punctuation differences, split quotes
not claiming joint exactness, and extra-quote mode still rejecting rewritten or
reordered segments. Dataset and prompt hashes and all 105 case/repeat combinations
were checked in every run. No corpus or historical prompt version was edited.
The [saved verification](round2/verification.json) also records an offline audit
of all model responses: 607 valid generations were reparsed and rescored with
matching source offsets and metrics; all 23 rejected outputs failed validation
again and retained zero credit.

Reproduce a version's development run with a new output path:

```bash
uv run alex eval-quotes \
  --dataset evals/quote_extraction/quotebacks_dataset/combined_examples.jsonl \
  --split dev --count 5 --prompt-version v001 \
  --repeats 3 --workers 6 --model openai/gpt-6-luna \
  --output /tmp/pull-quotes-v001-dev-r3.json
```

The corpus supplies one human-selected passage per source. Alternate valid quotes
can score zero, and reference agreement does not measure every aspect of editorial
quality or whether omissions preserve meaning. The sample remains concentrated
in a few curators and has no negative/no-quote cases.
