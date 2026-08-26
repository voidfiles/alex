from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from alex.lib.summary_manifest_schema import (
    SummaryManifestContext,
    SummaryManifestGraph,
    SummaryManifestStages,
)

if TYPE_CHECKING:
    from alex.lib.claim_graph import ClaimGraph
    from alex.lib.summarize import ChunkGraphBundle, GraphSummaryDraft


_SENSITIVE_ERROR_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED_ANTHROPIC_KEY]",
    ),
    (
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED_OPENAI_KEY]",
    ),
    (
        re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
        "[REDACTED_GEMINI_KEY]",
    ),
    (
        re.compile(
            r"(?i)\b((?:api|provider)[_-]?(?:key|token)\s*[:=]\s*)"
            r"[A-Za-z0-9._~+/=-]{24,}\b"
        ),
        r"\1[REDACTED_PROVIDER_TOKEN]",
    ),
    (
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+"),
        "[REDACTED_BEARER_TOKEN]",
    ),
    (
        re.compile(
            r"(?<![\w:/])/(?!/)(?:[^/\s\x00,;)'\"<>]+(?: [^/\s\x00,;)'\"<>]+)?/)+"
            r"[^/\s\x00,;)'\"<>]+(?: [^/\s\x00,;)'\"<>]+)?\.[A-Za-z0-9]+"
        ),
        "[REDACTED_LOCAL_PATH]",
    ),
    (
        re.compile(
            r"\b[A-Za-z]:[\\/]"
            r"(?:[^\\/\s\x00,;)'\"<>]+(?: [^\\/\s\x00,;)'\"<>]+)?[\\/])+"
            r"[^\\/\s\x00,;)'\"<>]+(?: [^\\/\s\x00,;)'\"<>]+)?\.[A-Za-z0-9]+"
        ),
        "[REDACTED_LOCAL_PATH]",
    ),
    (
        re.compile(r"(?<![\w:/])/(?!/)[^\s\x00,;)'\"<>]*"),
        "[REDACTED_LOCAL_PATH]",
    ),
    (
        re.compile(r"\b[A-Za-z]:[\\/][^\s\x00,;)'\"<>]*"),
        "[REDACTED_LOCAL_PATH]",
    ),
)


def summary_manifest_stages(context: SummaryManifestContext) -> SummaryManifestStages:
    evidence_artifacts = (
        (
            context.asset_dir / "summary_evidence.md",
            context.artifact_dir / "source_blocks.json",
            context.artifact_dir / "evidence_records.json",
            context.artifact_dir / "summary_plan.json",
            context.artifact_dir / "summary_claims.json",
            context.artifact_dir / "claim_verification.json",
            context.artifact_dir / "revision_passes.json",
        )
        if context.settings.evidence_ledger
        else ()
    )
    return SummaryManifestStages(
        chunk_graphs=tuple(
            path
            for bundle in context.chunk_graph_bundles
            for path in (
                manifest_artifact_path(
                    context,
                    "chunks",
                    bundle.chunk_path.stem,
                    "graph.json",
                ),
                manifest_artifact_path(
                    context,
                    "chunks",
                    bundle.chunk_path.stem,
                    "selected_subgraph.json",
                ),
                manifest_artifact_path(
                    context,
                    "chunks",
                    bundle.chunk_path.stem,
                    "selected_subgraph.md",
                ),
            )
        ),
        standard_summary=(manifest_artifact_path(context, "standard_summary.md"),),
        graph_summary=(manifest_artifact_path(context, "graph_summary.md"),),
        merged_summary=(manifest_artifact_path(context, "merged_summary.md"),),
        coverage_repair=(
            (manifest_artifact_path(context, "repaired_summary.md"),)
            if context.settings.coverage_repair
            else ()
        ),
        faithfulness_filter=(
            manifest_artifact_path(context, "faithfulness_filtered_summary.md"),
            manifest_artifact_path(context, "pre_filter_claim_verdicts.json"),
        ),
        document_graph=(
            manifest_artifact_path(context, "document_graph.json"),
            manifest_artifact_path(context, "selected_document_subgraph.json"),
            manifest_artifact_path(context, "selected_document_subgraph.md"),
            manifest_artifact_path(context, "graph.json"),
            manifest_artifact_path(context, "selected_subgraph.json"),
            manifest_artifact_path(context, "selected_subgraph.md"),
        ),
        evidence_ledger=tuple(
            relative_artifact_path(asset_dir=context.asset_dir, path=path)
            for path in evidence_artifacts
        ),
    )


