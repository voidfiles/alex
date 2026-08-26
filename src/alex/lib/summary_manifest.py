from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from alex.lib.llm import (
    CHUNK_GRAPH_MAX_CLAIMS_ENV,
    GRAPH_MAX_CLAIMS_ENV,
    SOURCE_CLAIMS_PER_SECTION_ENV,
)
from alex.lib.production_prompts import MergePrompts
from alex.lib.summary_manifest_artifacts import (
    failed_summary_manifest_artifacts,
    failed_summary_manifest_stages,
    relative_artifact_path,
    running_summary_manifest_artifacts,
    sanitize_error_message,
    summary_manifest_artifacts,
    summary_manifest_graph,
    summary_manifest_stages,
)
from alex.lib.summary_manifest_schema import (
    SummaryFailedManifestContext,
    SummaryManifest,
    SummaryManifestChunks,
    SummaryManifestContext,
    SummaryManifestError,
    SummaryManifestSettings,
    SummaryRunningManifestContext,
)

if TYPE_CHECKING:
    from alex.lib.summarize import SummarySettings

__all__ = (
    "SummaryFailedManifestContext",
    "SummaryManifestContext",
    "SummaryRunningManifestContext",
    "write_failed_summary_graph_manifest",
    "write_running_summary_graph_manifest",
    "write_summary_graph_manifest",
)


def write_summary_graph_manifest(context: SummaryManifestContext) -> None:
    stages = summary_manifest_stages(context)
    manifest = SummaryManifest(
        schema_version=1,
        status="complete",
        last_completed_stage="summary",
        source_path=relative_artifact_path(
            asset_dir=context.asset_dir,
            path=context.source_path,
        ),
        output_path=relative_artifact_path(
            asset_dir=context.asset_dir,
            path=context.output_path,
        ),
        settings=SummaryManifestSettings(
            graph_enhanced=context.settings.graph_enhanced,
            chunk_graph_enhanced=context.settings.chunk_graph_enhanced,
            coverage_repair=context.settings.coverage_repair,
            graph_artifacts=context.settings.graph_artifacts,
            evidence_ledger=context.settings.evidence_ledger,
            force=context.settings.force,
        ),
        prompt_versions=summary_manifest_prompt_versions(context.settings),
        environment_caps=summary_manifest_environment_caps(context.settings),
        chunks=SummaryManifestChunks(
            count=len(context.chunk_paths),
            artifacts=tuple(
                relative_artifact_path(asset_dir=context.asset_dir, path=path)
                for path in context.chunk_paths
            ),
        ),
        graph=summary_manifest_graph(
            graph_draft=context.graph_draft,
            chunk_graph_bundles=context.chunk_graph_bundles,
        ),
        stages=stages,
        artifacts=summary_manifest_artifacts(stages=stages),
    )
    write_manifest_json(context.artifact_dir / "manifest.json", manifest)


def write_running_summary_graph_manifest(
    context: SummaryRunningManifestContext,
) -> None:
    context.artifact_dir.mkdir(parents=True, exist_ok=True)
    stages = failed_summary_manifest_stages()
    manifest = SummaryManifest(
        schema_version=1,
        status="running",
        last_completed_stage=context.last_completed_stage,
        source_path=relative_artifact_path(
            asset_dir=context.asset_dir,
            path=context.source_path,
        ),
        output_path=relative_artifact_path(
            asset_dir=context.asset_dir,
            path=context.output_path,
        ),
        settings=SummaryManifestSettings(
            graph_enhanced=context.settings.graph_enhanced,
            chunk_graph_enhanced=context.settings.chunk_graph_enhanced,
            coverage_repair=context.settings.coverage_repair,
            graph_artifacts=context.settings.graph_artifacts,
            evidence_ledger=context.settings.evidence_ledger,
            force=context.settings.force,
        ),
        prompt_versions=summary_manifest_prompt_versions(context.settings),
        environment_caps=summary_manifest_environment_caps(context.settings),
        chunks=SummaryManifestChunks(
            count=len(context.chunk_paths),
            artifacts=tuple(
                relative_artifact_path(asset_dir=context.asset_dir, path=path)
                for path in context.chunk_paths
            ),
        ),
        graph=summary_manifest_graph(
            graph_draft=context.graph_draft,
            chunk_graph_bundles=context.chunk_graph_bundles,
        ),
        stages=stages,
        artifacts=running_summary_manifest_artifacts(
            asset_dir=context.asset_dir,
            artifact_dir=context.artifact_dir,
        ),
    )
    write_manifest_json(context.artifact_dir / "manifest.json", manifest)


