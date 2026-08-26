"""Map-reduce summarization of a chunked document asset."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from alex.lib.chunking import count_tokens_estimate
from alex.lib.document_sources import DocumentMetadata
from alex.lib.llm import (
    Completer,
    Embedder,
    complete_all,
    ordered_parallel_map,
    resolve_chunk_graph_max_claims,
    resolve_claim_similarity_threshold,
    resolve_embedding_model,
    resolve_eval_judge_model,
    resolve_fact_extractor_model,
    resolve_fast_summary_model,
    resolve_final_summary_model,
    resolve_graph_cache_dir,
    resolve_graph_max_claims,
    resolve_source_claims_per_section,
    resolve_summary_max_workers,
)
from alex.lib.production_prompts import MergePrompts
from alex.lib.prompt_templates import PromptTemplate, load_prompt
from alex.lib.summary_manifest import (
    SummaryFailedManifestContext,
    SummaryManifestContext,
    SummaryRunningManifestContext,
    write_failed_summary_graph_manifest,
    write_running_summary_graph_manifest,
    write_summary_graph_manifest,
)

if TYPE_CHECKING:
    from alex.lib.claim_graph import ClaimGraph
    from alex.lib.graph_cache import CachedDocumentGraphs
    from alex.lib.summary_eval import ClaimVerdict

DEFAULT_CHUNK_SUMMARY_MAX_TOKENS = 20_000
DEFAULT_FINAL_SUMMARY_MAX_TOKENS = 8_192
DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS = 180_000
MAX_SUMMARY_COMPRESSION_ITERATIONS = 8


class SummarizationError(ValueError):
    pass


SUMMARY_PROMPT_NAMES = (
    "chunk_summary",
    "chunk_summary_with_graph",
    "compression_summary",
    "final_summary",
)


@dataclass(frozen=True)
class SummaryPrompts:
    chunk_summary: PromptTemplate
    chunk_summary_with_graph: PromptTemplate
    compression_summary: PromptTemplate
    final_summary: PromptTemplate

    @classmethod
    def load(
        cls,
        overrides: Mapping[str, str] | None = None,
        *,
        root: Traversable | None = None,
    ) -> SummaryPrompts:
        versions = dict(overrides or {})
        unknown = sorted(set(versions) - set(SUMMARY_PROMPT_NAMES))
        if unknown:
            raise SummarizationError(
                f"Unknown summary prompts in overrides: {', '.join(unknown)}"
            )
        return cls(
            chunk_summary=load_prompt(
                "chunk_summary", version=versions.get("chunk_summary"), root=root
            ),
            chunk_summary_with_graph=load_prompt(
                "chunk_summary_with_graph",
                version=versions.get("chunk_summary_with_graph"),
                root=root,
            ),
            compression_summary=load_prompt(
                "compression_summary",
                version=versions.get("compression_summary"),
                root=root,
            ),
            final_summary=load_prompt(
                "final_summary", version=versions.get("final_summary"), root=root
            ),
        )


@dataclass(frozen=True)
class SummarySettings:
    fast_model: str = field(default_factory=resolve_fast_summary_model)
    final_model: str = field(default_factory=resolve_final_summary_model)
    judge_model: str = field(default_factory=resolve_eval_judge_model)
    fact_extractor_model: str = field(default_factory=resolve_fact_extractor_model)
    prompts: SummaryPrompts = field(default_factory=SummaryPrompts.load)
    prompt_overrides: Mapping[str, str] = field(default_factory=dict)
    chunk_summary_max_tokens: int = DEFAULT_CHUNK_SUMMARY_MAX_TOKENS
    final_summary_max_tokens: int = DEFAULT_FINAL_SUMMARY_MAX_TOKENS
    # Keep in sync with EvalSettings.judge_max_tokens: the graph faithfulness
    # filter runs the same claim-extraction call and hits the same truncation.
    judge_max_tokens: int = 32_768
    extractor_max_tokens: int = 8_192
    graph_enhanced: bool = True
    chunk_graph_enhanced: bool = True
    coverage_repair: bool = True
    chunk_graph_max_claims: int = field(default_factory=resolve_chunk_graph_max_claims)
    graph_max_claims: int = field(default_factory=resolve_graph_max_claims)
    source_claims_per_section: int = field(
        default_factory=resolve_source_claims_per_section
    )
    graph_artifacts: bool = True
    # Off unless ALEX_GRAPH_CACHE_DIR is set: reuse chunk claim graphs and the
    # merged document graph across runs of the same doc + graph-build config.
    graph_cache_dir: Path | None = field(default_factory=resolve_graph_cache_dir)
    evidence_ledger: bool = True
    verification_passes: int = 2
    max_context_tokens: int = DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS
    max_workers: int = field(default_factory=resolve_summary_max_workers)
    force: bool = False


@dataclass(frozen=True)
class SummaryOutput:
    chunk_summary_path: Path | None
    summary_path: Path | None
    graph_artifact_dir: Path | None = None


@dataclass(frozen=True)
class SummaryChunkReference:
    index: int
    filename: str
    path: str


@dataclass(frozen=True)
class GraphEnhancedSummary:
    final_summary: str
    artifact_dir: Path | None


@dataclass(frozen=True)
class GraphSummaryDraft:
    document_graph: ClaimGraph
    selected: ClaimGraph
    selected_markdown: str
    graph_summary_text: str


@dataclass(frozen=True)
class ChunkGraphBundle:
    chunk_path: Path
    graph: ClaimGraph
    selected: ClaimGraph
    selected_markdown: str


@dataclass(frozen=True)
class SourceBlock:
    id: str
    kind: str
    source_path: str
    heading_path: str
    text: str
    start_char: int
    end_char: int
    chunk_index: int | None = None
    chunk_filename: str | None = None


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    source_block_id: str
    kind: str
    text: str
    claim: str
    entities: tuple[str, ...]
    dates: tuple[str, ...]
    quantities: tuple[str, ...]
    section_path: str
    score: float
    validated_exact_span: bool


@dataclass(frozen=True)
class SummaryPlanTopic:
    title: str
    evidence_ids: tuple[str, ...]
    section_path: str
    word_budget_hint: int


@dataclass(frozen=True)
class SummaryPlan:
    document: str
    topics: tuple[SummaryPlanTopic, ...]
    section_coverage: dict[str, int]


@dataclass(frozen=True)
class RepairPass:
    pass_index: int
    input_summary: str
    output_summary: str
    repaired_claims: tuple[str, ...]
    unsupported_claims: tuple[str, ...]


def summarize_doc_asset(
    *,
    settings: SummarySettings,
    asset_dir: Path,
    metadata: DocumentMetadata,
    markdown_path: Path,
    headers_path: Path,
    chunk_paths: tuple[Path, ...],
    completer: Completer,
    embedder: Embedder,
) -> SummaryOutput:
    summary_path = asset_dir / "summary.md"
    chunk_summary_path = asset_dir / "chunk_summary.md"
    graph_artifact_dir = asset_dir / "summary_graph"
    if summary_path.exists() and not settings.force:
        return SummaryOutput(
            chunk_summary_path=(
                chunk_summary_path if chunk_summary_path.exists() else None
            ),
            summary_path=summary_path,
            graph_artifact_dir=(
                graph_artifact_dir if graph_artifact_dir.exists() else None
            ),
        )
    if not chunk_paths:
        return SummaryOutput(chunk_summary_path=None, summary_path=None)

    headers = headers_path.read_text(encoding="utf-8")
    authors = authors_for_display(metadata)
    chunk_summaries_dir = asset_dir / "chunk_summaries"
    if chunk_summaries_dir.exists():
        shutil.rmtree(chunk_summaries_dir)
    chunk_summaries_dir.mkdir()

    chunk_graph_bundles: tuple[ChunkGraphBundle, ...] = ()
    selected_graph_by_chunk: dict[Path, str] = {}
    graph_cache_key: str | None = None
    cached_graphs: CachedDocumentGraphs | None = None
    if settings.graph_enhanced:
        if settings.graph_cache_dir is not None:
            from alex.lib.graph_cache import load_graph_cache

            graph_cache_key = document_graph_cache_key(
                settings=settings,
                doc_name=markdown_path.name,
                chunk_paths=chunk_paths,
            )
            cached_graphs = load_graph_cache(
                cache_dir=settings.graph_cache_dir,
                key=graph_cache_key,
            )
        cached_bundles = (
            chunk_graph_bundles_from_cache(
                settings=settings,
                chunk_paths=chunk_paths,
                cached=cached_graphs,
            )
            if cached_graphs is not None
            else None
        )
        if cached_bundles is not None:
            chunk_graph_bundles = cached_bundles
        else:
            cached_graphs = None
            chunk_graph_bundles = build_chunk_graph_bundles(
                settings=settings,
                doc_name=markdown_path.name,
                chunk_paths=chunk_paths,
                completer=completer,
                embedder=embedder,
            )
        if settings.chunk_graph_enhanced:
            selected_graph_by_chunk = {
                bundle.chunk_path: bundle.selected_markdown
                for bundle in chunk_graph_bundles
            }

    prompts = tuple(
        chunk_summary_prompt(
            settings=settings,
            title=metadata.title,
            authors=authors,
            headers=headers,
            chunk_path=chunk_path,
            selected_graph_by_chunk=selected_graph_by_chunk,
        )
        for chunk_path in chunk_paths
    )
    chunk_summaries = complete_all(
        completer=completer,
        prompts=prompts,
        model=settings.fast_model,
        max_tokens=settings.chunk_summary_max_tokens,
        max_workers=settings.max_workers,
    )

    references = tuple(
        SummaryChunkReference(
            index=index,
            filename=chunk_path.name,
            path=f"chunks/{chunk_path.name}",
        )
        for index, chunk_path in enumerate(chunk_paths, 1)
    )
    write_individual_chunk_summaries(
        chunk_summaries_dir=chunk_summaries_dir,
        chunk_paths=chunk_paths,
        chunk_summaries=chunk_summaries,
    )
    concatenated = concatenate_chunk_summaries(chunk_summaries_dir)
    consolidated = compress_summary_until_within_context(
        content=concatenated,
        title=metadata.title,
        authors=authors,
        template=settings.prompts.compression_summary,
        max_context_tokens=settings.max_context_tokens,
        completer=completer,
        model=settings.fast_model,
        max_tokens=settings.chunk_summary_max_tokens,
        max_workers=settings.max_workers,
    )

    chunk_summary_path.write_text(
        chunk_summary_content(
            title=metadata.title,
            authors=authors,
            markdown_filename=markdown_path.name,
            references=references,
            consolidated=consolidated,
        ),
        encoding="utf-8",
    )
    shutil.rmtree(chunk_summaries_dir)
    last_completed_stage = "chunk_summary"

    final_summary_prompt = settings.prompts.final_summary.render(
        title=metadata.title,
        authors=authors,
        section_summaries=consolidated,
        chunk_reference_list=chunk_reference_list(references),
    )

    def build_standard_final_summary() -> str:
        return completer.complete(
            prompt=final_summary_prompt,
            model=settings.final_model,
            max_tokens=settings.final_summary_max_tokens,
        )

    if not settings.graph_enhanced:
        final_summary = build_standard_final_summary()
        summary_path.write_text(
            summary_content(
                title=metadata.title,
                authors=authors,
                markdown_filename=markdown_path.name,
                final_summary=final_summary,
                references=references,
            ),
            encoding="utf-8",
        )
        return SummaryOutput(
            chunk_summary_path=chunk_summary_path,
            summary_path=summary_path,
            graph_artifact_dir=None,
        )

    source_markdown = markdown_path.read_text(encoding="utf-8")
    graph_draft: GraphSummaryDraft | None = None
    if settings.graph_artifacts:
        if graph_artifact_dir.exists():
            shutil.rmtree(graph_artifact_dir)
        graph_artifact_dir.mkdir(parents=True)
        write_running_summary_graph_manifest(
            SummaryRunningManifestContext(
                settings=settings,
                asset_dir=asset_dir,
                source_path=markdown_path,
                output_path=summary_path,
                chunk_paths=chunk_paths,
                artifact_dir=graph_artifact_dir,
                last_completed_stage=last_completed_stage,
                graph_draft=graph_draft,
                chunk_graph_bundles=chunk_graph_bundles,
            )
        )

    try:

        def build_graph_summary_draft() -> GraphSummaryDraft:
            if cached_graphs is not None:
                document_graph = cached_graphs.document_graph
            else:
                document_graph = merged_document_graph(
                    doc_name=markdown_path.name,
                    chunk_graph_bundles=chunk_graph_bundles,
                    embedder=embedder,
                )
                if settings.graph_cache_dir is not None and graph_cache_key is not None:
                    from alex.lib.graph_cache import (
                        CachedChunkGraph,
                        CachedDocumentGraphs,
                        store_graph_cache,
                    )

                    store_graph_cache(
                        cache_dir=settings.graph_cache_dir,
                        key=graph_cache_key,
                        graphs=CachedDocumentGraphs(
                            document_graph=document_graph,
                            chunk_graphs=tuple(
                                CachedChunkGraph(
                                    chunk_filename=bundle.chunk_path.name,
                                    graph=bundle.graph,
                                )
                                for bundle in chunk_graph_bundles
                            ),
                        ),
                    )
            return graph_summary_draft(
                settings=settings,
                doc_name=markdown_path.name,
                document_graph=document_graph,
                completer=completer,
            )

        standard_final_summary, graph_draft_result = ordered_parallel_map(
            (build_standard_final_summary, build_graph_summary_draft),
            lambda task: task(),
            max_workers=min(settings.max_workers, 2),
        )
        graph_draft = cast(GraphSummaryDraft, graph_draft_result)
        last_completed_stage = "summary_drafts"
        graph_summary = graph_enhanced_summary(
            settings=settings,
            asset_dir=asset_dir,
            doc_name=markdown_path.name,
            doc_text=source_markdown,
            standard_summary=cast(str, standard_final_summary),
            graph_draft=graph_draft,
            chunk_graph_bundles=chunk_graph_bundles,
            completer=completer,
        )
        last_completed_stage = "graph_summary"
        final_summary = graph_summary.final_summary
        final_graph_artifact_dir = graph_summary.artifact_dir
        summary_path.write_text(
            summary_content(
                title=metadata.title,
                authors=authors,
                markdown_filename=markdown_path.name,
                final_summary=final_summary,
                references=references,
                evidence_ledger=(
                    "summary_evidence.md"
                    if settings.graph_enhanced
                    and settings.graph_artifacts
                    and settings.evidence_ledger
                    else None
                ),
            ),
            encoding="utf-8",
        )
        last_completed_stage = "summary"
    except (OSError, RuntimeError, ValueError) as error:
        if settings.graph_artifacts:
            write_failed_summary_graph_manifest(
                SummaryFailedManifestContext(
                    settings=settings,
                    asset_dir=asset_dir,
                    source_path=markdown_path,
                    output_path=summary_path,
                    chunk_paths=chunk_paths,
                    artifact_dir=graph_artifact_dir,
                    last_completed_stage=last_completed_stage,
                    error=error,
                    graph_draft=graph_draft,
                    chunk_graph_bundles=chunk_graph_bundles,
                )
            )
        raise
    if final_graph_artifact_dir is not None:
        write_summary_graph_manifest(
            SummaryManifestContext(
                settings=settings,
                asset_dir=asset_dir,
                source_path=markdown_path,
                output_path=summary_path,
                chunk_paths=chunk_paths,
                graph_draft=graph_draft,
                chunk_graph_bundles=chunk_graph_bundles,
                artifact_dir=final_graph_artifact_dir,
            )
        )
    return SummaryOutput(
        chunk_summary_path=chunk_summary_path,
        summary_path=summary_path,
        graph_artifact_dir=final_graph_artifact_dir,
    )


def chunk_summary_prompt(
    *,
    settings: SummarySettings,
    title: str,
    authors: str,
    headers: str,
    chunk_path: Path,
    selected_graph_by_chunk: Mapping[Path, str],
) -> str:
    chunk = chunk_path.read_text(encoding="utf-8")
    selected_chunk_graph = selected_graph_by_chunk.get(chunk_path)
    if selected_chunk_graph is None:
        return settings.prompts.chunk_summary.render(
            title=title,
            authors=authors,
            headers=headers,
            chunk=chunk,
        )
    return settings.prompts.chunk_summary_with_graph.render(
        title=title,
        authors=authors,
        headers=headers,
        chunk=chunk,
        selected_chunk_graph=selected_chunk_graph,
    )


def build_chunk_graph_bundles(
    *,
    settings: SummarySettings,
    doc_name: str,
    chunk_paths: Sequence[Path],
    completer: Completer,
    embedder: Embedder,
) -> tuple[ChunkGraphBundle, ...]:
    from alex.lib.claim_graph import (
        GraphPrompts,
        GraphSettings,
        build_claim_graph,
        chunk_graph_source,
        render_selected_subgraph,
        select_claim_subgraph,
    )
    from alex.lib.summary_eval import EvalSettings

    eval_settings = EvalSettings(
        judge_model=settings.judge_model,
        fact_extractor_model=settings.fact_extractor_model,
        judge_max_tokens=settings.judge_max_tokens,
        extractor_max_tokens=settings.extractor_max_tokens,
    )
    graph_prompts = GraphPrompts.load(overrides=settings.prompt_overrides)
    graph_settings = GraphSettings(
        max_claims=settings.chunk_graph_max_claims,
        source_claims_per_section=settings.source_claims_per_section,
    )

    def build_bundle(item: tuple[int, Path]) -> ChunkGraphBundle:
        chunk_index, chunk_path = item
        chunk_text = chunk_path.read_text(encoding="utf-8")
        graph = build_claim_graph(
            source=chunk_graph_source(
                doc_name=doc_name,
                chunk_index=chunk_index,
                chunk_path=chunk_path,
                chunk_text=chunk_text,
            ),
            prompts=graph_prompts,
            completer=completer,
            embedder=embedder,
            eval_settings=eval_settings,
            settings=graph_settings,
        )
        selected = select_claim_subgraph(graph, settings=graph_settings)
        return ChunkGraphBundle(
            chunk_path=chunk_path,
            graph=graph,
            selected=selected,
            selected_markdown=render_selected_subgraph(selected),
        )

    return ordered_parallel_map(
        tuple(enumerate(chunk_paths, 1)),
        build_bundle,
        max_workers=settings.max_workers,
    )


def document_graph_cache_key(
    *,
    settings: SummarySettings,
    doc_name: str,
    chunk_paths: Sequence[Path],
) -> str:
    """Content hash over everything that feeds claim-graph CONSTRUCTION.

    Selection caps (graph_max_claims, chunk_graph_max_claims) are excluded on
    purpose: they only drive select_claim_subgraph, which is deterministic and
    recomputed from the cached full graphs on load.
    """
    from alex.lib.claim_graph import GraphPrompts
    from alex.lib.graph_cache import graph_cache_key

    graph_prompts = GraphPrompts.load(overrides=settings.prompt_overrides)
    return graph_cache_key(
        doc_name=doc_name,
        chunks=tuple(
            (chunk_path.name, chunk_path.read_text(encoding="utf-8"))
            for chunk_path in chunk_paths
        ),
        extraction_prompt_version=graph_prompts.source_claim_extraction.version,
        extraction_model=settings.fact_extractor_model,
        source_claims_per_section=settings.source_claims_per_section,
        extractor_max_tokens=settings.extractor_max_tokens,
        embedding_model=resolve_embedding_model(),
        similarity_threshold=resolve_claim_similarity_threshold(),
    )


def chunk_graph_bundles_from_cache(
    *,
    settings: SummarySettings,
    chunk_paths: Sequence[Path],
    cached: CachedDocumentGraphs,
) -> tuple[ChunkGraphBundle, ...] | None:
    """Rebuild chunk bundles from cached graphs; None when they don't line up."""
    from alex.lib.claim_graph import (
        GraphSettings,
        render_selected_subgraph,
        select_claim_subgraph,
    )

    if len(cached.chunk_graphs) != len(chunk_paths):
        return None
    if any(
        entry.chunk_filename != chunk_path.name
        for entry, chunk_path in zip(cached.chunk_graphs, chunk_paths, strict=True)
    ):
        return None
    graph_settings = GraphSettings(
        max_claims=settings.chunk_graph_max_claims,
        source_claims_per_section=settings.source_claims_per_section,
    )
    bundles: list[ChunkGraphBundle] = []
    for entry, chunk_path in zip(cached.chunk_graphs, chunk_paths, strict=True):
        selected = select_claim_subgraph(entry.graph, settings=graph_settings)
        bundles.append(
            ChunkGraphBundle(
                chunk_path=chunk_path,
                graph=entry.graph,
                selected=selected,
                selected_markdown=render_selected_subgraph(selected),
            )
        )
    return tuple(bundles)


