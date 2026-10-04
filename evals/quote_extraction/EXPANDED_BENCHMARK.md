# Expanded quote-extraction benchmark — 2026-10-04

The latest **119 source–quote pairs are incorporated into the default evaluation
dataset**, alongside the original 50 Simon Willison pairs: **169 cases total**.
All six previously compared prompts were re-benchmarked with three fresh
generations per source, for **3,042 generations**. Previous predictions were
not reused.

`v006` has the highest mean on the complete corpus, but **`v001` performs best on
the 94 newly evaluated test sources**. No candidate passes the full-corpus or
new-test promotion gate. **`v001` remains active.**

## Dataset and fixed settings

The [combined manifest](quotebacks_dataset/combined_examples.jsonl) contains
**35 development / 134 test** cases. The 134 test cases include 94 new Quotebacks
sources and 40 previously evaluated Simon Willison sources. The 119 additions
comprise 25 development cases and those 94 test cases. Source documents, references,
and splits were preserved; all checksums and reference alignments validate.

The [benchmark plan](round3/benchmark_plan.json) was saved before calls began and
froze the six versions: `v001`, `v003`, `v006`, `v007`, `v008`, and `v009`.
No prompts were edited during this comparison, and test labels were not used
to create candidates. Model: `openai/gpt-6-luna`; requested quotes: **5**;
repeats: **3**; output ceiling: **8,192 tokens**; reasoning effort: `None`;
workers per run: **6**; renderer: `markdown-it-py` **4.2.0**.

Dataset SHA-256:
`7ec80cdd0f38fc212dbc3b3250608a97ad92fed6f4c699f8d0f7e4693f19ffac`.

Only the full original source, rendered from saved Markdown to readable text,
goes to the model. The selected reference quote and curator metadata are withheld.
The scorer remains `best-pull-quote-match/v2`:

```text
best individual quote score = 0.50 × source-span F1
                            + 0.25 × exact source-span match
                            + 0.25 × exact reference-text match
```

An exact text/span match scores **1.0**. Whitespace may reflow; exact text retains
case and punctuation. Complete normalized span agreement without exact text
scores **0.75**. Additional source-valid candidates, including overlapping quotes
and more than the requested count, never lower agreement. Every segment must
still be verbatim and in source order. Invalid responses score zero and remain
in the denominator. There is no LLM judge. The interactive `quotes` command
retains its count and overlap limits.

## Complete corpus: 169 sources

Each row covers **507 generations**. Exact-match counts describe the highest
scoring individual quote in each generation.

| Version | Mean match score | Change from v001 | Exact text / 507 | Exact span / 507 | Errors / 507 |
| --- | ---: | ---: | ---: | ---: | ---: |
| v001 | 0.2529 | — | 42 | 67 | 25 |
| v003 | 0.1977 | −0.0551 | 26 | 48 | 28 |
| v006 | **0.2655** | +0.0126 | 41 | 67 | 29 |
| v007 | 0.2608 | +0.0080 | **45** | **68** | **22** |
| v008 | 0.2283 | −0.0245 | 31 | 59 | 26 |
| v009 | 0.2547 | +0.0018 | 36 | 64 | 35 |

`v006` improves mean agreement by 0.0126, below the existing 0.0200 threshold.
Its paired source results are **61 wins / 66 ties / 42 losses**. It introduces
failures on 16 sources that the baseline handled and reduces source validity
on 17 sources. `v007` has the most exact matches and fewest failed generations
overall, but also introduces failures on sources that the baseline handled.
These aggregate rankings do not satisfy the promotion gate.

## Newly evaluated test sources: 94 sources

These cases were not evaluated in the preceding prompt-tuning round. Each row
covers **282 generations**, with the prompts fixed beforehand.

| Version | Mean match score | Change from v001 | Exact text / 282 | Exact span / 282 | Errors / 282 |
| --- | ---: | ---: | ---: | ---: | ---: |
| v001 | **0.2357** | — | **21** | **31** | 18 |
| v003 | 0.1697 | −0.0660 | 12 | 20 | 18 |
| v006 | 0.2197 | −0.0160 | 16 | 24 | 19 |
| v007 | 0.2138 | −0.0219 | 18 | 25 | 18 |
| v008 | 0.1842 | −0.0515 | 14 | 21 | 18 |
| v009 | 0.2103 | −0.0254 | 16 | 23 | 20 |