def write_failed_summary_graph_manifest(context: SummaryFailedManifestContext) -> None:
    context.artifact_dir.mkdir(parents=True, exist_ok=True)
    stages = failed_summary_manifest_stages()
    manifest = SummaryManifest(
        schema_version=1,
        status="failed",
        last_completed_stage=context.last_completed_stage,
        source_path=relative_artifact_path(
            asset_dir=context.asset_dir,
            path=context.source_path,
        ),
        output_path=relative_artifact_path(
            asset_dir=context.asset_dir,
            path=context.output_path,
        ),
        settings=SummaryManifestSettings(
            graph_enhanced=context.settings.graph_enhanced,
            chunk_graph_enhanced=context.settings.chunk_graph_enhanced,
            coverage_repair=context.settings.coverage_repair,
            graph_artifacts=context.settings.graph_artifacts,
            evidence_ledger=context.settings.evidence_ledger,
            force=context.settings.force,
        ),
        prompt_versions=summary_manifest_prompt_versions(context.settings),
        environment_caps=summary_manifest_environment_caps(context.settings),
        chunks=SummaryManifestChunks(
            count=len(context.chunk_paths),
            artifacts=tuple(
                relative_artifact_path(asset_dir=context.asset_dir, path=path)
                for path in context.chunk_paths
            ),
        ),
        graph=summary_manifest_graph(
            graph_draft=context.graph_draft,
            chunk_graph_bundles=context.chunk_graph_bundles,
        ),
        stages=stages,
        artifacts=failed_summary_manifest_artifacts(
            asset_dir=context.asset_dir,
            artifact_dir=context.artifact_dir,
            stages=stages,
        ),
        error=SummaryManifestError(
            type=context.error.__class__.__name__,
            message=sanitize_error_message(str(context.error)),
        ),
    )
    write_manifest_json(context.artifact_dir / "manifest.json", manifest)


def summary_manifest_prompt_versions(
    settings: SummarySettings,
) -> dict[str, str]:
    from alex.lib.claim_graph import GraphPrompts
    from alex.lib.summary_eval import EvalPrompts

    graph_prompts = GraphPrompts.load(overrides=settings.prompt_overrides)
    merge_prompts = MergePrompts.load(overrides=settings.prompt_overrides)
    eval_prompts = EvalPrompts.load()
    return {
        "chunk_summary": settings.prompts.chunk_summary.version,
        "chunk_summary_with_graph": settings.prompts.chunk_summary_with_graph.version,
        "compression_summary": settings.prompts.compression_summary.version,
        "final_summary": settings.prompts.final_summary.version,
        "source_claim_extraction": graph_prompts.source_claim_extraction.version,
        "graph_guided_summary": graph_prompts.graph_guided_summary.version,
        "merged_summary": merge_prompts.merged_summary.version,
        "merged_summary_repair": merge_prompts.merged_summary_repair.version,
        "merged_summary_faithfulness_filter": (
            merge_prompts.merged_summary_faithfulness_filter.version
        ),
        "claim_extraction": eval_prompts.claim_extraction.version,
        "claim_verification": eval_prompts.claim_verification.version,
    }


def summary_manifest_environment_caps(
    settings: SummarySettings,
) -> dict[str, int]:
    return {
        CHUNK_GRAPH_MAX_CLAIMS_ENV: settings.chunk_graph_max_claims,
        GRAPH_MAX_CLAIMS_ENV: settings.graph_max_claims,
        SOURCE_CLAIMS_PER_SECTION_ENV: settings.source_claims_per_section,
    }


def write_manifest_json(path: Path, manifest: SummaryManifest) -> None:
    path.write_text(json.dumps(asdict(manifest), indent=2) + "\n", encoding="utf-8")
