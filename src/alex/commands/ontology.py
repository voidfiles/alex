"""Click entry point for per-document ontology experiments."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import click

from alex.lib.llm import resolve_ontology_model
from alex.lib.ontology import (
    DEFAULT_ONTOLOGY_SAFETY_MARGIN,
    OntologyConfig,
    generate_ontology,
)
from alex.lib.ontology_models import OntologyOutput


class OntologyGenerator(Protocol):
    def __call__(
        self, config: OntologyConfig, *, progress: Callable[[str], None] | None
    ) -> OntologyOutput: ...


def build_ontology_command(
    generator: OntologyGenerator = generate_ontology,
) -> click.Command:
    @click.command("ontology")
    @click.argument(
        "source",
        metavar="INPUT",
        type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    )
    @click.argument(
        "output_path",
        metavar="[OUTPUT_JSON]",
        required=False,
        type=click.Path(dir_okay=False, path_type=Path),
    )
    @click.option(
        "--model",
        default=resolve_ontology_model,
        help="LiteLLM model (default: ALEX_ONTOLOGY_MODEL or openai/gpt-6.1-sol).",
    )
    @click.option(
        "--context-window",
        type=click.IntRange(1),
        default=None,
        envvar="ALEX_ONTOLOGY_CONTEXT_WINDOW",
        help="Override the model token limit; otherwise use LiteLLM metadata.",
    )
    @click.option(
        "--max-output-tokens",
        type=click.IntRange(1),
        default=None,
        help="Reserve response tokens (default: up to 32768, capped by model).",
    )
    @click.option(
        "--safety-margin",
        type=click.IntRange(0),
        default=DEFAULT_ONTOLOGY_SAFETY_MARGIN,
        show_default=True,
        help="Additional tokens kept free in each request.",
    )
    @click.option(
        "--reasoning-effort",
        type=click.Choice(["none", "minimal", "low", "medium", "high", "xhigh"]),
        default=None,
        help="Reasoning effort, if supported by the chosen model.",
    )
    @click.option(
        "--force", is_flag=True, help="Replace an existing ontology artifact."
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Estimate passes without model calls or writing an artifact.",
    )
    @click.option(
        "--enrich",
        is_flag=True,
        help="Add standard vocabulary, themes, and provenance.",
    )
    @click.option(
        "--metadata",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="Optional book metadata JSON; requires --enrich.",
    )
    @click.option(
        "--vocabulary",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="Optional curated vocabulary catalog JSON; requires --enrich.",
    )
    @click.option(
        "--requirements",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="Scope and competency questions JSON; requires --enrich.",
    )
    @click.option(
        "--application-iri",
        default="urn:alex:ontology:book:",
        help="Shared application ontology namespace for enriched extraction.",
    )
    @click.option(
        "--response-dir",
        type=click.Path(file_okay=False, path_type=Path),
        help="Save original model responses for review or recovery.",
    )
    def command(
        source: Path,
        output_path: Path | None,
        model: str,
        context_window: int | None,
        max_output_tokens: int | None,
        safety_margin: int,
        reasoning_effort: str | None,
        force: bool,
        dry_run: bool,
        enrich: bool,
        metadata: Path | None,
        vocabulary: Path | None,
        requirements: Path | None,
        application_iri: str,
        response_dir: Path | None,
    ) -> None:
        """Extract a source-grounded JSON ontology from a Markdown file.

        OUTPUT_JSON defaults to INPUT_STEM.ontology.json alongside the input.
        Fits the entire source in one call when possible; otherwise packs large
        passages and carries the vocabulary forward between calls.
        """
        try:
            result = generator(
                OntologyConfig(
                    source=source,
                    output_path=output_path,
                    model=model,
                    context_window=context_window,
                    max_output_tokens=max_output_tokens,
                    safety_margin=safety_margin,
                    reasoning_effort=reasoning_effort,
                    force=force,
                    dry_run=dry_run,
                    enrich=enrich,
                    metadata=metadata,
                    vocabulary=vocabulary,
                    requirements=requirements,
                    application_iri=application_iri,
                    response_dir=response_dir,
                ),
                progress=lambda message: click.echo(message, err=True),
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Model: {result.model}")
        click.echo(
            f"Token budget: {result.budget.input_budget:,} input + "
            f"{result.budget.max_output_tokens:,} output + "
            f"{result.budget.safety_margin:,} margin"
        )
        if dry_run:
            click.echo(f"Estimated passes: {len(result.passes)}")
            if len(result.passes) > 1:
                click.echo("Actual passes may increase as the shared vocabulary grows.")
        else:
            click.echo(f"Wrote {result.output_path}")
            click.echo(
                f"Passes: {len(result.passes)}; concepts: {result.concept_count}; "
                f"relation types: {result.relation_type_count}; "
                f"relationships: {result.relationship_count}"
            )

    return command


ontology = build_ontology_command()