Every candidate scores below the baseline on these new test sources. The closest,
`v006`, has **29 paired wins / 45 ties / 20 losses**, but a negative mean change,
9 newly failed sources, and 10 per-source validity regressions. The full-corpus
gain is concentrated in the previously evaluated Simon test cases: `v006` scores
0.4181 there versus 0.3273 for `v001`. Those 40 cases are not fresh confirmation.

## Corpus and split breakdown

These are mean match scores; the subsets overlap and must not be added together.

| Version | Original 50 | New 119 | Dev 35 | Test 134 |
| --- | ---: | ---: | ---: | ---: |
| v001 | 0.3158 | **0.2264** | 0.2138 | 0.2631 |
| v003 | 0.2629 | 0.1703 | 0.1781 | 0.2028 |
| v006 | **0.3744** | 0.2197 | 0.2138 | **0.2790** |
| v007 | 0.3632 | 0.2178 | 0.2393 | 0.2665 |
| v008 | 0.3130 | 0.1928 | 0.2154 | 0.2317 |
| v009 | 0.3267 | 0.2244 | **0.2560** | 0.2544 |

The [decision](round3/promotion_decision.json) retains `v001`, consistent with
the policy frozen before these calls. This is a comparison of existing prompts,
not another prompt-development round. All 94 new test sources are now evaluated;
later tuning must not describe them as untouched.

Generation variation remains material even with three repeats. The baseline's
development mean moved from 0.2850 in [round 2](PULL_QUOTE_RESULTS.md) to 0.2138
here. All 630 development requests across the six versions have exactly the
same request hashes as their earlier counterparts. The change comes from fresh
provider responses under identical recorded inputs, not a corpus or scorer edit.
Small mean differences should not be treated as proof of a general improvement.
There is one human reference per source; valid alternative quotations can score
zero agreement, so this metric does not independently measure editorial quality.

## Evidence and validation

[benchmark_summary.json](round3/benchmark_summary.json) records every subset's
metrics, exact counts, paired source comparisons, configuration, costs, run paths,
and artifact hashes. [verification.json](round3/verification.json) records the
offline checks. All **3,042 responses were audited**: 2,877 valid generations were
reparsed and rescored with matching source offsets and stored metrics; all 165
rejected responses failed validation again and retained zero score. There were
145 source-segment mismatches and 20 invalid JSON responses, with no missing
provider responses.

Recorded cost: **$2.8139**; input tokens: **9,165,177**; output tokens:
**4,985,857**. Every generation has metered cost. These are recorded usage/pricing
figures, not a billing reconciliation. Each run containing invalid responses
returned a nonzero CLI status after saving its full artifact; all were included.

Raw runs preserve provider responses, accepted predictions, failures and usage:

- [v001](../runs/quote_extraction/20261004-v2-v001-all-r3-expanded.json)
- [v003](../runs/quote_extraction/20261004-v2-v003-all-r3-expanded.json)
- [v006](../runs/quote_extraction/20261004-v2-v006-all-r3-expanded.json)
- [v007](../runs/quote_extraction/20261004-v2-v007-all-r3-expanded.json)
- [v008](../runs/quote_extraction/20261004-v2-v008-all-r3-expanded.json)
- [v009](../runs/quote_extraction/20261004-v2-v009-all-r3-expanded.json)

**46 relevant offline tests pass**, including the lightweight CLI-help import
check. Scoped Ruff and formatting checks pass. Strict MyPy passes for the three
quote modules and the new offline audit script. Live evaluations remain outside CI.

The expanded collection is now the CLI default. Reproduce a version with a new
output path:

```bash
uv run alex eval-quotes --split all --prompt-version v001 \
  --count 5 --repeats 3 --workers 6 --model openai/gpt-6-luna \
  --output /tmp/quotes-expanded-v001.json
```

Use `--dataset evals/quote_extraction/simonwillison/examples.jsonl` to select the
original 50 explicitly. Revalidate the saved benchmark without model calls or
rewriting artifacts:

```bash
uv run python evals/quote_extraction/round3/summarize_benchmark.py --check-only
```
