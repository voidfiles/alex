from __future__ import annotations

from pathlib import Path

import click

from alex.lib.eval_report import write_eval_report


def build_eval_report_command() -> click.Command:
    @click.command("eval-report")
    @click.option(
        "--evals-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("evals"),
        show_default=True,
        help="Eval data directory holding runs/ and claim_graph/.",
    )
    @click.option(
        "--output-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        help="Directory for the Markdown report and SVG charts.",
    )
    def command(evals_dir: Path, output_dir: Path | None) -> None:
        """Generate Markdown and SVG charts from eval artifacts."""
        try:
            report = write_eval_report(evals_dir=evals_dir, output_dir=output_dir)
        except (OSError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Report: {report.report_path}")
        click.echo(f"Mean chart: {report.mean_chart_path}")
        click.echo(f"Doc chart: {report.doc_chart_path}")
        if report.latest_graph_vs_latest_standard:
            mean_delta = sum(
                delta.delta for delta in report.latest_graph_vs_latest_standard
            ) / len(report.latest_graph_vs_latest_standard)
            click.echo(f"Latest graph vs standard delta: {mean_delta:+.3f}")

    return command


eval_report = build_eval_report_command()
