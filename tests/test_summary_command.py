from pathlib import Path

from click.testing import CliRunner

from alex.commands.summary import build_summary_command
from alex.lib.converters.to_markdown import MarkdownOutput, ToMarkdownConfig
from alex.lib.summary_assets import SummaryAssetConfig, SummaryAssetOutput


def test_summary_command_writes_stem_named_workspace(tmp_path: Path) -> None:
    source = tmp_path / "paper.md"
    source.write_text("# Paper\n", encoding="utf-8")
    captured_configs: list[SummaryAssetConfig] = []

    def fake_processor(
        config: SummaryAssetConfig,
        *,
        pdf_markdowner: object,
    ) -> SummaryAssetOutput:
        captured_configs.append(config)
        asset_dir = config.output_path / config.source.stem
        asset_dir.mkdir(parents=True)
        full_markdown = asset_dir / "paper.md"
        source_copy = full_markdown
        metadata = asset_dir / "metadata.json"
        for path in (full_markdown, metadata):
            path.write_text("created", encoding="utf-8")
        return SummaryAssetOutput(
            asset_dir=asset_dir,
            source_copy=source_copy,
            full_markdown=full_markdown,
            metadata_path=metadata,
            headers_path=asset_dir / "headers.md",
            chunks_dir=asset_dir / "chunks",
            chunk_paths=(asset_dir / "chunks" / "001_paper.md",),
            chunk_summary_path=asset_dir / "chunk_summary.md",
            summary_path=asset_dir / "summary.md",
        )

    result = CliRunner().invoke(
        build_summary_command(fake_processor),
        [
            str(source),
            str(tmp_path / "summaries"),
            "--force",
        ],
    )

    assert result.exit_code == 0
    asset_dir = tmp_path / "summaries" / "paper"
    assert result.output == (
        f"Wrote {asset_dir}\nChunks: 1\nSummary: {asset_dir / 'summary.md'}\n"
    )
    assert captured_configs == [
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            force=True,
        )
    ]


def test_summary_command_miner_option_selects_miner_pdf_markdowner(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    selected_markdowners: list[object] = []

    def default_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        return MarkdownOutput(config=config, asset=config.asset_path)

    def miner_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        return MarkdownOutput(config=config, asset=config.asset_path)

    def fake_processor(
        config: SummaryAssetConfig,
        *,
        pdf_markdowner: object,
    ) -> SummaryAssetOutput:
        selected_markdowners.append(pdf_markdowner)
        asset_dir = config.output_path / config.source.stem
        asset_dir.mkdir(parents=True)
        full_markdown = asset_dir / "paper.md"
        source_copy = asset_dir / "paper.pdf"
        metadata = asset_dir / "metadata.json"
        for path in (full_markdown, source_copy, metadata):
            path.write_text("created", encoding="utf-8")
        return SummaryAssetOutput(
            asset_dir=asset_dir,
            source_copy=source_copy,
            full_markdown=full_markdown,
            metadata_path=metadata,
            headers_path=asset_dir / "headers.md",
            chunks_dir=asset_dir / "chunks",
            chunk_paths=(),
            chunk_summary_path=None,
            summary_path=None,
        )

    result = CliRunner().invoke(
        build_summary_command(
            processor=fake_processor,
            default_pdf_markdowner=default_markdowner,
            miner_pdf_markdowner=miner_markdowner,
        ),
        [str(source), str(tmp_path / "summaries"), "--miner"],
    )

    assert result.exit_code == 0
    assert selected_markdowners == [miner_markdowner]


def test_summary_command_rejects_multiple_pdf_converter_options(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    result = CliRunner().invoke(
        build_summary_command(),
        [str(source), str(tmp_path / "summaries"), "--miner", "--datalab"],
    )

    assert result.exit_code == 2
    assert "Choose only one converter option" in result.output


def test_summary_help_describes_input_output_and_force() -> None:
    result = CliRunner().invoke(build_summary_command(), ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "INPUT" in result.output
    assert "OUTPUT_PATH" in result.output
    assert "--force" in result.output
    assert "--miner" in result.output
    assert "--datalab" in result.output
