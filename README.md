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
```

Processes an existing asset directory (it must contain the original file,
one Markdown extract, and `headers.md`). Infers the chapter level, writes
`chapter_level.txt`, `metadata.json`, and `canonical_name.txt`, regenerates
`chunks/*.md`, and generates `chunk_summary.md` plus graph-enhanced
`summary.md` unless `summary.md` already exists. The graph pass extracts
claim/evidence graphs from raw chunks before chunk summarization, merges them
into a document graph, and writes debug artifacts under `summary_graph/`.

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
`summary_graph/chunks/` and merged document graph artifacts. Use `summary` for
the stem-named one-command workflow, or `to-asset` followed by `process-doc`
for the canonical-named pipeline.

Chunking is structure-first: documents split along their headers, and only
oversized chapters (or documents with no usable structure) are split
semantically with embeddings at topic boundaries. Small documents never
call the embedding model.

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

### eval-summary

```bash
just eval                                   # = alex eval-summary
alex eval-summary --docs guide.md --prompt chunk_summary=v002
alex eval-summary --judge-model anthropic/claude-sonnet-4-6
```

Scores summary quality over the documents in `evals/corpus/`. Each doc is
summarized through the real pipeline and graded on fact coverage,
faithfulness to the source, information density, and an LLM rubric for
writing quality; the blended score and per-doc evidence land in
`evals/runs/<run-id>.json`. Salient facts are extracted section-by-section
and cached in `evals/facts/`, so prompt comparisons grade against the same
answer key.

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
| Chunk summaries + compression | `ALEX_FAST_SUMMARY_MODEL` | `anthropic/claude-haiku-4-5` |
| Final synthesis | `ALEX_FINAL_SUMMARY_MODEL` | `anthropic/claude-opus-4-8` |
| Asset naming | `ALEX_NAMING_MODEL` | `anthropic/claude-sonnet-4-6` |
| Semantic chunking embeddings | `ALEX_EMBEDDING_MODEL` | `openai/text-embedding-3-small` |
| Eval judging | `ALEX_EVAL_JUDGE_MODEL` | `anthropic/claude-sonnet-4-6` |
| Eval fact extraction | `ALEX_FACT_EXTRACTOR_MODEL` | `anthropic/claude-opus-4-8` |
| Prompt critic | `ALEX_PROMPT_CRITIC_MODEL` | `anthropic/claude-opus-4-8` |
| Audio transcription | `ALEX_TRANSCRIPTION_MODEL` | `whisper-1` |

Example: `ALEX_FINAL_SUMMARY_MODEL=openai/gpt-5 alex process-doc assets/book_asset`.

Anthropic has no embeddings endpoint, so the embedding default needs an
OpenAI key (or point `ALEX_EMBEDDING_MODEL` at another provider, e.g.
`voyage/voyage-3.5-lite`). It is only ever called for oversized or
structureless documents.

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
