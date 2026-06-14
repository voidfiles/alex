from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from alex.lib.asset_folders import DEFAULT_VAULT_ASSET_ROOT
from alex.lib.locking import LockHeldError, exclusive_lock
from alex.lib.process_doc_assets import process_doc_asset
from alex.lib.process_vault import (
    DEFAULT_LOCK_PATH,
    DEFAULT_VAULT_ROOT,
    AssetBuilder,
    DocProcessor,
    ProcessVaultConfig,
    ProcessVaultOutput,
    default_asset_builder,
    process_vault_root,
)


def build_process_vault_command(
    asset_builder: AssetBuilder = default_asset_builder,
    doc_processor: DocProcessor = process_doc_asset,
) -> click.Command:
    @click.command("process-vault")
    @click.option(
        "--vault-root",
        type=click.Path(file_okay=False, path_type=Path),
        default=DEFAULT_VAULT_ROOT,
        show_default=True,
        help="Vault root scanned for top-level PDF/EPUB files.",
    )
    @click.option(
        "--asset-root",
        type=click.Path(file_okay=False, path_type=Path),
        default=DEFAULT_VAULT_ASSET_ROOT,
        show_default=True,
        help="Root vault asset folder.",
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Replace existing asset folders with the same source name.",
    )
    @click.option(
        "--lock-path",
        type=click.Path(dir_okay=False, path_type=Path),
        default=DEFAULT_LOCK_PATH,
        show_default=True,
        help="Mutual-exclusion lock file (machine-local; prevents overlapping runs).",
    )
    def command(
        vault_root: Path,
        asset_root: Path,
        force: bool,
        lock_path: Path,
    ) -> None:
        """Ingest every top-level PDF/EPUB in the vault root.

        Discovers .pdf and .epub files at the vault root (non-recursive),
        converts each to a vault asset folder via to-asset, then chunks and
        summarizes it via process-doc.  Files are moved into their asset
        folder on success, so re-running is safe.

        If another run is already in progress the command prints a message
        and exits without doing any work.  Per-file failures are reported in
        the summary; they do not abort the rest of the batch.
        """
        config = ProcessVaultConfig(
            vault_root=vault_root,
            asset_root=asset_root,
            force=force,
            lock_path=lock_path,
        )
        _log = logging.getLogger("alex.lib.process_vault")
        _handler = logging.StreamHandler(sys.stderr)
        _handler.setFormatter(logging.Formatter("%(message)s"))
        _log.addHandler(_handler)
        _log.setLevel(logging.INFO)
        try:
            # LockHeldError MUST be caught before (OSError, RuntimeError, ValueError)
            # because LockHeldError is a RuntimeError.
            with exclusive_lock(config.lock_path):
                output = process_vault_root(
                    config,
                    asset_builder=asset_builder,
                    doc_processor=doc_processor,
                )
        except LockHeldError:
            click.echo("Another process-vault run is in progress; skipping.")
            return
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        finally:
            _log.removeHandler(_handler)

        _echo_summary(output)

    return command


def _echo_summary(output: ProcessVaultOutput) -> None:
    if not output.results:
        click.echo("No PDF or EPUB files found at the vault root.")
        return
    for result in output.results:
        if result.ok:
            click.echo(f"Ingested {result.source.name} -> {result.asset_dir}")
        else:
            msg = f"FAILED {result.source.name}: {result.error}"
            if result.asset_dir is not None:
                msg += f" (run `alex process-doc {result.asset_dir}` to finish)"
            click.echo(msg)
    total = len(output.results)
    n_ok = len(output.processed)
    n_fail = len(output.failed)
    click.echo(f"Done: {n_ok} ingested, {n_fail} failed (total {total}).")


process_vault = build_process_vault_command()
