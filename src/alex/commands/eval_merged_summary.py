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
from alex.lib.llm import Completer, LiteLlmCompleter, LiteLlmEmbedder
from alex.lib.prompt_templates import PromptTemplate, load_prompt
from alex.lib.summarize import SummaryPrompts
from alex.lib.summary_eval import (
    ClaimVerdict,
    DocScore,
    EvalConfig,
    EvalPrompts,
    GeneratedSummary,
    Progress,
    corpus_docs,
    doc_score_line,
    eval_config_for,
    extract_claims,
    failed_doc_score,
    generate_summary,
    no_progress,
    score_generated_summary,
    verify_claims,
)

MERGED_SUMMARY_PROMPT_NAME = "merged_summary"
MERGED_SUMMARY_REPAIR_PROMPT_NAME = "merged_summary_repair"
MERGED_SUMMARY_FAITHFULNESS_FILTER_PROMPT_NAME = "merged_summary_faithfulness_filter"


@dataclass(frozen=True)
class MergePrompts:
    merged_summary: PromptTemplate
    merged_summary_repair: PromptTemplate
    merged_summary_faithfulness_filter: PromptTemplate

    @classmethod
    def load(cls) -> MergePrompts:
        return cls(
            merged_summary=load_prompt(MERGED_SUMMARY_PROMPT_NAME),
            merged_summary_repair=load_prompt(MERGED_SUMMARY_REPAIR_PROMPT_NAME),
            merged_summary_faithfulness_filter=load_prompt(
                MERGED_SUMMARY_FAITHFULNESS_FILTER_PROMPT_NAME
            ),
        )


@dataclass(frozen=True)
class MergedDocResult:
    doc_name: str
    score: DocScore
    graph_nodes: int
    graph_edges: int
    selected_nodes: int
    selected_edges: int
    artifact_dir: Path
    standard_summary: str = ""
    graph_summary: str = ""
    merged_summary: str = ""
    repaired_summary: str | None = None
    faithfulness_filtered_summary: str | None = None
    pre_filter_claim_verdicts: tuple[ClaimVerdict, ...] = ()


@dataclass(frozen=True)
class MergedEvalRun:
    run_id: str
    prompt_versions: dict[str, str]
    judge_model: str
    fact_extractor_model: str
    summary_fast_model: str
    summary_final_model: str
    max_claims: int
    repair: bool
    faithfulness_filter: bool
    doc_results: tuple[MergedDocResult, ...]
    mean_blended: float


