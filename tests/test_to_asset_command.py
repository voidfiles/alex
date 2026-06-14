import hashlib
import json
import zipfile
from pathlib import Path

from click.testing import CliRunner

from alex.commands.to_asset import build_to_asset_command
from alex.lib.asset_folders import AssetName, AssetNameInput, AssetNamer
from alex.lib.converters.to_markdown import (
    DatalabApiError,
    MarkdownOutput,
    ToMarkdownConfig,
)


def fixed_asset_namer(
    canonical_name: str,
    *,
    title: str = "Canonical Title",
    authors: tuple[str, ...] = ("Canonical Author",),
    captured_inputs: list[AssetNameInput] | None = None,
) -> AssetNamer:
    def namer(asset_input: AssetNameInput) -> AssetName:
        if captured_inputs is not None:
            captured_inputs.append(asset_input)
        return AssetName(
            title=title,
            authors=authors,
            canonical_name=canonical_name,
        )

    return namer


def test_to_asset_moves_pdf_original_markdown_and_headers_to_asset_folder(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    asset_root = tmp_path / "vault-assets"
    captured_configs: list[ToMarkdownConfig] = []
    captured_name_inputs: list[AssetNameInput] = []

    def fake_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        captured_configs.append(config)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text(
            "# Paper\n\n## Intro\n\nBody.\n",
            encoding="utf-8",
        )
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = CliRunner().invoke(
        build_to_asset_command(
            fake_markdowner,
            asset_namer=fixed_asset_namer(
                "deep_work_cal_newport",
                title="Deep Work",
                authors=("Cal Newport",),
                captured_inputs=captured_name_inputs,
            ),
        ),
        [str(source), "--asset-root", str(asset_root)],
    )

    asset_dir = asset_root / "deep_work_cal_newport"
    assert result.exit_code == 0
    assert result.output == f"Wrote {asset_dir}\n"
    assert not source.exists()
    assert (asset_dir / "deep_work_cal_newport.pdf").read_bytes() == b"%PDF-1.7\n"
    assert (asset_dir / "deep_work_cal_newport.md").read_text(encoding="utf-8") == (
        "# Paper\n\n## Intro\n\nBody.\n"
    )
    assert (asset_dir / "headers.md").read_text(encoding="utf-8") == (
        "# Document Structure\n\n"
        "Table of Contents:\n\n"
        "- Paper (H1, line 1, 5 lines)\n"
        "  - Intro (H2, line 3, 3 lines)\n"
    )
    assert len(captured_configs) == 1
    assert captured_configs[0].source == source
    assert captured_configs[0].name == "paper"
    assert captured_configs[0].output_dir.parent == asset_root / ".tmp"
    assert captured_name_inputs == [
        AssetNameInput(
            source=source,
            markdown="# Paper\n\n## Intro\n\nBody.\n",
            headers=(
                "# Document Structure\n\n"
                "Table of Contents:\n\n"
                "- Paper (H1, line 1, 5 lines)\n"
                "  - Intro (H2, line 3, 3 lines)\n"
            ),
        )
    ]
    source_sha256 = hashlib.sha256(b"%PDF-1.7\n").hexdigest()
    metadata = json.loads((asset_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "Deep Work"
    assert metadata["authors"] == ["Cal Newport"]
    assert metadata["source_sha256"] == source_sha256
    assert (asset_dir / "canonical_name.txt").read_text(encoding="utf-8") == (
        "deep_work_cal_newport\n"
    )


def test_to_asset_moves_epub_original_markdown_and_headers_to_asset_folder(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.epub"
    write_minimal_epub(source)
    source_bytes = source.read_bytes()
    asset_root = tmp_path / "vault-assets"
    captured_configs: list[ToMarkdownConfig] = []

    def fake_pdf_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        raise AssertionError("PDF markdowner should not handle EPUB inputs.")

    def fake_epub_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        captured_configs.append(config)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text(
            "# Example Book\n\n"
            "By Jane Writer\n\n"
            "# Opening\n\n"
            "The first paragraph.\n\n"
            "The second paragraph.\n",
            encoding="utf-8",
        )
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = CliRunner().invoke(
        build_to_asset_command(
            markdowner=fake_pdf_markdowner,
            epub_markdowner=fake_epub_markdowner,
            asset_namer=fixed_asset_namer(
                "example_book_jane_writer",
                title="Example Book",
                authors=("Jane Writer",),
            ),
        ),
        [str(source), "--asset-root", str(asset_root)],
    )

    asset_dir = asset_root / "example_book_jane_writer"
    assert result.exit_code == 0
    assert result.output == f"Wrote {asset_dir}\n"
    assert not source.exists()
    assert len(captured_configs) == 1
    assert captured_configs[0].source == source
    assert captured_configs[0].name == "sample"
    assert captured_configs[0].output_dir.parent == asset_root / ".tmp"
    assert (asset_dir / "example_book_jane_writer.epub").read_bytes() == source_bytes
    assert (asset_dir / "example_book_jane_writer.md").read_text(encoding="utf-8") == (
        "# Example Book\n\n"
        "By Jane Writer\n\n"
        "# Opening\n\n"
        "The first paragraph.\n\n"
        "The second paragraph.\n"
    )
    assert (asset_dir / "headers.md").read_text(encoding="utf-8") == (
        "# Document Structure\n\n"
        "Table of Contents:\n\n"
        "- Example Book (H1, line 1, 4 lines)\n"
        "- Opening (H1, line 5, 5 lines)\n"
    )


def test_to_asset_miner_option_uses_miner_markdowner(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    called_markdowners: list[str] = []

    def default_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        called_markdowners.append("default")
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text("# Default\n", encoding="utf-8")
        return MarkdownOutput(config=config, asset=config.asset_path)

    def miner_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        called_markdowners.append("miner")
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text("# Miner\n", encoding="utf-8")
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = CliRunner().invoke(
        build_to_asset_command(
            markdowner=default_markdowner,
            miner_markdowner=miner_markdowner,
            asset_namer=fixed_asset_namer("paper"),
        ),
        [str(source), "--miner", "--asset-root", str(tmp_path / "assets")],
    )

    assert result.exit_code == 0
    assert (tmp_path / "assets" / "paper" / "paper.md").read_text(
        encoding="utf-8"
    ) == "# Miner\n"
    assert called_markdowners == ["miner"]


def test_to_asset_datalab_option_uses_datalab_markdowner(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    called_markdowners: list[str] = []

    def default_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        called_markdowners.append("default")
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text("# Default\n", encoding="utf-8")
        return MarkdownOutput(config=config, asset=config.asset_path)

    def datalab_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        called_markdowners.append("datalab")
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text("# Datalab\n", encoding="utf-8")
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = CliRunner().invoke(
        build_to_asset_command(
            markdowner=default_markdowner,
            datalab_markdowner=datalab_markdowner,
            asset_namer=fixed_asset_namer("paper"),
        ),
        [str(source), "--datalab", "--asset-root", str(tmp_path / "assets")],
    )

    assert result.exit_code == 0
    assert (tmp_path / "assets" / "paper" / "paper.md").read_text(
        encoding="utf-8"
    ) == "# Datalab\n"
    assert called_markdowners == ["datalab"]


def test_to_asset_force_replaces_existing_asset_folder(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    asset_dir = tmp_path / "assets" / "paper"
    asset_dir.mkdir(parents=True)
    stale = asset_dir / "stale.md"
    stale.write_text("stale", encoding="utf-8")

    def fake_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text("# Paper\n", encoding="utf-8")
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = CliRunner().invoke(
        build_to_asset_command(
            fake_markdowner,
            asset_namer=fixed_asset_namer("paper"),
        ),
        [
            str(source),
            "--asset-root",
            str(tmp_path / "assets"),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert not stale.exists()
    assert (asset_dir / "paper.pdf").exists()
    assert (asset_dir / "paper.md").exists()
    assert (asset_dir / "headers.md").exists()


def test_to_asset_refuses_existing_asset_folder_without_force(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    (tmp_path / "assets" / "paper").mkdir(parents=True)

    def fake_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.asset_path.write_text("# Paper\n", encoding="utf-8")
        return MarkdownOutput(config=config, asset=config.asset_path)

    result = CliRunner().invoke(
        build_to_asset_command(
            fake_markdowner,
            asset_namer=fixed_asset_namer("paper"),
        ),
        [str(source), "--asset-root", str(tmp_path / "assets")],
    )

    assert result.exit_code == 1
    assert "Asset directory already exists" in result.output
    assert source.exists()


def test_to_asset_rejects_multiple_converter_options(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    result = CliRunner().invoke(
        build_to_asset_command(),
        [str(source), "--miner", "--datalab"],
    )

    assert result.exit_code == 2
    assert "Choose only one converter option" in result.output


def test_to_asset_rejects_pdf_converter_options_for_epubs(tmp_path: Path) -> None:
    source = tmp_path / "sample.epub"
    write_minimal_epub(source)

    result = CliRunner().invoke(
        build_to_asset_command(),
        [str(source), "--miner", "--asset-root", str(tmp_path / "assets")],
    )

    assert result.exit_code == 2
    assert "PDF converter options only apply to PDF inputs" in result.output
    assert source.exists()


def test_to_asset_reports_datalab_api_errors_without_traceback(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    def failing_datalab_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        raise DatalabApiError("Datalab API request failed with HTTP 403: forbidden")

    result = CliRunner().invoke(
        build_to_asset_command(
            datalab_markdowner=failing_datalab_markdowner,
            asset_namer=fixed_asset_namer("paper"),
        ),
        [str(source), "--datalab", "--asset-root", str(tmp_path / "assets")],
    )

    assert result.exit_code == 1
    assert "Error: Datalab API request failed with HTTP 403: forbidden" in result.output
    assert "Traceback" not in result.output
    assert source.exists()


def test_to_asset_rejects_unsupported_file_types(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("plain text", encoding="utf-8")
    converter_was_called = False

    def fake_markdowner(config: ToMarkdownConfig) -> MarkdownOutput:
        nonlocal converter_was_called
        converter_was_called = True
        return MarkdownOutput(config=config, asset=Path("unused.md"))

    result = CliRunner().invoke(build_to_asset_command(fake_markdowner), [str(source)])

    assert result.exit_code == 1
    assert (
        "Unsupported file type '.txt'. Supported file types: .epub, .pdf"
        in result.output
    )
    assert converter_was_called is False


def test_to_asset_help_describes_asset_folder() -> None:
    result = CliRunner().invoke(build_to_asset_command(), ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "INPUT" in result.output
    assert "--asset-root" in result.output
    assert "--force" in result.output
    assert "--output" not in result.output
    assert "--miner" in result.output
    assert "--datalab" in result.output


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
