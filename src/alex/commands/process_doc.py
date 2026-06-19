from __future__ import annotations

from pathlib import Path
from typing import Protocol

import click

from alex.lib.process_doc_assets import (
    ProcessDocAssetConfig,
    ProcessDocAssetOutput,
    process_doc_asset,
)


class ProcessDocAssetProcessor(Protocol):
    def __call__(self, config: ProcessDocAssetConfig) -> ProcessDocAssetOutput: ...


def build_process_doc_command(
    processor: ProcessDocAssetProcessor = process_doc_asset,
) -> click.Command:
    @click.command("process-doc")
    @click.argument(
        "asset_path",
        metavar="ASSET_PATH",
        type=click.Path(
            exists=True,
            file_okay=False,
            readable=True,
            path_type=Path,
        ),
    )
    def command(asset_path: Path) -> None:
        """Process an existing document asset directory."""
        try:
            result = processor(ProcessDocAssetConfig(asset_path=asset_path))
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Processed {result.asset_dir}")
        click.echo(f"Chunks: {len(result.chunk_paths)}")
        if result.chunk_summary_path is not None:
            click.echo(f"Chunk summary: {result.chunk_summary_path.name}")
        if result.summary_path is not None:
            click.echo(f"Summary: {result.summary_path.name}")
        if result.graph_artifact_dir is not None:
            click.echo(f"Summary graph: {result.graph_artifact_dir.name}")

    return command


process_doc = build_process_doc_command()
