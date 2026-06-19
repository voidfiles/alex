"""Map-reduce summarization of a chunked document asset."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING

from alex.lib.chunking import count_tokens_estimate
from alex.lib.document_sources import DocumentMetadata
from alex.lib.llm import (
    Completer,
    complete_all,
    resolve_eval_judge_model,
    resolve_fact_extractor_model,
    resolve_fast_summary_model,
    resolve_final_summary_model,
)
from alex.lib.prompt_templates import PromptTemplate, load_prompt

if TYPE_CHECKING:
    from alex.lib.claim_graph import ClaimGraph
    from alex.lib.summary_eval import ClaimVerdict

DEFAULT_CHUNK_SUMMARY_MAX_TOKENS = 20_000
DEFAULT_FINAL_SUMMARY_MAX_TOKENS = 8_192
DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS = 180_000
DEFAULT_SUMMARY_MAX_WORKERS = 4
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
    chunk_summary_max_tokens: int = DEFAULT_CHUNK_SUMMARY_MAX_TOKENS
    final_summary_max_tokens: int = DEFAULT_FINAL_SUMMARY_MAX_TOKENS
    judge_max_tokens: int = 8_192
    extractor_max_tokens: int = 8_192
    graph_enhanced: bool = True
    chunk_graph_enhanced: bool = True
    chunk_graph_max_claims: int = 12
    graph_max_claims: int = 48
    graph_artifacts: bool = True
    max_context_tokens: int = DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS
    max_workers: int = DEFAULT_SUMMARY_MAX_WORKERS
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
class ChunkGraphBundle:
    chunk_path: Path
    graph: ClaimGraph
    selected: ClaimGraph
    selected_markdown: str


def summarize_doc_asset(
    *,
    settings: SummarySettings,
    asset_dir: Path,
    metadata: DocumentMetadata,
    markdown_path: Path,
    headers_path: Path,
    chunk_paths: tuple[Path, ...],
    completer: Completer,
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
    if settings.graph_enhanced:
        chunk_graph_bundles = build_chunk_graph_bundles(
            settings=settings,
            doc_name=markdown_path.name,
            chunk_paths=chunk_paths,
            completer=completer,
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

    standard_final_summary = completer.complete(
        prompt=settings.prompts.final_summary.render(
            title=metadata.title,
            authors=authors,
            section_summaries=consolidated,
            chunk_reference_list=chunk_reference_list(references),
        ),
        model=settings.final_model,
        max_tokens=settings.final_summary_max_tokens,
    )
    final_summary = standard_final_summary
    final_graph_artifact_dir: Path | None = None
    if settings.graph_enhanced:
        source_markdown = markdown_path.read_text(encoding="utf-8")
        document_graph = merged_document_graph(
            doc_name=markdown_path.name,
            chunk_graph_bundles=chunk_graph_bundles,
        )
        graph_summary = graph_enhanced_summary(
            settings=settings,
            asset_dir=asset_dir,
            doc_name=markdown_path.name,
            doc_text=source_markdown,
            standard_summary=standard_final_summary,
            document_graph=document_graph,
            chunk_graph_bundles=chunk_graph_bundles,
            completer=completer,
        )
        final_summary = graph_summary.final_summary
        final_graph_artifact_dir = graph_summary.artifact_dir
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
    graph_prompts = GraphPrompts.load()
    graph_settings = GraphSettings(max_claims=settings.chunk_graph_max_claims)
    bundles: list[ChunkGraphBundle] = []
    for chunk_index, chunk_path in enumerate(chunk_paths, 1):
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
            eval_settings=eval_settings,
            settings=graph_settings,
        )
        selected = select_claim_subgraph(graph, settings=graph_settings)
        bundles.append(
            ChunkGraphBundle(
                chunk_path=chunk_path,
                graph=graph,
                selected=selected,
                selected_markdown=render_selected_subgraph(selected),
            )
        )
    return tuple(bundles)


def merged_document_graph(
    *,
    doc_name: str,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
) -> ClaimGraph:
    from alex.lib.claim_graph import merge_chunk_graphs

    return merge_chunk_graphs(
        doc_name=doc_name,
        source_path=doc_name,
        chunk_graphs=tuple(bundle.graph for bundle in chunk_graph_bundles),
    )


def graph_enhanced_summary(
    *,
    settings: SummarySettings,
    asset_dir: Path,
    doc_name: str,
    doc_text: str,
    standard_summary: str,
    document_graph: ClaimGraph,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
    completer: Completer,
) -> GraphEnhancedSummary:
    from alex.lib.claim_graph import (
        GraphPrompts,
        GraphSettings,
        graph_summary_prompt,
        render_selected_subgraph,
        select_claim_subgraph,
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
    )
    graph_prompts = GraphPrompts.load()
    eval_prompts = EvalPrompts.load()
    merge_template = load_prompt("merged_summary")
    filter_template = load_prompt("merged_summary_faithfulness_filter")

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
    merged_summary = completer.complete(
        prompt=merge_template.render(
            document_name=doc_name,
            standard_summary=standard_summary,
            graph_summary=graph_summary_text,
        ),
        model=settings.final_model,
        max_tokens=settings.final_summary_max_tokens,
    )
    claims = extract_claims(
        summary=merged_summary,
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
    filtered_summary = completer.complete(
        prompt=filter_template.render(
            document_name=doc_name,
            candidate_summary=merged_summary,
            supported_claims=render_supported_claims(verdicts),
            unsupported_claims=render_unsupported_claims(verdicts),
        ),
        model=settings.final_model,
        max_tokens=settings.final_summary_max_tokens,
    )

    artifact_dir: Path | None = None
    if settings.graph_artifacts:
        artifact_dir = asset_dir / "summary_graph"
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "standard_summary.md").write_text(
            standard_summary,
            encoding="utf-8",
        )
        (artifact_dir / "graph_summary.md").write_text(
            graph_summary_text,
            encoding="utf-8",
        )
        (artifact_dir / "merged_summary.md").write_text(
            merged_summary,
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
        write_graph_json(artifact_dir / "document_graph.json", document_graph)
        write_graph_json(artifact_dir / "selected_document_subgraph.json", selected)
        (artifact_dir / "selected_document_subgraph.md").write_text(
            selected_markdown,
            encoding="utf-8",
        )
        write_graph_json(artifact_dir / "graph.json", document_graph)
        write_graph_json(artifact_dir / "selected_subgraph.json", selected)
        (artifact_dir / "selected_subgraph.md").write_text(
            selected_markdown,
            encoding="utf-8",
        )
        write_claim_verdicts_json(
            artifact_dir / "pre_filter_claim_verdicts.json",
            verdicts,
        )

    return GraphEnhancedSummary(
        final_summary=filtered_summary,
        artifact_dir=artifact_dir,
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
            "evidence": verdict.evidence,
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
) -> str:
    chunk_index = "\n".join(
        f"{reference.index}. [{reference.filename}]({reference.path})"
        for reference in references
    )
    return f"""# Summary: {title}
**Author(s):** {authors}

[Back to full document]({markdown_filename}) | [View chunk summary](chunk_summary.md)

---

{final_summary}

---

## Explore by Section

For detailed exploration of specific sections, see the individual chunks:

{chunk_index}
"""
