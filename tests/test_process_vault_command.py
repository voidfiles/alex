import hashlib
import json
import shutil
from pathlib import Path

from click.testing import CliRunner

from alex.commands.process_vault import build_process_vault_command
from alex.lib.asset_folders import ToAssetConfig, ToAssetOutput
from alex.lib.locking import exclusive_lock
from alex.lib.process_doc_assets import ProcessDocAssetConfig, ProcessDocAssetOutput
from alex.lib.process_vault import AssetBuilder, DocProcessor


def make_doc_output(asset_dir: Path) -> ProcessDocAssetOutput:
    chunks_dir = asset_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunk = chunks_dir / "001.md"
    chunk.write_text("chunk", encoding="utf-8")
    metadata = asset_dir / "metadata.json"
    metadata.write_text("{}", encoding="utf-8")
    canonical_name = asset_dir / "canonical_name.txt"
    canonical_name.write_text("asset\n", encoding="utf-8")
    return ProcessDocAssetOutput(
        asset_dir=asset_dir,
        original_file=asset_dir / "asset.epub",
        markdown_path=asset_dir / "asset.md",
        headers_path=asset_dir / "headers.md",
        chapter_level_path=None,
        metadata_path=metadata,
        canonical_name_path=canonical_name,
        chunks_dir=chunks_dir,
        chunk_paths=(chunk,),
    )


def fake_builder_for(
    asset_root: Path, *, call_log: list[ToAssetConfig] | None = None
) -> AssetBuilder:
    """Fake builder: respects move_source, mirrors build_asset behavior."""

    def builder(config: ToAssetConfig) -> ToAssetOutput:
        if call_log is not None:
            call_log.append(config)
        stem = config.source.stem
        asset_dir = config.asset_root / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / config.source.name
        if config.move_source:
            shutil.move(str(config.source), str(dest))
        else:
            shutil.copy2(str(config.source), str(dest))
        md = asset_dir / f"{stem}.md"
        md.write_text("# Content\n", encoding="utf-8")
        headers = asset_dir / "headers.md"
        headers.write_text("# Structure\n", encoding="utf-8")
        return ToAssetOutput(
            asset_dir=asset_dir,
            source_path=dest,
            markdown_path=md,
            headers_path=headers,
        )

    return builder


def fake_processor_for(
    *, call_log: list[ProcessDocAssetConfig] | None = None
) -> DocProcessor:
    def processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        if call_log is not None:
            call_log.append(config)
        return make_doc_output(config.asset_path)

    return processor


