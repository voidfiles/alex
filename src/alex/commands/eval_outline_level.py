from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import click

from alex.lib.outline_level_eval import (
    OutlineLevelRunResult,
    evaluate_outline_level,
    validate_outline_level_run_id,
)


class OutlineLevelEvaluator(Protocol):
    def __call__(
        self,
        *,
        evals_dir: Path,
        run_id: str,
    ) -> OutlineLevelRunResult: ...


def build_eval_outline_level_command(
    evaluator: OutlineLevelEvaluator = evaluate_outline_level,
) -> click.Command:
    @click.command("eval-outline-level")
    @click.option(
        "--evals-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("evals"),
        show_default=True,
    )
    @click.option("--run-id", default=None, help="Run artifact directory name.")
    def command(evals_dir: Path, run_id: str | None) -> None:
        """Evaluate chapter-level inference against manual annotations."""
        resolved_run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        try:
            validate_outline_level_run_id(
                evals_dir=evals_dir,
                run_id=resolved_run_id,
            )
            result = evaluator(evals_dir=evals_dir, run_id=resolved_run_id)
        except (OSError, UnicodeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        for case in result.cases:
            expected = case.expected or "TODO"
            click.echo(
                f"{case.case_id}: predicted={case.predicted} "
                f"expected={expected} status={case.status}"
            )
        accuracy = "n/a" if result.accuracy is None else f"{result.accuracy:.4f}"
        click.echo(f"Accuracy: {accuracy} ({result.annotated_count} annotated)")
        click.echo(f"Pending: {result.pending_count}")
        click.echo(f"Run artifact: {result.run_path}")

    return command


eval_outline_level = build_eval_outline_level_command()
