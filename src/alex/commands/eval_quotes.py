"""Manual live benchmark for quote selection."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import click

from alex.lib.llm import resolve_quote_model
from alex.lib.quote_eval import (
    DEFAULT_QUOTE_DATASET,
    QuoteEvalSettings,
    evaluate_quotes,
)
from alex.lib.quotes import QuoteSettings


def build_eval_quotes_command(
    evaluator: Callable[..., dict[str, Any]] = evaluate_quotes,
) -> click.Command:
    @click.command("eval-quotes")
    @click.option(
        "--dataset",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        default=DEFAULT_QUOTE_DATASET,
        show_default=True,
    )
    @click.option(
        "--split",
        type=click.Choice(["dev", "test", "all"]),
        default="dev",
        show_default=True,
    )
    @click.option("--prompt-version", help="Pin a quote_extraction prompt version.")
    @click.option("--model", default=resolve_quote_model)
    @click.option("--count", type=click.IntRange(1, 10), default=1, show_default=True)
    @click.option("--repeats", type=click.IntRange(1), default=1, show_default=True)
    @click.option("--workers", type=click.IntRange(1), default=4, show_default=True)
    @click.option(
        "--max-cost",
        type=click.FloatRange(min=0, min_open=True),
        default=5.0,
        show_default=True,
        help="USD estimated request ceiling.",
    )
    @click.option(
        "--max-output-tokens", type=click.IntRange(1), default=8192, show_default=True
    )
    @click.option(
        "--reasoning-effort",
        type=click.Choice(["low", "medium", "high"]),
        default=None,
        help="Optional reasoning effort, only for models that support it.",
    )
    @click.option(
        "--output",
        type=click.Path(dir_okay=False, path_type=Path),
        help="Run JSON path; existing artifacts are never overwritten.",
    )
    def command(
        dataset: Path,
        split: Literal["dev", "test", "all"],
        prompt_version: str | None,
        model: str,
        count: int,
        repeats: int,
        workers: int,
        max_cost: float,
        max_output_tokens: int,
        reasoning_effort: str | None,
        output: Path | None,
    ) -> None:
        """Benchmark real quote extraction; makes paid model calls, never runs in CI."""
        output = output or Path("evals/runs/quote_extraction") / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".json"
        )
        settings = QuoteEvalSettings(
            dataset=dataset,
            split=split,
            repeats=repeats,
            workers=workers,
            max_cost=max_cost,
            extraction=QuoteSettings(
                model=model,
                count=count,
                prompt_version=prompt_version,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
            ),
        )
        try:
            run = evaluator(
                settings, output, progress=lambda text: click.echo(text, err=True)
            )
            click.echo(json.dumps(run["summary"], indent=2))
            click.echo(f"Run: {output}", err=True)
            if run["summary"]["error_count"]:
                raise click.ClickException(
                    "Some extractions failed; see the saved run."
                )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

    return command


eval_quotes = build_eval_quotes_command()
