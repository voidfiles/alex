from __future__ import annotations

from pathlib import Path
from typing import Protocol

import click

from alex.lib.outline_level_eval import (
    PreparedOutlineCorpus,
    prepare_outline_level_corpus,
)


class OutlineCorpusPreparer(Protocol):
    def __call__(
        self,
        *,
        asset_root: Path,
        evals_dir: Path,
        count: int,
    ) -> PreparedOutlineCorpus: ...


def build_prepare_outline_level_eval_command(
    preparer: OutlineCorpusPreparer = prepare_outline_level_corpus,
) -> click.Command:
    @click.command("prepare-outline-level-eval")
    @click.option(
        "--asset-root",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("~/Documents/Alex3/assets").expanduser(),
        show_default=True,
    )
    @click.option(
        "--evals-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("evals"),
        show_default=True,
    )
    @click.option("--count", type=click.IntRange(min=1), default=25, show_default=True)
    def command(asset_root: Path, evals_dir: Path, count: int) -> None:
        """Prepare raw outlines for manual chapter-level annotation."""
        try:
            preparer(asset_root=asset_root, evals_dir=evals_dir, count=count)
        except (OSError, UnicodeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Prepared {count} cases in {evals_dir / 'outline_level'}")

    return command


prepare_outline_level_eval = build_prepare_outline_level_eval_command()
