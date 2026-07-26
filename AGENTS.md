# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-23
**Commit:** 8fa4a4d
**Branch:** main

## OVERVIEW

`alex` is a Python 3.12 CLI for turning PDFs, EPUBs, Markdown, and audio into
Obsidian-ready assets, summaries, eval artifacts, and prompt-improvement runs.
It is a single `uv`-managed package with one console script: `alex`.

## STRUCTURE

```text
alex/
|-- src/alex/commands/   # Click command layer; keep wrappers thin
|-- src/alex/lib/        # Core asset, summary, graph, eval, LLM, and vault logic
|-- src/alex/prompts/    # Versioned Markdown prompt assets; see scoped rules
|-- tests/               # Flat pytest suite, one file per command/domain
|-- evals/               # Corpus, facts, lineage, reports, and generated runs
|-- docs/superpowers/    # Prompt-loop plans, specs, and workflow docs
|-- pyproject.toml       # Package metadata plus Ruff/MyPy config
|-- Justfile             # Local command entry points
`-- README.md            # User-facing CLI behavior and model/env notes
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Add or change a CLI command | `src/alex/commands/` and `src/alex/commands/main.py` | Commands are Click factories registered in `main.py`. |
| Change asset conversion | `src/alex/lib/asset_folders.py`, `src/alex/lib/converters/` | PDF converter flags apply only to PDFs. |
| Change document processing | `src/alex/lib/process_doc_assets.py`, `src/alex/lib/summarize.py` | Summary artifacts and graph flow are behavior-heavy. |
| Change vault-wide ingestion | `src/alex/lib/process_vault.py`, `src/alex/commands/process_vault.py` | Locking and per-file failure behavior matter. |
| Change eval scoring/reporting | `src/alex/lib/summary_eval.py`, `src/alex/lib/eval_report.py`, `src/alex/commands/eval_*.py` | Live evals call LLMs; reports read stored artifacts. |
| Change prompt versions | `src/alex/prompts/` | Append new `vNNN.md`; see child `AGENTS.md`. |
| Add tests | `tests/` | Reuse `tests/helpers.py` for deterministic fake LLM/embedder behavior. |

## CODE MAP

| Symbol | Type | Location | Refs | Role |
| --- | --- | --- | --- | --- |
| `main` | Click group | `src/alex/commands/main.py` | 4 | Console-script root and command registry. |
| `build_*_command` | function pattern | `src/alex/commands/*.py` | command tests | Injectable Click command factories for tests. |
| `build_asset` | function | `src/alex/lib/asset_folders.py` | command/process paths | Converts source files into canonical asset folders. |
| `process_doc_asset` | function | `src/alex/lib/process_doc_assets.py` | 9 | Processes existing asset dirs into chunks and summaries. |
| `process_vault_root` | function | `src/alex/lib/process_vault.py` | command/tests | Discovers vault sources and orchestrates ingestion. |
| `process_summary_asset` | function | `src/alex/lib/summary_assets.py` | summary command/tests | One-command summary workspace flow. |
| `summarize_doc_asset` | function | `src/alex/lib/summarize.py` | core/tests | Chunk, graph, merge, repair, and final summary flow. |
| `ClaimGraph` | model | `src/alex/lib/claim_graph.py` | graph/tests | Source-grounded claim/evidence graph representation. |
| `SummaryEvaluator` | class | `src/alex/lib/summary_eval.py` | eval/improve commands | Runs corpus scoring and writes eval artifacts. |
| `PromptTemplate` | class | `src/alex/lib/prompt_templates.py` | prompt/eval/tests | Loads versioned prompts and substitutes placeholders. |

LSP was unavailable in this workspace because `basedpyright` is not installed;
code map and reference counts come from CodeGraph plus static inspection.

## CONVENTIONS

- Python target is `>=3.12`; use modern type syntax and keep MyPy strict clean.
- Ruff is authoritative: target `py312`, line length 88, rules `E,F,I,UP,B,SIM,RUF`.
- `src/alex/lib/asset_folders.py` intentionally ignores `E501` because wrapping
  long prompt prose would change the prompt text.
- CLI modules should keep business logic in `alex.lib` and expose injectable
  `build_*_command(...)` factories so tests can pass fakes.
- CLI help must stay lightweight. `tests/test_cli.py` guards against importing
  heavy PDF/LLM dependencies for `--help`.
- `.env` loads from this checkout at CLI startup and must not override already
  exported environment variables.
- Tests are deterministic and offline when practical; use `RecordingCompleter`
  and `BagOfWordsEmbedder` from `tests/helpers.py`.

## ANTI-PATTERNS (THIS PROJECT)

- Do not silently change prompt contracts; add a new prompt version or prompt
  name and evaluate it.
- Do not extract graph claims from generated chunk summaries; graph extraction
  is source/chunk-text grounded.
- Do not replace raw chunk text with graph-only input for chunk summaries.
- Do not add a graph DB, vector DB, or external indexing service without a
  design change proving the current helpers are insufficient.
- Do not change the public `alex summary INPUT OUTPUT_PATH` workflow casually;
  docs treat that shape as stable.
- Do not make live LLM evals part of CI. `just eval` is explicitly local/manual.

## COMMANDS

```bash
uv sync --locked
just check
just lint
just typecheck
just test
uv run pytest tests/test_prompt_templates.py tests/test_prompt_improvement.py -q
uv run alex --help
```

CI runs `uv sync --locked`, Ruff check, Ruff format check, MyPy, and pytest.

## NOTES

- Runtime model calls go through LiteLLM; model env var names are documented in
  `README.md` and centralized in `src/alex/lib/llm.py`.
- Eval artifacts may be large and numerous. Check `evals/AGENTS.md` before
  editing anything under `evals/`.
- The current worktree may contain generated eval/prompt artifacts. Do not
  revert or clean them unless explicitly asked.
