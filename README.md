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
alex to-asset paper.pdf --asset-root /Users/alex/Dropbox/obsidian/Alex3/assets
alex to-asset paper.pdf --miner     # local marker-pdf instead of PyMuPDF4LLM
alex to-asset paper.pdf --datalab   # Datalab Convert API
```

Converts a PDF or EPUB into a vault asset folder. Extracts Markdown in a
temporary workspace, asks an LLM for canonical title/author metadata, then
finalizes the asset as `ASSET_ROOT/CANONICAL_NAME` (default asset root is
the Obsidian vault above). The folder ends up with `CANONICAL_NAME.md`,
`headers.md`, `metadata.json`, `canonical_name.txt`, extracted images, and
the original source file renamed to `CANONICAL_NAME.ext`. The converter
flags only apply to PDFs.

### process-doc

```bash
alex process-doc assets/book_asset
```

Processes an existing asset directory (it must contain the original file,
one Markdown extract, and `headers.md`). Infers the chapter level, writes
`chapter_level.txt`, `metadata.json`, and `canonical_name.txt`, regenerates
`chunks/*.md`, and generates `chunk_summary.md` plus `summary.md` unless
`summary.md` already exists.

### summary

```bash
alex summary paper.pdf assets
alex summary book.md assets
```

Creates a summary workspace at `OUTPUT_PATH/INPUT_STEM` from a PDF,
Markdown, TXT, or EPUB input: source copy, extracted Markdown, images, and
metadata together. Use `summary` for the stem-named one-command workflow,
or `to-asset` followed by `process-doc` for the canonical-named pipeline.

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

Example: `ALEX_FINAL_SUMMARY_MODEL=openai/gpt-5 alex process-doc assets/book_asset`.

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
src/alex/lib/       # Reusable library code
  llm.py                 # LiteLLM completer + model roles
  markdown_structure.py  # header parsing, chapters, chunking, TOC
  summarize.py           # map-reduce summary pipeline + prompts
  asset_metadata.py      # the metadata.json contract
  asset_folders.py       # to-asset flow
  summary_assets.py      # summary workspace flow
  process_doc_assets.py  # asset validation + process-doc orchestration
  converters/            # PDF/EPUB -> Markdown backends
tests/              # Focused CLI tests
```
