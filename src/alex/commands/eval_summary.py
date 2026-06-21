from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import click

from alex.lib.llm import LiteLlmCompleter, LiteLlmEmbedder
from alex.lib.production_prompts import (
    PRODUCTION_PROMPT_NAMES,
    SUMMARY_PROMPT_NAMES,
    unknown_production_overrides,
)
from alex.lib.summarize import SummaryPrompts
from alex.lib.summary_eval import (
    EvalConfig,
    EvalRun,
    PipelineSummaryEvaluator,
    SummaryEvaluator,
    doc_score_line,
    eval_config_for,
)

EvaluatorFactory = Callable[[EvalConfig, tuple[str, ...] | None], SummaryEvaluator]


def default_evaluator_factory(
    config: EvalConfig,
    doc_names: tuple[str, ...] | None,
) -> SummaryEvaluator:
    return PipelineSummaryEvaluator(
        config=config,
        completer=LiteLlmCompleter(),
        embedder=LiteLlmEmbedder(),
        doc_names=doc_names,
    )


def parse_prompt_overrides(values: Sequence[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        name, separator, version = value.partition("=")
        if not separator or not name or not version:
            raise click.UsageError(f"--prompt expects NAME=VERSION, got {value!r}.")
        overrides[name] = version
    return overrides


def with_eval_model_overrides(
    config: EvalConfig,
    *,
    judge_model: str | None,
    fact_extractor_model: str | None,
) -> EvalConfig:
    if judge_model is None and fact_extractor_model is None:
        return config
    return replace(
        config,
        settings=replace(
            config.settings,
            judge_model=judge_model or config.settings.judge_model,
            fact_extractor_model=(
                fact_extractor_model or config.settings.fact_extractor_model
            ),
        ),
    )


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def build_eval_summary_command(
    evaluator_factory: EvaluatorFactory = default_evaluator_factory,
) -> click.Command:
    @click.command("eval-summary")
    @click.option(
        "--docs",
        "doc_names",
        multiple=True,
        metavar="FILENAME",
        help="Corpus documents to evaluate (default: every corpus/*.md).",
    )
    @click.option(
        "--prompt",
        "prompt_overrides",
        multiple=True,
        metavar="NAME=VERSION",
        help="Pin a summary prompt version, e.g. chunk_summary=v002.",
    )
    @click.option(
        "--evals-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("evals"),
        show_default=True,
        help="Eval data directory holding corpus/, facts/, and runs/.",
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
        "--no-graph",
        "no_graph",
        is_flag=True,
        default=False,
        help="Disable the claim-graph pass to score the plain no-graph pipeline.",
    )
    @click.option(
        "--no-coverage-repair",
        "no_coverage_repair",
        is_flag=True,
        default=False,
        help="Disable the coverage-repair pass to A/B it against the default.",
    )
    @click.option(
        "--run-id",
        type=str,
        default=None,
        help="Run identifier for reproducible, labelled artifact paths.",
    )
    def command(
        doc_names: tuple[str, ...],
        prompt_overrides: tuple[str, ...],
        evals_dir: Path,
        judge_model: str | None,
        fact_extractor_model: str | None,
        no_graph: bool,
        no_coverage_repair: bool,
        run_id: str | None,
    ) -> None:
        """Score summary quality over the eval corpus."""
        overrides = parse_prompt_overrides(prompt_overrides)
        unknown = unknown_production_overrides(overrides)
        if unknown:
            raise click.UsageError(
                f"--prompt names unknown production prompt(s): {', '.join(unknown)}"
            )
        summary_overrides = {
            name: version
            for name, version in overrides.items()
            if name in SUMMARY_PROMPT_NAMES
        }
        config = with_eval_model_overrides(
            eval_config_for(evals_dir),
            judge_model=judge_model,
            fact_extractor_model=fact_extractor_model,
        )
        if overrides:
            config = replace(
                config,
                summary=replace(config.summary, prompt_overrides=overrides),
            )
        if no_graph:
            config = replace(
                config,
                summary=replace(config.summary, graph_enhanced=False),
            )
        if no_coverage_repair:
            config = replace(
                config,
                summary=replace(config.summary, coverage_repair=False),
            )
        evaluator = evaluator_factory(config, doc_names or None)
        try:
            prompts = SummaryPrompts.load(overrides=summary_overrides or None)
            resolved_run_id = run_id or new_run_id()
            echo_eval_start(
                config=config,
                doc_names=doc_names or None,
                prompts=prompts,
                run_id=resolved_run_id,
            )
            run = evaluator.evaluate(
                prompts=prompts,
                run_id=resolved_run_id,
                progress=click.echo,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        echo_run(run, runs_dir=config.runs_dir)

    return command


def echo_eval_start(
    *,
    config: EvalConfig,
    doc_names: tuple[str, ...] | None,
    prompts: SummaryPrompts,
    run_id: str,
) -> None:
    versions = " ".join(
        f"{name}={version}"
        for name, version in initial_prompt_versions(
            prompts=prompts,
            overrides=config.summary.prompt_overrides,
        ).items()
    )
    selected_docs = ", ".join(doc_names) if doc_names else "all corpus docs"
    click.echo(f"Starting eval-summary run: {run_id}")
    click.echo(f"Docs: {selected_docs}")
    click.echo(f"Corpus: {config.corpus_dir}")
    click.echo(f"Facts cache: {config.facts_dir}")
    click.echo(f"Prompts: {versions}")
    click.echo(
        "Summary pipeline: "
        f"graph={'on' if config.summary.graph_enhanced else 'off'}, "
        f"chunk_graph={'on' if config.summary.chunk_graph_enhanced else 'off'}, "
        f"coverage_repair={'on' if config.summary.coverage_repair else 'off'}"
    )
    click.echo(
        "Models: "
        f"fast={config.summary.fast_model}, "
        f"final={config.summary.final_model}, "
        f"judge={config.settings.judge_model}, "
        f"extractor={config.settings.fact_extractor_model}"
    )


def echo_run(run: EvalRun, *, runs_dir: Path) -> None:
    versions = " ".join(
        f"{name}={version}" for name, version in run.prompt_versions.items()
    )
    click.echo(f"Prompts: {versions}")
    for score in run.doc_scores:
        click.echo(doc_score_line(score))
    click.echo(f"Mean blended: {run.mean_blended:.3f}")
    click.echo(f"Run artifact: {runs_dir / (run.run_id + '.json')}")


eval_summary = build_eval_summary_command()


def initial_prompt_versions(
    *,
    prompts: SummaryPrompts,
    overrides: Mapping[str, str],
) -> dict[str, str]:
    from alex.lib.summary_eval import summary_prompt_versions

    return {
        name: version
        for name, version in summary_prompt_versions(
            prompts=prompts,
            overrides=overrides,
        ).items()
        if name in PRODUCTION_PROMPT_NAMES
    }
