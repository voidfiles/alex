"""Thin command wrapper for pull-quote extraction."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

import click

from alex.lib.llm import resolve_quote_model
from alex.lib.quotes import (
    QuoteExtraction,
    QuoteSettings,
    extract_quotes,
    quotes_markdown,
)


def build_quotes_command(
    extractor: Callable[[str, QuoteSettings], QuoteExtraction] = extract_quotes,
) -> click.Command:
    @click.command("quotes")
    @click.argument(
        "source", metavar="MARKDOWN", type=click.File("r", encoding="utf-8")
    )
    @click.option("--count", type=click.IntRange(1, 10), default=3, show_default=True)
    @click.option(
        "--model",
        default=resolve_quote_model,
        help="LiteLLM model (ALEX_QUOTE_MODEL or openai/gpt-6-luna).",
    )
    @click.option("--prompt-version", help="Pin a quote_extraction prompt version.")
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
        "--json",
        "as_json",
        is_flag=True,
        help="Output JSON with exact source spans and provenance.",
    )
    @click.option(
        "-o",
        "--output",
        type=click.File("w", encoding="utf-8", lazy=True),
        help="Write to this file instead of stdout.",
    )
    def command(
        source: TextIO,
        count: int,
        model: str,
        prompt_version: str | None,
        max_output_tokens: int,
        reasoning_effort: str | None,
        as_json: bool,
        output: TextIO | None,
    ) -> None:
        """Select ranked pull quotes from MARKDOWN (use - for stdin)."""
        try:
            if (
                output is not None
                and source.name != "<stdin>"
                and output.name not in {"<stdout>", "-"}
                and Path(source.name).resolve() == Path(output.name).resolve()
            ):
                raise ValueError("Quote output must not replace the source file.")
            result = extractor(
                source.read(),
                QuoteSettings(
                    model=model,
                    count=count,
                    prompt_version=prompt_version,
                    max_output_tokens=max_output_tokens,
                    reasoning_effort=reasoning_effort,
                ),
            )
            text = (
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
                if as_json
                else quotes_markdown(result)
            )
            click.echo(text, file=output, nl=False)
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

    return command


quotes = build_quotes_command()