CompleterFactory = Callable[[], Completer]


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def build_eval_merged_summary_command(
    completer_factory: CompleterFactory = LiteLlmCompleter,
) -> click.Command:
    @click.command("eval-merged-summary")
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
        help="Eval data directory holding corpus/, facts/, and merged_summary/.",
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
        default=48,
        show_default=True,
        help="Maximum selected graph claims per document.",
    )
    @click.option(
        "--repair",
        is_flag=True,
        help="Run a graph-coverage repair pass after the first merge.",
    )
    @click.option(
        "--faithfulness-filter",
        is_flag=True,
        help="Run a strict claim verification and rewrite pass before scoring.",
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
        repair: bool,
        faithfulness_filter: bool,
        run_id: str | None,
    ) -> None:
        """Evaluate merged standard+graph summaries over the eval corpus."""
        config = with_eval_model_overrides(
            eval_config_for(evals_dir),
            judge_model=judge_model,
            fact_extractor_model=fact_extractor_model,
        )
        try:
            run = evaluate_merged_summary(
                config=config,
                doc_names=doc_names or None,
                graph_settings=GraphSettings(max_claims=max_claims),
                run_id=run_id or new_run_id(),
                repair=repair,
                faithfulness_filter=faithfulness_filter,
                completer=completer_factory(),
                progress=click.echo,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        echo_merged_run(run, artifact_root=evals_dir / "merged_summary" / run.run_id)

    return command


def evaluate_merged_summary(
    *,
    config: EvalConfig,
    doc_names: Sequence[str] | None,
    graph_settings: GraphSettings,
    run_id: str,
    repair: bool,
    faithfulness_filter: bool,
    completer: Completer,
    progress: Progress = no_progress,
) -> MergedEvalRun:
    docs = corpus_docs(config.corpus_dir, doc_names)
    summary_prompts = SummaryPrompts.load()
    graph_prompts = GraphPrompts.load()
    merge_prompts = MergePrompts.load()
    eval_prompts = EvalPrompts.load()
    run_dir = config.runs_dir.parent / "merged_summary" / run_id
    results: list[MergedDocResult] = []

    for index, doc_path in enumerate(docs, 1):
        progress(f"merged scoring ({index}/{len(docs)}) {doc_path.name}")
        try:
            result = evaluate_merged_summary_doc(
                doc_path=doc_path,
                run_dir=run_dir,
                summary_prompts=summary_prompts,
                graph_prompts=graph_prompts,
                merge_prompts=merge_prompts,
                eval_prompts=eval_prompts,
                config=config,
                graph_settings=graph_settings,
                repair=repair,
                faithfulness_filter=faithfulness_filter,
                completer=completer,
            )
        except (OSError, RuntimeError, ValueError) as error:
            result = failed_merged_doc_result(
                doc_name=doc_path.name,
                artifact_dir=run_dir / doc_path.stem,
                error=error,
            )
        progress(doc_score_line(result.score))
        results.append(result)

    run = MergedEvalRun(
        run_id=run_id,
        prompt_versions=prompt_versions(
            summary_prompts=summary_prompts,
            graph_prompts=graph_prompts,
            merge_prompts=merge_prompts,
            eval_prompts=eval_prompts,
            repair=repair,
            faithfulness_filter=faithfulness_filter,
        ),
        judge_model=config.settings.judge_model,
        fact_extractor_model=config.settings.fact_extractor_model,
        summary_fast_model=config.summary.fast_model,
        summary_final_model=config.summary.final_model,
        max_claims=graph_settings.max_claims,
        repair=repair,
        faithfulness_filter=faithfulness_filter,
        doc_results=tuple(results),
        mean_blended=mean_blended(tuple(result.score for result in results)),
    )
    write_merged_run_artifact(run, run_dir=run_dir)
    return run


def evaluate_merged_summary_doc(
    *,
    doc_path: Path,
    run_dir: Path,
    summary_prompts: SummaryPrompts,
    graph_prompts: GraphPrompts,
    merge_prompts: MergePrompts,
    eval_prompts: EvalPrompts,
    config: EvalConfig,
    graph_settings: GraphSettings,
    repair: bool,
    faithfulness_filter: bool,
    completer: Completer,
) -> MergedDocResult:
    doc_text = doc_path.read_text(encoding="utf-8")
    standard_summary = generate_summary(
        doc_path=doc_path,
        prompts=summary_prompts,
        config=replace(config, summary=replace(config.summary, graph_enhanced=False)),
        completer=completer,
        embedder=LiteLlmEmbedder(),
    )

    graph = build_claim_graph(
        doc_name=doc_path.name,
        doc_text=doc_text,
        prompts=graph_prompts,
        completer=completer,
        eval_settings=config.settings,
    )
    selected = select_claim_subgraph(graph, settings=graph_settings)
    selected_markdown = render_selected_subgraph(selected)
    graph_summary = completer.complete(
        prompt=graph_summary_prompt(
            doc_name=doc_path.name,
            selected_subgraph_markdown=selected_markdown,
            template=graph_prompts.graph_guided_summary,
        ),
        model=config.summary.final_model,
        max_tokens=config.summary.final_summary_max_tokens,
    )
    merged_summary = merge_summaries(
        doc_name=doc_path.name,
        standard_summary=standard_summary,
        graph_summary=graph_summary,
        template=merge_prompts.merged_summary,
        completer=completer,
        config=config,
    )
    repaired_summary = None
    summary_to_score = merged_summary
    if repair:
        repaired_summary = repair_summary(
            doc_name=doc_path.name,
            selected_subgraph_markdown=selected_markdown,
            merged_summary=merged_summary,
            template=merge_prompts.merged_summary_repair,
            completer=completer,
            config=config,
        )
        summary_to_score = repaired_summary
    faithfulness_filtered_summary = None
    pre_filter_claim_verdicts: tuple[ClaimVerdict, ...] = ()
    if faithfulness_filter:
        faithfulness_filtered_summary, pre_filter_claim_verdicts = (
            faithfulness_filter_summary(
                doc_name=doc_path.name,
                doc_text=doc_text,
                candidate_summary=summary_to_score,
                template=merge_prompts.merged_summary_faithfulness_filter,
                eval_prompts=eval_prompts,
                completer=completer,
                config=config,
            )
        )
        summary_to_score = faithfulness_filtered_summary

    score = score_generated_summary(
        generated=GeneratedSummary(
            doc_name=doc_path.name,
            doc_text=doc_text,
            summary=summary_to_score,
        ),
        config=config,
        eval_prompts=eval_prompts,
        completer=completer,
    )

    artifact_dir = run_dir / doc_path.stem
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "standard_summary.md").write_text(
        standard_summary,
        encoding="utf-8",
    )
    write_graph_json(artifact_dir / "graph.json", graph)
    write_graph_json(artifact_dir / "selected_subgraph.json", selected)
    (artifact_dir / "selected_subgraph.md").write_text(
        selected_markdown,
        encoding="utf-8",
    )
    (artifact_dir / "graph_summary.md").write_text(graph_summary, encoding="utf-8")
    (artifact_dir / "merged_summary.md").write_text(merged_summary, encoding="utf-8")
    if repaired_summary is not None:
        (artifact_dir / "repaired_summary.md").write_text(
            repaired_summary,
            encoding="utf-8",
        )
    if faithfulness_filtered_summary is not None:
        (artifact_dir / "faithfulness_filtered_summary.md").write_text(
            faithfulness_filtered_summary,
            encoding="utf-8",
        )

    return MergedDocResult(
        doc_name=doc_path.name,
        score=score,
        graph_nodes=len(graph.nodes),
        graph_edges=len(graph.edges),
        selected_nodes=len(selected.nodes),
        selected_edges=len(selected.edges),
        artifact_dir=artifact_dir,
        standard_summary=standard_summary,
        graph_summary=graph_summary,
        merged_summary=merged_summary,
        repaired_summary=repaired_summary,
        faithfulness_filtered_summary=faithfulness_filtered_summary,
        pre_filter_claim_verdicts=pre_filter_claim_verdicts,
    )


