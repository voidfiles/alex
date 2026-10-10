# Selecting quotes with text anchors

`alex.lib.text_anchors` lets an LLM select passages using compact anchors while
Python extracts the quotation from the source. It makes no model calls and
imports no LLM, PDF, or embedding libraries. The existing `alex quotes` command
continues to use its existing copied-passage contract.

## Quick start

```python
import json
from pathlib import Path

from alex.lib.text_anchors import TextAnchorDocument

# Preserve the exact decoded text, including CRLF line endings.
source = Path("book.md").read_bytes().decode("utf-8")
document = TextAnchorDocument(
    source,
    document_id="book.md",
    representation_id="raw-markdown-v1",
)
window = document.window()  # Or window("p000042", "p000060") for a large book.
prompt = window.prompt("Passages explaining why exact quotations matter", count=3)

# Send prompt to your chosen LLM. An illustrative response selecting one block:
response = json.dumps({
    "document_id": document.document_id,
    "source_revision": document.source_revision,
    "representation_id": document.representation_id,
    "selections": [{
        "kind": "units",
        "first_unit_id": "p000001",
        "last_unit_id_inclusive": "p000001",
        "purpose": "Introduces the argument.",
    }],
})

quotes = window.extract(response)
for quote in quotes:
    assert source[quote.start:quote.end] == quote.exact
    quote.validate_source(document)
    print(quote.quote_id, quote.exact)
    Path(f"{quote.quote_id}.json").write_text(
        quote.model_dump_json(indent=2), encoding="utf-8"
    )
```

The response copies the three identity fields from the source view. Obtain a
JSON Schema for provider-specific structured outputs with
`AnchorSelections.model_json_schema()`. `window.prompt()` includes this schema
and the versioned instructions in `text_anchor_selection/v001.md`.
`prompt_version="v001"` pins the instructions; otherwise the active version is
loaded from the prompt registry.

## The anchor contract

Preprocessing assigns `p000001`, `p000002`, etc. to runs of nonblank lines.
Soft-wrapped lines remain in one unit. Leading and trailing whitespace lies
outside each unit; whitespace between selected units remains in the quotation.
This is a text segmentation rule, not a Markdown parser: blank lines inside code
blocks also separate units. IDs remain deterministic for the same snapshot.

Choose complete blocks with `kind: "units"`. Both named endpoints are included,
along with all source text between them. The library slices the source directly;
it never joins reconstructed paragraphs.

For precise boundaries, use this selection inside the same response envelope:

```json
{
  "kind": "boundaries",
  "start_unit_id": "p000042",
  "start_text": "The central difficulty is not",
  "end_unit_id": "p000045",
  "end_text": "without changing the underlying evidence.",
  "purpose": "Defines the source fidelity problem."
}
```

Extraction starts at the beginning of `start_text` and ends immediately after
`end_text`. Each snippet is matched exactly within its named unit. Both must lie
inside the resulting passage; snippets can overlap or be identical. Exactly one
ordered boundary pair must match. About 8–15 words is a starting point; extend
snippets when repeated wording creates ambiguity. Do not normalize punctuation,
case, Unicode, or whitespace. Newlines in JSON snippets use `\n` or `\r\n`.

Programmatic callers can use `window.resolve(UnitSelection(kind="units", ...))`
or `window.resolve(BoundarySelection(kind="boundaries", ...))` directly.
A direct selection belongs to the window supplied by the caller; use
`window.extract(response)` when accepting model output so its document identity
is also checked.

## Large documents and validation

Create one document registry, then prepare contiguous windows from its global
IDs. The rendered JSON contains only units in that window, and extraction checks
membership in the same window. Resolve against that window rather than the full
document. A selection cannot cross an unshown gap. Represent nonadjacent
passages as separate selections; a renderer can add ellipses between them.

The default limits are 10 selections and 20,000 code points per quote. Pass
`max_selections`, `max_quote_chars`, and `context_chars` to `extract()`;
`max_quote_chars=None` permits longer passages. Limits reject excessive spans;
they do not choose among ambiguous matches. `prompt(count=...)` controls the
requested count; pass the same count to `extract(max_selections=...)` to enforce
it. Overlapping stand-off annotations are allowed. An invalid selection rejects
the entire response. An empty `selections` array represents abstention.

Errors are `AnchorError` subclasses: `SourceMismatchError`, `UnknownUnitError`,
`AnchorNotFoundError`, and `AmbiguousAnchorError`. Invalid JSON, reversed ranges,
and exceeded limits raise `AnchorError`. Catch these to request corrected
anchors, expand the source window, or abstain. No fuzzy or normalized fallback
silently accepts changed wording.

## Source snapshots and storage

Persist the exact source snapshot along with the quote records. `source_revision`
is SHA-256 of the supplied text encoded as UTF-8. It identifies that text
representation, not an original PDF or EPUB. Keep original artifacts separately.
`representation_id` names the representation chosen by your application. Raw
Markdown retains its syntax in extracted quotes. For readable quotations, first
produce and persist a separate prose snapshot; use a different representation ID.
Offsets from that snapshot cannot be applied to raw Markdown without a mapping.

Every quote stores document identity, revision, representation, start/end,
`exact`, adjacent `prefix`/`suffix`, resolution method, and optional purpose.
Context defaults to 64 code points on either side and can extend outside the
model-visible window. It is extracted by code, unlike model-selected snippets,
which lie inside the passage. `quote_id` is derived from identity and coordinates;
it does not change with purpose or context length. It is a property, so save it
alongside `model_dump()` if downstream consumers need the ID in the JSON.

`quote.selectors()` returns W3C-shaped `TextPositionSelector` and
`TextQuoteSelector` objects. Positions are start-inclusive and end-exclusive;
quote context identifies immediately adjacent text. These shapes follow the
[W3C selector definitions](https://www.w3.org/TR/annotation-model/#selectors).
The enclosing quote record is an application contract, not a complete JSON-LD
Web Annotation. Selectors refer to the supplied representation without implicit
W3C normalization or markup removal.

Offsets count Python Unicode code points, not UTF-8 bytes or JavaScript UTF-16
code units. Emoji and decomposed Unicode are preserved exactly. This library
does not segment grapheme clusters; boundary snippets should include complete
visible characters, as the selection prompt requests.

Restore saved records with `AnchoredQuote.model_validate_json(...)`, then call
`quote.validate_source(document)`. This checks identity, bounds, exact text, and
stored context against the snapshot. It does not reattach quotes after edits.
`locate_exact_quote(source, quote, window=..., prefix=..., suffix=...)` also
provides a strict standalone verifier for full quote strings, detecting repeated
and overlapping occurrences. Its caller must establish source identity.

For later summarization, store quote IDs in generated prose and substitute
`quote.exact` during rendering. Exact extraction establishes text fidelity;
relevance, attribution, and contextual fairness still require review.
