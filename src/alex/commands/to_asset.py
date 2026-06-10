from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import click

from alex.lib.asset_folders import (
    DEFAULT_VAULT_ASSET_ROOT,
    AssetNamer,
    EpubMarkdowner,
    PdfMarkdowner,
    ToAssetConfig,
    ToAssetOutput,
    build_asset,
    llm_asset_namer,
)

if TYPE_CHECKING:
    from alex.lib.converters.to_markdown import MarkdownOutput, ToMarkdownConfig


SUPPORTED_SOURCE_EXTENSIONS = frozenset({".epub", ".pdf"})


class UnsupportedAssetSourceError(ValueError):
    pass


class AssetBuilder(Protocol):
    def __call__(
        self,
        config: ToAssetConfig,
        *,
        pdf_markdowner: PdfMarkdowner,
        epub_markdowner: EpubMarkdowner,
        asset_namer: AssetNamer,
    ) -> ToAssetOutput: ...


def validate_supported_source(source: Path) -> None:
    source_extension = source.suffix.lower()
    if source_extension in SUPPORTED_SOURCE_EXTENSIONS:
        return

    supported_extensions = ", ".join(sorted(SUPPORTED_SOURCE_EXTENSIONS))
    raise UnsupportedAssetSourceError(
        f"Unsupported file type '{source_extension}'. "
        f"Supported file types: {supported_extensions}"
    )


def lazy_pymupdf4llm_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    from alex.lib.converters.to_markdown import pymupdf4llm_markdowner

    return pymupdf4llm_markdowner(config)


def lazy_marker_pdf_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    from alex.lib.converters.to_markdown import marker_pdf_markdowner

    return marker_pdf_markdowner(config)


def lazy_datalab_pdf_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    from alex.lib.converters.to_markdown import datalab_pdf_markdowner

    return datalab_pdf_markdowner(config)


def lazy_epub_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
    from alex.lib.converters.to_markdown import epub_markdowner

    return epub_markdowner(config)


def build_to_asset_command(
    markdowner: PdfMarkdowner = lazy_pymupdf4llm_markdowner,
    epub_markdowner: EpubMarkdowner = lazy_epub_markdowner,
    asset_namer: AssetNamer = llm_asset_namer,
    miner_markdowner: PdfMarkdowner = lazy_marker_pdf_markdowner,
    datalab_markdowner: PdfMarkdowner = lazy_datalab_pdf_markdowner,
    asset_builder: AssetBuilder = build_asset,
) -> click.Command:
    @click.command("to-asset")
    @click.argument(
        "source",
        metavar="INPUT",
        type=click.Path(
            exists=True,
            dir_okay=False,
            readable=True,
            path_type=Path,
        ),
    )
    @click.option(
        "--asset-root",
        type=click.Path(file_okay=False, path_type=Path),
        default=DEFAULT_VAULT_ASSET_ROOT,
        show_default=True,
        help="Root vault asset folder.",
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Replace an existing asset folder with the same source name.",
    )
    @click.option(
        "--miner",
        is_flag=True,
        help="Use local marker-pdf instead of PyMuPDF4LLM.",
    )
    @click.option(
        "--datalab",
        is_flag=True,
        help="Use the Datalab Convert API instead of a local converter.",
    )
    def command(
        source: Path,
        asset_root: Path,
        force: bool,
        miner: bool,
        datalab: bool,
    ) -> None:
        """Convert a PDF or EPUB into a vault asset folder."""
        if miner and datalab:
            raise click.UsageError("Choose only one converter option.")

        try:
            validate_supported_source(source)
        except UnsupportedAssetSourceError as error:
            raise click.ClickException(str(error)) from error
        if source.suffix.lower() != ".pdf" and (miner or datalab):
            raise click.UsageError("PDF converter options only apply to PDF inputs.")

        selected_markdowner = select_markdowner(
            default_markdowner=markdowner,
            miner_markdowner=miner_markdowner,
            datalab_markdowner=datalab_markdowner,
            use_miner=miner,
            use_datalab=datalab,
        )
        config = ToAssetConfig(source=source, asset_root=asset_root, force=force)
        try:
            result = asset_builder(
                config,
                pdf_markdowner=selected_markdowner,
                epub_markdowner=epub_markdowner,
                asset_namer=asset_namer,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Wrote {result.asset_dir}")

    return command


def select_markdowner(
    default_markdowner: PdfMarkdowner,
    miner_markdowner: PdfMarkdowner,
    datalab_markdowner: PdfMarkdowner,
    *,
    use_miner: bool,
    use_datalab: bool,
) -> PdfMarkdowner:
    if use_datalab:
        return datalab_markdowner
    if use_miner:
        return miner_markdowner
    return default_markdowner


to_asset = build_to_asset_command()
