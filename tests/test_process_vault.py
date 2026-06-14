import shutil
from pathlib import Path

import pytest

from alex.lib.asset_folders import ToAssetConfig, ToAssetOutput
from alex.lib.process_doc_assets import ProcessDocAssetConfig, ProcessDocAssetOutput
from alex.lib.process_vault import (
    ProcessVaultConfig,
    VaultSourceResult,
    find_vault_sources,
    process_vault_root,
)


def make_process_doc_output(asset_dir: Path) -> ProcessDocAssetOutput:
    chunks_dir = asset_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunk = chunks_dir / "001.md"
    chunk.write_text("chunk", encoding="utf-8")
    metadata = asset_dir / "metadata.json"
    metadata.write_text("{}", encoding="utf-8")
    canonical_name = asset_dir / "canonical_name.txt"
    canonical_name.write_text("asset\n", encoding="utf-8")
    original = asset_dir / "asset.epub"
    markdown = asset_dir / "asset.md"
    headers = asset_dir / "headers.md"
    return ProcessDocAssetOutput(
        asset_dir=asset_dir,
        original_file=original,
        markdown_path=markdown,
        headers_path=headers,
        chapter_level_path=None,
        metadata_path=metadata,
        canonical_name_path=canonical_name,
        chunks_dir=chunks_dir,
        chunk_paths=(chunk,),
    )


def make_fake_asset_builder(
    asset_root: Path,
    *,
    captured_configs: list[ToAssetConfig] | None = None,
) -> object:
    """Returns a fake that moves the source into an asset dir, mirroring build_asset."""

    def builder(config: ToAssetConfig) -> ToAssetOutput:
        if captured_configs is not None:
            captured_configs.append(config)
        stem = config.source.stem
        asset_dir = config.asset_root / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / config.source.name
        shutil.move(str(config.source), str(dest))
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


# --- find_vault_sources ---


def test_find_vault_sources_returns_sorted_pdf_epub_only(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "b.pdf").write_bytes(b"%PDF")
    (vault / "a.epub").write_bytes(b"epub")
    (vault / "c.txt").write_text("text", encoding="utf-8")
    (vault / "note.md").write_text("note", encoding="utf-8")
    sub = vault / "subdir"
    sub.mkdir()
    (sub / "nested.pdf").write_bytes(b"%PDF")

    result = find_vault_sources(vault, asset_root=asset_root)

    assert result == (vault / "a.epub", vault / "b.pdf")


def test_find_vault_sources_excludes_asset_root_contents(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    asset_dir = asset_root / "some_book"
    asset_dir.mkdir()
    (asset_dir / "some_book.pdf").write_bytes(b"%PDF")

    result = find_vault_sources(vault, asset_root=asset_root)

    assert result == ()


def test_find_vault_sources_skips_dotfiles(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / ".hidden.pdf").write_bytes(b"%PDF")
    (vault / "visible.pdf").write_bytes(b"%PDF")

    result = find_vault_sources(vault, asset_root=asset_root)

    assert result == (vault / "visible.pdf",)


def test_find_vault_sources_skips_symlinks(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    real = tmp_path / "real.pdf"
    real.write_bytes(b"%PDF")
    (vault / "link.pdf").symlink_to(real)
    (vault / "actual.pdf").write_bytes(b"%PDF")

    result = find_vault_sources(vault, asset_root=asset_root)

    assert result == (vault / "actual.pdf",)


def test_find_vault_sources_empty_vault_returns_empty(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()

    assert find_vault_sources(vault, asset_root=asset_root) == ()


def test_find_vault_sources_missing_vault_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(NotADirectoryError):
        find_vault_sources(missing, asset_root=tmp_path / "assets")


# --- process_vault_root ---


def test_process_vault_root_processes_each_source(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "a.epub").write_bytes(b"epub")
    (vault / "b.pdf").write_bytes(b"%PDF")

    captured_builder_configs: list[ToAssetConfig] = []
    captured_processor_configs: list[ProcessDocAssetConfig] = []

    def fake_builder(config: ToAssetConfig) -> ToAssetOutput:
        captured_builder_configs.append(config)
        stem = config.source.stem
        asset_dir = config.asset_root / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / config.source.name
        shutil.move(str(config.source), str(dest))
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

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        captured_processor_configs.append(config)
        return make_process_doc_output(config.asset_path)

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(
        config, asset_builder=fake_builder, doc_processor=fake_processor
    )

    assert len(output.results) == 2
    assert len(output.processed) == 2
    assert len(output.failed) == 0
    # Sources were moved out of the vault root.
    assert not (vault / "a.epub").exists()
    assert not (vault / "b.pdf").exists()
    # Builder received the right asset_root.
    assert all(c.asset_root == asset_root for c in captured_builder_configs)
    # Processor received the asset dirs created by the builder.
    processor_asset_dirs = {c.asset_path for c in captured_processor_configs}
    assert processor_asset_dirs == {asset_root / "a", asset_root / "b"}


def test_process_vault_root_continues_on_builder_failure(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "bad.pdf").write_bytes(b"%PDF")
    (vault / "good.epub").write_bytes(b"epub")

    def fake_builder(config: ToAssetConfig) -> ToAssetOutput:
        if config.source.name == "bad.pdf":
            raise FileExistsError("Asset directory already exists: /some/dir")
        stem = config.source.stem
        asset_dir = config.asset_root / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / config.source.name
        shutil.move(str(config.source), str(dest))
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

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        return make_process_doc_output(config.asset_path)

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(
        config, asset_builder=fake_builder, doc_processor=fake_processor
    )

    assert len(output.failed) == 1
    assert len(output.processed) == 1
    assert output.failed[0].source.name == "bad.pdf"
    assert output.failed[0].asset_dir is None
    assert "Asset directory already exists" in (output.failed[0].error or "")
    assert output.processed[0].source.name == "good.epub"


def test_process_vault_root_doc_processor_failure_records_asset_dir(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "book.pdf").write_bytes(b"%PDF")

    def fake_builder(config: ToAssetConfig) -> ToAssetOutput:
        stem = config.source.stem
        asset_dir = config.asset_root / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / config.source.name
        shutil.move(str(config.source), str(dest))
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

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        raise ValueError("chunking failed")

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(
        config, asset_builder=fake_builder, doc_processor=fake_processor
    )

    assert len(output.failed) == 1
    result = output.failed[0]
    assert result.asset_dir == asset_root / "book"  # built; processing failed
    assert result.error is not None
    assert "processing failed" in result.error
    assert "chunking failed" in result.error


def test_process_vault_root_empty_vault_returns_empty_output(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(config)

    assert output.results == ()
    assert output.processed == ()
    assert output.failed == ()


def test_process_vault_root_force_flag_threads_through_to_builder(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    (vault / "book.pdf").write_bytes(b"%PDF")

    captured: list[ToAssetConfig] = []

    def fake_builder(config: ToAssetConfig) -> ToAssetOutput:
        captured.append(config)
        stem = config.source.stem
        asset_dir = config.asset_root / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest = asset_dir / config.source.name
        shutil.move(str(config.source), str(dest))
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

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        return make_process_doc_output(config.asset_path)

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root, force=True)
    process_vault_root(config, asset_builder=fake_builder, doc_processor=fake_processor)

    assert len(captured) == 1
    assert captured[0].force is True


def test_vault_source_result_ok_property() -> None:
    ok = VaultSourceResult(source=Path("x.pdf"), asset_dir=Path("/a"), error=None)
    bad = VaultSourceResult(source=Path("y.pdf"), asset_dir=None, error="boom")

    assert ok.ok is True
    assert bad.ok is False