def merged_document_graph(
    *,
    doc_name: str,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
    embedder: Embedder,
) -> ClaimGraph:
    from alex.lib.claim_graph import merge_chunk_graphs

    return merge_chunk_graphs(
        doc_name=doc_name,
        source_path=doc_name,
        chunk_graphs=tuple(bundle.graph for bundle in chunk_graph_bundles),
        embedder=embedder,
    )


def graph_enhanced_summary(
    *,
    settings: SummarySettings,
    asset_dir: Path,
    doc_name: str,
    doc_text: str,
    standard_summary: str,
    graph_draft: GraphSummaryDraft,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
    completer: Completer,
) -> GraphEnhancedSummary:
    from alex.lib.claim_graph import (
        write_graph_json,
    )
    from alex.lib.summary_eval import (
        EvalPrompts,
        EvalSettings,
        extract_claims,
        verify_claims,
    )

    eval_settings = EvalSettings(
        judge_model=settings.judge_model,
        fact_extractor_model=settings.fact_extractor_model,
        judge_max_tokens=settings.judge_max_tokens,
        extractor_max_tokens=settings.extractor_max_tokens,
        max_workers=settings.max_workers,
    )
    eval_prompts = EvalPrompts.load()
    merge_prompts = MergePrompts.load(overrides=settings.prompt_overrides)
    merged_summary = completer.complete(
        prompt=merge_prompts.merged_summary.render(
            document_name=doc_name,
            standard_summary=standard_summary,
            graph_summary=graph_draft.graph_summary_text,
        ),
        model=settings.final_model,
        max_tokens=settings.final_summary_max_tokens,
    )
    # The merge favors brevity and the faithfulness filter only ever removes, so
    # left alone the graph path sheds real facts. Repair re-adds high-value claims
    # that are in the graph but missing from the merge, BEFORE the filter, so any
    # claim it reintroduces is still verified against the full source and dropped
    # if unsupported. Coverage up, faithfulness still guaranteed.
    summary_for_verification = merged_summary
    if settings.coverage_repair:
        summary_for_verification = completer.complete(
            prompt=merge_prompts.merged_summary_repair.render(
                document_name=doc_name,
                selected_subgraph=graph_draft.selected_markdown,
                merged_summary=merged_summary,
            ),
            model=settings.final_model,
            max_tokens=settings.final_summary_max_tokens,
        )
    claims = extract_claims(
        summary=summary_for_verification,
        template=eval_prompts.claim_extraction,
        completer=completer,
        settings=eval_settings,
    )
    verdicts = verify_claims(
        doc_text=doc_text,
        claims=claims,
        template=eval_prompts.claim_verification,
        completer=completer,
        settings=eval_settings,
    )
    repair_passes = tuple(
        [
            RepairPass(
                pass_index=1,
                input_summary=summary_for_verification,
                output_summary="",
                repaired_claims=tuple(
                    verdict.claim for verdict in verdicts if not verdict.supported
                ),
                unsupported_claims=tuple(
                    verdict.claim for verdict in verdicts if not verdict.supported
                ),
            )
        ]
        if any(not verdict.supported for verdict in verdicts)
        and settings.verification_passes > 0
        else []
    )
    filtered_summary = completer.complete(
        prompt=merge_prompts.merged_summary_faithfulness_filter.render(
            document_name=doc_name,
            candidate_summary=summary_for_verification,
            supported_claims=render_supported_claims(verdicts),
            unsupported_claims=render_unsupported_claims(verdicts),
        ),
        model=settings.final_model,
        max_tokens=settings.final_summary_max_tokens,
    )
    if repair_passes:
        repair_passes = (
            RepairPass(
                pass_index=repair_passes[0].pass_index,
                input_summary=repair_passes[0].input_summary,
                output_summary=filtered_summary,
                repaired_claims=repair_passes[0].repaired_claims,
                unsupported_claims=repair_passes[0].unsupported_claims,
            ),
        )

    artifact_dir: Path | None = None
    if settings.graph_artifacts:
        artifact_dir = asset_dir / "summary_graph"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "standard_summary.md").write_text(
            standard_summary,
            encoding="utf-8",
        )
        (artifact_dir / "graph_summary.md").write_text(
            graph_draft.graph_summary_text,
            encoding="utf-8",
        )
        (artifact_dir / "merged_summary.md").write_text(
            merged_summary,
            encoding="utf-8",
        )
        if settings.coverage_repair:
            (artifact_dir / "repaired_summary.md").write_text(
                summary_for_verification,
                encoding="utf-8",
            )
        (artifact_dir / "faithfulness_filtered_summary.md").write_text(
            filtered_summary,
            encoding="utf-8",
        )
        write_chunk_graph_artifacts(
            artifact_dir=artifact_dir,
            chunk_graph_bundles=chunk_graph_bundles,
            write_graph_json=write_graph_json,
        )
        write_graph_json(
            artifact_dir / "document_graph.json",
            graph_draft.document_graph,
        )
        write_graph_json(
            artifact_dir / "selected_document_subgraph.json",
            graph_draft.selected,
        )
        (artifact_dir / "selected_document_subgraph.md").write_text(
            graph_draft.selected_markdown,
            encoding="utf-8",
        )
        write_graph_json(artifact_dir / "graph.json", graph_draft.document_graph)
        write_graph_json(artifact_dir / "selected_subgraph.json", graph_draft.selected)
        (artifact_dir / "selected_subgraph.md").write_text(
            graph_draft.selected_markdown,
            encoding="utf-8",
        )
        write_claim_verdicts_json(
            artifact_dir / "pre_filter_claim_verdicts.json",
            verdicts,
        )
        if settings.evidence_ledger:
            source_blocks = source_blocks_for_summary(
                doc_name=doc_name,
                doc_text=doc_text,
                chunk_graph_bundles=chunk_graph_bundles,
            )
            evidence_records = evidence_records_for_graph(
                graph_draft.selected,
                source_blocks=source_blocks,
            )
            summary_plan = summary_plan_for_evidence(
                doc_name=doc_name,
                evidence_records=evidence_records,
            )
            write_json_dataclasses(artifact_dir / "source_blocks.json", source_blocks)
            write_json_dataclasses(
                artifact_dir / "evidence_records.json",
                evidence_records,
            )
            write_json_dataclass(artifact_dir / "summary_plan.json", summary_plan)
            write_summary_claims_json(
                artifact_dir / "summary_claims.json",
                verdicts,
                evidence_records=evidence_records,
            )
            write_claim_verdicts_json(
                artifact_dir / "claim_verification.json",
                verdicts,
            )
            write_json_dataclasses(
                artifact_dir / "revision_passes.json",
                repair_passes,
            )
            (asset_dir / "summary_evidence.md").write_text(
                summary_evidence_markdown(
                    doc_name=doc_name,
                    evidence_records=evidence_records,
                    verdicts=verdicts,
                    repair_passes=repair_passes,
                ),
                encoding="utf-8",
            )

    return GraphEnhancedSummary(
        final_summary=filtered_summary,
        artifact_dir=artifact_dir,
    )


