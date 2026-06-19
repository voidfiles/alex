from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import click

from alex.commands.eval_summary import (
    EvaluatorFactory,
    default_evaluator_factory,
    new_run_id,
    with_eval_model_overrides,
)
from alex.lib.llm import Completer, LiteLlmCompleter
from alex.lib.prompt_improvement import (
    ImprovementReport,
    ImprovementSettings,
    IterationResult,
    improve_prompt,
    outcome_label,
)
from alex.lib.summary_eval import Progress, SummaryEvaluator, eval_config_for


class PromptImprover(Protocol):
    def __call__(
        self,
        *,
        prompt_name: str,
        evaluator: SummaryEvaluator,
        critic: Completer,
        settings: ImprovementSettings,
        lineage_dir: Path,
        run_id_prefix: str,
        progress: Progress,
    ) -> ImprovementReport: ...


def build_improve_prompt_command(
    improver: PromptImprover = improve_prompt,
    evaluator_factory: EvaluatorFactory = default_evaluator_factory,
    critic_factory: Callable[[], Completer] = LiteLlmCompleter,
) -> click.Command:
    @click.command("improve-prompt")
    @click.argument("prompt_name", metavar="PROMPT_NAME")
    @click.option(
        "--iterations",
        type=click.IntRange(min=1),
        default=3,
        show_default=True,
        help="Maximum critique-and-evaluate iterations.",
    )
    @click.option(
        "--min-delta",
        type=float,
        default=0.02,
        show_default=True,
        help="Minimum mean blended-score improvement to pass the gate.",
    )
    @click.option(
        "--promote",
        is_flag=True,
        help="Rewrite active.txt when a candidate passes the gate.",
    )
    @click.option(
        "--docs",
        "doc_names",
        multiple=True,
        metavar="FILENAME",
        help="Corpus documents to evaluate (default: every corpus/*.md).",
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
        help="Model for extracting reference facts.",
    )
    @click.option(
        "--adjudication-margin",
        type=float,
        default=0.02,
        show_default=True,
        help="Rejudge when candidate delta is this close to the gate.",
    )
    @click.option(
        "--adjudication-repeats",
        type=click.IntRange(min=0),
        default=1,
        show_default=True,
        help="Additional judge-only passes for near-threshold candidates.",
    )
    def command(
        prompt_name: str,
        iterations: int,
        min_delta: float,
        promote: bool,
        doc_names: tuple[str, ...],
        evals_dir: Path,
        judge_model: str | None,
        fact_extractor_model: str | None,
        adjudication_margin: float,
        adjudication_repeats: int,
    ) -> None:
        """Iteratively rewrite a summary prompt, keeping only measured winners."""
        config = with_eval_model_overrides(
            eval_config_for(evals_dir),
            judge_model=judge_model,
            fact_extractor_model=fact_extractor_model,
        )
        try:
            report = improver(
                prompt_name=prompt_name,
                evaluator=evaluator_factory(config, doc_names or None),
                critic=critic_factory(),
                settings=ImprovementSettings(
                    iterations=iterations,
                    min_delta=min_delta,
                    promote=promote,
                    adjudication_margin=adjudication_margin,
                    adjudication_repeats=adjudication_repeats,
                ),
                lineage_dir=evals_dir / "lineage",
                run_id_prefix=new_run_id(),
                progress=click.echo,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo("Summary:")
        for result in report.iterations:
            click.echo(iteration_line(result))
        click.echo(f"Lineage: {evals_dir / 'lineage' / (prompt_name + '.jsonl')}")

    return command


def iteration_line(result: IterationResult) -> str:
    if (
        result.candidate_version is None
        or result.candidate_score is None
        or result.delta is None
    ):
        return (
            f"[{result.iteration}] {result.parent_version}: "
            f"rejected ({result.rejected_reason})"
        )
    return (
        f"[{result.iteration}] {result.parent_version} -> "
        f"{result.candidate_version}: parent {result.parent_score:.3f}, "
        f"candidate {result.candidate_score:.3f}, "
        f"delta {result.delta:+.3f} "
        f"({outcome_label(result.promoted, result.rejected_reason)})"
    )


improve_prompt_command = build_improve_prompt_command()
