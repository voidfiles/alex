# alex

Personal command line tools for turning PDFs, EPUBs, and Markdown into
Obsidian vault assets with LLM-generated names and summaries. Python,
managed with `uv`.

## Install

Install the CLI globally in editable mode:

```bash
uv tool install --editable /Users/alex/Documents/codes/alex --force
```

This makes `alex` available from any directory while continuing to use the
code in this checkout.

## Setup

Copy `.env.example` to `.env` and fill in the keys you use. The CLI loads
`.env` from this checkout on every run and never overrides variables that
are already exported.

- `ANTHROPIC_API_KEY` — required for `to-asset` naming and `process-doc`
  summaries with the default models.
- `DATALAB_API_KEY` — required only for `--datalab` PDF conversion.
- Other provider keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`, ...) — only if
  you point a model override at that provider.

## Commands

### to-asset

```bash
alex to-asset paper.pdf
alex to-asset book.epub
alex to-asset notes.md
alex to-asset paper.pdf --asset-root /Users/alex/Dropbox/obsidian/Alex3/assets
alex to-asset paper.pdf --miner     # local marker-pdf instead of PyMuPDF4LLM
alex to-asset paper.pdf --datalab   # Datalab Convert API
```

Converts a PDF, EPUB, or Markdown file into a vault asset folder. Extracts
or copies Markdown in a temporary workspace, asks an LLM for canonical
title/author metadata, then finalizes the asset as
`ASSET_ROOT/CANONICAL_NAME` (default asset root is the Obsidian vault
above). The folder ends up with `CANONICAL_NAME.md`, `headers.md`,
`metadata.json`, `canonical_name.txt`, extracted images when applicable,
and the original non-Markdown source file renamed to `CANONICAL_NAME.ext`.
Markdown inputs become the canonical `CANONICAL_NAME.md` directly. The
converter flags only apply to PDFs.

### process-doc

```bash
alex process-doc assets/book_asset
alex process-doc --reprocess-summary assets/book_asset
```

Processes an existing asset directory (it must contain the original file,
one Markdown extract, and `headers.md`). Infers the chapter level, writes
`chapter_level.txt`, `metadata.json`, and `canonical_name.txt`, regenerates
`chunks/*.md`, and generates `chunk_summary.md` plus graph-enhanced
`summary.md` unless `summary.md` already exists. The graph pass extracts
claim/evidence graphs from raw chunks before chunk summarization, merges them
into a document graph, and writes debug artifacts under `summary_graph/`. The
final summary links to `summary_evidence.md`, a sidecar ledger that maps final
claims back to selected evidence, verification status, and repair-pass records.
Generated graph runs also write `summary_graph/manifest.json`, an additive run
index with settings, prompt versions, environment caps, chunk and graph counts,
stage artifact paths, and status/error metadata. It references existing files
instead of copying generated summary bodies.

Use `--reprocess-summary` to compare a previous generated summary against a
fresh run. It moves existing `summary.md`, `chunk_summary.md`,
`summary_evidence.md`, and `summary_graph/` into a timestamped
`_summary_runs/` folder inside the asset before regenerating the summary
artifacts.

### summary

```bash
alex summary paper.pdf assets
alex summary book.md assets
```

Summarizes a PDF, Markdown, TXT, or EPUB input end-to-end into a workspace
at `OUTPUT_PATH/INPUT_STEM`: source copy, extracted Markdown, images,
`headers.md`, `metadata.json`, semantic chunks under `chunks/`, and the
generated `chunk_summary.md`, graph-enhanced `summary.md`, and debug
artifacts under `summary_graph/`, including per-chunk graphs under
`summary_graph/chunks/`, merged document graph artifacts,
`evidence_records.json`, `summary_plan.json`, `summary_claims.json`, and
`revision_passes.json`, plus the additive `summary_graph/manifest.json` run
index when graph artifacts are generated. Use `summary` for the stem-named
one-command workflow, or `to-asset` followed by `process-doc` for the
canonical-named pipeline. The public workflow remains:

```bash
alex summary INPUT OUTPUT_PATH
```

The generated summary wrapper navigation is stable. Links such as "Explore by
Section" and evidence links are produced by the wrapper around the generated
summary text, not by prompt candidates, and should remain available across
summary prompt changes.

Chunking is structure-first: documents split along their headers, and only
oversized chapters (or documents with no usable structure) are split
semantically with embeddings at topic boundaries. Small documents never
call the embedding model.

### ontology

```bash
alex ontology book.md --dry-run
alex ontology book.md
alex ontology book.md artifacts/book.ontology.json --model openai/gpt-6.1-sol
```

Extracts an experimental ontology directly from a Markdown file, defaulting to
`INPUT_STEM.ontology.json` beside the input. It uses the original source text
and discovers its vocabulary: classes and instances with definitions and
aliases, reusable relation types with optional domain/range classes, and
relationship assertions including `subclass_of`, `instance_of`, and `part_of`.
Domain/range lists describe alternative candidate classes, rather than OWL
intersection constraints. The artifact is a versioned JSON document (schema 2).

Each relationship records its own `logic`: `subject_quantifier` (`all`, `some`,
`individual`, or `unspecified`), `object_quantifier` (`some`, `only`, `value`,
or `unspecified`), `polarity`, `strength` (`categorical`, `typical`, `possible`,
or `conditional`), an optional `condition`, and a source-supported `rationale`.
Subject and target scopes are independent. `only` restricts the types of targets
without asserting their existence. Missing scope stays `unspecified`; source
tendencies and possibilities retain their qualifications. Quantifiers are part
of relationship identity, so merging preserves differences in logical strength.

The command tries the whole document in one model call. If it does not fit,
it packs large contiguous passages near the input limit, preferring paragraph
boundaries. Later calls receive the accumulated vocabulary so the model can
reuse concepts and relation types. Local merging normalizes identical labels
and respects reused IDs; no separate model synthesis call is required. Semantic
deduplication of differently named concepts depends on the model reusing IDs.

Token limits come from LiteLLM's model metadata. The input budget subtracts
the response reservation (up to 32,768 tokens by default) and a 2,048-token
safety margin from the model input limit. Full rendered prompts, including
the vocabulary, are counted with LiteLLM's tokenizer. Override the supported
limit with `--context-window` or `ALEX_ONTOLOGY_CONTEXT_WINDOW` when necessary;
unknown models require an explicit limit. `--max-output-tokens` and
`--safety-margin` adjust the reservations. `--reasoning-effort` is passed to
the model when set. `--dry-run` counts initial passes without calling an LLM
or writing files; multi-pass estimates can grow with the shared vocabulary.

Every extracted item must carry exact source quotes. The command validates
the JSON contract, references, evidence substrings, class/instance distinctions,
and subclass cycles before publishing the artifact. Evidence records include
one-based inclusive line numbers and zero-based character offsets with an
exclusive end. The artifact also records the source SHA-256, model, prompt
version and hash, token budget, and each pass's source range and input count.
These checks support review; they do not establish semantic correctness or
complete coverage. A large input fitting in one call can still produce an
incomplete ontology because the output is bounded.

If a model normalizes whitespace (such as a nonbreaking space or line wrap),
the quote is aligned back to the original source span with every word and
punctuation character preserved. The stored `quote` always contains the exact
original substring; `match_mode` and `model_quote` record any whitespace repair.
Changed words or punctuation are rejected.

Use `--force` to replace an existing JSON artifact. A failed run does not
replace an existing artifact. Run `ontology` on a book's extracted Markdown
to experiment alongside its summary; this command is independent of `summary`.

The extraction and normalization choices draw on the
[source-grounded triple extraction workflow](https://arxiv.org/html/2509.00140v2),
the [refinement framework](https://arxiv.org/pdf/2201.05910), and
[OntoMiner's concepts, aliases, and relations](https://files.eric.ed.gov/fulltext/ED558457.pdf).
[Evontree](https://arxiv.org/html/2510.26683v2) motivates consistency checks;
its model-knowledge extraction and fine-tuning workflow is separate from this
document extraction experiment.

#### Standard vocabulary enrichment

Use `--enrich` to add an optional, independently versioned `enrichment` section
to the existing schema-2 JSON. All existing concept, relation, evidence, and
logical-quantifier fields retain their meanings. The original extraction mode
and existing JSON files continue to work with the updated reader.

```bash
alex ontology book.md ontology.json --enrich --max-output-tokens 65536
alex ontology book.md ontology.json --enrich --metadata metadata.json \
  --vocabulary vocabulary.json --requirements requirements.json
```

Enrichment reuses Schema.org, Dublin Core, PROV-O, Web Annotation, SKOS, and
OWL-Time through a bounded offline catalog. The model proposes entity typings,
themes, source metadata, and temporal references in the same source passes.
Code assigns final IDs, maps exact evidence, records actual extraction activity
times, and generates document parts and normalized text representations.
Interpretation generation is disabled; unsupported facts and page numbers are
omitted. Confidence, when supplied with a basis, describes extraction fidelity.

The enriched extraction prompt embeds a compact vocabulary profile with definitions
for people, organizations, books, articles, podcasts, places, events, equipment,
datasets, actions, learning resources, defined terms, and controlled topics. It
selects standard types during extraction and exposes them directly on concept
records, with source-grounded alignment records retained for provenance:

```json
{
  "id": "person-id",
  "type": ["schema:Person"],
  "name": "Rob Gray",
  "label": "Rob Gray",
  "kind": "instance"
}
```

This example omits definitions, aliases, and evidence for brevity. `type` is an
array because an entity may have multiple supported types. `name` mirrors its
source-grounded label (`schema:name`). The primary book record also receives a
`title` property from book metadata (`dcterms:title`); a title is not a separate
concept. These fields are optional in the persisted schema, so older artifacts
still load. Only approved typings appear in `type`; proposals remain in the
alignment records.

`kind` retains the logical class/individual distinction used by quantifiers and
OWL export. A formal class uses `type: ["owl:Class"]`; it can propose a standard
superclass without becoming an individual of that type. Defined terms and SKOS
topics are individuals when they represent terms or classifications themselves.
An individual with no supported semantic category uses `owl:NamedIndividual`;
the extractor does not guess a more specific type. Legacy extraction omits these
optional native fields.

`--metadata` accepts a `title` string, `creator` and `identifier` lists, `language`,
`issued`, and `created`. Language and dates are strings. Explicit metadata
overrides frontmatter; source-extracted values fill remaining fields. Copyright
does not establish publication. `--requirements` accepts `purpose`, `boundaries`,
`competency_questions`, and `assumptions`.

Curated domain vocabulary can provide shared topic identities across books:

```json
{
  "schema_version": 1,
  "terms": [{
    "key": "topics:motor-learning",
    "iri": "urn:alex:topics:motor-learning",
    "kind": "concept",
    "definition": "The acquisition or adaptation of movement skills through practice.",
    "operations": ["exact_match"],
    "roles": ["topic", "instance"],
    "automatic": true
  }]
}
```

`automatic: true` authorizes source-supported use of a curated term; omit it to
retain model mappings as proposals. Established infrastructure types can be
accepted through catalog rules. Matching labels alone never merges books or
asserts `owl:sameAs` or OWL equivalence. Specialized source concepts retain
their definitions. `--application-iri` sets the shared application namespace;
instance identifiers stay source-scoped. `--response-dir` optionally archives
original responses and request hashes for review or recovery.

Enriched evidence quotes must be unambiguous; copied prefix/suffix context can
locate repeated text. Existing raw Markdown coordinates are preserved. Standard
annotation selectors address a separately hashed normalized text representation,
with its normalization version and exact selected substring retained.

Older program versions that reject unknown fields require an updated reader
for enriched JSON. The original schema-2 fields are preserved, and updated
readers still reject unrecognized fields outside the known extension and optional
native `type`, `name`, and `title` concept fields.

### ontology-export

```bash
alex ontology-export assets/book/ontology.json
alex ontology-export assets/book/ontology.json assets/book/ontology.owl
alex ontology-export assets/book/ontology.json assets/book/ontology.jsonld
alex ontology-export assets/book/ontology.json assets/book/ontology.ttl \
  --bundle assets/book/ontology-bundle
```

Converts schema 2 JSON to standard OWL/RDF programmatically, with no model call.
The default is `INPUT_STEM.ttl` (Turtle); `.owl` and `.rdf` select RDF/XML.
`.jsonld` selects JSON-LD using an embedded context, without remote context
resolution. All formats serialize the same graph and undergo a graph-equivalence
round-trip check. Enriched input defaults to the standard book/provenance
projection; `--profile legacy` explicitly selects the original projection.
The standard projection uses SHACL without inference or remote ontology imports.
`--report REPORT.md` writes the requested A-H scope, ontology, evidence, and
validation report with application and instance Turtle files. `--bundle DIR`
writes those artifacts plus a completion manifest of file hashes. Structural
validation does not establish source truth or full semantic consistency.
Concepts become OWL classes or named individuals, with labels, definitions,
aliases, source quotes, and evidence coordinates preserved. Ontology identity
defaults to a stable source-hash URN; set `--base-iri` to use your own absolute
IRI. Use `--force` to replace an export. Serialization is parsed back and checked
for graph equivalence before the file is published.

Categorical positive taxonomy and membership become `rdfs:subClassOf` and
`rdf:type`. Supported ordinary-property assertions become OWL object properties
and restrictions:

| Subject scope | Target scope | OWL reading |
| --- | --- | --- |
| `all` | `some` | Every source member has at least one target-class successor. |
| `all` | `only` | Every source member's successors belong to the target class; existence is unspecified. |
| `some` | `some` / `only` | An anonymous source witness has the specified restriction; the source class is not universally restricted. |
| `individual` | `value` | A named individual relates to a particular named individual. |
| `all` / `some` / `individual` | `value` | The property has a specified named-individual value within the subject scope. |

Negative ordinary restrictions use class complements; negative named-individual
property assertions use `owl:NegativePropertyAssertion`. Negative membership
uses a complement class. Negative taxonomy remains an annotation because
negated subsumption and class disjointness need distinct representations.
Typical, possible, conditional, and unresolved claims retain their logic,
descriptions, and evidence as annotations. Candidate domain/range lists also
remain annotations. These choices follow the
[OWL 2 quantifier and annotation semantics](https://www.w3.org/TR/owl2-primer/).
Export checks validate syntax and structural mappings; a domain expert or
reasoner can provide further semantic review. Older JSON artifacts need
regeneration to add explicit logic before this exporter can consume them.

### quotes

For reusable selection by paragraph IDs or short boundary snippets, see the
[text anchoring library](docs/text-anchors.md). It provides a versioned LLM
selection prompt, exact source extraction, and separate source-backed quote
records through `alex.lib.text_anchors`.

```bash
alex quotes article.md                         # up to three ranked pull quotes
alex quotes article.md --count 1 -o quote.md
cat article.md | alex quotes - --count 2 --json
alex quotes article.md --prompt-version v001   # compare a historical prompt
```

Accepts a Markdown file or `-` for stdin and writes selected quotes as Markdown
blockquotes to stdout. `--json` adds exact source spans and model/prompt
provenance; `-o/--output` writes either format to a file. The default model is
`openai/gpt-6-luna`, with overrides through `ALEX_QUOTE_MODEL` or `--model`.
`--reasoning-effort` is opt-in for models that support it.

The whole document is rendered to readable text before selection. Links keep
their visible text, and Markdown emphasis is removed. Every returned segment
must occur in that rendered source with identical words, case, and punctuation.
Whitespace may reflow; the output recovers the original source substring.
Multiple segments display omissions as `[...]`. Overlapping, invented, or
rewritten quotes fail validation. JSON offsets are zero-based characters into
`alex.lib.quotes.markdown_to_text(source_markdown)`, with exclusive ends;
the artifact stores hashes of both the Markdown and rendered text.

### transcribe

```bash
alex transcribe meeting.wav transcripts
alex transcribe meeting.m4a transcripts --model whisper-1
alex transcribe meeting.wav transcripts --force
```

Transcribes an audio file through LiteLLM and writes a stem-named output
folder at `OUTPUT_PATH/INPUT_STEM` with `transcript.txt` and
`transcript.json`. The default model is OpenAI `whisper-1`; override it
with `ALEX_TRANSCRIPTION_MODEL` or `--model`.

`transcript.txt` is speaker-labelled when the transcription response
includes speaker metadata. OpenAI `whisper-1` does not do real speaker
diarization, so Whisper output is labelled as `Speaker 1` until you switch
to a model that returns speaker-aware segments.

Files above the transcription request size budget are transcoded to 16 kHz
mono mp3 and split into bounded chunks automatically. Oversized inputs
require `ffmpeg` and `ffprobe` on `PATH`.

### brain, brainstorm, and lsd

```bash
alex brain index /path/to/vault --rebuild
alex brainstorm 'How can teams preserve clarity under stress?' --vault /path/to/vault
alex lsd 'What assumption about attention should we invert?' --vault /path/to/vault --limit 1 --save --json
```

`brain` is a disposable local SQLite index; a schema change requires
`alex brain index VAULT --rebuild`. `brainstorm` crosses four close pages with
six distant pages and saves passing/rejected results under `resources/ideas/`
by default. `lsd` crosses two close pages with twelve distant pages, explicitly
tests an axiom inversion, and remains ephemeral unless `--save` is passed.
`--limit` only overrides the profile's distant-page count.

Runs enforce a US$5 default ceiling with `--max-cost`; local models are treated
as free and unpriced remote models fail before a call. JSON goes only to stdout;
progress and errors go to stderr. A credentialed manual smoke run should use a
small fixture vault and `--limit 1`, inspect the returned provenance and cost,
then repeat with `--resume RUN_ID` after an interrupted run. Live provider runs
are deliberately outside CI.

### eval-quotes

```bash
alex eval-quotes --split dev --prompt-version v001 --repeats 3
alex eval-quotes --split test --prompt-version v001 --output /tmp/quotes-test.json
alex eval-quotes --split all --prompt-version v001 --repeats 3
```

Runs the real quote extractor on the
[expanded corpus of 169 source/quote pairs](evals/quote_extraction/quotebacks_dataset/README.md):
the original 50 Simon Willison pairs plus 119 from other curators. The default
requests five candidate quotes on the 35 development cases; `--split test`
selects 134 test cases, and `--split all` selects all 169. Use development cases
to tune new immutable `quote_extraction/vNNN.md` versions; reserve test cases
for comparisons with fixed prompts. The reference quote and editorial metadata
are withheld from the model. To reproduce the original corpus, pass
`--dataset evals/quote_extraction/simonwillison/examples.jsonl` explicitly.

The `best-pull-quote-match/v2` scorer takes the **best individual quote**:
50% source-span F1, 25% exact source-span agreement, and 25% exact reference text
agreement (whitespace may reflow; case and punctuation must match). A complete
text/span match scores 1.0; a complete span with editorial or typographic
differences scores 0.75. Without an exact match, partial passages score below
0.5. Extra quotes,
including overlapping candidates and more than the requested count, never
reduce agreement. Separate quotes cannot jointly claim an exact match.

Only independently source-validated segments are scored. Every returned
segment must be verbatim and in source order; invalid outputs remain in the
denominator with zero score. Precision/recall describe the best quote, and
total reference coverage, exact-match rates, quote count and source validity
are separate diagnostics. Valid alternative quotes can score zero reference
agreement. Quoting the whole article loses precision. There is no LLM judge.
The interactive `quotes` command retains its requested-count and non-overlap
limits. Historical `source-span-f1/v1` runs are not comparable to this scorer.

`--repeats` retains independent generations to measure variation. Request
settings, prompt text/hash, source hashes, raw responses, errors, token usage,
and provider-reported cost are saved under `evals/runs/quote_extraction/`.
`--output` sets an explicit artifact path; existing artifacts are preserved.
`--max-cost` defaults to a US$5 estimated request ceiling, checked before any
model calls. These live benchmarks are local/manual and outside CI.

The first [benchmark and prompt-iteration report](evals/quote_extraction/RESULTS.md)
retains `v001`: development gains from the revised prompts did not survive the
repeated test comparison. The new scoring experiment is documented in
[the pull-quote matching report](evals/quote_extraction/PULL_QUOTE_RESULTS.md).
The [expanded benchmark](evals/quote_extraction/EXPANDED_BENCHMARK.md) reruns six
fixed prompts on all 169 sources with three generations each. `v006` has the
highest overall mean, but `v001` performs best on the 94 new test sources and
remains active.

### eval-summary

```bash
just eval                                   # = alex eval-summary
alex eval-summary --docs guide.md --prompt chunk_summary=v002
alex eval-summary --judge-model openai/gpt-5.6-terra
alex eval-summary --run-id 20260619-graph             # graph-enhanced pipeline
alex eval-summary --no-graph --run-id 20260619-nograph  # plain no-graph baseline
```

Scores summary quality over the documents in `evals/corpus/`. Each doc is
summarized through the real pipeline and graded on fact coverage,
faithfulness to the source, information density, and an LLM rubric for
writing quality; the blended score and per-doc evidence land in
`evals/runs/<run-id>.json`. Salient facts are extracted section-by-section
and cached in `evals/facts/`, so prompt comparisons grade against the same
answer key.

`--no-graph` disables the claim-graph pass so the same harness scores the
plain pipeline; pairing a default run with a `--no-graph` run on the same
corpus (same cached facts and judges) gives a clean A/B of the graph
method against the no-graph baseline. `--no-coverage-repair` disables just
the coverage-repair pass (the step that re-adds graph-supported facts the
merge dropped, before the faithfulness filter) so you can A/B repair on its
own. `--run-id` pins the artifact name so those paired runs are labelled
instead of bare timestamps.

The claim caps that trade brevity for coverage are env-tunable for sweeps:
`ALEX_GRAPH_MAX_CLAIMS` (document subgraph, default 48),
`ALEX_CHUNK_GRAPH_MAX_CLAIMS` (per-chunk subgraph, default 12), and
`ALEX_SOURCE_CLAIMS_PER_SECTION` (claims extracted per section, default 8).

Live summary evals are local/manual gates, not CI. Use explicit run IDs when
comparing candidates so the artifacts in `evals/runs/` are paired and
inspectable:

```bash
alex eval-summary --docs how_to_take_smart_notes_sönke_ahrens.md --run-id sum-pipeline-probe-baseline
alex eval-summary --docs how_to_take_smart_notes_sönke_ahrens.md --prompt final_summary=vNNN --prompt merged_summary=vNNN --run-id sum-pipeline-probe-candidate
alex eval-summary --docs how_to_take_smart_notes_sönke_ahrens.md --prompt final_summary=vNNN --prompt merged_summary=vNNN --no-graph --run-id sum-pipeline-probe-candidate-nograph
alex eval-summary --docs how_to_take_smart_notes_sönke_ahrens.md --prompt final_summary=vNNN --prompt merged_summary=vNNN --no-coverage-repair --run-id sum-pipeline-probe-candidate-norepair
```

Only run the full corpus after the probe passes. A prompt promotion gate should
require mean score delta `>= +0.0200`, a majority of paired docs winning or
tying, no paired-document faithfulness delta `< -0.0100`, and no newly failed
eval document. If no LLM provider credentials are configured, record that
preflight result, run deterministic tests instead, and leave `active.txt`
unchanged.

### improve-prompt

```bash
alex improve-prompt chunk_summary --iterations 3
alex improve-prompt chunk_summary --promote   # activate gate-passing winners
alex improve-prompt chunk_summary --adjudication-repeats 2
```

Iteratively rewrites one of the summary prompts: evaluate the incumbent,
have a critic model rewrite it from the worst document's failures, save
the rewrite as the next `vNNN.md` under `src/alex/prompts/`, and re-score
on the same docs. A candidate passes the gate only with a mean improvement
of at least `--min-delta` and wins-or-ties on a strict majority of docs,
and `active.txt` is only rewritten with `--promote`. Candidates near the
promotion threshold are rejudged without regenerating summaries, then the
promotion gate uses averaged per-document deltas. Every iteration is
appended to `evals/lineage/<prompt>.jsonl`.

### improve-prompts

```bash
alex improve-prompts --critic-model-b openai/gpt-5.5
alex improve-prompts --critic-model-b openai/gpt-5.5 --promote
```

Improves the production summarization prompt stack as one bundle. Two critic
models independently propose rewrites for the summary, graph, and merge prompts;
a synthesis pass blends the proposals; then the candidate bundle is scored
against the fixed eval judges. Changed prompt versions are saved for audit, and
`active.txt` files are only rewritten with `--promote` after the bundle clears
the same mean-delta and majority-doc gate. Raw critic/synthesis artifacts are
written under `evals/prompt_bundles/`, and bundle lineage is appended to
`evals/lineage/production_prompt_bundle.jsonl`.

### eval-judges

```bash
alex eval-judges
alex eval-judges --fail-under 0.85
```

Scores the coverage and faithfulness judges against labelled JSON cases in
`evals/calibration/*.json`. This is report-only unless `--fail-under` is
provided.

### eval-report

```bash
alex eval-report
alex eval-report --output-dir evals/reports/latest
```

Builds `evals/reports/eval-report.md` plus SVG charts from standard
`evals/runs/*.json` and graph-guided `evals/claim_graph/*/run.json`
artifacts. The report compares the latest graph-guided run with the latest
standard run on matching clean documents, then checks the graph-guided scores
against the best historical standard score for each doc.

### pdf-samples

```bash
alex pdf-samples --limit 5
```

Dev tool: re-runs `to-asset` over known sample PDFs with both the default
and marker converters so their Markdown output can be compared.

### dump-env / version

`dump-env` prints the selected `.env` file. `version` prints the installed
version.

## Models

LLM calls go through [LiteLLM](https://docs.litellm.ai), so any provider's
model string works. Each role has an env override (see `src/alex/lib/llm.py`):

| Role | Env var | Default |
| --- | --- | --- |
| Chunk summaries + compression | `ALEX_FAST_SUMMARY_MODEL` | `openai/gpt-6-luna` |
| Pull-quote extraction | `ALEX_QUOTE_MODEL` | `openai/gpt-6-luna` |
| Final synthesis | `ALEX_FINAL_SUMMARY_MODEL` | `openai/gpt-6.1-sol` |
| Ontology extraction | `ALEX_ONTOLOGY_MODEL` | `openai/gpt-6.1-sol` |
| Asset naming | `ALEX_NAMING_MODEL` | `openai/gpt-5.6-terra` |
| Semantic chunking embeddings | `ALEX_EMBEDDING_MODEL` | `openai/text-embedding-3-small` |
| Eval judging | `ALEX_EVAL_JUDGE_MODEL` | `openai/gpt-5.6-terra` |
| Eval fact extraction | `ALEX_FACT_EXTRACTOR_MODEL` | `openai/gpt-6.1-sol` |
| Prompt critic | `ALEX_PROMPT_CRITIC_MODEL` | `openai/gpt-5.6-sol` |
| Audio transcription | `ALEX_TRANSCRIPTION_MODEL` | `whisper-1` |

Example: `ALEX_FINAL_SUMMARY_MODEL=anthropic/claude-opus-5 alex process-doc assets/book_asset`.

Embeddings power semantic chunking (only for oversized or structureless
documents) and claim-graph similarity (claims are linked by embedding cosine
similarity whenever a graph is built). Point `ALEX_EMBEDDING_MODEL` at
another provider (e.g. `voyage/voyage-3.5-lite`) to swap them.

The claim graph links claims whose embeddings exceed a cosine threshold
(`ALEX_CLAIM_SIMILARITY_THRESHOLD`, default `0.8`). Lower it to draw more
`similar_to` edges between claims, raise it to draw fewer.

## Prompts

The pipeline's prompts live as versioned Markdown templates in
`src/alex/prompts/<name>/vNNN.md` with `{{placeholder}}` substitution;
`active.txt` names the version in use. Edit by adding a new version (by
hand or via `improve-prompt`), comparing with
`alex eval-summary --prompt <name>=vNNN`, and flipping `active.txt` when
the numbers say it won.

## Development

```bash
just            # lint + typecheck + tests (same as CI)
just test       # pytest
just lint       # ruff check + format check
just typecheck  # mypy --strict
just fmt        # autoformat + autofix
```

CI runs the same four steps on every push (`.github/workflows/ci.yml`).
Live `alex eval-summary` runs and prompt-promotion gates are local/manual
checks and are not part of CI.

### prepare-outline-level-eval

Create a deterministic sample of raw outlines for manual chapter-level
annotation. Each `output.md` starts with nested frontmatter maps `document`,
`section`, `chapter`, and `subchapter`; fill heading levels with `H1` through
`H6`, leave unknown fields as `TODO`, and do not change the retained outline.

```bash
alex prepare-outline-level-eval --asset-root ~/Documents/Alex3/assets --count 25
```

### eval-outline-level

Score the current chapter-level selector against the annotations and write a
run artifact under the ignored `evals/outline_level/runs/` directory.

```bash
alex eval-outline-level --run-id baseline
```

## Project Layout

```text
src/alex/commands/  # Click command modules
src/alex/prompts/   # Versioned prompt templates (one dir per prompt)
src/alex/lib/       # Reusable library code
  llm.py                 # LiteLLM completer/embedder + model roles
  prompt_templates.py    # versioned {{placeholder}} prompt loader
  markdown_structure.py  # header parsing, chapters, TOC
  chunking.py            # structure-first + semantic chunking
  summarize.py           # map-reduce summary pipeline
  summary_eval.py        # blended summary-quality scoring
  prompt_improvement.py  # critic loop with promotion gate
  asset_metadata.py      # the metadata.json contract
  asset_folders.py       # to-asset flow
  summary_assets.py      # end-to-end summary workspace flow
  process_doc_assets.py  # asset validation + process-doc orchestration
  converters/            # PDF/EPUB/Markdown -> Markdown backends
tests/              # Focused CLI tests
evals/              # Eval corpus, cached facts, run artifacts, lineage
```
