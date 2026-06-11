from __future__ import annotations

from pathlib import Path

import click

from alex.lib.pdf_markdown_samples import (
    DEFAULT_ASSET_ROOT,
    DEFAULT_LIMIT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SAMPLE_FILE,
    run_pdf_markdown_samples,
)


@click.command("pdf-samples")
@click.option(
    "--sample-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=DEFAULT_SAMPLE_FILE,
    show_default=True,
    help="File containing sample names, one per line.",
)
@click.option(
    "--asset-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_ASSET_ROOT,
    show_default=True,
    help="Root Obsidian asset directory to copy samples from.",
)
@click.option(
    "--output-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_OUTPUT_ROOT,
    show_default=True,
    help="Directory where sample test folders are written.",
)
@click.option(
    "--alex",
    "alex_command",
    default="alex",
    show_default=True,
    help="Command used to invoke the alex CLI.",
)
@click.option(
    "--limit",
    type=int,
    default=DEFAULT_LIMIT,
    show_default=True,
    help="Maximum number of samples to process.",
)
def pdf_samples(
    sample_file: Path,
    asset_root: Path,
    output_root: Path,
    alex_command: str,
    limit: int,
) -> None:
    """Compare PDF converters by re-running to-asset over known samples."""
    try:
        results = run_pdf_markdown_samples(
            sample_file=sample_file,
            asset_root=asset_root,
            output_root=output_root,
            alex_command=alex_command,
            limit=limit,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    for result in results:
        click.echo(f"Wrote {result.default_markdown} and {result.miner_markdown}")
