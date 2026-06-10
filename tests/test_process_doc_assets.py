import json
from pathlib import Path
from typing import NamedTuple

import pytest

from alex.lib.process_doc_assets import (
    ProcessDocAssetConfig,
    ProcessDocAssetError,
    process_doc_asset,
)


class BatchSummaryCall(NamedTuple):
    prompts: tuple[str, ...]
    model: str
    max_tokens: int


class FinalSummaryCall(NamedTuple):
    prompt: str
    model: str
    max_tokens: int


class RecordingSummarizer:
    def __init__(
        self,
        *,
        batch_responses: list[tuple[str, ...] | str] | None = None,
        final_response: str = "Final synthesis.",
    ) -> None:
        self.batch_responses = batch_responses or []
        self.final_response = final_response
        self.batch_calls: list[BatchSummaryCall] = []
        self.final_calls: list[FinalSummaryCall] = []

    def complete_batch(
        self,
        *,
        prompts: tuple[str, ...],
        model: str,
        max_tokens: int,
    ) -> tuple[str, ...]:
        self.batch_calls.append(BatchSummaryCall(prompts, model, max_tokens))
        if self.batch_responses:
            response = self.batch_responses.pop(0)
            if isinstance(response, str):
                return tuple(response for _ in prompts)
            return response
        return tuple(f"Summary for chunk {index + 1}." for index in range(len(prompts)))

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> str:
        self.final_calls.append(FinalSummaryCall(prompt, model, max_tokens))
        return self.final_response


