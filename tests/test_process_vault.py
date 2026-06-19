import hashlib
import json
import shutil
from pathlib import Path

import pytest

from alex.lib.asset_folders import ToAssetConfig, ToAssetOutput
from alex.lib.process_doc_assets import ProcessDocAssetConfig, ProcessDocAssetOutput
from alex.lib.process_vault import (
    AssetBuilder,
    AssetIndexEntry,
    ProcessVaultConfig,
    VaultSourceResult,
    find_vault_sources,
    index_existing_assets,
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
) -> AssetBuilder:
    """Returns a fake that respects move_source, mirroring build_asset."""

    def builder(config: ToAssetConfig) -> ToAssetOutput:
        if captured_configs is not None:
            captured_configs.append(config)
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
    (vault / "draft.markdown").write_text("markdown note", encoding="utf-8")
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


# --- index_existing_assets ---


def test_index_existing_assets_empty_when_asset_root_missing(tmp_path: Path) -> None:
    assert index_existing_assets(tmp_path / "missing") == {}


def test_index_existing_assets_finds_processed_asset(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    sha = hashlib.sha256(b"%PDF").hexdigest()
    asset_dir = asset_root / "some_book"
    asset_dir.mkdir(parents=True)
    (asset_dir / "metadata.json").write_text(
        json.dumps({"title": "Book", "source_sha256": sha}),
        encoding="utf-8",
    )
    chunks_dir = asset_dir / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "001.md").write_text("chunk", encoding="utf-8")

    result = index_existing_assets(asset_root)

    assert sha in result
    entry = result[sha]
    assert entry.asset_dir == asset_dir
    assert entry.processed is True


