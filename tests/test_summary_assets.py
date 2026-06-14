import json
import zipfile
from pathlib import Path

import pytest

from alex.lib.converters.to_markdown import MarkdownOutput, ToMarkdownConfig
from alex.lib.summarize import SummarySettings
from alex.lib.summary_assets import (
    SummaryAssetConfig,
    SummaryAssetExistsError,
    UnsupportedSummarySourceError,
    process_summary_asset,
)
from helpers import RecordingCompleter


def test_process_markdown_summary_runs_the_full_pipeline(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    completer = RecordingCompleter(
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1),
        ),
        completer=completer,
    )

    asset_dir = tmp_path / "summaries" / "deep-work"
    assert result.asset_dir == asset_dir
    assert result.source_copy == asset_dir / "deep-work.md"
    assert result.full_markdown == asset_dir / "deep-work.md"
    assert result.metadata_path == asset_dir / "metadata.json"
    assert result.headers_path == asset_dir / "headers.md"
    assert result.chunks_dir == asset_dir / "chunks"
    assert tuple(path.name for path in result.chunk_paths) == ("001_deep_work.md",)
    assert result.chunk_summary_path == asset_dir / "chunk_summary.md"
    assert result.summary_path == asset_dir / "summary.md"

    assert result.full_markdown.read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )
    headers = result.headers_path.read_text(encoding="utf-8")
    assert "- Deep Work (H1, line 1, 5 lines)" in headers

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata == {
        "title": "Deep Work",
        "authors": ["Cal Newport"],
        "source_format": "markdown",
        "source_file": "deep-work.md",
        "full_markdown": "deep-work.md",
        "headers_file": "headers.md",
        "chapter_level": 1,
        "chunks_dir": "chunks",
    }

    assert result.summary_path is not None
    summary = result.summary_path.read_text(encoding="utf-8")
    assert "Deep work synthesis." in summary
    assert "1. [001_deep_work.md](chunks/001_deep_work.md)" in summary

    chunk_calls = completer.chunk_calls()
    assert len(chunk_calls) == 1
    assert "Title: Deep Work" in chunk_calls[0].prompt
    assert "Body text." in chunk_calls[0].prompt
    assert len(completer.final_calls()) == 1


def test_process_pdf_summary_converts_inside_stem_named_workspace(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Paper Draft.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    captured_configs: list[ToMarkdownConfig] = []

    def fake_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        captured_configs.append(config)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.image_path.mkdir(parents=True, exist_ok=True)
        (config.image_path / "page-1.png").write_bytes(b"image")
        config.asset_path.write_text(
            "# Paper Draft\n\nExtracted text.\n",
            encoding="utf-8",
        )
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1),
        ),
        pdf_markdowner=fake_markdowner,
        completer=RecordingCompleter(),
    )

    asset_dir = tmp_path / "summaries" / "Paper Draft"
    assert captured_configs == [
        ToMarkdownConfig(source=source, output_dir=asset_dir, name="Paper Draft")
    ]
    assert result.asset_dir == asset_dir
    assert result.source_copy == asset_dir / "Paper Draft.pdf"
    assert result.full_markdown == asset_dir / "Paper Draft.md"
    assert (asset_dir / "images" / "page-1.png").read_bytes() == b"image"
    assert tuple(path.name for path in result.chunk_paths) == ("001_paper_draft.md",)
    assert result.summary_path == asset_dir / "summary.md"

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_format"] == "pdf"
    assert metadata["source_file"] == "Paper Draft.pdf"
    assert metadata["chapter_level"] == 1


def test_process_epub_summary_extracts_markdown_and_preserves_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.epub"
    write_minimal_epub(source)

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1),
        ),
        completer=RecordingCompleter(),
    )

    asset_dir = tmp_path / "summaries" / "sample"
    assert result.source_copy == asset_dir / "sample.epub"
    assert result.full_markdown == asset_dir / "sample.md"
    assert result.source_copy.read_bytes() == source.read_bytes()
    assert result.full_markdown.read_text(encoding="utf-8") == (
        "# Example Book\n\n"
        "By Jane Writer\n\n"
        "# Opening\n\n"
        "The first paragraph.\n\n"
        "The second paragraph.\n"
    )
    assert tuple(path.name for path in result.chunk_paths) == (
        "001_example_book.md",
        "002_opening.md",
    )
    assert result.summary_path == asset_dir / "summary.md"


def test_process_summary_refuses_existing_workspace_without_force(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n", encoding="utf-8")
    existing_asset = tmp_path / "summaries" / "notes"
    existing_asset.mkdir(parents=True)

    with pytest.raises(SummaryAssetExistsError, match="already exists"):
        process_summary_asset(
            SummaryAssetConfig(source=source, output_path=tmp_path / "summaries"),
        )


def write_minimal_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Example Book</dc:title>
    <dc:creator>Jane Writer</dc:creator>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>
""",
        )
        archive.writestr(
            "OEBPS/chapter.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>Opening</h1>
    <p>The first paragraph.</p>
    <p>The second paragraph.</p>
  </body>
</html>
""",
        )


def test_process_summary_force_replaces_existing_workspace(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n", encoding="utf-8")
    existing_asset = tmp_path / "summaries" / "notes"
    existing_asset.mkdir(parents=True)
    stale_file = existing_asset / "stale.md"
    stale_file.write_text("stale", encoding="utf-8")

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            force=True,
            summary=SummarySettings(max_workers=1),
        ),
        completer=RecordingCompleter(),
    )

    assert result.asset_dir == existing_asset
    assert not stale_file.exists()
    assert result.metadata_path.exists()
    assert result.summary_path is not None
    assert result.summary_path.exists()


def test_process_summary_rejects_unsupported_sources(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    source.write_text("name,value\n", encoding="utf-8")

    with pytest.raises(UnsupportedSummarySourceError, match="Supported file types"):
        process_summary_asset(
            SummaryAssetConfig(source=source, output_path=tmp_path / "summaries"),
        )
