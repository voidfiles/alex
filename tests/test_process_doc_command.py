from pathlib import Path

from click.testing import CliRunner

from alex.commands.process_doc import build_process_doc_command
from alex.lib.process_doc_assets import ProcessDocAssetConfig, ProcessDocAssetOutput


def test_process_doc_command_processes_asset_path(tmp_path: Path) -> None:
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    captured_configs: list[ProcessDocAssetConfig] = []

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        captured_configs.append(config)
        chunks_dir = config.asset_path / "chunks"
        chunks_dir.mkdir()
        chunk = chunks_dir / "001_intro.md"
        chunk.write_text("chunk", encoding="utf-8")
        metadata = config.asset_path / "metadata.json"
        metadata.write_text("{}", encoding="utf-8")
        canonical_name = config.asset_path / "canonical_name.txt"
        canonical_name.write_text("asset\n", encoding="utf-8")
        chapter_level = config.asset_path / "chapter_level.txt"
        chapter_level.write_text("1\n", encoding="utf-8")
        chunk_summary = config.asset_path / "chunk_summary.md"
        chunk_summary.write_text("chunk summary", encoding="utf-8")
        summary = config.asset_path / "summary.md"
        summary.write_text("summary", encoding="utf-8")
        original = config.asset_path / "asset.epub"
        markdown = config.asset_path / "asset.md"
        headers = config.asset_path / "headers.md"
        return ProcessDocAssetOutput(
            asset_dir=config.asset_path,
            original_file=original,
            markdown_path=markdown,
            headers_path=headers,
            chapter_level_path=chapter_level,
            metadata_path=metadata,
            canonical_name_path=canonical_name,
            chunks_dir=chunks_dir,
            chunk_paths=(chunk,),
            chunk_summary_path=chunk_summary,
            summary_path=summary,
        )

    result = CliRunner().invoke(
        build_process_doc_command(fake_processor),
        [str(asset_dir)],
    )

    assert result.exit_code == 0
    assert result.output == (
        f"Processed {asset_dir}\n"
        "Chunks: 1\n"
        "Chunk summary: chunk_summary.md\n"
        "Summary: summary.md\n"
    )
    assert captured_configs == [ProcessDocAssetConfig(asset_path=asset_dir)]


def test_process_doc_help_only_accepts_asset_path() -> None:
    result = CliRunner().invoke(build_process_doc_command(), ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "ASSET_PATH" in result.output
    assert "--asset-root" not in result.output
    assert "--force" not in result.output
    assert "--max-lines" not in result.output