def test_index_existing_assets_marks_unprocessed_when_no_chunks(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    sha = hashlib.sha256(b"epub").hexdigest()
    asset_dir = asset_root / "some_book"
    asset_dir.mkdir(parents=True)
    (asset_dir / "metadata.json").write_text(
        json.dumps({"title": "Book", "source_sha256": sha}),
        encoding="utf-8",
    )

    result = index_existing_assets(asset_root)

    assert sha in result
    assert result[sha].processed is False


def test_index_existing_assets_skips_missing_sha256(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_dir = asset_root / "no_sha"
    asset_dir.mkdir(parents=True)
    (asset_dir / "metadata.json").write_text(
        json.dumps({"title": "Book"}),
        encoding="utf-8",
    )

    assert index_existing_assets(asset_root) == {}


def test_index_existing_assets_skips_corrupt_json(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_dir = asset_root / "corrupt"
    asset_dir.mkdir(parents=True)
    (asset_dir / "metadata.json").write_text("not json!!", encoding="utf-8")

    assert index_existing_assets(asset_root) == {}


def test_index_existing_assets_skips_dotdirs(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    dot_dir = asset_root / ".tmp"
    dot_dir.mkdir()
    sha = hashlib.sha256(b"data").hexdigest()
    (dot_dir / "metadata.json").write_text(
        json.dumps({"source_sha256": sha}),
        encoding="utf-8",
    )

    assert index_existing_assets(asset_root) == {}


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
    # Sources are removed by _unlink_original after process-doc succeeds.
    assert not (vault / "a.epub").exists()
    assert not (vault / "b.pdf").exists()
    # Builder received move_source=False (process-vault defers removal).
    assert all(c.move_source is False for c in captured_builder_configs)
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

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        raise ValueError("chunking failed")

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(
        config, asset_builder=fake_builder, doc_processor=fake_processor
    )

    assert len(output.failed) == 1
    result = output.failed[0]
    assert result.asset_dir == asset_root / "book"
    assert result.error is not None
    assert "processing failed" in result.error
    assert "chunking failed" in result.error
    # Original stays on failure — nothing deleted it.
    assert (vault / "book.pdf").exists()


def test_process_vault_root_empty_vault_returns_empty_output(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(config)

    assert output.results == ()
    assert output.processed == ()
    assert output.skipped == ()
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

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        return make_process_doc_output(config.asset_path)

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root, force=True)
    process_vault_root(config, asset_builder=fake_builder, doc_processor=fake_processor)

    assert len(captured) == 1
    assert captured[0].force is True
    assert captured[0].move_source is False


# --- idempotency / dedup ---


def _seed_processed_asset(asset_root: Path, sha: str) -> Path:
    """Create an already-processed asset dir with the given sha in its metadata."""
    asset_dir = asset_root / "existing_book"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "metadata.json").write_text(
        json.dumps({"title": "Existing", "source_sha256": sha}),
        encoding="utf-8",
    )
    chunks_dir = asset_dir / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "001.md").write_text("chunk", encoding="utf-8")
    (asset_dir / "existing_book.md").write_text("# Content\n", encoding="utf-8")
    return asset_dir


def _seed_built_not_processed_asset(asset_root: Path, sha: str) -> Path:
    """Create a built-but-not-yet-processed asset (has metadata, no chunks/)."""
    asset_dir = asset_root / "half_built"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "metadata.json").write_text(
        json.dumps({"title": "Half", "source_sha256": sha}),
        encoding="utf-8",
    )
    (asset_dir / "half_built.md").write_text("# Content\n", encoding="utf-8")
    (asset_dir / "headers.md").write_text("# TOC\n", encoding="utf-8")
    return asset_dir


def test_process_vault_root_skips_already_processed_asset(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    content = b"%PDF-already-done"
    sha = hashlib.sha256(content).hexdigest()
    source = vault / "book.pdf"
    source.write_bytes(content)
    existing_dir = _seed_processed_asset(asset_root, sha)

    builder_calls: list[ToAssetConfig] = []
    processor_calls: list[ProcessDocAssetConfig] = []

    def recording_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        processor_calls.append(config)
        return make_process_doc_output(config.asset_path)

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(
        config,
        asset_builder=make_fake_asset_builder(
            asset_root, captured_configs=builder_calls
        ),
        doc_processor=recording_processor,
    )

    assert len(output.results) == 1
    result = output.results[0]
    assert result.status == "skipped"
    assert result.asset_dir == existing_dir
    # Original removed because it was already done.
    assert not source.exists()
    # Neither builder nor processor was called.
    assert builder_calls == []
    assert processor_calls == []


def test_process_vault_root_resumes_built_not_processed_asset(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    content = b"%PDF-half-built"
    sha = hashlib.sha256(content).hexdigest()
    source = vault / "book.pdf"
    source.write_bytes(content)
    existing_dir = _seed_built_not_processed_asset(asset_root, sha)

    builder_calls: list[ToAssetConfig] = []
    processor_calls: list[ProcessDocAssetConfig] = []

    def fake_builder(config: ToAssetConfig) -> ToAssetOutput:
        builder_calls.append(config)
        raise AssertionError("builder must not be called on resume")

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        processor_calls.append(config)
        return make_process_doc_output(config.asset_path)

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(
        config, asset_builder=fake_builder, doc_processor=fake_processor
    )

    assert len(output.results) == 1
    result = output.results[0]
    assert result.status == "ingested"
    assert result.asset_dir == existing_dir
    # Original removed after successful resume.
    assert not source.exists()
    # Builder never called; processor called on the pre-existing dir.
    assert builder_calls == []
    assert len(processor_calls) == 1
    assert processor_calls[0].asset_path == existing_dir


def test_process_vault_root_resume_failure_leaves_original(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    asset_root = vault / "assets"
    asset_root.mkdir()
    content = b"%PDF-resume-fail"
    sha = hashlib.sha256(content).hexdigest()
    source = vault / "book.pdf"
    source.write_bytes(content)
    existing_dir = _seed_built_not_processed_asset(asset_root, sha)

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        raise ValueError("chunking broken")

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    output = process_vault_root(
        config,
        asset_builder=make_fake_asset_builder(asset_root),
        doc_processor=fake_processor,
    )

    assert len(output.failed) == 1
    result = output.failed[0]
    assert result.asset_dir == existing_dir
    # Original stays — process-doc failed.
    assert source.exists()


def test_process_vault_root_move_source_false_threaded_to_builder(
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
        shutil.copy2(str(config.source), str(asset_dir / config.source.name))
        md = asset_dir / f"{stem}.md"
        md.write_text("# Content\n", encoding="utf-8")
        headers = asset_dir / "headers.md"
        headers.write_text("# Structure\n", encoding="utf-8")
        return ToAssetOutput(
            asset_dir=asset_dir,
            source_path=asset_dir / config.source.name,
            markdown_path=md,
            headers_path=headers,
        )

    def fake_processor(config: ProcessDocAssetConfig) -> ProcessDocAssetOutput:
        return make_process_doc_output(config.asset_path)

    config = ProcessVaultConfig(vault_root=vault, asset_root=asset_root)
    process_vault_root(config, asset_builder=fake_builder, doc_processor=fake_processor)

    assert len(captured) == 1
    assert captured[0].move_source is False


# --- VaultSourceResult ---


def test_vault_source_result_ok_property() -> None:
    ok = VaultSourceResult(
        source=Path("x.pdf"), asset_dir=Path("/a"), status="ingested"
    )
    skipped = VaultSourceResult(
        source=Path("y.pdf"), asset_dir=Path("/b"), status="skipped"
    )
    bad = VaultSourceResult(source=Path("z.pdf"), asset_dir=None, status="failed")

    assert ok.ok is True
    assert skipped.ok is True
    assert bad.ok is False


def test_asset_index_entry_fields() -> None:
    entry = AssetIndexEntry(asset_dir=Path("/some/dir"), processed=True)
    assert entry.asset_dir == Path("/some/dir")
    assert entry.processed is True
