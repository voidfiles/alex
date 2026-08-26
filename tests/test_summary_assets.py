import json
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from alex.lib.converters.to_markdown import MarkdownOutput, ToMarkdownConfig
from alex.lib.document_sources import DocumentMetadata
from alex.lib.summarize import (
    SummarySettings,
    build_chunk_graph_bundles,
    summarize_doc_asset,
)
from alex.lib.summary_assets import (
    SummaryAssetConfig,
    SummaryAssetExistsError,
    UnsupportedSummarySourceError,
    process_summary_asset,
)
from helpers import BagOfWordsEmbedder, RecordingCompleter


@dataclass
class SlowGraphCompleter:
    active: int = 0
    max_active: int = 0
    calls: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(prompt)
        try:
            if "Alpha" in prompt:
                time.sleep(0.05)
                label = "Alpha"
            elif "Beta" in prompt:
                time.sleep(0.01)
                label = "Beta"
            else:
                time.sleep(0.01)
                label = "Gamma"
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": f"{label} claim.",
                            "evidence": f"{label} evidence.",
                        }
                    ],
                    "concepts": [],
                    "key_passages": [],
                }
            )
        finally:
            with self.lock:
                self.active -= 1


class FailingFinalSummaryCompleter(RecordingCompleter):
    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        response = super().complete(prompt=prompt, model=model, max_tokens=max_tokens)
        if "<section_summaries>" in prompt:
            raise RuntimeError("final summary failed\nmodel returned \x00 control text")
        return response


class SensitiveFailingFinalSummaryCompleter(RecordingCompleter):
    def __init__(self, *, failure_message: str) -> None:
        super().__init__(
            chunk_responses=["Chunk body should stay out."],
            final_response="Generated summary body should stay out.",
        )
        self.failure_message = failure_message

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        response = super().complete(prompt=prompt, model=model, max_tokens=max_tokens)
        if "<section_summaries>" in prompt:
            raise RuntimeError(self.failure_message)
        return response


class RunningManifestInspectingCompleter(RecordingCompleter):
    def __init__(
        self,
        *,
        graph_artifact_dir: Path,
        fail_on_merge: bool = False,
        chunk_responses: list[str] | None = None,
        final_response: str = "Final synthesis.",
    ) -> None:
        super().__init__(
            chunk_responses=chunk_responses,
            final_response=final_response,
        )
        self.graph_artifact_dir = graph_artifact_dir
        self.fail_on_merge = fail_on_merge
        self.saw_running_manifest = False
        self.running_status: str | None = None
        self.running_last_completed_stage: str | None = None
        self.running_artifacts: list[str] = []
        self.files_present_at_running: list[str] = []
        self.running_manifest_inode: int | None = None

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if "merging two independently generated summaries" in prompt:
            manifest_path = self.graph_artifact_dir / "manifest.json"
            assert manifest_path.is_file()
            self.running_manifest_inode = manifest_path.stat().st_ino
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.saw_running_manifest = True
            self.running_status = manifest["status"]
            self.running_last_completed_stage = manifest["last_completed_stage"]
            self.running_artifacts = list(manifest["artifacts"])
            self.files_present_at_running = [
                name
                for name in (
                    "standard_summary.md",
                    "graph_summary.md",
                    "merged_summary.md",
                    "faithfulness_filtered_summary.md",
                )
                if (self.graph_artifact_dir / name).exists()
            ]
            if self.fail_on_merge:
                raise RuntimeError(
                    "graph merge failed\nmodel returned \x00 control text"
                )
        return super().complete(prompt=prompt, model=model, max_tokens=max_tokens)


