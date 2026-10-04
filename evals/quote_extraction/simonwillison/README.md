# Quote extraction reference dataset

50 original-source / pull-quote pairs selected from
[Simon Willison's quotations archive](https://simonwillison.net/quotations/).
Collected on 2026-10-04; the selected posts run from 2026-02-26 to 2026-10-01.
These are human editorial selections. No LLM generated the sources or labels.

Browse the [50 cases](INDEX.md), or load [examples.jsonl](examples.jsonl).

## Contents

- `examples.jsonl`: one self-contained record per case, including the source
  Markdown, reference quote, provenance, split, and source-grounding checks.
- `cases/<id>/source.md`: the original source item's body converted to Markdown.
- `cases/<id>/quote.md`: Simon's selected quote, with attribution and links to
  both the original source and the quotation post.
- `splits.json`: 10 development IDs and 40 held-out test IDs.
- `candidates.jsonl`: all 150 quotation posts discovered across five archive pages.
- `rejected.jsonl`: the 73 attempted cases excluded from the final dataset,
  with their source links, quote text, and exclusion reasons.
- `crawl_report.json`: collection counts, source hosts, word counts, and the
  status of the three examples supplied in the request.
- `validation_report.json`: integrity checks, comparison with the original
  archive quotation blocks, and negative checks for altered numbers, reordered
  segments, and changed source text.
- `build_dataset.py`: standalone, cached collector and offline validator.
  Its pinned dependencies do not change the application's dependencies.

The 50 sources span 43 hosts. Source length is 182–11,226 words, with a median
of 1,309.5 words. Reference quotes are 30–248 words. Counts use Unicode word
tokens after converting Markdown to plain text.

## Record fields

| Field | Meaning |
| --- | --- |
| `id` | Stable quotation-post date and slug. |
| `source_markdown` | Model input: the source body, not the quotation post. |
| `reference_quote` | Plain text of the complete quotation block, including lists. |
| `reference_quote_markdown` | The same quote with paragraph/list formatting and links. |
| `source_markdown_path`, `quote_markdown_path` | File paths relative to this directory. |
| `post_url`, `post_date` | Where and when Simon selected the quote. |
| `attribution`, `context`, `tags` | Attribution and editorial metadata from the quotation post. |
| `source_url`, `resolved_source_url` | Original citation and URL after HTTP redirects. |
| `source_title`, `source_fetched_at` | Source title and acquisition time. |
| `source_sha256` | SHA-256 of the UTF-8 source Markdown. |
| `extraction_method` | How the source body was extracted. |
| `source_word_count`, `quote_word_count` | Input and reference lengths. |
| `split` | `dev` or `test`. |
| `validation` | Ordered source matches and editorial markers. |

Example loading from the repository root:

```python
import json
from pathlib import Path

path = Path("evals/quote_extraction/simonwillison/examples.jsonl")
cases = [json.loads(line) for line in path.read_text().splitlines()]
test_cases = [case for case in cases if case["split"] == "test"]

model_input = test_cases[0]["source_markdown"]
reference = test_cases[0]["reference_quote"]
```

Give the extractor only `source_markdown`. Keep the reference, quotation-post
URL, tags, and other editorial metadata outside its input. Use the development
cases for prompt work and reserve the test cases for comparisons. The split is
deterministic for this snapshot, using a hash of the case ID; no original source
URL or source Markdown hash appears twice.

## Collection and verification

The collector follows the quotations archive's pagination, newest first, and
reads each quotation's `blockquote[cite]` to identify its original source.
It keeps the complete main quotation block, rather than selecting arbitrary
blockquotes from longer blog posts. Each source is fetched independently and
converted from its article body to Markdown. It preserves headings, links,
lists, and available footnotes, while removing common navigation and interface
elements. GitHub commit sources contain the original commit message; forum
links are restricted to the cited comment, never the entire discussion.

Sources are body snapshots extracted from published HTML, not summaries or
quote-centered windows. Automatic article extraction can still leave minor
boilerplate or omit non-text media. Matching the quote establishes source
grounding; it does not independently certify every other paragraph of the page.

An example is included only if its source has at least 150 words and at least
80 words beyond the quote, and **every non-editorial quote segment appears in
source order**. Comparison ignores whitespace, case, Unicode typography, and
punctuation. Simon's ellipses (`[...]`, `…`, `...`) separate segments; bracketed
insertions such as `[internal Binary Exploitation benchmark]` are explicitly
recorded and excluded from verbatim matching. The published quote remains
unchanged in the reference Markdown. This permits edited pull quotes without
pretending they are single, contiguous, exact source substrings.

`normalized_source_start` and `normalized_source_end` are zero-based character
offsets into `normalized(markdown_text(source_markdown))`, as defined in the
collector; the end is exclusive. They are not offsets into the raw Markdown.

Social/video posts, blocked pages, incomplete or short sources, configuration
files, unsupported PDF/text responses, and unmatched quotes are excluded and
logged. Requests are bounded, paced per host, and checked against available
robots rules. The Matthew Green and Anthropic Frontier Red Team examples are
included. The @joedaroo example is excluded because its X/Twitter source
disallows this crawler; its source text was not reconstructed from Simon's quote.

## Reproduce or validate

From the repository root, validate the saved corpus without network requests:

```bash
uv run --script evals/quote_extraction/simonwillison/build_dataset.py --validate-only
```

Validation checks the count, unique sources, file/JSONL agreement, checksums,
full quote text versus quote Markdown, ordered source matches, and split integrity.

Collect another snapshot into a separate directory:

```bash
uv run --script evals/quote_extraction/simonwillison/build_dataset.py \
  --target 50 --max-pages 8 --refresh --output /tmp/quote-dataset
```

Raw HTTP responses are cached outside the repository at
`~/.cache/alex/quote-dataset/`. Without `--refresh`, the collector reuses them.
Recollection can change the selected cases and split as source pages change;
the committed dataset files are the fixed evaluation inputs.

## Evaluation interpretation

These references capture **which passage Simon chose**, not the only acceptable
quote in each source. Source faithfulness and agreement with his selection are
separate questions. Exact match alone will penalize valid alternate selections,
different excerpt boundaries, and omission of editorial annotations.
`alex eval-quotes` checks source grounding separately from source-passage overlap;
the [benchmark report](../RESULTS.md) documents the first prompt iterations and
the subsequent reuse of the test set. It does not independently judge editorial
quality. There are no negative/no-quote cases in this corpus, and it
reflects this blog's subject matter and selection preferences rather than a
representative sample of all writing.

Original sources retain their authors' copyrights; quote selections are
attributed to Simon Willison. Provenance is retained for every case.
