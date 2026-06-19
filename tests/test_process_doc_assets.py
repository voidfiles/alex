import hashlib
import json
from pathlib import Path

import pytest

from alex.lib.process_doc_assets import (
    ProcessDocAssetConfig,
    ProcessDocAssetError,
    process_doc_asset,
)
from alex.lib.summarize import SummarySettings
from helpers import RecordingCompleter


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
    completer = RecordingCompleter(
        chunk_responses=["Foundations summary.", "Practice summary."],
        final_response="Systems synthesis.",
    )

    result = process_doc_asset(
        ProcessDocAssetConfig(
            asset_path=asset_dir,
            summary=SummarySettings(max_workers=1),
        ),
        completer=completer,
    )

    assert result.asset_dir == asset_dir
    assert result.original_file == original
    assert result.markdown_path == markdown
    assert result.headers_path == headers
    assert result.chapter_level_path is not None
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
        "source_sha256": hashlib.sha256(b"epub").hexdigest(),
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
    assert result.graph_artifact_dir == asset_dir / "summary_graph"
    assert result.graph_artifact_dir.is_dir()
    assert not (asset_dir / "chunk_summaries").exists()

    chunk_calls = completer.chunk_calls()
    assert len(chunk_calls) == 2
    assert {call.model for call in chunk_calls} == {"anthropic/claude-haiku-4-5"}
    assert {call.max_tokens for call in chunk_calls} == {20_000}
    assert "<document_metadata>" in chunk_calls[0].prompt
    assert "Title: Systems Book" in chunk_calls[0].prompt
    assert "Authors: Dana Example" in chunk_calls[0].prompt
    assert "<document_structure>" in chunk_calls[0].prompt
    assert "- Systems Book (H1, line 1, 14 lines)" in chunk_calls[0].prompt
    assert "Foundations body." in chunk_calls[0].prompt
    assert completer.compression_calls() == []

    chunk_summary = result.chunk_summary_path.read_text(encoding="utf-8")
    assert chunk_summary.startswith("# Chunk Summary: Systems Book\n")
    assert "**Author(s):** Dana Example" in chunk_summary
    assert "[Back to full document](systems-book.md)" in chunk_summary
    assert "1. [001_foundations.md](chunks/001_foundations.md)" in chunk_summary
    assert "2. [002_practice.md](chunks/002_practice.md)" in chunk_summary
    assert "Foundations summary." in chunk_summary
    assert "Practice summary." in chunk_summary

    final_calls = completer.final_calls()
    assert len(final_calls) == 1
    final_call = final_calls[0]
    assert final_call.model == "anthropic/claude-opus-4-8"
    assert final_call.max_tokens == 8_192
    assert "Foundations summary." in final_call.prompt
    assert "chunks/001_foundations.md" in final_call.prompt

    summary = result.summary_path.read_text(encoding="utf-8")
    assert summary.startswith("# Summary: Systems Book\n")
    assert "[Back to full document](systems-book.md)" in summary
    assert "[View chunk summary](chunk_summary.md)" in summary
    assert "Faithful Systems synthesis." in summary
    assert "## Explore by Section" in summary
    assert "1. [001_foundations.md](chunks/001_foundations.md)" in summary
    assert (result.graph_artifact_dir / "standard_summary.md").read_text(
        encoding="utf-8"
    ) == "Systems synthesis."
    assert (result.graph_artifact_dir / "faithfulness_filtered_summary.md").read_text(
        encoding="utf-8"
    ) == "Faithful Systems synthesis."


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
    completer = RecordingCompleter(
        chunk_responses=["Long summary. " * 20],
        compression_response="Compressed summary.",
        final_response="Final from compressed summaries.",
    )

    result = process_doc_asset(
        ProcessDocAssetConfig(
            asset_path=asset_dir,
            summary=SummarySettings(max_context_tokens=50, max_workers=1),
        ),
        completer=completer,
    )

    assert len(completer.chunk_calls()) == 1
    compression_calls = completer.compression_calls()
    assert len(compression_calls) == 2
    assert {call.model for call in compression_calls} == {"anthropic/claude-haiku-4-5"}
    assert all(
        "Consolidate them into a comprehensive summary" in call.prompt
        for call in compression_calls
    )
    assert any("Long summary." in call.prompt for call in compression_calls)

    assert result.chunk_summary_path is not None
    chunk_summary = result.chunk_summary_path.read_text(encoding="utf-8")
    assert "Compressed summary." in chunk_summary
    assert "Long summary. Long summary." not in chunk_summary
    assert "Compressed summary." in completer.final_calls()[0].prompt


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
    completer = RecordingCompleter()

    first = process_doc_asset(
        ProcessDocAssetConfig(
            asset_path=asset_dir,
            summary=SummarySettings(max_workers=1),
        ),
        completer=completer,
    )
    (first.chunks_dir / "stale.md").write_text("stale", encoding="utf-8")

    second = process_doc_asset(
        ProcessDocAssetConfig(
            asset_path=asset_dir,
            summary=SummarySettings(max_workers=1),
        ),
        completer=completer,
    )

    assert second.original_file == asset_dir / "rerunnable.pdf"
    assert tuple(path.name for path in second.chunk_paths) == ("001_first.md",)
    assert not (second.chunks_dir / "stale.md").exists()
    assert len(completer.chunk_calls()) == 1


def test_process_doc_asset_handles_structureless_markdown(tmp_path: Path) -> None:
    asset_dir = tmp_path / "structureless"
    asset_dir.mkdir()
    (asset_dir / "notes.pdf").write_bytes(b"%PDF")
    (asset_dir / "notes.md").write_text(
        "Plain notes without any headings.\n\nJust prose paragraphs.\n",
        encoding="utf-8",
    )
    (asset_dir / "headers.md").write_text(
        "# Document Structure\n\nTable of Contents:\n",
        encoding="utf-8",
    )
    # A stale marker from a previous structured run must not survive.
    (asset_dir / "chapter_level.txt").write_text("2\n", encoding="utf-8")
    completer = RecordingCompleter()

    result = process_doc_asset(
        ProcessDocAssetConfig(
            asset_path=asset_dir,
            summary=SummarySettings(max_workers=1),
        ),
        completer=completer,
    )

    assert result.chapter_level_path is None
    assert not (asset_dir / "chapter_level.txt").exists()
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert "chapter_level" not in metadata
    assert tuple(path.name for path in result.chunk_paths) == (
        "001_plain_notes_without_any_headings.md",
    )
    chunk = result.chunk_paths[0].read_text(encoding="utf-8")
    assert chunk.startswith("[Back to full document](../notes.md)\n\n")
    assert "Just prose paragraphs." in chunk
    assert result.summary_path == asset_dir / "summary.md"


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
