# Additional Quotebacks evaluation cases

**119 additional, verified source–quote pairs**, collected on 2026-10-04 from
the [potential-source catalog](../quotebacks/potential_sources.md). Each case
contains an independently fetched original source in Markdown and a complete
human-selected text excerpt from a Quotebacks embed. No LLM generated the
documents or reference quotes.

Browse [INDEX.md](INDEX.md), load [examples.jsonl](examples.jsonl) for the new
collection, or use [combined_examples.jsonl](combined_examples.jsonl) for all
**169 cases**, including the original 50 Simon Willison cases unchanged.
The combined manifest is now the default dataset for `alex eval-quotes`.
Its default development split has 35 sources; use `--split test` for 134
test sources or `--split all` for the complete collection.
The [expanded benchmark](../EXPANDED_BENCHMARK.md) evaluates all 169 pairs with
six fixed prompts and three generations per source, including all 94 new test
cases. These test cases have now been evaluated and are no longer untouched.

## Coverage

| Curator | New cases |
| --- | ---: |
| Tom Critchlow | 38 |
| Jay Springett / thejaymo | 20 |
| Warren Ellis | 18 |
| Sonya, Supposedly | 13 |
| Sense of Doubt | 8 |
| Velcro City Tourist Board | 7 |
| Don Pizarro / DONFOOLERY | 5 |
| Michael Dempsey | 5 |
| Chuck Grimmett | 3 |
| Brendan Langen | 1 |
| Writing Slowly | 1 |

The original documents span **84 source hosts**. Sources contain **260–9,289
words**, with a median of **1,527**; reference quotes contain **30–496 words**.
These include essays, personal blogs, reporting, research, reference articles,
and some publication or album descriptions. The collection remains concentrated
in a few curators; it is not a representative sample of all editorial tastes.

There are **25 development cases and 94 test cases**. Cases are stratified by
curator and sorted by a deterministic ID hash within each group; approximately
20% go to development. Each original source occurs only once, and no new case
shares a source URL or source Markdown checksum with the original corpus.
The combined collection contains **35 dev / 134 test** cases and retains every
original case's split. Earlier benchmark results still refer to the original
50-case dataset; changing the dataset changes the comparison baseline.

**24 cases cite the curator's own site or its subdomain.** They are marked
`same_publisher_source: true`; these are human selections from other original
documents, and can be filtered out for a stricter study of independent curation.
Domain matching cannot identify every same-author citation across different
domains. Quoted blog posts can themselves quote earlier works: this dataset
stores and validates against the immediately cited source, with its attribution
retained, rather than claiming that page is the ultimate origin of every phrase.

## Files and schema

- `examples.jsonl`: self-contained new cases, compatible with `alex eval-quotes`.
- `combined_examples.jsonl`: original 50 plus the new 119 cases; original file
  paths are rebased to this directory, while source text, labels and splits stay
  unchanged.
- `cases/<id>/source.md`: extracted original source body, never the referring
  quote post or a quote-centered window.
- `cases/<id>/quote.md`: reference excerpt, curator, original URL, and selection
  page URL.
- `splits.json`: explicit new development/test ID lists.
- `candidates.jsonl`: 367 distinct discovered excerpt candidates, including
  multiple selections from the same original source.
- `rejected.jsonl`: attempted pairings rejected for inaccessible, incomplete,
  short, duplicate, unsupported, or unmatched sources. It also records three
  candidates excluded by the final renderer audit.
- `crawl_report.json`: crawl evidence, acquisition counts, lengths, source
  distribution and exclusions.
- `validation_report.json`: offline integrity and negative alignment checks.
- `eval_compatibility_report.json`: loader and reference-position checks using
  the application's actual Markdown renderer, without model calls.
- `build_dataset.py`: standalone collector and offline validator, with pinned
  dependencies; the application's dependencies are unchanged.

The record contract follows the [original dataset](../simonwillison/README.md).
Additional fields include `publisher_domain`, `publisher_name`,
`post_fetched_at`, `publisher_html_sha256`, `source_html_sha256`,
`reference_quote_sha256`, and `same_publisher_source`.

Give the extractor **only `source_markdown`**. Keep the reference quote,
selection-page URL, curator metadata and validation information out of its
input. The labels identify one actual human choice; other source-grounded
selections can also be good quotes. The current evaluator measures agreement
with that reference passage, rather than independently judging editorial merit.

## Collection and verification

The collector starts with verified, promising publishers in the local catalog,
reuses their discovery snapshots, and follows internal links, sitemaps and feeds
in bounded stages. It observed 367 distinct eligible excerpts while checking
1,174 publisher page candidates. The acceptance target was 120; the last batch
produced 122 cases, and the final CommonMark audit excluded three, leaving 119.

Every original is acquired independently through its citation URL. Source
extraction removes comments, webmentions and common interface elements before
converting the body to Markdown. This avoids accepting a short source because
a referring blog's excerpt was copied back into a comment. Sources must have
at least 150 words and 80 words beyond the reference; very long documents above
15,000 words are excluded. No source text is reconstructed from the reference.

All reference words must occur in source order, normalizing case, whitespace,
Unicode typography and punctuation. Explicit ellipses permit intervening
omissions. Bracketed words are **not** silently discarded or treated as
editorial insertions. Published quote text remains unchanged. Validation
offsets address the normalized CommonMark source text, not raw Markdown bytes;
the evaluator independently relocates every reference using its own renderer.

The final audit re-extracted every source from its independently fetched HTML
snapshot, checked its HTML checksum, and recomputed its Markdown and alignment.
The application then loaded all 119 new cases and all 169 combined cases and
located every reference without an LLM call. Source extraction can still omit
non-text media or leave minor boilerplate; verified text matching does not
certify every other paragraph on the page.

Known robots disallows, HTTP failures, login/challenge responses, unsupported
documents, social timelines and inaccessible full text were not reconstructed
or bypassed. Raw responses remain in the task-specific caches outside the
repository. The recorded snapshot and exclusion reasons make these limits
inspectable.

## Validate or evaluate

Validate saved files offline:

```bash
uv run --script evals/quote_extraction/quotebacks_dataset/build_dataset.py \
  --validate-only
```

Run a new development evaluation explicitly against this collection:

```bash
uv run alex eval-quotes \
  --dataset evals/quote_extraction/quotebacks_dataset/examples.jsonl \
  --split dev --output evals/runs/quote_extraction/quotebacks-dev-v001.json
```

For the combined evaluation, replace the dataset path with
`combined_examples.jsonl`. Live evaluations call the configured model and use
the command's usual cost preflight; collection and validation did not call one.

Collect a new snapshot into a separate directory:

```bash
uv run --script evals/quote_extraction/quotebacks_dataset/build_dataset.py \
  --target 120 --max-pages 80 --output /tmp/quotebacks-dataset
```

This can produce different cases as publisher pages and availability change.
The saved collection is the fixed input for future comparisons. `--audit-saved`
re-extracts saved inputs from exact cached HTML and regenerates the manifests;
it requires those local raw snapshots and is intended for collection auditing,
not routine validation of a checked-out dataset.

Original sources retain their authors' copyrights. Each reference selection is
attributed to its curator, with both publication URLs retained.
