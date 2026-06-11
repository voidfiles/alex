from __future__ import annotations

from pathlib import Path

import click

from alex.lib.asset_folders import (
    DEFAULT_VAULT_ASSET_ROOT,
    AssetNamer,
    ToAssetConfig,
    build_asset,
    llm_asset_namer,
)
from alex.lib.converters.to_markdown import (
    Markdowner,
    datalab_pdf_markdowner,
    epub_markdowner,
    marker_pdf_markdowner,
    pymupdf4llm_markdowner,
    select_markdowner,
)

SUPPORTED_SOURCE_EXTENSIONS = frozenset({".epub", ".pdf"})


class UnsupportedAssetSourceError(ValueError):
    pass


def validate_supported_source(source: Path) -> None:
    source_extension = source.suffix.lower()
    if source_extension in SUPPORTED_SOURCE_EXTENSIONS:
        return

    supported_extensions = ", ".join(sorted(SUPPORTED_SOURCE_EXTENSIONS))
    raise UnsupportedAssetSourceError(
        f"Unsupported file type '{source_extension}'. "
        f"Supported file types: {supported_extensions}"
    )


def build_to_asset_command(
    markdowner: Markdowner = pymupdf4llm_markdowner,
    epub_markdowner: Markdowner = epub_markdowner,
    asset_namer: AssetNamer = llm_asset_namer,
    miner_markdowner: Markdowner = marker_pdf_markdowner,
    datalab_markdowner: Markdowner = datalab_pdf_markdowner,
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
            markdowner,
            miner_markdowner,
            datalab_markdowner,
            use_miner=miner,
            use_datalab=datalab,
        )
        config = ToAssetConfig(source=source, asset_root=asset_root, force=force)
        try:
            result = build_asset(
                config,
                pdf_markdowner=selected_markdowner,
                epub_markdowner=epub_markdowner,
                asset_namer=asset_namer,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Wrote {result.asset_dir}")

    return command


to_asset = build_to_asset_command()
