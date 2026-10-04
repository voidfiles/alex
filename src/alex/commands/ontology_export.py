"""Export ontology JSON without a model call."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

import click

from alex.lib.ontology_export import (
    OntologyExportConfig,
    OntologyExportOutput,
    export_ontology,
)


class OntologyExporter(Protocol):
    def __call__(self, config: OntologyExportConfig) -> OntologyExportOutput: ...


def build_ontology_export_command(
    exporter: OntologyExporter = export_ontology,
) -> click.Command:
    @click.command("ontology-export")
    @click.argument(
        "source",
        metavar="INPUT_JSON",
        type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    )
    @click.argument(
        "output_path",
        metavar="[OUTPUT_ONTOLOGY]",
        required=False,
        type=click.Path(dir_okay=False, path_type=Path),
    )
    @click.option(
        "--base-iri",
        default=None,
        help="Absolute ontology IRI (default: a stable source-hash URN).",
    )
    @click.option("--force", is_flag=True, help="Replace an existing export.")
    @click.option(
        "--profile",
        type=click.Choice(["standard", "legacy"]),
        default=None,
        help="Default: standard for enriched JSON, legacy otherwise.",
    )
    @click.option(
        "--report",
        "report_path",
        type=click.Path(dir_okay=False, path_type=Path),
        help="Write an A-H evidence/validation report with Turtle artifacts.",
    )
    @click.option(
        "--bundle",
        "bundle_dir",
        type=click.Path(file_okay=False, path_type=Path),
        help="Write application and instance Turtle, a report, and a manifest.",
    )
    def command(
        source: Path,
        output_path: Path | None,
        base_iri: str | None,
        force: bool,
        profile: Literal["standard", "legacy"] | None,
        report_path: Path | None,
        bundle_dir: Path | None,
    ) -> None:
        """Export quantified ontology JSON to OWL/RDF without an LLM.

        Defaults to INPUT_STEM.ttl. Use .owl/.rdf for RDF/XML or .jsonld for JSON-LD.
        Qualified or unresolved claims retain their logic and evidence as
        annotations; supported categorical statements become logical axioms.
        """
        try:
            result = exporter(
                OntologyExportConfig(
                    source,
                    output_path,
                    base_iri,
                    force,
                    profile=profile,
                    report_path=report_path,
                    bundle_dir=bundle_dir,
                )
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Wrote {result.output_path}")
        click.echo(f"Ontology IRI: {result.base_iri}")
        click.echo(
            f"RDF triples: {result.triple_count}; formalized relationships: "
            f"{result.formalized_relationships}; annotated relationships: "
            f"{result.annotated_relationships}"
        )

    return command


ontology_export = build_ontology_export_command()