def test_process_markdown_summary_runs_the_full_pipeline(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    completer = RecordingCompleter(
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1),
        ),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )

    asset_dir = tmp_path / "summaries" / "deep-work"
    assert result.asset_dir == asset_dir
    assert result.source_copy == asset_dir / "deep-work.md"
    assert result.full_markdown == asset_dir / "deep-work.md"
    assert result.metadata_path == asset_dir / "metadata.json"
    assert result.headers_path == asset_dir / "headers.md"
    assert result.chunks_dir == asset_dir / "chunks"
    assert tuple(path.name for path in result.chunk_paths) == ("001_deep_work.md",)
    assert result.chunk_summary_path == asset_dir / "chunk_summary.md"
    assert result.summary_path == asset_dir / "summary.md"
    assert result.graph_artifact_dir == asset_dir / "summary_graph"
    assert result.graph_artifact_dir.is_dir()

    assert result.full_markdown.read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )
    headers = result.headers_path.read_text(encoding="utf-8")
    assert "- Deep Work (H1, line 1, 5 lines)" in headers

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata == {
        "title": "Deep Work",
        "authors": ["Cal Newport"],
        "source_format": "markdown",
        "source_file": "deep-work.md",
        "full_markdown": "deep-work.md",
        "headers_file": "headers.md",
        "chapter_level": 1,
        "chunks_dir": "chunks",
    }

    assert result.summary_path is not None
    summary = result.summary_path.read_text(encoding="utf-8")
    assert "Faithful Deep work synthesis." in summary
    assert "[View evidence ledger](summary_evidence.md)" in summary
    assert "1. [001_deep_work.md](chunks/001_deep_work.md)" in summary
    assert (asset_dir / "summary_evidence.md").is_file()
    assert "# Evidence Ledger: deep-work.md" in (
        asset_dir / "summary_evidence.md"
    ).read_text(encoding="utf-8")
    assert (result.graph_artifact_dir / "standard_summary.md").read_text(
        encoding="utf-8"
    ) == "Deep work synthesis."
    assert (result.graph_artifact_dir / "graph_summary.md").read_text(
        encoding="utf-8"
    ) == "Graph-grounded summary."
    assert (result.graph_artifact_dir / "merged_summary.md").read_text(
        encoding="utf-8"
    ) == "Merged summary from Deep work synthesis."
    assert (result.graph_artifact_dir / "repaired_summary.md").read_text(
        encoding="utf-8"
    ) == "Repaired Deep work synthesis."
    assert (result.graph_artifact_dir / "faithfulness_filtered_summary.md").read_text(
        encoding="utf-8"
    ) == "Faithful Deep work synthesis."
    assert (result.graph_artifact_dir / "graph.json").is_file()
    assert (result.graph_artifact_dir / "selected_subgraph.json").is_file()
    assert (result.graph_artifact_dir / "selected_subgraph.md").is_file()
    assert (result.graph_artifact_dir / "document_graph.json").is_file()
    assert (result.graph_artifact_dir / "selected_document_subgraph.json").is_file()
    assert (result.graph_artifact_dir / "selected_document_subgraph.md").is_file()
    assert (result.graph_artifact_dir / "chunks" / "001_deep_work").is_dir()
    assert (
        result.graph_artifact_dir / "chunks" / "001_deep_work" / "graph.json"
    ).is_file()
    assert (
        result.graph_artifact_dir
        / "chunks"
        / "001_deep_work"
        / "selected_subgraph.json"
    ).is_file()
    assert (
        result.graph_artifact_dir / "chunks" / "001_deep_work" / "selected_subgraph.md"
    ).is_file()
    assert (result.graph_artifact_dir / "pre_filter_claim_verdicts.json").is_file()
    assert (result.graph_artifact_dir / "source_blocks.json").is_file()
    assert (result.graph_artifact_dir / "evidence_records.json").is_file()
    assert (result.graph_artifact_dir / "summary_plan.json").is_file()
    assert (result.graph_artifact_dir / "summary_claims.json").is_file()
    assert (result.graph_artifact_dir / "claim_verification.json").is_file()
    assert (result.graph_artifact_dir / "revision_passes.json").is_file()
    manifest_path = result.graph_artifact_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["status"] == "complete"
    assert manifest["source_path"] == "deep-work.md"
    assert manifest["output_path"] == "summary.md"
    assert manifest["settings"] == {
        "graph_enhanced": True,
        "chunk_graph_enhanced": True,
        "coverage_repair": True,
        "graph_artifacts": True,
        "evidence_ledger": True,
        "force": False,
    }
    assert manifest["environment_caps"] == {
        "ALEX_CHUNK_GRAPH_MAX_CLAIMS": 12,
        "ALEX_GRAPH_MAX_CLAIMS": 48,
        "ALEX_SOURCE_CLAIMS_PER_SECTION": 8,
    }
    assert manifest["chunks"] == {
        "count": 1,
        "artifacts": ["chunks/001_deep_work.md"],
    }
    assert manifest["graph"]["document_claim_count"] == 2
    assert manifest["graph"]["document_edge_count"] >= 1
    assert manifest["graph"]["selected_claim_count"] == 2
    assert manifest["graph"]["selected_edge_count"] >= 1
    assert manifest["prompt_versions"]["chunk_summary"].startswith("v")
    assert manifest["prompt_versions"]["source_claim_extraction"].startswith("v")
    assert manifest["prompt_versions"]["merged_summary"].startswith("v")
    assert manifest["prompt_versions"]["claim_verification"].startswith("v")
    assert manifest["stages"]["standard_summary"] == [
        "summary_graph/standard_summary.md"
    ]
    assert manifest["stages"]["coverage_repair"] == [
        "summary_graph/repaired_summary.md"
    ]
    assert "summary_graph/faithfulness_filtered_summary.md" in manifest["artifacts"]
    manifest_text = json.dumps(manifest)
    assert "Deep work synthesis." not in manifest_text
    assert "Faithful Deep work synthesis." not in manifest_text
    source_blocks = json.loads(
        (result.graph_artifact_dir / "source_blocks.json").read_text(encoding="utf-8")
    )
    assert source_blocks[0]["id"] == "doc:full"
    assert source_blocks[1]["id"] == "chunk:001"
    evidence_records = json.loads(
        (result.graph_artifact_dir / "evidence_records.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence_records
    assert {"id", "source_block_id", "validated_exact_span"} <= set(evidence_records[0])
    summary_claims = json.loads(
        (result.graph_artifact_dir / "summary_claims.json").read_text(encoding="utf-8")
    )
    assert summary_claims[0]["status"] == "SUPPORTED"
    selected_graph = json.loads(
        (result.graph_artifact_dir / "selected_subgraph.json").read_text(
            encoding="utf-8"
        )
    )
    selected_node_types = {node["type"] for node in selected_graph["nodes"]}
    assert "concept" in selected_node_types
    assert "key_passage" in selected_node_types

    chunk_calls = completer.chunk_calls()
    assert len(chunk_calls) == 1
    assert "Title: Deep Work" in chunk_calls[0].prompt
    assert "Body text." in chunk_calls[0].prompt
    assert "<selected_chunk_graph>" in chunk_calls[0].prompt
    assert "The document preserves important claims." in chunk_calls[0].prompt
    source_claim_calls = [
        call for call in completer.calls if "source-grounded items" in call.prompt
    ]
    assert source_claim_calls
    assert completer.calls.index(source_claim_calls[0]) < completer.calls.index(
        chunk_calls[0]
    )
    assert len(completer.final_calls()) == 1

    # Repair runs between the merge and the faithfulness filter, so anything it
    # re-adds for coverage is still verified against the source and filtered.
    prompts = [call.prompt for call in completer.calls]
    merge_index = next(
        index
        for index, prompt in enumerate(prompts)
        if "merging two independently generated summaries" in prompt
    )
    repair_index = next(
        index
        for index, prompt in enumerate(prompts)
        if "revising a merged summary" in prompt
    )
    filter_index = next(
        index
        for index, prompt in enumerate(prompts)
        if "filtering a merged summary for source faithfulness" in prompt
    )
    assert merge_index < repair_index < filter_index


def test_process_markdown_summary_skips_chunk_graph_when_graph_disabled(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    completer = RecordingCompleter(
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1, graph_enhanced=False),
        ),
        completer=completer,
    )

    assert result.graph_artifact_dir is None
    assert not any("source-grounded items" in call.prompt for call in completer.calls)
    assert "<selected_chunk_graph>" not in completer.chunk_calls()[0].prompt


def test_process_markdown_summary_skips_repair_when_coverage_repair_disabled(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    completer = RecordingCompleter(
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1, coverage_repair=False),
        ),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )

    assert result.graph_artifact_dir is not None
    assert not (result.graph_artifact_dir / "repaired_summary.md").exists()
    assert not any(
        "revising a merged summary" in call.prompt for call in completer.calls
    )
    # The rest of the graph path still runs and the filter still has the last word.
    assert result.summary_path is not None
    assert "Faithful Deep work synthesis." in result.summary_path.read_text(
        encoding="utf-8"
    )


