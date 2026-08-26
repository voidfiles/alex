"""Click entry points for the disposable vault retrieval index."""

from __future__ import annotations

import json
from pathlib import Path

import click

from alex.lib.brain import (
    BrainError,
    BrainIndex,
    BrainIndexConfig,
    normalize_embedding_model,
)
from alex.lib.llm import LiteLlmEmbedder

DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "alex"


def build_brain_command(cache_root: Path = DEFAULT_CACHE_ROOT) -> click.Group:
    @click.group("brain")
    def command() -> None:
        """Index and inspect the disposable Markdown retrieval database."""

    @command.command("index")
    @click.argument(
        "vault", type=click.Path(exists=True, file_okay=False, path_type=Path)
    )
    @click.option("--embedding-model", default=None)
    @click.option(
        "--rebuild", is_flag=True, help="Discard and recreate this vault index."
    )
    @click.option("--defer-embeddings", is_flag=True)
    def index(
        vault: Path, embedding_model: str | None, rebuild: bool, defer_embeddings: bool
    ) -> None:
        config = _config(vault, cache_root, embedding_model)
        if rebuild and config.database_path.exists():
            config.database_path.unlink()
        try:
            brain = BrainIndex(config)
            result = brain.index(defer_embeddings=True)
            click.echo(
                "Indexed: "
                f"{result.indexed_files} changed, {result.skipped_files} skipped."
            )
            if result.large_files:
                click.echo(f"Warning: indexed {result.large_files} files over 500 KB.")
            if not defer_embeddings:
                done, failed, error = brain.embed_stale(LiteLlmEmbedder())
                click.echo(
                    f"Embeddings: {done} completed, {failed} deferred after failures."
                )
                if error:
                    click.echo(f"Embedding error: {error}", err=True)
        except (BrainError, OSError, ValueError) as error:
            raise click.ClickException(str(error)) from error

    @command.command("embed")
    @click.argument(
        "vault", type=click.Path(exists=True, file_okay=False, path_type=Path)
    )
    @click.option("--embedding-model", default=None)
    def embed(vault: Path, embedding_model: str | None) -> None:
        brain = BrainIndex(_config(vault, cache_root, embedding_model))
        done, failed, error = brain.embed_stale(LiteLlmEmbedder())
        click.echo(f"Embeddings: {done} completed, {failed} stale.")
        if error:
            click.echo(f"Embedding error: {error}", err=True)

    @command.command("status")
    @click.argument(
        "vault", type=click.Path(exists=True, file_okay=False, path_type=Path)
    )
    @click.option("--embedding-model", default=None)
    @click.option("--json", "as_json", is_flag=True)
    def status(vault: Path, embedding_model: str | None, as_json: bool) -> None:
        payload = BrainIndex(_config(vault, cache_root, embedding_model)).status()
        if as_json:
            click.echo(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for key, value in payload.items():
                click.echo(f"{key.replace('_', ' ').title()}: {value}")

    return command


def _config(
    vault: Path, cache_root: Path, embedding_model: str | None
) -> BrainIndexConfig:
    selected_model = normalize_embedding_model(
        embedding_model or "ollama/nomic-embed-text"
    )
    return BrainIndexConfig(
        vault=vault,
        cache_root=cache_root,
        embedding_model=selected_model,
    )


brain = build_brain_command()
