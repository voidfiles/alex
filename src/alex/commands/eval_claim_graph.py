from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

import click

from alex.commands.eval_summary import with_eval_model_overrides
from alex.lib.claim_graph import (
    GraphPrompts,
    GraphSettings,
    build_claim_graph,
    graph_summary_prompt,
    render_selected_subgraph,
    select_claim_subgraph,
    write_graph_json,
)
from alex.lib.llm import Completer, LiteLlmCompleter
from alex.lib.summary_eval import (
    DocScore,
    EvalConfig,
    EvalPrompts,
    GeneratedSummary,
    Progress,
    corpus_docs,
    doc_score_line,
    eval_config_for,
    failed_doc_score,
    no_progress,
    score_generated_summary,
)


@dataclass(frozen=True)
class GraphDocResult:
    doc_name: str
    score: DocScore
    graph_nodes: int
    graph_edges: int
    selected_nodes: int
    selected_edges: int
    artifact_dir: Path


@dataclass(frozen=True)
class GraphEvalRun:
    run_id: str
    prompt_versions: dict[str, str]
    judge_model: str
    fact_extractor_model: str
    summary_final_model: str
    max_claims: int
    doc_results: tuple[GraphDocResult, ...]
    mean_blended: float


CompleterFactory = Callable[[], Completer]


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def build_eval_claim_graph_command(
    completer_factory: CompleterFactory = LiteLlmCompleter,
) -> click.Command:
    @click.command("eval-claim-graph")
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
        help="Eval data directory holding corpus/, facts/, and claim_graph/.",
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
        help="Model for source claim extraction and reference facts.",
    )
    @click.option(
        "--max-claims",
        type=int,
        default=24,
        show_default=True,
        help="Maximum selected claims per document.",
    )
    @click.option(
        "--run-id",
        type=str,
        default=None,
        help="Run identifier for reproducible artifact paths.",
    )
    def command(
        doc_names: tuple[str, ...],
        evals_dir: Path,
        judge_model: str | None,
        fact_extractor_model: str | None,
        max_claims: int,
        run_id: str | None,
    ) -> None:
        """Evaluate graph-guided summaries over the eval corpus."""
        config = with_eval_model_overrides(
            eval_config_for(evals_dir),
            judge_model=judge_model,
            fact_extractor_model=fact_extractor_model,
        )
        try:
            run = evaluate_claim_graph(
                config=config,
                doc_names=doc_names or None,
                graph_settings=GraphSettings(max_claims=max_claims),
                run_id=run_id or new_run_id(),
                completer=completer_factory(),
                progress=click.echo,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        echo_graph_run(run, artifact_root=evals_dir / "claim_graph" / run.run_id)

    return command


def evaluate_claim_graph(
    *,
    config: EvalConfig,
    doc_names: Sequence[str] | None,
    graph_settings: GraphSettings,
    run_id: str,
    completer: Completer,
    progress: Progress = no_progress,
) -> GraphEvalRun:
    docs = corpus_docs(config.corpus_dir, doc_names)
    graph_prompts = GraphPrompts.load()
    eval_prompts = EvalPrompts.load()
    run_dir = config.runs_dir.parent / "claim_graph" / run_id
    results: list[GraphDocResult] = []

    for index, doc_path in enumerate(docs, 1):
        progress(f"graph scoring ({index}/{len(docs)}) {doc_path.name}")
        try:
            result = evaluate_claim_graph_doc(
                doc_path=doc_path,
                run_dir=run_dir,
                graph_prompts=graph_prompts,
                eval_prompts=eval_prompts,
                config=config,
                graph_settings=graph_settings,
                completer=completer,
            )
        except (OSError, RuntimeError, ValueError) as error:
            result = failed_graph_doc_result(
                doc_name=doc_path.name,
                artifact_dir=run_dir / doc_path.stem,
                error=error,
            )
        progress(doc_score_line(result.score))
        results.append(result)

    run = GraphEvalRun(
        run_id=run_id,
        prompt_versions={
            "source_claim_extraction": graph_prompts.source_claim_extraction.version,
            "graph_guided_summary": graph_prompts.graph_guided_summary.version,
            "fact_extraction": eval_prompts.fact_extraction.version,
            "fact_coverage_judge": eval_prompts.fact_coverage_judge.version,
            "claim_extraction": eval_prompts.claim_extraction.version,
            "claim_verification": eval_prompts.claim_verification.version,
            "rubric_judge": eval_prompts.rubric_judge.version,
        },
        judge_model=config.settings.judge_model,
        fact_extractor_model=config.settings.fact_extractor_model,
        summary_final_model=config.summary.final_model,
        max_claims=graph_settings.max_claims,
        doc_results=tuple(results),
        mean_blended=mean_blended(tuple(result.score for result in results)),
    )
    write_graph_run_artifact(run, run_dir=run_dir)
    return run


def evaluate_claim_graph_doc(
    *,
    doc_path: Path,
    run_dir: Path,
    graph_prompts: GraphPrompts,
    eval_prompts: EvalPrompts,
    config: EvalConfig,
    graph_settings: GraphSettings,
    completer: Completer,
) -> GraphDocResult:
    doc_text = doc_path.read_text(encoding="utf-8")
    graph = build_claim_graph(
        doc_name=doc_path.name,
        doc_text=doc_text,
        prompts=graph_prompts,
        completer=completer,
        eval_settings=config.settings,
    )
    selected = select_claim_subgraph(graph, settings=graph_settings)
    selected_markdown = render_selected_subgraph(selected)
    summary = completer.complete(
        prompt=graph_summary_prompt(
            doc_name=doc_path.name,
            selected_subgraph_markdown=selected_markdown,
            template=graph_prompts.graph_guided_summary,
        ),
        model=config.summary.final_model,
        max_tokens=config.summary.final_summary_max_tokens,
    )

    score = score_generated_summary(
        generated=GeneratedSummary(
            doc_name=doc_path.name,
            doc_text=doc_text,
            summary=summary,
        ),
        config=config,
        eval_prompts=eval_prompts,
        completer=completer,
    )

    artifact_dir = run_dir / doc_path.stem
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_graph_json(artifact_dir / "graph.json", graph)
    write_graph_json(artifact_dir / "selected_subgraph.json", selected)
    (artifact_dir / "selected_subgraph.md").write_text(
        selected_markdown,
        encoding="utf-8",
    )
    (artifact_dir / "graph_summary.md").write_text(summary, encoding="utf-8")

    return GraphDocResult(
        doc_name=doc_path.name,
        score=score,
        graph_nodes=len(graph.nodes),
        graph_edges=len(graph.edges),
        selected_nodes=len(selected.nodes),
        selected_edges=len(selected.edges),
        artifact_dir=artifact_dir,
    )


def failed_graph_doc_result(
    *,
    doc_name: str,
    artifact_dir: Path,
    error: Exception,
) -> GraphDocResult:
    return GraphDocResult(
        doc_name=doc_name,
        score=failed_doc_score(doc_name=doc_name, error=error),
        graph_nodes=0,
        graph_edges=0,
        selected_nodes=0,
        selected_edges=0,
        artifact_dir=artifact_dir,
    )


def mean_blended(scores: Sequence[DocScore]) -> float:
    scored = [score.blended for score in scores if score.error is None]
    if not scored:
        return 0.0
    return sum(scored) / len(scored)


def echo_graph_run(run: GraphEvalRun, *, artifact_root: Path) -> None:
    versions = " ".join(
        f"{name}={version}" for name, version in run.prompt_versions.items()
    )
    click.echo(f"Prompts: {versions}")
    for result in run.doc_results:
        click.echo(doc_score_line(result.score))
        click.echo(
            "Graph: "
            f"{result.graph_nodes} nodes/{result.graph_edges} edges; "
            f"selected {result.selected_nodes} nodes/{result.selected_edges} edges"
        )
    click.echo(f"Mean blended: {run.mean_blended:.3f}")
    click.echo(f"Run artifact: {artifact_root / 'run.json'}")


def write_graph_run_artifact(run: GraphEvalRun, *, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = run_dir / "run.json"
    payload = {
        "run_id": run.run_id,
        "prompt_versions": run.prompt_versions,
        "judge_model": run.judge_model,
        "fact_extractor_model": run.fact_extractor_model,
        "summary_final_model": run.summary_final_model,
        "max_claims": run.max_claims,
        "mean_blended": run.mean_blended,
        "docs": [
            {
                "doc_name": result.doc_name,
                "score": asdict(replace(result.score, summary="")),
                "summary": result.score.summary,
                "graph_nodes": result.graph_nodes,
                "graph_edges": result.graph_edges,
                "selected_nodes": result.selected_nodes,
                "selected_edges": result.selected_edges,
                "artifact_dir": str(result.artifact_dir),
            }
            for result in run.doc_results
        ],
    }
    artifact_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact_path


eval_claim_graph = build_eval_claim_graph_command()