def failed_summary_manifest_stages() -> SummaryManifestStages:
    return SummaryManifestStages(
        chunk_graphs=(),
        standard_summary=(),
        graph_summary=(),
        merged_summary=(),
        coverage_repair=(),
        faithfulness_filter=(),
        document_graph=(),
        evidence_ledger=(),
    )


def summary_manifest_graph(
    *,
    graph_draft: GraphSummaryDraft | None,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
) -> SummaryManifestGraph:
    return SummaryManifestGraph(
        document_claim_count=(
            claim_count(graph_draft.document_graph) if graph_draft is not None else 0
        ),
        document_edge_count=(
            len(graph_draft.document_graph.edges) if graph_draft is not None else 0
        ),
        selected_claim_count=(
            claim_count(graph_draft.selected) if graph_draft is not None else 0
        ),
        selected_edge_count=(
            len(graph_draft.selected.edges) if graph_draft is not None else 0
        ),
        chunk_graph_count=len(chunk_graph_bundles),
        chunk_claim_count=sum(
            claim_count(bundle.graph) for bundle in chunk_graph_bundles
        ),
        chunk_edge_count=sum(len(bundle.graph.edges) for bundle in chunk_graph_bundles),
    )


def summary_manifest_artifacts(*, stages: SummaryManifestStages) -> tuple[str, ...]:
    return (
        "summary.md",
        "chunk_summary.md",
        "summary_graph/manifest.json",
        *stages.chunk_graphs,
        *stages.standard_summary,
        *stages.graph_summary,
        *stages.merged_summary,
        *stages.coverage_repair,
        *stages.faithfulness_filter,
        *stages.document_graph,
        *stages.evidence_ledger,
    )


def failed_summary_manifest_artifacts(
    *,
    asset_dir: Path,
    artifact_dir: Path,
    stages: SummaryManifestStages,
) -> tuple[str, ...]:
    candidates = (
        asset_dir / "summary.md",
        asset_dir / "chunk_summary.md",
        artifact_dir / "manifest.json",
        *(
            asset_dir / path
            for path in summary_manifest_artifacts(stages=stages)
            if path != "summary.md"
            and path != "chunk_summary.md"
            and path != "summary_graph/manifest.json"
        ),
    )
    return tuple(
        relative_artifact_path(asset_dir=asset_dir, path=path)
        for path in candidates
        if path.exists() or path == artifact_dir / "manifest.json"
    )


def running_summary_manifest_artifacts(
    *,
    asset_dir: Path,
    artifact_dir: Path,
) -> tuple[str, ...]:
    candidates = (
        asset_dir / "chunk_summary.md",
        artifact_dir / "manifest.json",
    )
    return tuple(
        relative_artifact_path(asset_dir=asset_dir, path=path)
        for path in candidates
        if path.exists() or path == artifact_dir / "manifest.json"
    )


def sanitize_error_message(message: str) -> str:
    redacted = message.replace("\x00", "")
    for pattern, replacement in _SENSITIVE_ERROR_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return " ".join(redacted.split())[:500]


def claim_count(graph: ClaimGraph) -> int:
    return sum(1 for node in graph.nodes if node.type == "claim")


def relative_artifact_path(*, asset_dir: Path, path: Path) -> str:
    if path.is_relative_to(asset_dir):
        return path.relative_to(asset_dir).as_posix()
    return path.as_posix()


def manifest_artifact_path(context: SummaryManifestContext, *parts: str) -> str:
    return relative_artifact_path(
        asset_dir=context.asset_dir,
        path=context.artifact_dir.joinpath(*parts),
    )
