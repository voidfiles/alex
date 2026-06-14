from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from alex.lib.asset_metadata import AssetMetadata
from alex.lib.chunking import ChunkSettings, chunk_markdown_document
from alex.lib.converters.to_markdown import (
    Markdowner,
    ToMarkdownConfig,
    pymupdf4llm_markdowner,
)
from alex.lib.document_sources import (
    DocumentMetadata,
    copy_file,
    metadata_from_markdown,
    read_epub_source,
    title_from_stem,
)
from alex.lib.llm import Completer, Embedder, LiteLlmCompleter, LiteLlmEmbedder
from alex.lib.markdown_structure import table_of_contents_markdown
from alex.lib.summarize import SummarySettings, summarize_doc_asset

SUMMARY_SOURCE_EXTENSIONS = frozenset({".epub", ".markdown", ".md", ".pdf", ".txt"})


class UnsupportedSummarySourceError(ValueError):
    pass


class SummaryAssetExistsError(FileExistsError):
    pass


@dataclass(frozen=True)
class SummaryAssetConfig:
    source: Path
    output_path: Path
    force: bool = False
    summary: SummarySettings = field(default_factory=SummarySettings)
    chunking: ChunkSettings = field(default_factory=ChunkSettings)


@dataclass(frozen=True)
class SummaryAssetOutput:
    asset_dir: Path
    source_copy: Path
    full_markdown: Path
    metadata_path: Path
    headers_path: Path
    chunks_dir: Path
    chunk_paths: tuple[Path, ...]
    chunk_summary_path: Path | None
    summary_path: Path | None


@dataclass(frozen=True)
class SummarySourceContent:
    source_format: str
    metadata: DocumentMetadata
    markdown: str
    source_copy: Path
    full_markdown: Path


def process_summary_asset(
    config: SummaryAssetConfig,
    *,
    pdf_markdowner: Markdowner = pymupdf4llm_markdowner,
    completer: Completer | None = None,
    embedder: Embedder | None = None,
) -> SummaryAssetOutput:
    source_format = summary_source_format_for(config.source)
    asset_dir = config.output_path / config.source.stem

    prepare_summary_asset_dir(asset_dir=asset_dir, force=config.force)
    content = write_summary_source_content(
        source=config.source,
        source_format=source_format,
        asset_dir=asset_dir,
        asset_name=config.source.stem,
        pdf_markdowner=pdf_markdowner,
    )

    headers = table_of_contents_markdown(content.markdown)
    headers_path = asset_dir / "headers.md"
    headers_path.write_text(headers, encoding="utf-8")

    chunks_dir = asset_dir / "chunks"
    chunking_result = chunk_markdown_document(
        chunks_dir=chunks_dir,
        markdown=content.markdown,
        markdown_filename=content.full_markdown.name,
        headers=headers,
        settings=config.chunking,
        embedder=embedder or LiteLlmEmbedder(),
    )

    metadata_path = asset_dir / "metadata.json"
    write_summary_metadata(
        metadata_path=metadata_path,
        content=content,
        headers_filename=headers_path.name,
        chapter_level=chunking_result.chapter_level,
        chunks_dirname=chunks_dir.name,
    )

    summary_output = summarize_doc_asset(
        settings=config.summary,
        asset_dir=asset_dir,
        metadata=content.metadata,
        markdown_path=content.full_markdown,
        headers_path=headers_path,
        chunk_paths=chunking_result.chunk_paths,
        completer=completer or LiteLlmCompleter(),
    )

    return SummaryAssetOutput(
        asset_dir=asset_dir,
        source_copy=content.source_copy,
        full_markdown=content.full_markdown,
        metadata_path=metadata_path,
        headers_path=headers_path,
        chunks_dir=chunks_dir,
        chunk_paths=chunking_result.chunk_paths,
        chunk_summary_path=summary_output.chunk_summary_path,
        summary_path=summary_output.summary_path,
    )