def graph_summary_draft(
    *,
    settings: SummarySettings,
    doc_name: str,
    document_graph: ClaimGraph,
    completer: Completer,
) -> GraphSummaryDraft:
    from alex.lib.claim_graph import (
        GraphPrompts,
        GraphSettings,
        graph_summary_prompt,
        render_selected_subgraph,
        select_claim_subgraph,
    )

    graph_prompts = GraphPrompts.load(overrides=settings.prompt_overrides)
    selected = select_claim_subgraph(
        document_graph,
        settings=GraphSettings(max_claims=settings.graph_max_claims),
    )
    selected_markdown = render_selected_subgraph(selected)
    graph_summary_text = completer.complete(
        prompt=graph_summary_prompt(
            doc_name=doc_name,
            selected_subgraph_markdown=selected_markdown,
            template=graph_prompts.graph_guided_summary,
        ),
        model=settings.final_model,
        max_tokens=settings.final_summary_max_tokens,
    )
    return GraphSummaryDraft(
        document_graph=document_graph,
        selected=selected,
        selected_markdown=selected_markdown,
        graph_summary_text=graph_summary_text,
    )


def write_chunk_graph_artifacts(
    *,
    artifact_dir: Path,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
    write_graph_json: Callable[[Path, ClaimGraph], None],
) -> None:
    chunks_dir = artifact_dir / "chunks"
    chunks_dir.mkdir()
    for bundle in chunk_graph_bundles:
        chunk_dir = chunks_dir / bundle.chunk_path.stem
        chunk_dir.mkdir()
        write_graph_json(chunk_dir / "graph.json", bundle.graph)
        write_graph_json(chunk_dir / "selected_subgraph.json", bundle.selected)
        (chunk_dir / "selected_subgraph.md").write_text(
            bundle.selected_markdown,
            encoding="utf-8",
        )