def merge_summaries(
    *,
    doc_name: str,
    standard_summary: str,
    graph_summary: str,
    template: PromptTemplate,
    completer: Completer,
    config: EvalConfig,
) -> str:
    return completer.complete(
        prompt=template.render(
            document_name=doc_name,
            standard_summary=standard_summary,
            graph_summary=graph_summary,
        ),
        model=config.summary.final_model,
        max_tokens=config.summary.final_summary_max_tokens,
    )


def repair_summary(
    *,
    doc_name: str,
    selected_subgraph_markdown: str,
    merged_summary: str,
    template: PromptTemplate,
    completer: Completer,
    config: EvalConfig,
) -> str:
    return completer.complete(
        prompt=template.render(
            document_name=doc_name,
            selected_subgraph=selected_subgraph_markdown,
            merged_summary=merged_summary,
        ),
        model=config.summary.final_model,
        max_tokens=config.summary.final_summary_max_tokens,
    )


def faithfulness_filter_summary(
    *,
    doc_name: str,
    doc_text: str,
    candidate_summary: str,
    template: PromptTemplate,
    eval_prompts: EvalPrompts,
    completer: Completer,
    config: EvalConfig,
) -> tuple[str, tuple[ClaimVerdict, ...]]:
    claims = extract_claims(
        summary=candidate_summary,
        template=eval_prompts.claim_extraction,
        completer=completer,
        settings=config.settings,
    )
    verdicts = verify_claims(
        doc_text=doc_text,
        claims=claims,
        template=eval_prompts.claim_verification,
        completer=completer,
        settings=config.settings,
    )
    filtered = completer.complete(
        prompt=template.render(
            document_name=doc_name,
            candidate_summary=candidate_summary,
            supported_claims=render_supported_claims(verdicts),
            unsupported_claims=render_unsupported_claims(verdicts),
        ),
        model=config.summary.final_model,
        max_tokens=config.summary.final_summary_max_tokens,
    )
    return filtered, verdicts


