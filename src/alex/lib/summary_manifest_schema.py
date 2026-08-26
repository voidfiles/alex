from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alex.lib.summarize import ChunkGraphBundle, GraphSummaryDraft, SummarySettings


@dataclass(frozen=True)
class SummaryManifestContext:
    settings: SummarySettings
    asset_dir: Path
    source_path: Path
    output_path: Path
    chunk_paths: Sequence[Path]
    graph_draft: GraphSummaryDraft
    chunk_graph_bundles: Sequence[ChunkGraphBundle]
    artifact_dir: Path


@dataclass(frozen=True)
class SummaryFailedManifestContext:
    settings: SummarySettings
    asset_dir: Path
    source_path: Path
    output_path: Path
    chunk_paths: Sequence[Path]
    artifact_dir: Path
    last_completed_stage: str
    error: Exception
    graph_draft: GraphSummaryDraft | None = None
    chunk_graph_bundles: Sequence[ChunkGraphBundle] = ()


@dataclass(frozen=True)
class SummaryRunningManifestContext:
    settings: SummarySettings
    asset_dir: Path
    source_path: Path
    output_path: Path
    chunk_paths: Sequence[Path]
    artifact_dir: Path
    last_completed_stage: str
    graph_draft: GraphSummaryDraft | None = None
    chunk_graph_bundles: Sequence[ChunkGraphBundle] = ()


@dataclass(frozen=True)
class SummaryManifestSettings:
    graph_enhanced: bool
    chunk_graph_enhanced: bool
    coverage_repair: bool
    graph_artifacts: bool
    evidence_ledger: bool
    force: bool


@dataclass(frozen=True)
class SummaryManifestChunks:
    count: int
    artifacts: tuple[str, ...]


@dataclass(frozen=True)
class SummaryManifestGraph:
    document_claim_count: int
    document_edge_count: int
    selected_claim_count: int
    selected_edge_count: int
    chunk_graph_count: int
    chunk_claim_count: int
    chunk_edge_count: int


@dataclass(frozen=True)
class SummaryManifestError:
    type: str
    message: str


@dataclass(frozen=True)
class SummaryManifestStages:
    chunk_graphs: tuple[str, ...]
    standard_summary: tuple[str, ...]
    graph_summary: tuple[str, ...]
    merged_summary: tuple[str, ...]
    coverage_repair: tuple[str, ...]
    faithfulness_filter: tuple[str, ...]
    document_graph: tuple[str, ...]
    evidence_ledger: tuple[str, ...]


@dataclass(frozen=True)
class SummaryManifest:
    schema_version: int
    status: str
    last_completed_stage: str | None
    source_path: str
    output_path: str
    settings: SummaryManifestSettings
    prompt_versions: Mapping[str, str]
    environment_caps: Mapping[str, int]
    chunks: SummaryManifestChunks
    graph: SummaryManifestGraph
    stages: SummaryManifestStages
    artifacts: tuple[str, ...]
    error: SummaryManifestError | None = None