def source_blocks_for_summary(
    *,
    doc_name: str,
    doc_text: str,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
) -> tuple[SourceBlock, ...]:
    blocks = [
        SourceBlock(
            id="doc:full",
            kind="document",
            source_path=doc_name,
            heading_path=doc_name,
            text=doc_text,
            start_char=0,
            end_char=len(doc_text),
        )
    ]
    for index, bundle in enumerate(chunk_graph_bundles, 1):
        text = bundle.chunk_path.read_text(encoding="utf-8")
        blocks.append(
            SourceBlock(
                id=f"chunk:{index:03d}",
                kind="chunk",
                source_path=f"chunks/{bundle.chunk_path.name}",
                heading_path=heading_path_for_chunk(
                    text, fallback=bundle.chunk_path.stem
                ),
                text=text,
                start_char=0,
                end_char=len(text),
                chunk_index=index,
                chunk_filename=bundle.chunk_path.name,
            )
        )
    return tuple(blocks)


def heading_path_for_chunk(text: str, *, fallback: str) -> str:
    headings = [
        line.strip().lstrip("#").strip()
        for line in text.splitlines()
        if line.startswith("#")
    ]
    return " > ".join(heading for heading in headings if heading) or fallback


def evidence_records_for_graph(
    graph: ClaimGraph,
    *,
    source_blocks: Sequence[SourceBlock],
) -> tuple[EvidenceRecord, ...]:
    nodes_by_id = graph.node_map()
    records: list[EvidenceRecord] = []
    for node in graph.nodes:
        if node.type not in {"claim", "evidence", "concept", "key_passage"}:
            continue
        text = node.text
        if node.type == "concept":
            text = f"{node.label}: {node.text}"
        source_block = source_block_for_node(node.metadata, source_blocks)
        section_path = node.metadata.get("section") or source_block.heading_path
        claim_text = node.text
        if node.type == "evidence":
            claim_text = claims_supported_by_evidence(node.id, graph)
        if node.type == "claim":
            evidence_id = node.metadata.get("evidence_id")
            if evidence_id and evidence_id in nodes_by_id:
                text = nodes_by_id[evidence_id].text
        records.append(
            EvidenceRecord(
                id=stable_evidence_record_id(node.id),
                source_block_id=source_block.id,
                kind=node.type,
                text=text,
                claim=claim_text,
                entities=extract_capitalized_entities(claim_text),
                dates=extract_dates(f"{claim_text} {text}"),
                quantities=extract_quantities(f"{claim_text} {text}"),
                section_path=section_path,
                score=node.score,
                validated_exact_span=bool(text and text in source_block.text),
            )
        )
    return tuple(records)


