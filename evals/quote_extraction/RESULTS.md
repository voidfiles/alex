# Quote extraction benchmark — 2026-10-04

The extractor and benchmark are implemented. Four prompt revisions were tested;
none improved agreement on the repeated test comparison. **`v001` remains active.**
The development winners improved F1 on 10 sources but regressed on the 40 test
sources. The initial single-generation test gain did not survive repetition.

## Use the commands

```bash
uv run alex quotes article.md --count 3
cat article.md | uv run alex quotes - --count 1 --json
uv run alex quotes article.md -o quotes.md

uv run alex eval-quotes --split dev --prompt-version v001 --repeats 3
uv run alex eval-quotes --split test --prompt-version v001 --repeats 3
```

`quotes` renders the entire Markdown document to readable text, asks the LLM
for ranked passages, and validates each passage against that text. Words, case,
and punctuation must match; whitespace may reflow. The command recovers exact
source substrings and rejects invented wording, modified numbers, reordered
segments, and overlapping selections. Markdown output preserves literal markup
from the source as visible text. JSON includes source hashes, model/prompt
provenance, and character offsets into the rendered text.

The default model is `openai/gpt-6-luna`; use `ALEX_QUOTE_MODEL` or `--model`
to override it. Prompt versions can be pinned with `--prompt-version`.
Reasoning effort is optional because the installed LiteLLM adapter rejects
that parameter for this model. Model calls use the project's LiteLLM completer.

## Evaluation contract

The frozen [dataset](simonwillison/README.md) contains 50 distinct original-source
documents and Simon Willison's reference selections, split into 10 development
and 40 test cases. Only the complete source text goes to the model. Reference
quotes, quotation-post metadata, tags, and source-selection validation are
withheld. Each benchmark requests **one quote**, because each reference contains
one editorial selection; the interactive command defaults to up to three.

Primary score: F1 over **source-word positions** selected by the model and the
reference. Precision penalizes excess text; recall measures how much of the
reference passage was selected. Editorial insertions and omission markers are
excluded using the dataset's validated ordered reference segments. Case,
punctuation, and typography are normalized for agreement scoring. Verbatim
validation of model output is stricter and happens before scoring.

Failures remain in the denominator with F1 zero. Exact span agreement, source
validity, nonempty output, usage, and errors are reported separately. There is
no LLM judge. Source validity means the passages are verbatim; it does not prove
that an omission preserves the author's meaning. A valid alternate passage can
score zero agreement with Simon's selection.

All comparisons keep the dataset, source renderer (`markdown-it-py` 4.2.0),
scorer (`source-span-f1/v1`), system prompt, model, quote count, output-token
ceiling (8,192), and reasoning setting (`None`) fixed. No source truncation,
chunking, or scorer changes were made during prompt development. Later fixes
only escape displayed Markdown and reject non-finite cost ceilings; neither
changes these requests or their scores.

Dataset SHA-256:
`42dda5ed1406b2d4774690a0b7b0effb87bd54a68dba454aa9652c9787c0729a`.

## Prompt iterations

Each development run used three independent generations per source: 30
generations per version. Versions are immutable assets in
[quote_extraction](../../src/alex/prompts/quote_extraction/).

| Version | Selection change | Dev mean F1 | Change from baseline | Errors / 30 |
| --- | --- | ---: | ---: | ---: |
| v001 | Generic informative, memorable, self-contained passages | 0.2219 | — | 0 |
| v002 | Prioritize surprising facts, incidents, comparisons, and practical details | 0.1791 | −0.0428 | 3 |
| v003 | Balance specific observations with significance, lessons, and context | 0.2548 | +0.0329 | 0 |
| v004 | Emphasize expert conclusions and complete causal arguments | 0.1819 | −0.0400 | 0 |
| v005 | Shorter rubric: standalone information, significance, and one complete thought | 0.2538 | +0.0319 | 0 |

The manual gate requires mean F1 improvement of at least 0.02, a majority of
paired source documents winning or tying, no newly failed source, and no
per-source validity regression. Development comparisons average the three
generations for each document. Both `v003` and `v005` passed the development
gate with 3 wins, 5 ties, and 2 losses. `v002` and `v004` were rejected there.

Inspection of development predictions showed that `v003` selected the concrete
AI-assisted learning experience in the Matt Webb source more often than the
baseline, which favored the emotional description of the app. It also improved
agreement for OpenClaw and John Gruber. That came with losses on Laurie Voss and
Tim Schilling. The shorter `v005` helped Tim Schilling but lost some Julia Evans
overlap. These are development observations, not reasons inferred from test
labels. Many choices remained valid but different from the reference.

