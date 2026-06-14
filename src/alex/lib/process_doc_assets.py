"""Validation and processing of an existing document asset directory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from alex.lib.asset_metadata import AssetMetadata
from alex.lib.chunking import ChunkSettings, chunk_markdown_document
from alex.lib.document_sources import canonical_name_for, metadata_from_markdown
from alex.lib.llm import Completer, Embedder, LiteLlmCompleter, LiteLlmEmbedder
from alex.lib.summarize import (
    SummaryOutput,
    SummarySettings,
    summarize_doc_asset,
)

MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
SOURCE_EXTENSIONS = frozenset({".epub", ".pdf", ".txt", *MARKDOWN_EXTENSIONS})
GENERATED_MARKDOWN_FILES = frozenset(
    {
        "headers.md",
        "summary.md",
        "chunk_summary.md",
    }
)
GENERATED_ASSET_FILES = frozenset(
    {
        "canonical_name.txt",
        "chapter_level.txt",
        "metadata.json",
        "schema.json",
        *GENERATED_MARKDOWN_FILES,
    }
)


class ProcessDocAssetError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessDocAssetConfig:
    asset_path: Path
    summarize: bool = True
    summary: SummarySettings = field(default_factory=SummarySettings)
    chunking: ChunkSettings = field(default_factory=ChunkSettings)


@dataclass(frozen=True)
class ProcessDocAssetOutput:
    asset_dir: Path
    original_file: Path
    markdown_path: Path
    headers_path: Path
    chapter_level_path: Path | None
    metadata_path: Path
    canonical_name_path: Path
    chunks_dir: Path
    chunk_paths: tuple[Path, ...]
    chunk_summary_path: Path | None = None
    summary_path: Path | None = None


def process_doc_asset(
    config: ProcessDocAssetConfig,
    *,
    completer: Completer | None = None,
    embedder: Embedder | None = None,
) -> ProcessDocAssetOutput:
    asset_dir = config.asset_path
    if not asset_dir.is_dir():
        raise ProcessDocAssetError(f"Asset path must be a directory: {asset_dir}")

    headers_path = find_headers_extract(asset_dir)
    markdown_path = find_markdown_extract(asset_dir)
    original_file = find_original_file(asset_dir, markdown_path)

    markdown = markdown_path.read_text(encoding="utf-8")
    headers = headers_path.read_text(encoding="utf-8")

    chunks_dir = asset_dir / "chunks"
    chunking_result = chunk_markdown_document(
        chunks_dir=chunks_dir,
        markdown=markdown,
        markdown_filename=markdown_path.name,
        headers=headers,
        settings=config.chunking,
        embedder=embedder or LiteLlmEmbedder(),
    )
    chunk_paths = chunking_result.chunk_paths

    chapter_level_file = asset_dir / "chapter_level.txt"
    chapter_level_path: Path | None = None
    if chunking_result.chapter_level is None:
        chapter_level_file.unlink(missing_ok=True)
    else:
        chapter_level_file.write_text(
            f"{chunking_result.chapter_level}\n", encoding="utf-8"
        )
        chapter_level_path = chapter_level_file

    metadata = metadata_from_markdown(markdown, markdown_path)
    metadata_path = asset_dir / "metadata.json"
    AssetMetadata(
        title=metadata.title,
        authors=metadata.authors,
        source_format=source_format_for(original_file),
        source_file=original_file.name,
        full_markdown=markdown_path.name,
        headers_file=headers_path.name,
        chapter_level=chunking_result.chapter_level,
        chunks_dir=chunks_dir.name,
    ).write(metadata_path)

    canonical_name_path = asset_dir / "canonical_name.txt"
    canonical_name_path.write_text(
        canonical_name_for(metadata=metadata, source=markdown_path, name_override=None)
        + "\n",
        encoding="utf-8",
    )

    summary_output = SummaryOutput(
        chunk_summary_path=asset_dir / "chunk_summary.md"
        if (asset_dir / "chunk_summary.md").exists()
        else None,
        summary_path=asset_dir / "summary.md"
        if (asset_dir / "summary.md").exists()
        else None,
    )
    if config.summarize:
        summary_output = summarize_doc_asset(
            settings=config.summary,
            asset_dir=asset_dir,
            metadata=metadata,
            markdown_path=markdown_path,
            headers_path=headers_path,
            chunk_paths=chunk_paths,
            completer=completer or LiteLlmCompleter(),
        )

    return ProcessDocAssetOutput(
        asset_dir=asset_dir,
        original_file=original_file,
        markdown_path=markdown_path,
        headers_path=headers_path,
        chapter_level_path=chapter_level_path,
        metadata_path=metadata_path,
        canonical_name_path=canonical_name_path,
        chunks_dir=chunks_dir,
        chunk_paths=chunk_paths,
        chunk_summary_path=summary_output.chunk_summary_path,
        summary_path=summary_output.summary_path,
    )


def find_headers_extract(asset_dir: Path) -> Path:
    headers_path = asset_dir / "headers.md"
    if not headers_path.is_file():
        raise ProcessDocAssetError(
            f"Expected table of contents extract at {headers_path}"
        )
    return headers_path


def find_markdown_extract(asset_dir: Path) -> Path:
    markdown_files = tuple(
        path
        for path in sorted(asset_dir.iterdir())
        if path.is_file()
        and path.suffix.lower() in MARKDOWN_EXTENSIONS
        and path.name not in GENERATED_MARKDOWN_FILES
    )
    if not markdown_files:
        raise ProcessDocAssetError(
            f"Expected one markdown extract in asset folder: {asset_dir}"
        )
    if len(markdown_files) > 1:
        names = ", ".join(path.name for path in markdown_files)
        raise ProcessDocAssetError(
            f"Expected one markdown extract, found multiple: {names}"
        )
    return markdown_files[0]


def find_original_file(asset_dir: Path, markdown_path: Path) -> Path:
    source_files = tuple(
        path
        for path in sorted(asset_dir.iterdir())
        if path.is_file()
        and path.suffix.lower() in SOURCE_EXTENSIONS
        and path.name not in GENERATED_ASSET_FILES
        and path != markdown_path
    )
    if len(source_files) > 1:
        names = ", ".join(path.name for path in source_files)
        raise ProcessDocAssetError(
            f"Expected one original file, found multiple original files: {names}"
        )
    if source_files:
        return source_files[0]

    if markdown_path.suffix.lower() in MARKDOWN_EXTENSIONS:
        return markdown_path

    raise ProcessDocAssetError(f"Expected original file in asset folder: {asset_dir}")


def source_format_for(source: Path) -> str:
    extension = source.suffix.lower()
    if extension in MARKDOWN_EXTENSIONS:
        return "markdown"
    return extension.removeprefix(".")