def render_supported_claims(verdicts: Sequence[ClaimVerdict]) -> str:
    supported = [verdict.claim for verdict in verdicts if verdict.supported]
    if not supported:
        return "None."
    return "\n".join(f"{index}. {claim}" for index, claim in enumerate(supported, 1))


def render_unsupported_claims(verdicts: Sequence[ClaimVerdict]) -> str:
    unsupported = [verdict for verdict in verdicts if not verdict.supported]
    if not unsupported:
        return "None."
    return "\n".join(
        f"{index}. {verdict.claim}\n   Reason: {verdict.evidence}"
        for index, verdict in enumerate(unsupported, 1)
    )


def prompt_versions(
    *,
    summary_prompts: SummaryPrompts,
    graph_prompts: GraphPrompts,
    merge_prompts: MergePrompts,
    eval_prompts: EvalPrompts,
    repair: bool,
    faithfulness_filter: bool,
) -> dict[str, str]:
    versions = {
        "chunk_summary": summary_prompts.chunk_summary.version,
        "compression_summary": summary_prompts.compression_summary.version,
        "final_summary": summary_prompts.final_summary.version,
        "source_claim_extraction": graph_prompts.source_claim_extraction.version,
        "graph_guided_summary": graph_prompts.graph_guided_summary.version,
        "merged_summary": merge_prompts.merged_summary.version,
        "fact_extraction": eval_prompts.fact_extraction.version,
        "fact_coverage_judge": eval_prompts.fact_coverage_judge.version,
        "claim_extraction": eval_prompts.claim_extraction.version,
        "claim_verification": eval_prompts.claim_verification.version,
        "rubric_judge": eval_prompts.rubric_judge.version,
    }
    if repair:
        versions["merged_summary_repair"] = merge_prompts.merged_summary_repair.version
    if faithfulness_filter:
        versions["merged_summary_faithfulness_filter"] = (
            merge_prompts.merged_summary_faithfulness_filter.version
        )
    return versions


def failed_merged_doc_result(
    *,
    doc_name: str,
    artifact_dir: Path,
    error: Exception,
) -> MergedDocResult:
    return MergedDocResult(
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


def echo_merged_run(run: MergedEvalRun, *, artifact_root: Path) -> None:
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


def write_merged_run_artifact(run: MergedEvalRun, *, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = run_dir / "run.json"
    payload = {
        "run_id": run.run_id,
        "prompt_versions": run.prompt_versions,
        "judge_model": run.judge_model,
        "fact_extractor_model": run.fact_extractor_model,
        "summary_fast_model": run.summary_fast_model,
        "summary_final_model": run.summary_final_model,
        "max_claims": run.max_claims,
        "repair": run.repair,
        "faithfulness_filter": run.faithfulness_filter,
        "mean_blended": run.mean_blended,
        "docs": [
            {
                "doc_name": result.doc_name,
                "score": asdict(replace(result.score, summary="")),
                "summary": result.score.summary,
                "standard_summary": result.standard_summary,
                "graph_summary": result.graph_summary,
                "merged_summary": result.merged_summary,
                "repaired_summary": result.repaired_summary,
                "faithfulness_filtered_summary": (result.faithfulness_filtered_summary),
                "pre_filter_claim_verdicts": [
                    {
                        "claim": verdict.claim,
                        "supported": verdict.supported,
                        "evidence": verdict.evidence,
                    }
                    for verdict in result.pre_filter_claim_verdicts
                ],
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


eval_merged_summary = build_eval_merged_summary_command()