def source_block_for_node(
    metadata: Mapping[str, str],
    source_blocks: Sequence[SourceBlock],
) -> SourceBlock:
    chunk_filename = metadata.get("chunk_filename")
    if chunk_filename:
        for block in source_blocks:
            if block.chunk_filename == chunk_filename:
                return block
    return source_blocks[0]


def claims_supported_by_evidence(evidence_id: str, graph: ClaimGraph) -> str:
    node_map = graph.node_map()
    claims = [
        node_map[edge.target].text
        for edge in graph.edges
        if edge.source == evidence_id
        and edge.type == "supports"
        and edge.target in node_map
    ]
    return " ".join(claims)


def stable_evidence_record_id(node_id: str) -> str:
    return "ev:" + re.sub(r"[^a-zA-Z0-9._:-]+", "-", node_id).strip("-")


def extract_capitalized_entities(text: str) -> tuple[str, ...]:
    candidates = re.findall(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*\b", text)
    return tuple(
        dict.fromkeys(candidate for candidate in candidates if len(candidate) > 1)
    )


def extract_dates(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            re.findall(r"\b(?:1[6-9]\d{2}|20\d{2}|21\d{2})\b", text)
            + re.findall(
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
                text,
            )
        )
    )


def extract_quantities(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\b\d+(?:\.\d+)?%?|\b\d+/\d+\b", text)))


def summary_plan_for_evidence(
    *,
    doc_name: str,
    evidence_records: Sequence[EvidenceRecord],
) -> SummaryPlan:
    by_section: dict[str, list[EvidenceRecord]] = {}
    for record in evidence_records:
        by_section.setdefault(record.section_path, []).append(record)
    topics = tuple(
        SummaryPlanTopic(
            title=section,
            evidence_ids=tuple(record.id for record in records[:8]),
            section_path=section,
            word_budget_hint=max(80, min(300, len(records) * 45)),
        )
        for section, records in by_section.items()
    )
    return SummaryPlan(
        document=doc_name,
        topics=topics,
        section_coverage={
            section: len(records) for section, records in by_section.items()
        },
    )


def write_json_dataclass(path: Path, item: Any) -> None:
    path.write_text(json.dumps(asdict(item), indent=2) + "\n", encoding="utf-8")


def write_json_dataclasses(path: Path, items: Sequence[Any]) -> None:
    path.write_text(
        json.dumps([asdict(item) for item in items], indent=2) + "\n",
        encoding="utf-8",
    )


def write_summary_claims_json(
    path: Path,
    verdicts: Sequence[ClaimVerdict],
    *,
    evidence_records: Sequence[EvidenceRecord],
) -> None:
    evidence_ids = tuple(record.id for record in evidence_records)
    payload = [
        {
            "claim": verdict.claim,
            "status": verdict_status(verdict),
            "supported": verdict.supported,
            "evidence": verdict.evidence,
            "evidence_ids": list(evidence_ids[:3]),
            "issue_categories": list(getattr(verdict, "issue_categories", ())),
        }
        for verdict in verdicts
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def summary_evidence_markdown(
    *,
    doc_name: str,
    evidence_records: Sequence[EvidenceRecord],
    verdicts: Sequence[ClaimVerdict],
    repair_passes: Sequence[RepairPass],
) -> str:
    lines = [
        f"# Evidence Ledger: {doc_name}",
        "",
        "## Final Claim Verification",
        "",
    ]
    if verdicts:
        for index, verdict in enumerate(verdicts, 1):
            lines.extend(
                [
                    f"{index}. **{verdict_status(verdict)}** {verdict.claim}",
                    f"   - Evidence: {verdict.evidence}",
                    "",
                ]
            )
    else:
        lines.extend(["No final summary claims were extracted.", ""])
    lines.extend(["## Evidence Records", ""])
    if evidence_records:
        for record in evidence_records:
            exact_span = str(record.validated_exact_span).lower()
            lines.extend(
                [
                    f"### {record.id}",
                    "",
                    f"- Kind: {record.kind}",
                    f"- Source block: `{record.source_block_id}`",
                    f"- Section: {record.section_path}",
                    f"- Exact span validated: {exact_span}",
                    f"- Claim: {record.claim or 'None'}",
                    "",
                    record.text,
                    "",
                ]
            )
    else:
        lines.extend(["No evidence records were selected.", ""])
    lines.extend(["## Repair Passes", ""])
    if repair_passes:
        for repair in repair_passes:
            lines.extend(
                [
                    f"- Pass {repair.pass_index}: "
                    f"{len(repair.repaired_claims)} claim(s) targeted.",
                ]
            )
    else:
        lines.append("- No unsupported claims required a targeted repair pass.")
    return "\n".join(lines).strip() + "\n"


def verdict_status(verdict: ClaimVerdict) -> str:
    status = getattr(verdict, "status", "")
    if status:
        return status
    return "SUPPORTED" if verdict.supported else "NOT_IN_SOURCE"


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


def write_claim_verdicts_json(
    path: Path,
    verdicts: Sequence[ClaimVerdict],
) -> None:
    payload = [
        {
            "claim": verdict.claim,
            "supported": verdict.supported,
            "status": verdict_status(verdict),
            "evidence": verdict.evidence,
            "issue_categories": list(getattr(verdict, "issue_categories", ())),
        }
        for verdict in verdicts
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def authors_for_display(metadata: DocumentMetadata) -> str:
    if metadata.authors:
        return ", ".join(metadata.authors)
    return "Unknown"


def write_individual_chunk_summaries(
    *,
    chunk_summaries_dir: Path,
    chunk_paths: tuple[Path, ...],
    chunk_summaries: tuple[str, ...],
) -> None:
    for chunk_path, summary in zip(chunk_paths, chunk_summaries, strict=True):
        summary_path = chunk_summaries_dir / f"{chunk_path.stem}_summary.md"
        summary_path.write_text(
            f"""# Summary: {chunk_path.name}
**Source Chunk:** `chunks/{chunk_path.name}`

{summary}
""",
            encoding="utf-8",
        )


def concatenate_chunk_summaries(chunk_summaries_dir: Path) -> str:
    return "\n\n---\n\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(chunk_summaries_dir.glob("*.md"))
    )


def compress_summary_until_within_context(
    *,
    content: str,
    title: str,
    authors: str,
    template: PromptTemplate,
    max_context_tokens: int,
    completer: Completer,
    model: str,
    max_tokens: int,
    max_workers: int,
) -> str:
    if max_context_tokens <= 0:
        raise SummarizationError("max_context_tokens must be positive.")

    current = content
    iterations = 0
    while count_tokens_estimate(current) > max_context_tokens:
        iterations += 1
        if iterations > MAX_SUMMARY_COMPRESSION_ITERATIONS:
            raise SummarizationError(
                "Recursive summary compression did not fit within the context limit."
            )

        chunks = split_content_for_summary_compression(
            content=current,
            max_context_tokens=max_context_tokens,
        )
        prompts = tuple(
            template.render(title=title, authors=authors, content=chunk)
            for chunk in chunks
        )
        compressed_chunks = complete_all(
            completer=completer,
            prompts=prompts,
            model=model,
            max_tokens=max_tokens,
            max_workers=max_workers,
        )
        compressed = "\n\n---\n\n".join(compressed_chunks)
        if len(compressed) >= len(current):
            raise SummarizationError(
                "Recursive summary compression did not reduce the summary size."
            )
        current = compressed

    return current


def split_content_for_summary_compression(
    *,
    content: str,
    max_context_tokens: int,
) -> tuple[str, ...]:
    # count_tokens_estimate assumes ~4 chars per token; splitting at 3 chars
    # per token leaves headroom for the compression prompt wrapped around
    # each chunk.
    chunk_size = max(1, max_context_tokens * 3)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for line in content.splitlines():
        line_length = len(line) + 1
        if current_chunk and current_length + line_length > chunk_size:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = line_length
            continue
        current_chunk.append(line)
        current_length += line_length

    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return tuple(chunks)


def chunk_summary_content(
    *,
    title: str,
    authors: str,
    markdown_filename: str,
    references: tuple[SummaryChunkReference, ...],
    consolidated: str,
) -> str:
    chunk_index = "\n".join(
        f"{reference.index}. [{reference.filename}]({reference.path})"
        for reference in references
    )
    return f"""# Chunk Summary: {title}
**Author(s):** {authors}

[Back to full document]({markdown_filename})

This document contains consolidated summaries of all chunks from the source material.

## Available Chunks

{chunk_index}

---

{consolidated}
"""


def chunk_reference_list(references: tuple[SummaryChunkReference, ...]) -> str:
    return "\n".join(
        f"{reference.index}. {reference.filename} "
        f"-> Link as: `[text]({reference.path})`"
        for reference in references
    )


def summary_content(
    *,
    title: str,
    authors: str,
    markdown_filename: str,
    final_summary: str,
    references: tuple[SummaryChunkReference, ...],
    evidence_ledger: str | None = None,
) -> str:
    chunk_index = "\n".join(
        f"{reference.index}. [{reference.filename}]({reference.path})"
        for reference in references
    )
    evidence_link = (
        f" | [View evidence ledger]({evidence_ledger})" if evidence_ledger else ""
    )
    navigation = (
        f"[Back to full document]({markdown_filename}) | "
        f"[View chunk summary](chunk_summary.md){evidence_link}"
    )
    return f"""# Summary: {title}
**Author(s):** {authors}

{navigation}

---

{final_summary}

---

## Explore by Section

For detailed exploration of specific sections, see the individual chunks:

{chunk_index}
"""
