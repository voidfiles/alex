"""Batch ingestion of top-level PDF/EPUB files from the vault root."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from alex.lib.asset_folders import (
    DEFAULT_VAULT_ASSET_ROOT,
    SUPPORTED_SOURCE_EXTENSIONS,
    ToAssetConfig,
    ToAssetOutput,
    build_asset,
    llm_asset_namer,
)
from alex.lib.converters.to_markdown import epub_markdowner, pymupdf4llm_markdowner
from alex.lib.process_doc_assets import (
    ProcessDocAssetConfig,
    ProcessDocAssetOutput,
    process_doc_asset,
)

logger = logging.getLogger(__name__)

DEFAULT_VAULT_ROOT = DEFAULT_VAULT_ASSET_ROOT.parent
DEFAULT_LOCK_PATH = Path.home() / ".cache" / "alex" / "process-vault.lock"


class AssetBuilder(Protocol):
    def __call__(self, config: ToAssetConfig) -> ToAssetOutput: ...


class DocProcessor(Protocol):
    def __call__(self, config: ProcessDocAssetConfig) -> ProcessDocAssetOutput: ...


@dataclass(frozen=True)
class ProcessVaultConfig:
    vault_root: Path = DEFAULT_VAULT_ROOT
    asset_root: Path = DEFAULT_VAULT_ASSET_ROOT
    force: bool = False
    lock_path: Path = DEFAULT_LOCK_PATH


@dataclass(frozen=True)
class VaultSourceResult:
    source: Path
    asset_dir: Path | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class ProcessVaultOutput:
    results: tuple[VaultSourceResult, ...]

    @property
    def processed(self) -> tuple[VaultSourceResult, ...]:
        return tuple(r for r in self.results if r.ok)

    @property
    def failed(self) -> tuple[VaultSourceResult, ...]:
        return tuple(r for r in self.results if not r.ok)


def find_vault_sources(
    vault_root: Path,
    *,
    asset_root: Path,
) -> tuple[Path, ...]:
    """Return sorted top-level .pdf/.epub files under vault_root.

    Skips directories, dotfiles, symlinks, and anything inside asset_root
    (which is nested under vault_root by default).
    """
    if not vault_root.is_dir():
        raise NotADirectoryError(f"Vault root is not a directory: {vault_root}")
    resolved_asset_root = asset_root.resolve()
    sources: list[Path] = []
    for entry in sorted(vault_root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_symlink():
            continue
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in SUPPORTED_SOURCE_EXTENSIONS:
            continue
        try:
            entry.resolve().relative_to(resolved_asset_root)
            continue  # skip anything inside the asset tree
        except ValueError:
            pass
        sources.append(entry)
    return tuple(sources)


def default_asset_builder(config: ToAssetConfig) -> ToAssetOutput:
    return build_asset(
        config,
        pdf_markdowner=pymupdf4llm_markdowner,
        epub_markdowner=epub_markdowner,
        asset_namer=llm_asset_namer,
    )


def process_vault_root(
    config: ProcessVaultConfig,
    *,
    asset_builder: AssetBuilder = default_asset_builder,
    doc_processor: DocProcessor = process_doc_asset,
) -> ProcessVaultOutput:
    """Discover and process every top-level source. Continues on per-file error."""
    logger.info("Scanning %s for PDF and EPUB files", config.vault_root)
    sources = find_vault_sources(config.vault_root, asset_root=config.asset_root)
    if not sources:
        logger.info("No PDF or EPUB files found")
        return ProcessVaultOutput(results=())
    logger.info("Found %d file(s) to process", len(sources))
    results = tuple(
        _process_one(
            source,
            index=i,
            total=len(sources),
            config=config,
            asset_builder=asset_builder,
            doc_processor=doc_processor,
        )
        for i, source in enumerate(sources, 1)
    )
    return ProcessVaultOutput(results=results)


def _process_one(
    source: Path,
    *,
    index: int,
    total: int,
    config: ProcessVaultConfig,
    asset_builder: AssetBuilder,
    doc_processor: DocProcessor,
) -> VaultSourceResult:
    prefix = f"[{index}/{total}] {source.name}"
    logger.info("%s: running to-asset", prefix)
    try:
        asset = asset_builder(
            ToAssetConfig(
                source=source,
                asset_root=config.asset_root,
                force=config.force,
            )
        )
    except (OSError, RuntimeError, ValueError) as error:
        logger.info("%s: to-asset failed — %s", prefix, error)
        return VaultSourceResult(source=source, asset_dir=None, error=str(error))
    logger.info("%s: to-asset done -> %s", prefix, asset.asset_dir.name)
    logger.info("%s: running process-doc", prefix)
    try:
        doc_processor(ProcessDocAssetConfig(asset_path=asset.asset_dir))
    except (OSError, RuntimeError, ValueError) as error:
        logger.info("%s: process-doc failed — %s", prefix, error)
        return VaultSourceResult(
            source=source,
            asset_dir=asset.asset_dir,
            error=f"built asset but processing failed: {error}",
        )
    logger.info("%s: process-doc done", prefix)
    return VaultSourceResult(source=source, asset_dir=asset.asset_dir, error=None)