def test_process_markdown_summary_writes_failed_manifest_when_final_summary_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    completer = FailingFinalSummaryCompleter(
        chunk_responses=["Chunk body should stay out."],
        final_response="Generated summary body should stay out.",
    )

    with pytest.raises(RuntimeError, match="final summary failed"):
        process_summary_asset(
            SummaryAssetConfig(
                source=source,
                output_path=tmp_path / "summaries",
                summary=SummarySettings(max_workers=1),
            ),
            completer=completer,
            embedder=BagOfWordsEmbedder(),
        )

    asset_dir = tmp_path / "summaries" / "deep-work"
    manifest_path = asset_dir / "summary_graph" / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["last_completed_stage"] == "chunk_summary"
    assert manifest["error"] == {
        "type": "RuntimeError",
        "message": "final summary failed model returned control text",
    }
    assert manifest["source_path"] == "deep-work.md"
    assert manifest["output_path"] == "summary.md"
    assert manifest["chunks"] == {
        "count": 1,
        "artifacts": ["chunks/001_deep_work.md"],
    }
    assert manifest["graph"]["chunk_graph_count"] == 1
    assert manifest["graph"]["document_claim_count"] == 0
    assert manifest["artifacts"] == [
        "chunk_summary.md",
        "summary_graph/manifest.json",
    ]
    assert not (asset_dir / "summary.md").exists()
    manifest_text = json.dumps(manifest)
    assert "Generated summary body should stay out." not in manifest_text
    assert "Chunk body should stay out." not in manifest_text
    assert "\n" not in manifest["error"]["message"]
    assert "\x00" not in manifest["error"]["message"]


