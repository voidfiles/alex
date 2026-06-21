import json
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from alex.lib.converters.to_markdown import MarkdownOutput, ToMarkdownConfig
from alex.lib.summarize import SummarySettings, build_chunk_graph_bundles
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