[The original selection lock](prompt_selection.json) records `v003` as the
development winner **before** testing. Its first test run scored 0.2347 versus
0.2072 for the baseline. Two additional fixed-prompt generations per source
reversed that result. Original runs were preserved, and their repetitions
were combined into separate aggregate artifacts without regenerating predictions.

After that failure, one final simpler prompt (`v005`) was developed using only
development examples. [Its selection lock](followup_selection.json) precedes
its test run. **That follow-up reused an already evaluated test set**, so its
result is exploratory rather than a fresh held-out confirmation. No further
prompts were tried after this follow-up.

## Repeated test comparison

Each row covers the same 40 test sources, with three generations per source:
120 generations per version. Averages include errors.

| Version | Mean F1 | Precision | Recall | Exact span agreement | Source-valid generations | Errors / 120 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v001 | **0.2346** | 0.2457 | 0.2383 | 9.17% | 98.33% | 2 |
| v003 | 0.2109 | 0.2130 | 0.2292 | 4.17% | 100% | 0 |
| v005 | 0.2204 | 0.2162 | 0.2454 | 3.33% | 100% | 0 |

`v003` changed F1 by −0.0237, with 11 paired wins, 20 ties, and 9 losses.
`v005` changed F1 by −0.0142, with 10 wins, 19 ties, and 11 losses. Neither
passed the test gate, despite fewer extraction errors. The baseline's two
failures were invalid JSON and a non-verbatim segment; both were rejected and
saved, rather than emitted as accepted quotes.

Descriptive paired document bootstrap intervals for the F1 changes were
−0.1225 to +0.0688 (`v003`) and −0.1282 to +0.0976 (`v005`). They resample the
40 per-document mean differences 20,000 times with seed 20261004. These wide
intervals underscore the small sample; they do not correct for multiple
candidate attempts or the adaptive follow-up. The evidence supports retaining
the baseline, not claiming a proven quality improvement.

The [promotion decision](promotion_decision.json) retains `v001` explicitly.
Further prompt development needs a larger development set and a fresh test
set. This corpus has no negative/no-quote cases and only one reference editorial
selection per source, so it cannot establish general quote quality or abstention
behavior by itself.

## Evidence and validation

[benchmark_summary.json](benchmark_summary.json) records all aggregate metrics,
paired comparisons, request settings, artifact paths, and artifact hashes.
Raw responses, validated predictions, failures, prompt text, token usage, and
cost are saved under `evals/runs/quote_extraction/`. This feature's benchmark
artifacts are committed as evidence; future generated runs remain ignored.

Relevant raw artifacts:

- Development: `20261004-v001-dev-r3-fixed.json` and
  `20261004-v002-dev-r3.json` through `20261004-v005-dev-r3.json`.
- Repeated test: [v001 aggregate](../runs/quote_extraction/20261004-v001-test-r3-aggregate.json),
  [v003 aggregate](../runs/quote_extraction/20261004-v003-test-r3-aggregate.json),
  and [v005](../runs/quote_extraction/20261004-v005-test-r3.json).
- The first baseline attempt, `20261004-v001-dev-r3.json`, contains 30 local
  unsupported-parameter failures. It is preserved for audit and excluded from
  the prompt comparison; no provider response was received.
- [Default command smoke JSON](../runs/quote_extraction/20261004-command-smoke-v001.json)
  and [Markdown](../runs/quote_extraction/20261004-command-smoke-v001.md) contain
  three quotes from a real provider call. Every segment's source offset was
  checked against the full source.

The metered benchmarks comprise **510 generations** and a recorded cost of
**$0.1778**. This counts aggregate test runs once, excludes the local rejected
requests, and excludes two unmetered single-source command probes. Cost figures
use the completer's recorded usage/pricing and are not a billing reconciliation.
The benchmark command also checks an estimated request ceiling before any call;
its default limit is $5.

Verification: Ruff checks and formatting pass, strict MyPy passes, and 112
focused offline tests pass. All 50 source hashes and reference spans validate
under the command's renderer. The full suite also has four failures in the
pre-existing vault-ingestion changes (`tests/test_process_vault.py` and
`tests/test_process_vault_command.py`), involving processed/resumable asset
detection. Those unrelated changes were preserved.

Before committing, the quote-only staged snapshot passed all 36 quote-specific
tests, Ruff, formatting, strict MyPy, and an offline locked-dependency check.
Its full suite had 477 passes and three failures caused by collision prompt
assets missing from Git. The same three failures were reproduced on the
original HEAD; the unrelated collision assets were excluded from this commit.