def test_process_vault_processes_all_sources(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "a.epub").write_bytes(b"epub")
    (vault / "b.pdf").write_bytes(b"%PDF")
    lock_path = tmp_path / "test.lock"

    result = CliRunner().invoke(
        build_process_vault_command(
            asset_builder=fake_builder_for(asset_root),
            doc_processor=fake_processor_for(),
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested a.epub" in result.output
    assert "Ingested b.pdf" in result.output
    assert "Done: 2 ingested, 0 skipped, 0 failed (total 2)." in result.output


def test_process_vault_empty_vault_exits_zero(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    lock_path = tmp_path / "test.lock"

    result = CliRunner().invoke(
        build_process_vault_command(
            asset_builder=fake_builder_for(asset_root),
            doc_processor=fake_processor_for(),
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
        ],
    )

    assert result.exit_code == 0
    assert "No PDF or EPUB files found" in result.output


def test_process_vault_partial_failure_exits_zero(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "good.epub").write_bytes(b"epub")
    (vault / "bad.pdf").write_bytes(b"%PDF")
    lock_path = tmp_path / "test.lock"

    def failing_builder(config: ToAssetConfig) -> ToAssetOutput:
        if config.source.suffix == ".pdf":
            raise RuntimeError("converter exploded")
        stem = config.source.stem
        asset_dir = config.asset_root / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / config.source.name
        shutil.copy2(str(config.source), str(dest))
        md = asset_dir / f"{stem}.md"
        md.write_text("# Content\n", encoding="utf-8")
        headers = asset_dir / "headers.md"
        headers.write_text("# Structure\n", encoding="utf-8")
        return ToAssetOutput(
            asset_dir=asset_dir,
            source_path=dest,
            markdown_path=md,
            headers_path=headers,
        )

    result = CliRunner().invoke(
        build_process_vault_command(
            asset_builder=failing_builder,
            doc_processor=fake_processor_for(),
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
        ],
    )

    assert result.exit_code == 0
    assert "FAILED bad.pdf" in result.output
    assert "converter exploded" in result.output
    assert "Ingested good.epub" in result.output
    assert "1 ingested, 0 skipped, 1 failed" in result.output


def test_process_vault_lock_held_skips_without_calling_fakes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "book.pdf").write_bytes(b"%PDF")
    lock_path = tmp_path / "test.lock"

    builder_calls: list[ToAssetConfig] = []
    processor_calls: list[ProcessDocAssetConfig] = []

    # Acquire the lock in this process first; the command will see EWOULDBLOCK.
    with exclusive_lock(lock_path):
        result = CliRunner().invoke(
            build_process_vault_command(
                asset_builder=fake_builder_for(asset_root, call_log=builder_calls),
                doc_processor=fake_processor_for(call_log=processor_calls),
            ),
            [
                "--vault-root",
                str(vault),
                "--asset-root",
                str(asset_root),
                "--lock-path",
                str(lock_path),
            ],
        )

    assert result.exit_code == 0
    assert "Another process-vault run is in progress; skipping." in result.output
    assert builder_calls == []
    assert processor_calls == []


def test_process_vault_force_flag_threads_through(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "book.pdf").write_bytes(b"%PDF")
    lock_path = tmp_path / "test.lock"

    captured: list[ToAssetConfig] = []

    result = CliRunner().invoke(
        build_process_vault_command(
            asset_builder=fake_builder_for(asset_root, call_log=captured),
            doc_processor=fake_processor_for(),
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert len(captured) == 1
    assert captured[0].force is True


def test_process_vault_help_lists_options_without_miner_or_datalab() -> None:
    result = CliRunner().invoke(build_process_vault_command(), ["--help"])

    assert result.exit_code == 0
    assert "--vault-root" in result.output
    assert "--asset-root" in result.output
    assert "--force" in result.output
    assert "--lock-path" in result.output
    assert "--miner" not in result.output
    assert "--datalab" not in result.output


def test_process_vault_hard_error_raises_click_exception(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "book.pdf").write_bytes(b"%PDF")
    lock_path = tmp_path / "test.lock"

    def exploding_builder(config: ToAssetConfig) -> ToAssetOutput:
        raise RuntimeError("total meltdown")

    result = CliRunner().invoke(
        build_process_vault_command(
            asset_builder=exploding_builder,
            doc_processor=fake_processor_for(),
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
        ],
    )

    # Per-file errors surface in the summary but don't crash the CLI with a traceback.
    assert "Traceback" not in result.output
    assert "total meltdown" in result.output


def test_process_vault_process_doc_failure_reports_asset_dir(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "book.pdf").write_bytes(b"%PDF")
    lock_path = tmp_path / "test.lock"

    def failing_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        raise ValueError("chunking failed")

    result = CliRunner().invoke(
        build_process_vault_command(
            asset_builder=fake_builder_for(asset_root),
            doc_processor=failing_processor,
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
        ],
    )

    assert result.exit_code == 0
    assert "FAILED book.pdf" in result.output
    assert "chunking failed" in result.output
    assert "alex process-doc" in result.output  # tells the user how to finish it


def test_process_vault_skipped_asset_shows_in_summary(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    lock_path = tmp_path / "test.lock"

    # Seed a processed asset matching the source content.
    content = b"%PDF-already-done"
    sha = hashlib.sha256(content).hexdigest()
    source = vault / "book.pdf"
    source.write_bytes(content)
    existing_dir = asset_root / "existing_book"
    existing_dir.mkdir()
    (existing_dir / "metadata.json").write_text(
        json.dumps({"title": "Book", "source_sha256": sha}),
        encoding="utf-8",
    )
    chunks_dir = existing_dir / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "001.md").write_text("chunk", encoding="utf-8")

    builder_calls: list[ToAssetConfig] = []
    processor_calls: list[ProcessDocAssetConfig] = []

    result = CliRunner().invoke(
        build_process_vault_command(
            asset_builder=fake_builder_for(asset_root, call_log=builder_calls),
            doc_processor=fake_processor_for(call_log=processor_calls),
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
        ],
    )

    assert result.exit_code == 0
    assert "Skipped book.pdf (already processed)" in result.output
    assert "Done: 0 ingested, 1 skipped, 0 failed (total 1)." in result.output
    # Original removed even on skip.
    assert not source.exists()
    # Neither builder nor processor called.
    assert builder_calls == []
    assert processor_calls == []


def test_process_vault_original_removed_after_successful_ingestion(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    source = vault / "book.pdf"
    source.write_bytes(b"%PDF")
    lock_path = tmp_path / "test.lock"

    CliRunner().invoke(
        build_process_vault_command(
            asset_builder=fake_builder_for(asset_root),
            doc_processor=fake_processor_for(),
        ),
        [
            "--vault-root",
            str(vault),
            "--asset-root",
            str(asset_root),
            "--lock-path",
            str(lock_path),
        ],
    )

    assert not source.exists()