def summary_source_format_for(source: Path) -> str:
    extension = source.suffix.lower()
    if extension not in SUMMARY_SOURCE_EXTENSIONS:
        supported_extensions = ", ".join(sorted(SUMMARY_SOURCE_EXTENSIONS))
        raise UnsupportedSummarySourceError(
            f"Unsupported file type '{extension}'. "
            f"Supported file types: {supported_extensions}"
        )
    if extension == ".epub":
        return "epub"
    if extension in {".markdown", ".md"}:
        return "markdown"
    if extension == ".pdf":
        return "pdf"
    return "txt"


def prepare_summary_asset_dir(asset_dir: Path, *, force: bool) -> None:
    if asset_dir.exists():
        if not force:
            raise SummaryAssetExistsError(
                f"Summary asset directory already exists: {asset_dir}"
            )
        shutil.rmtree(asset_dir)

    asset_dir.mkdir(parents=True)


def write_summary_source_content(
    *,
    source: Path,
    source_format: str,
    asset_dir: Path,
    asset_name: str,
    pdf_markdowner: Markdowner,
) -> SummarySourceContent:
    if source_format == "pdf":
        return write_pdf_summary_source_content(
            source=source,
            asset_dir=asset_dir,
            asset_name=asset_name,
            pdf_markdowner=pdf_markdowner,
        )

    if source_format == "txt":
        return write_text_summary_source_content(
            source=source,
            asset_dir=asset_dir,
            asset_name=asset_name,
        )

    full_markdown = asset_dir / f"{asset_name}.md"
    if source_format == "markdown":
        markdown = source.read_text(encoding="utf-8")
        metadata = metadata_from_markdown(markdown, source)
        copy_file(source, full_markdown)
        source_copy = full_markdown
    else:
        metadata, markdown = read_epub_source(source)
        source_copy = asset_dir / source.name
        copy_file(source, source_copy)
        full_markdown.write_text(markdown, encoding="utf-8")

    return SummarySourceContent(
        source_format=source_format,
        metadata=metadata,
        markdown=markdown,
        source_copy=source_copy,
        full_markdown=full_markdown,
    )


def write_pdf_summary_source_content(
    *,
    source: Path,
    asset_dir: Path,
    asset_name: str,
    pdf_markdowner: Markdowner,
) -> SummarySourceContent:
    source_copy = asset_dir / source.name
    full_markdown = asset_dir / f"{asset_name}.md"
    copy_file(source, source_copy)

    result = pdf_markdowner(
        ToMarkdownConfig(source=source, output_dir=asset_dir, name=asset_name)
    )
    if result.asset != full_markdown:
        copy_file(result.asset, full_markdown)

    markdown = full_markdown.read_text(encoding="utf-8")
    return SummarySourceContent(
        source_format="pdf",
        metadata=metadata_from_markdown(markdown, source),
        markdown=markdown,
        source_copy=source_copy,
        full_markdown=full_markdown,
    )


def write_text_summary_source_content(
    *,
    source: Path,
    asset_dir: Path,
    asset_name: str,
) -> SummarySourceContent:
    source_copy = asset_dir / source.name
    full_markdown = asset_dir / f"{asset_name}.md"
    markdown = source.read_text(encoding="utf-8")
    copy_file(source, source_copy)
    full_markdown.write_text(markdown, encoding="utf-8")

    return SummarySourceContent(
        source_format="txt",
        metadata=DocumentMetadata(title=title_from_stem(source), authors=()),
        markdown=markdown,
        source_copy=source_copy,
        full_markdown=full_markdown,
    )


def write_summary_metadata(
    *,
    metadata_path: Path,
    content: SummarySourceContent,
    headers_filename: str,
    chapter_level: int | None,
    chunks_dirname: str,
) -> None:
    AssetMetadata(
        title=content.metadata.title,
        authors=content.metadata.authors,
        source_format=content.source_format,
        source_file=content.source_copy.name,
        full_markdown=content.full_markdown.name,
        headers_file=headers_filename,
        chapter_level=chapter_level,
        chunks_dir=chunks_dirname,
    ).write(metadata_path)
