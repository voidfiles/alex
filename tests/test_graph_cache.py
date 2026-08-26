"""Env-gated graph cache: off means byte-identical behavior, on means the
chunk claim extraction and document-graph merge are skipped on a hit."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from alex.lib.claim_graph import ClaimGraph, GraphEdge, GraphNode, graph_from_dict
from alex.lib.graph_cache import (
    CachedChunkGraph,
    CachedDocumentGraphs,
    graph_cache_key,
    graph_cache_path,
    load_graph_cache,
    store_graph_cache,
)
from alex.lib.llm import GRAPH_CACHE_DIR_ENV
from alex.lib.summarize import SummarySettings
from alex.lib.summary_assets import SummaryAssetConfig, process_summary_asset
from helpers import BagOfWordsEmbedder, RecordingCompleter

SOURCE_TEXT = "# Deep Work\n\nBy Cal Newport\n\nBody text.\n"


def run_pipeline(
    tmp_path: Path,
    *,
    run_name: str,
    settings: SummarySettings,
) -> tuple[RecordingCompleter, Path]:
    source = tmp_path / "deep-work.md"
    if not source.exists():
        source.write_text(SOURCE_TEXT, encoding="utf-8")
    completer = RecordingCompleter(
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )
    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / run_name,
            summary=settings,
        ),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )
    assert result.graph_artifact_dir is not None
    return completer, result.graph_artifact_dir


def extraction_calls(completer: RecordingCompleter) -> list[str]:
    return [
        call.prompt
        for call in completer.calls
        if "source-grounded items" in call.prompt
    ]


def test_graph_cache_dir_resolves_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(GRAPH_CACHE_DIR_ENV, raising=False)
    assert SummarySettings(max_workers=1).graph_cache_dir is None
    monkeypatch.setenv(GRAPH_CACHE_DIR_ENV, str(tmp_path / "cache"))
    assert SummarySettings(max_workers=1).graph_cache_dir == tmp_path / "cache"


def test_cache_off_prompt_sequence_matches_cold_cache_run(tmp_path: Path) -> None:
    off_settings = SummarySettings(max_workers=1, graph_cache_dir=None)
    cold_settings = SummarySettings(
        max_workers=1, graph_cache_dir=tmp_path / "graph-cache"
    )

    off_completer, off_artifacts = run_pipeline(
        tmp_path, run_name="off", settings=off_settings
    )
    cold_completer, cold_artifacts = run_pipeline(
        tmp_path, run_name="cold", settings=cold_settings
    )

    assert [call.prompt for call in off_completer.calls] == [
        call.prompt for call in cold_completer.calls
    ]
    assert (off_artifacts / "document_graph.json").read_bytes() == (
        cold_artifacts / "document_graph.json"
    ).read_bytes()
    assert extraction_calls(off_completer)


def test_cache_hit_skips_extraction_and_reuses_document_graph(tmp_path: Path) -> None:
    cache_dir = tmp_path / "graph-cache"
    settings = SummarySettings(max_workers=1, graph_cache_dir=cache_dir)

    first_completer, first_artifacts = run_pipeline(
        tmp_path, run_name="first", settings=settings
    )
    assert extraction_calls(first_completer)
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1

    second_completer, second_artifacts = run_pipeline(
        tmp_path, run_name="second", settings=settings
    )

    assert extraction_calls(second_completer) == []
    assert (first_artifacts / "document_graph.json").read_bytes() == (
        second_artifacts / "document_graph.json"
    ).read_bytes()
    # Chunk bundles are rebuilt from the cache, so chunk summaries still see
    # the selected chunk graph.
    chunk_calls = second_completer.chunk_calls()
    assert len(chunk_calls) == 1
    assert "<selected_chunk_graph>" in chunk_calls[0].prompt
    assert "The document preserves important claims." in chunk_calls[0].prompt
    # Everything after graph construction still runs.
    assert len(second_completer.final_calls()) == 1
    prompts = [call.prompt for call in second_completer.calls]
    assert any("merging two independently generated summaries" in p for p in prompts)
    assert any("revising a merged summary" in p for p in prompts)


def test_changed_key_ingredient_misses_the_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "graph-cache"
    settings = SummarySettings(max_workers=1, graph_cache_dir=cache_dir)
    run_pipeline(tmp_path, run_name="first", settings=settings)

    changed = replace(
        settings,
        source_claims_per_section=settings.source_claims_per_section + 1,
    )
    second_completer, _ = run_pipeline(tmp_path, run_name="second", settings=changed)

    assert extraction_calls(second_completer)
    assert len(list(cache_dir.glob("*.json"))) == 2


def test_graph_cache_key_tracks_construction_inputs_only() -> None:
    base: dict[str, Any] = {
        "doc_name": "deep-work.md",
        "chunks": (("001_deep_work.md", "Body text."),),
        "extraction_prompt_version": "v007",
        "extraction_model": "anthropic/claude-opus-5",
        "source_claims_per_section": 8,
        "extractor_max_tokens": 8_192,
        "embedding_model": "openai/text-embedding-3-small",
        "similarity_threshold": 0.8,
    }
    key = graph_cache_key(**base)
    assert key == graph_cache_key(**base)

    changed_variants: list[dict[str, Any]] = [
        {**base, "doc_name": "other.md"},
        {**base, "chunks": (("001_deep_work.md", "Different text."),)},
        {**base, "chunks": (("002_deep_work.md", "Body text."),)},
        {**base, "extraction_prompt_version": "v008"},
        {**base, "extraction_model": "anthropic/claude-sonnet-5"},
        {**base, "source_claims_per_section": 9},
        {**base, "extractor_max_tokens": 4_096},
        {**base, "embedding_model": "openai/text-embedding-3-large"},
        {**base, "similarity_threshold": 0.7},
    ]
    keys = {graph_cache_key(**variant) for variant in changed_variants}
    assert key not in keys
    assert len(keys) == len(changed_variants)


def sample_graph() -> ClaimGraph:
    return ClaimGraph(
        doc_name="deep-work.md",
        nodes=(
            GraphNode(
                id="doc:deep-work-md",
                type="document",
                label="deep-work.md",
                source="deep-work.md",
                metadata={"source_path": "deep-work.md"},
            ),
            GraphNode(
                id="claim:deep-work:focus:1",
                type="claim",
                label="Focus matters.",
                source="deep-work.md",
                text="Focus matters.",
                section_index=1,
                score=1.5,
                metadata={"section": "Deep Work"},
            ),
        ),
        edges=(
            GraphEdge(
                source="doc:deep-work-md",
                target="claim:deep-work:focus:1",
                type="contains",
                weight=0.5,
                evidence="Body text.",
            ),
        ),
    )


def test_store_and_load_round_trips_graphs(tmp_path: Path) -> None:
    graphs = CachedDocumentGraphs(
        document_graph=sample_graph(),
        chunk_graphs=(
            CachedChunkGraph(chunk_filename="001_deep_work.md", graph=sample_graph()),
        ),
    )
    path = store_graph_cache(cache_dir=tmp_path, key="abc123", graphs=graphs)
    assert path == graph_cache_path(tmp_path, "abc123")

    loaded = load_graph_cache(cache_dir=tmp_path, key="abc123")
    assert loaded == graphs


def test_load_returns_none_for_missing_or_corrupt_cache(tmp_path: Path) -> None:
    assert load_graph_cache(cache_dir=tmp_path, key="missing") is None
    graph_cache_path(tmp_path, "corrupt").write_text("not json", encoding="utf-8")
    assert load_graph_cache(cache_dir=tmp_path, key="corrupt") is None
    graph_cache_path(tmp_path, "partial").write_text(
        json.dumps({"format": 1, "chunk_graphs": []}), encoding="utf-8"
    )
    assert load_graph_cache(cache_dir=tmp_path, key="partial") is None


def test_graph_from_dict_round_trips() -> None:
    from alex.lib.claim_graph import graph_to_dict

    graph = sample_graph()
    assert graph_from_dict(graph_to_dict(graph)) == graph
