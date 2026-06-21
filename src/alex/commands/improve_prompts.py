from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import click

from alex.commands.eval_summary import (
    EvaluatorFactory,
    default_evaluator_factory,
    new_run_id,
    with_eval_model_overrides,
)
from alex.lib.llm import Completer, LiteLlmCompleter
from alex.lib.prompt_bundle_improvement import (
    DEFAULT_BUNDLE_CRITIC_MODEL_A,
    BundleImprovementReport,
    BundleImprovementSettings,
    improve_prompt_bundle,
)
from alex.lib.summary_eval import eval_config_for

BUNDLE_CRITIC_MODEL_B_ENV = "ALEX_PROMPT_CRITIC_MODEL_B"


def build_improve_prompts_command(
    improver: Callable[..., BundleImprovementReport] = improve_prompt_bundle,
    evaluator_factory: EvaluatorFactory = default_evaluator_factory,
    critic_factory: Callable[[], Completer] = LiteLlmCompleter,
) -> click.Command:
    @click.command("improve-prompts")
    @click.option(
        "--docs",
        "doc_names",
        multiple=True,
        metavar="FILENAME",
        help="Corpus documents to evaluate (default: every corpus/*.md).",
    )
    @click.option(
        "--min-delta",
        type=float,
        default=0.02,
        show_default=True,
        help="Minimum mean blended-score improvement to pass the bundle gate.",
    )
    @click.option(
        "--promote",
        is_flag=True,
        help="Rewrite active.txt files when the candidate bundle passes the gate.",
    )
    @click.option(
        "--critic-model-a",
        type=str,
        default=DEFAULT_BUNDLE_CRITIC_MODEL_A,
        show_default=True,
        help="First independent prompt-bundle critic model.",
    )
    @click.option(
        "--critic-model-b",
        type=str,
        default=None,
        help=(
            "Second independent critic model. Defaults to "
            f"${BUNDLE_CRITIC_MODEL_B_ENV}."
        ),
    )
    @click.option(
        "--synthesis-model",
        type=str,
        default=None,
        help="Model used to synthesize the two critic proposals (default: critic A).",
    )
    @click.option(
        "--critic-max-tokens",
        type=click.IntRange(min=1),
        default=32_000,
        show_default=True,
        help="Max tokens for critic and synthesis completions.",
    )
    @click.option(
        "--evals-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("evals"),
        show_default=True,
        help="Eval data directory holding corpus/, facts/, runs/, lineage/.",
    )
    @click.option(
        "--judge-model",
        type=str,
        default=None,
        help="Model for coverage, faithfulness, and rubric judges.",
    )
    @click.option(
        "--fact-extractor-model",
        type=str,
        default=None,
        help="Model for extracting reference facts and graph items.",
    )
    @click.option(
        "--run-id",
        type=str,
        default=None,
        help="Run identifier prefix for reproducible, labelled artifacts.",
    )
    def command(
        doc_names: tuple[str, ...],
        min_delta: float,
        promote: bool,
        critic_model_a: str,
        critic_model_b: str | None,
        synthesis_model: str | None,
        critic_max_tokens: int,
        evals_dir: Path,
        judge_model: str | None,
        fact_extractor_model: str | None,
        run_id: str | None,
    ) -> None:
        """Improve the production summary prompt stack as one gated bundle."""
        model_b = critic_model_b or os.getenv(BUNDLE_CRITIC_MODEL_B_ENV)
        if not model_b:
            raise click.UsageError(
                "--critic-model-b is required unless "
                f"{BUNDLE_CRITIC_MODEL_B_ENV} is set."
            )
        config = with_eval_model_overrides(
            eval_config_for(evals_dir),
            judge_model=judge_model,
            fact_extractor_model=fact_extractor_model,
        )
        resolved_run_id = run_id or new_run_id()
        try:
            report = improver(
                config=config,
                doc_names=doc_names or None,
                evaluator_factory=evaluator_factory,
                critic=critic_factory(),
                settings=BundleImprovementSettings(
                    min_delta=min_delta,
                    promote=promote,
                    critic_model_a=critic_model_a,
                    critic_model_b=model_b,
                    synthesis_model=synthesis_model,
                    critic_max_tokens=critic_max_tokens,
                ),
                run_id_prefix=resolved_run_id,
                lineage_dir=evals_dir / "lineage",
                artifact_dir=evals_dir / "prompt_bundles" / resolved_run_id,
                progress=click.echo,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        echo_report(report, evals_dir=evals_dir)

    return command


def echo_report(report: BundleImprovementReport, *, evals_dir: Path) -> None:
    click.echo("Summary:")
    baseline_path = evals_dir / "runs" / f"{report.baseline_run.run_id}.json"
    click.echo(f"Baseline run: {baseline_path}")
    if report.candidate_run is not None:
        candidate_path = evals_dir / "runs" / f"{report.candidate_run.run_id}.json"
        click.echo(f"Candidate run: {candidate_path}")
    click.echo(f"Changed prompts: {format_changed_versions(report.changed_versions)}")
    if report.delta is not None:
        click.echo(f"Mean paired delta: {report.delta:+.3f}")
    if report.promoted:
        click.echo("Outcome: promoted")
    elif report.rejected_reason is None:
        click.echo("Outcome: passed gate; rerun with --promote to activate")
    else:
        click.echo(f"Outcome: rejected ({report.rejected_reason})")
    click.echo(f"Artifacts: {report.artifact_dir}")
    click.echo(f"Lineage: {evals_dir / 'lineage' / 'production_prompt_bundle.jsonl'}")


def format_changed_versions(versions: dict[str, str]) -> str:
    if not versions:
        return "(none)"
    return " ".join(f"{name}={version}" for name, version in versions.items())


improve_prompts_command = build_improve_prompts_command()