def test_process_markdown_summary_redacts_sensitive_failed_manifest_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    sensitive_path = tmp_path / "secret" / "file.txt"
    opt_path = "/opt/vendor/private.cfg"
    etc_path = "/etc/alex/private.env"
    windows_path = r"C:\Users\alex\secret\file.txt"
    unix_path_with_spaces = "/tmp/secret dir/file name.txt"
    windows_path_with_spaces = r"C:\Users\Alex\Secret Dir\file name.txt"
    openai_key = "sk-proj-task15OpenAISecretToken1234567890"
    anthropic_key = "sk-ant-task15AnthropicSecretToken1234567890"
    gemini_key = "AIza" + "Task15GeminiSecretToken1234567890"
    provider_token = "task15_" + ("ProviderSecretToken" * 3)
    bearer_token = "task15BearerSecretToken.abc123"
    completer = SensitiveFailingFinalSummaryCompleter(
        failure_message=(
            "provider call failed for "
            f"{sensitive_path} {opt_path} {etc_path} {windows_path} "
            f"{unix_path_with_spaces} {windows_path_with_spaces}\n"
            f"openai={openai_key} anthropic={anthropic_key} "
            f"gemini={gemini_key} provider_token={provider_token} "
            f"Authorization: Bearer {bearer_token}\x00 retryable"
        )
    )

    with pytest.raises(RuntimeError, match="provider call failed"):
        process_summary_asset(
            SummaryAssetConfig(
                source=source,
                output_path=tmp_path / "summaries",
                summary=SummarySettings(max_workers=1),
            ),
            completer=completer,
            embedder=BagOfWordsEmbedder(),
        )

    manifest_path = (
        tmp_path / "summaries" / "deep-work" / "summary_graph" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    error_message = manifest["error"]["message"]
    assert manifest["error"]["type"] == "RuntimeError"
    assert "provider call failed" in error_message
    assert "retryable" in error_message
    assert "[REDACTED_OPENAI_KEY]" in error_message
    assert "[REDACTED_ANTHROPIC_KEY]" in error_message
    assert "[REDACTED_GEMINI_KEY]" in error_message
    assert "[REDACTED_PROVIDER_TOKEN]" in error_message
    assert "[REDACTED_BEARER_TOKEN]" in error_message
    assert "[REDACTED_LOCAL_PATH]" in error_message
    assert openai_key not in error_message
    assert anthropic_key not in error_message
    assert gemini_key not in error_message
    assert provider_token not in error_message
    assert bearer_token not in error_message
    assert sensitive_path.as_posix() not in error_message
    assert opt_path not in error_message
    assert etc_path not in error_message
    assert windows_path not in error_message
    assert unix_path_with_spaces not in error_message
    assert windows_path_with_spaces not in error_message
    assert "secret dir" not in error_message
    assert "Secret Dir" not in error_message
    assert "file name.txt" not in error_message
    assert "\n" not in error_message
    assert "\x00" not in error_message


def test_process_markdown_summary_writes_running_manifest_before_graph_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    graph_artifact_dir = tmp_path / "summaries" / "deep-work" / "summary_graph"
    completer = RunningManifestInspectingCompleter(
        graph_artifact_dir=graph_artifact_dir,
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )

    process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1),
        ),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )

    assert completer.saw_running_manifest
    assert completer.running_status == "running"
    assert completer.running_last_completed_stage == "chunk_summary"
    assert completer.running_artifacts == [
        "chunk_summary.md",
        "summary_graph/manifest.json",
    ]
    assert completer.files_present_at_running == []

    final_manifest = json.loads(
        (graph_artifact_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert final_manifest["status"] == "complete"
    assert (graph_artifact_dir / "manifest.json").stat().st_ino == (
        completer.running_manifest_inode
    )


def test_process_markdown_summary_writes_failed_manifest_after_running_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    graph_artifact_dir = tmp_path / "summaries" / "deep-work" / "summary_graph"
    completer = RunningManifestInspectingCompleter(
        graph_artifact_dir=graph_artifact_dir,
        fail_on_merge=True,
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )

    with pytest.raises(RuntimeError, match="graph merge failed"):
        process_summary_asset(
            SummaryAssetConfig(
                source=source,
                output_path=tmp_path / "summaries",
                summary=SummarySettings(max_workers=1),
            ),
            completer=completer,
            embedder=BagOfWordsEmbedder(),
        )

    assert completer.saw_running_manifest
    assert completer.running_status == "running"
    manifest = json.loads(
        (graph_artifact_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert (graph_artifact_dir / "manifest.json").stat().st_ino == (
        completer.running_manifest_inode
    )
    assert manifest["last_completed_stage"] == "summary_drafts"
    assert manifest["error"] == {
        "type": "RuntimeError",
        "message": "graph merge failed model returned control text",
    }
    assert manifest["artifacts"] == [
        "chunk_summary.md",
        "summary_graph/manifest.json",
    ]
    assert "\n" not in manifest["error"]["message"]
    assert "\x00" not in manifest["error"]["message"]


def test_summarize_doc_asset_reuses_existing_summary_without_force(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "asset"
    chunks_dir = asset_dir / "chunks"
    graph_dir = asset_dir / "summary_graph"
    chunks_dir.mkdir(parents=True)
    graph_dir.mkdir()
    markdown_path = asset_dir / "asset.md"
    markdown_path.write_text("# Asset\n\nImportant claims.\n", encoding="utf-8")
    headers_path = asset_dir / "headers.md"
    headers_path.write_text("- Asset (H1, line 1, 3 lines)\n", encoding="utf-8")
    chunk_path = chunks_dir / "001_asset.md"
    chunk_path.write_text("# Asset\n\nImportant claims.\n", encoding="utf-8")
    summary_path = asset_dir / "summary.md"
    summary_path.write_text("Existing summary.\n", encoding="utf-8")
    chunk_summary_path = asset_dir / "chunk_summary.md"
    chunk_summary_path.write_text("Existing chunk summary.\n", encoding="utf-8")
    stale_graph_marker = graph_dir / "stale.txt"
    stale_graph_marker.write_text("stale graph artifact\n", encoding="utf-8")
    completer = RecordingCompleter(final_response="Fresh synthesis.")

    result = summarize_doc_asset(
        settings=SummarySettings(max_workers=1),
        asset_dir=asset_dir,
        metadata=DocumentMetadata(title="Asset"),
        markdown_path=markdown_path,
        headers_path=headers_path,
        chunk_paths=(chunk_path,),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )

    assert result.summary_path == summary_path
    assert result.chunk_summary_path == chunk_summary_path
    assert result.graph_artifact_dir == graph_dir
    assert summary_path.read_text(encoding="utf-8") == "Existing summary.\n"
    assert stale_graph_marker.read_text(encoding="utf-8") == "stale graph artifact\n"
    assert completer.calls == []


def test_process_markdown_summary_reuse_does_not_create_missing_manifest(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "asset"
    chunks_dir = asset_dir / "chunks"
    graph_dir = asset_dir / "summary_graph"
    chunks_dir.mkdir(parents=True)
    graph_dir.mkdir()
    markdown_path = asset_dir / "asset.md"
    markdown_path.write_text("# Asset\n\nImportant claims.\n", encoding="utf-8")
    headers_path = asset_dir / "headers.md"
    headers_path.write_text("- Asset (H1, line 1, 3 lines)\n", encoding="utf-8")
    chunk_path = chunks_dir / "001_asset.md"
    chunk_path.write_text("# Asset\n\nImportant claims.\n", encoding="utf-8")
    summary_path = asset_dir / "summary.md"
    summary_path.write_text("Existing summary.\n", encoding="utf-8")
    completer = RecordingCompleter(final_response="Fresh synthesis.")

    result = summarize_doc_asset(
        settings=SummarySettings(max_workers=1),
        asset_dir=asset_dir,
        metadata=DocumentMetadata(title="Asset"),
        markdown_path=markdown_path,
        headers_path=headers_path,
        chunk_paths=(chunk_path,),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )

    assert result.summary_path == summary_path
    assert result.graph_artifact_dir == graph_dir
    assert not (graph_dir / "manifest.json").exists()
    assert completer.calls == []


def test_summarize_doc_asset_force_rebuilds_existing_summary(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "asset"
    chunks_dir = asset_dir / "chunks"
    graph_dir = asset_dir / "summary_graph"
    chunks_dir.mkdir(parents=True)
    graph_dir.mkdir()
    markdown_path = asset_dir / "asset.md"
    markdown_path.write_text("# Asset\n\nImportant claims.\n", encoding="utf-8")
    headers_path = asset_dir / "headers.md"
    headers_path.write_text("- Asset (H1, line 1, 3 lines)\n", encoding="utf-8")
    chunk_path = chunks_dir / "001_asset.md"
    chunk_path.write_text("# Asset\n\nImportant claims.\n", encoding="utf-8")
    summary_path = asset_dir / "summary.md"
    summary_path.write_text("Existing summary.\n", encoding="utf-8")
    stale_graph_marker = graph_dir / "stale.txt"
    stale_graph_marker.write_text("stale graph artifact\n", encoding="utf-8")
    completer = RecordingCompleter(
        chunk_responses=["Fresh chunk summary."],
        final_response="Fresh synthesis.",
    )

    result = summarize_doc_asset(
        settings=SummarySettings(max_workers=1, force=True),
        asset_dir=asset_dir,
        metadata=DocumentMetadata(title="Asset"),
        markdown_path=markdown_path,
        headers_path=headers_path,
        chunk_paths=(chunk_path,),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )

    assert result.summary_path == summary_path
    assert result.chunk_summary_path == asset_dir / "chunk_summary.md"
    assert result.graph_artifact_dir == graph_dir
    assert "Faithful Fresh synthesis." in summary_path.read_text(encoding="utf-8")
    assert not stale_graph_marker.exists()
    assert len(completer.chunk_calls()) == 1
    assert len(completer.final_calls()) == 1


def test_chunk_graph_bundles_are_bounded_and_ordered(tmp_path: Path) -> None:
    chunk_paths = tuple(
        tmp_path / name for name in ("001_alpha.md", "002_beta.md", "003_gamma.md")
    )
    for path, label in zip(chunk_paths, ("Alpha", "Beta", "Gamma"), strict=True):
        path.write_text(f"# {label}\n\n{label} evidence.\n", encoding="utf-8")
    completer = SlowGraphCompleter()

    bundles = build_chunk_graph_bundles(
        settings=SummarySettings(max_workers=2),
        doc_name="ordered.md",
        chunk_paths=chunk_paths,
        completer=completer,
        embedder=BagOfWordsEmbedder(),
    )

    assert tuple(bundle.chunk_path for bundle in bundles) == chunk_paths
    assert completer.max_active <= 2
    assert [bundle.graph.doc_name for bundle in bundles] == [
        "001_alpha.md",
        "002_beta.md",
        "003_gamma.md",
    ]


def test_parallel_chunk_graph_bundles_match_serial_output(tmp_path: Path) -> None:
    chunk_paths = tuple(tmp_path / name for name in ("001_alpha.md", "002_beta.md"))
    for path, label in zip(chunk_paths, ("Alpha", "Beta"), strict=True):
        path.write_text(f"# {label}\n\n{label} evidence.\n", encoding="utf-8")

    serial = build_chunk_graph_bundles(
        settings=SummarySettings(max_workers=1),
        doc_name="equivalent.md",
        chunk_paths=chunk_paths,
        completer=SlowGraphCompleter(),
        embedder=BagOfWordsEmbedder(),
    )
    parallel = build_chunk_graph_bundles(
        settings=SummarySettings(max_workers=2),
        doc_name="equivalent.md",
        chunk_paths=chunk_paths,
        completer=SlowGraphCompleter(),
        embedder=BagOfWordsEmbedder(),
    )

    assert tuple(bundle.selected_markdown for bundle in parallel) == tuple(
        bundle.selected_markdown for bundle in serial
    )
    assert tuple(
        tuple(node.id for node in bundle.graph.nodes) for bundle in parallel
    ) == tuple(tuple(node.id for node in bundle.graph.nodes) for bundle in serial)


def test_chunk_graph_bundle_exceptions_propagate(tmp_path: Path) -> None:
    chunk_path = tmp_path / "001_alpha.md"
    chunk_path.write_text("# Alpha\n\nAlpha evidence.\n", encoding="utf-8")

    class FailingCompleter:
        def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
            raise RuntimeError("extractor failed")

    with pytest.raises(RuntimeError, match="extractor failed"):
        build_chunk_graph_bundles(
            settings=SummarySettings(max_workers=2),
            doc_name="failing.md",
            chunk_paths=(chunk_path,),
            completer=FailingCompleter(),
            embedder=BagOfWordsEmbedder(),
        )


def test_process_pdf_summary_converts_inside_stem_named_workspace(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Paper Draft.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    captured_configs: list[ToMarkdownConfig] = []

    def fake_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        captured_configs.append(config)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.image_path.mkdir(parents=True, exist_ok=True)
        (config.image_path / "page-1.png").write_bytes(b"image")
        config.asset_path.write_text(
            "# Paper Draft\n\nExtracted text.\n",
            encoding="utf-8",
        )
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1),
        ),
        pdf_markdowner=fake_markdowner,
        completer=RecordingCompleter(),
        embedder=BagOfWordsEmbedder(),
    )

    asset_dir = tmp_path / "summaries" / "Paper Draft"
    assert captured_configs == [
        ToMarkdownConfig(source=source, output_dir=asset_dir, name="Paper Draft")
    ]
    assert result.asset_dir == asset_dir
    assert result.source_copy == asset_dir / "Paper Draft.pdf"
    assert result.full_markdown == asset_dir / "Paper Draft.md"
    assert (asset_dir / "images" / "page-1.png").read_bytes() == b"image"
    assert tuple(path.name for path in result.chunk_paths) == ("001_paper_draft.md",)
    assert result.summary_path == asset_dir / "summary.md"

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_format"] == "pdf"
    assert metadata["source_file"] == "Paper Draft.pdf"
    assert metadata["chapter_level"] == 1


def test_process_epub_summary_extracts_markdown_and_preserves_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.epub"
    write_minimal_epub(source)

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1),
        ),
        completer=RecordingCompleter(),
        embedder=BagOfWordsEmbedder(),
    )

    asset_dir = tmp_path / "summaries" / "sample"
    assert result.source_copy == asset_dir / "sample.epub"
    assert result.full_markdown == asset_dir / "sample.md"
    assert result.source_copy.read_bytes() == source.read_bytes()
    assert result.full_markdown.read_text(encoding="utf-8") == (
        "# Example Book\n\n"
        "By Jane Writer\n\n"
        "# Opening\n\n"
        "The first paragraph.\n\n"
        "The second paragraph.\n"
    )
    assert tuple(path.name for path in result.chunk_paths) == (
        "001_example_book.md",
        "002_opening.md",
    )
    assert result.summary_path == asset_dir / "summary.md"


def test_process_summary_refuses_existing_workspace_without_force(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n", encoding="utf-8")
    existing_asset = tmp_path / "summaries" / "notes"
    existing_asset.mkdir(parents=True)

    with pytest.raises(SummaryAssetExistsError, match="already exists"):
        process_summary_asset(
            SummaryAssetConfig(source=source, output_path=tmp_path / "summaries"),
        )


def write_minimal_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Example Book</dc:title>
    <dc:creator>Jane Writer</dc:creator>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>
""",
        )
        archive.writestr(
            "OEBPS/chapter.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>Opening</h1>
    <p>The first paragraph.</p>
    <p>The second paragraph.</p>
  </body>
</html>
""",
        )


def test_process_summary_force_replaces_existing_workspace(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n", encoding="utf-8")
    existing_asset = tmp_path / "summaries" / "notes"
    existing_asset.mkdir(parents=True)
    stale_file = existing_asset / "stale.md"
    stale_file.write_text("stale", encoding="utf-8")

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            force=True,
            summary=SummarySettings(max_workers=1),
        ),
        completer=RecordingCompleter(),
        embedder=BagOfWordsEmbedder(),
    )

    assert result.asset_dir == existing_asset
    assert not stale_file.exists()
    assert result.metadata_path.exists()
    assert result.summary_path is not None
    assert result.summary_path.exists()


def test_process_summary_rejects_unsupported_sources(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    source.write_text("name,value\n", encoding="utf-8")

    with pytest.raises(UnsupportedSummarySourceError, match="Supported file types"):
        process_summary_asset(
            SummaryAssetConfig(source=source, output_path=tmp_path / "summaries"),
        )
