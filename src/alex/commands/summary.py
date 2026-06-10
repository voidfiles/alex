from __future__ import annotations

from pathlib import Path
from typing import Protocol

import click

from alex.commands.to_asset import (
    lazy_datalab_pdf_markdowner,
    lazy_marker_pdf_markdowner,
    lazy_pymupdf4llm_markdowner,
    select_markdowner,
)
from alex.lib.summary_assets import (
    PdfMarkdowner,
    SummaryAssetConfig,
    SummaryAssetOutput,
    process_summary_asset,
)


class SummaryAssetProcessor(Protocol):
    def __call__(
        self,
        config: SummaryAssetConfig,
        *,
        pdf_markdowner: PdfMarkdowner,
    ) -> SummaryAssetOutput: ...


def build_summary_command(
    processor: SummaryAssetProcessor = process_summary_asset,
    default_pdf_markdowner: PdfMarkdowner = lazy_pymupdf4llm_markdowner,
    miner_pdf_markdowner: PdfMarkdowner = lazy_marker_pdf_markdowner,
    datalab_pdf_markdowner: PdfMarkdowner = lazy_datalab_pdf_markdowner,
) -> click.Command:
    @click.command("summary")
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
    @click.argument(
        "output_path",
        metavar="OUTPUT_PATH",
        type=click.Path(file_okay=False, path_type=Path),
    )
    @click.option(
        "--miner",
        is_flag=True,
        help="Use local marker-pdf for PDF inputs instead of PyMuPDF4LLM.",
    )
    @click.option(
        "--datalab",
        is_flag=True,
        help="Use the Datalab Convert API for PDF inputs.",
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Replace an existing summary asset directory with the same name.",
    )
    def command(
        source: Path,
        output_path: Path,
        miner: bool,
        datalab: bool,
        force: bool,
    ) -> None:
        """Create a summary workspace for an input file."""
        if miner and datalab:
            raise click.UsageError("Choose only one converter option.")

        pdf_markdowner = select_markdowner(
            default_markdowner=default_pdf_markdowner,
            miner_markdowner=miner_pdf_markdowner,
            datalab_markdowner=datalab_pdf_markdowner,
            use_miner=miner,
            use_datalab=datalab,
        )
        config = SummaryAssetConfig(
            source=source,
            output_path=output_path,
            force=force,
        )
        try:
            result = processor(config, pdf_markdowner=pdf_markdowner)
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Wrote {result.asset_dir}")

    return command


summary = build_summary_command()