def test_process_doc_asset_chunks_an_existing_asset_folder(tmp_path: Path) -> None:
    asset_dir = tmp_path / "systems_book"
    asset_dir.mkdir()
    original = asset_dir / "systems-book.epub"
    original.write_bytes(b"epub")
    markdown = asset_dir / "systems-book.md"
    markdown.write_text(
        "\n".join(
            [
                "# Systems Book",
                "",
                "By Dana Example",
                "",
                "## Foundations",
                "",
                "![Architecture](images/architecture.png)",
                "",
                "Foundations body.",
                "",
                "## Practice",
                "",
                "Practice body.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    headers = asset_dir / "headers.md"
    headers.write_text(
        "\n".join(
            [
                "# Document Structure",
                "",
                "Table of Contents:",
                "",
                "- Systems Book (H1, line 1, 14 lines)",
                "  - Foundations (H2, line 5, 5 lines)",
                "  - Practice (H2, line 11, 4 lines)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    summarizer = RecordingSummarizer(
        batch_responses=[("Foundations summary.", "Practice summary.")],
        final_response="Systems synthesis.",
    )

    result = process_doc_asset(
        ProcessDocAssetConfig(asset_path=asset_dir),
        summarizer=summarizer,
    )

    assert result.asset_dir == asset_dir
    assert result.original_file == original
    assert result.markdown_path == markdown
    assert result.headers_path == headers
    assert result.chapter_level_path.read_text(encoding="utf-8") == "2\n"

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata == {
        "title": "Systems Book",
        "authors": ["Dana Example"],
        "source_format": "epub",
        "source_file": "systems-book.epub",
        "full_markdown": "systems-book.md",
        "headers_file": "headers.md",
        "chapter_level": 2,
        "chunks_dir": "chunks",
    }
    assert result.canonical_name_path.read_text(encoding="utf-8") == (
        "systems_book_dana_example\n"
    )

    chunk_paths = tuple(path.name for path in result.chunk_paths)
    assert chunk_paths == ("001_foundations.md", "002_practice.md")

    foundations = (asset_dir / "chunks" / "001_foundations.md").read_text(
        encoding="utf-8"
    )
    assert foundations.startswith(
        "[Back to full document](../systems-book.md)\n\n# Systems Book\n\n"
    )
    assert "![Architecture](../images/architecture.png)" in foundations
    assert "## Foundations" in foundations
    assert result.chunk_summary_path == asset_dir / "chunk_summary.md"
    assert result.summary_path == asset_dir / "summary.md"
    assert not (asset_dir / "chunk_summaries").exists()

    assert len(summarizer.batch_calls) == 1
    batch_call = summarizer.batch_calls[0]
    assert batch_call.model == "claude-haiku-4-5"
    assert batch_call.max_tokens == 20_000
    assert len(batch_call.prompts) == 2
    assert "<document_metadata>" in batch_call.prompts[0]
    assert "Title: Systems Book" in batch_call.prompts[0]
    assert "Authors: Dana Example" in batch_call.prompts[0]
    assert "<document_structure>" in batch_call.prompts[0]
    assert "Foundations body." in batch_call.prompts[0]

    chunk_summary = result.chunk_summary_path.read_text(encoding="utf-8")
    assert chunk_summary.startswith("# Chunk Summary: Systems Book\n")
    assert "**Author(s):** Dana Example" in chunk_summary
    assert "[Back to full document](systems-book.md)" in chunk_summary
    assert "1. [001_foundations.md](chunks/001_foundations.md)" in chunk_summary
    assert "2. [002_practice.md](chunks/002_practice.md)" in chunk_summary
    assert "Foundations summary." in chunk_summary
    assert "Practice summary." in chunk_summary

    assert len(summarizer.final_calls) == 1
    final_call = summarizer.final_calls[0]
    assert final_call.model == "claude-opus-4-8"
    assert final_call.max_tokens == 8_192
    assert "<section_summaries>" in final_call.prompt
    assert "Foundations summary." in final_call.prompt
    assert "chunks/001_foundations.md" in final_call.prompt

    summary = result.summary_path.read_text(encoding="utf-8")
    assert summary.startswith("# Summary: Systems Book\n")
    assert "[Back to full document](systems-book.md)" in summary
    assert "[View chunk summary](chunk_summary.md)" in summary
    assert "Systems synthesis." in summary
    assert "## Explore by Section" in summary
    assert "1. [001_foundations.md](chunks/001_foundations.md)" in summary


def test_process_doc_asset_recursively_compresses_large_chunk_summaries(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "large_summary"
    asset_dir.mkdir()
    (asset_dir / "large-summary.pdf").write_bytes(b"%PDF")
    (asset_dir / "large-summary.md").write_text(
        "# Large Summary\n\nBy Ada Example\n\n## First\n\nBody.\n",
        encoding="utf-8",
    )
    (asset_dir / "headers.md").write_text(
        "- Large Summary (H1, line 1, 7 lines)\n  - First (H2, line 5, 3 lines)\n",
        encoding="utf-8",
    )
    summarizer = RecordingSummarizer(
        batch_responses=[
            ("Long summary. " * 20,),
            "Compressed summary.",
        ],
        final_response="Final from compressed summaries.",
    )

    result = process_doc_asset(
        ProcessDocAssetConfig(
            asset_path=asset_dir,
            max_summary_context_tokens=50,
        ),
        summarizer=summarizer,
    )

    assert len(summarizer.batch_calls) == 2
    compression_call = summarizer.batch_calls[1]
    assert compression_call.model == "claude-haiku-4-5"
    assert (
        "Consolidate them into a comprehensive summary" in compression_call.prompts[0]
    )
    assert any("Long summary." in prompt for prompt in compression_call.prompts)

    assert result.chunk_summary_path is not None
    chunk_summary = result.chunk_summary_path.read_text(encoding="utf-8")
    assert "Compressed summary." in chunk_summary
    assert "Long summary. Long summary." not in chunk_summary
    assert "Compressed summary." in summarizer.final_calls[0].prompt


def test_process_doc_asset_can_rerun_after_generated_files_exist(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "rerunnable"
    asset_dir.mkdir()
    (asset_dir / "rerunnable.pdf").write_bytes(b"%PDF")
    (asset_dir / "rerunnable.md").write_text(
        "# Rerunnable\n\n## First\n\nBody.\n",
        encoding="utf-8",
    )
    (asset_dir / "headers.md").write_text(
        "- Rerunnable (H1, line 1, 5 lines)\n  - First (H2, line 3, 2 lines)\n",
        encoding="utf-8",
    )
    summarizer = RecordingSummarizer()

    first = process_doc_asset(
        ProcessDocAssetConfig(asset_path=asset_dir),
        summarizer=summarizer,
    )
    (first.chunks_dir / "stale.md").write_text("stale", encoding="utf-8")

    second = process_doc_asset(
        ProcessDocAssetConfig(asset_path=asset_dir),
        summarizer=summarizer,
    )

    assert second.original_file == asset_dir / "rerunnable.pdf"
    assert tuple(path.name for path in second.chunk_paths) == ("001_first.md",)
    assert not (second.chunks_dir / "stale.md").exists()
    assert len(summarizer.batch_calls) == 1


def test_process_doc_asset_requires_headers_markdown_and_original(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "incomplete"
    asset_dir.mkdir()

    with pytest.raises(ProcessDocAssetError, match=r"headers\.md"):
        process_doc_asset(ProcessDocAssetConfig(asset_path=asset_dir))

    (asset_dir / "headers.md").write_text("# Document Structure\n", encoding="utf-8")

    with pytest.raises(ProcessDocAssetError, match="markdown extract"):
        process_doc_asset(ProcessDocAssetConfig(asset_path=asset_dir))

    (asset_dir / "extract.md").write_text("# Extract\n", encoding="utf-8")
    (asset_dir / "one.pdf").write_bytes(b"one")
    (asset_dir / "two.epub").write_bytes(b"two")

    with pytest.raises(ProcessDocAssetError, match="multiple original"):
        process_doc_asset(ProcessDocAssetConfig(asset_path=asset_dir))
