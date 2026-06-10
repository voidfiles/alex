# alex

Python command line tools managed with `uv`.

## Install

Install the CLI globally in editable mode:

```bash
uv tool install --editable /Users/alex/Documents/codes/alex --force
```

This makes `alex` available from any directory while continuing to use the code in this checkout.

## Usage

```bash
uv run alex --help
uv run alex dump-env
uv run alex version
uv run alex to-asset paper.pdf
uv run alex to-asset book.epub
uv run alex to-asset paper.pdf --asset-root /Users/alex/Dropbox/obsidian/Alex3/assets
uv run alex to-asset paper.pdf --miner
uv run alex to-asset paper.pdf --datalab
uv run alex summary paper.pdf assets
uv run alex summary book.md assets
uv run alex process-doc assets/book_asset
alex --help
alex dump-env
alex version
alex to-asset paper.pdf
alex to-asset book.epub
alex to-asset paper.pdf --asset-root /Users/alex/Dropbox/obsidian/Alex3/assets
alex to-asset paper.pdf --miner
alex to-asset paper.pdf --datalab
alex summary paper.pdf assets
alex summary book.md assets
alex process-doc assets/book_asset
```

`dump-env` prints the selected `/Users/alex/Documents/codes/alex/.env` file to stdout. `to-asset` accepts PDF or EPUB input, extracts Markdown in a temporary workspace, asks an LLM for canonical title/author metadata, and finalizes the asset as `ASSET_ROOT/CANONICAL_NAME`, defaulting to `/Users/alex/Dropbox/obsidian/Alex3/assets`. It writes `CANONICAL_NAME.md`, `headers.md`, `metadata.json`, and `canonical_name.txt`, keeps extracted PDF images beside the Markdown, and moves the original source file into the asset folder as `CANONICAL_NAME.ext` after conversion succeeds. For PDFs, it uses PyMuPDF4LLM by default. Pass `--miner` to use local marker-pdf, or pass `--datalab` to use the Datalab Convert API; those converter options only apply to PDFs. `summary` accepts PDF, Markdown, TXT, or EPUB input and creates `OUTPUT_PATH/INPUT_STEM`, keeping the source copy, extracted Markdown, images, and metadata together. `process-doc` accepts an existing asset directory only. The directory must already contain the original file, one Markdown extract, and `headers.md`; the command writes `chapter_level.txt`, `metadata.json`, `canonical_name.txt`, regenerates `chunks/*.md` in place, and generates `chunk_summary.md` plus `summary.md` when `summary.md` is not already present. Use `summary` for the stem-based one-command workflow, or use `to-asset` first and then pass the prepared asset directory to `process-doc`. On startup, the CLI loads `/Users/alex/Documents/codes/alex/.env` and leaves already-exported environment variables in place. The Datalab converter requires `DATALAB_API_KEY` from that file or the environment. To-asset naming and process-doc summarization require `ANTHROPIC_API_KEY`; override the to-asset naming model with `PROCESS_DOC_ASSET_NAMING_MODEL`, and override process-doc summary models with `PROCESS_DOC_FAST_SUMMARY_MODEL` and `PROCESS_DOC_FINAL_SUMMARY_MODEL`.

## Project Layout

```text
src/alex/commands/  # Click command modules
src/alex/lib/       # Reusable library code
tests/              # Focused CLI tests
```
