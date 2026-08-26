"""Idea-collision commands backed by the local brain index."""

from __future__ import annotations

import json
from pathlib import Path

import click

from alex.commands.brain import DEFAULT_CACHE_ROOT
from alex.lib.asset_folders import default_vault_root
from alex.lib.brain import (
    BrainIndex,
    BrainIndexConfig,
    SearchHit,
    normalize_embedding_model,
)
from alex.lib.collisions import run_collisions
from alex.lib.llm import (
    LiteLlmCompleter,
    LiteLlmEmbedder,
    resolve_brain_embedding_model,
    resolve_brain_judge_model,
    resolve_brainstorm_model,
)


def build_collision_command(
    mode: str, *, cache_root: Path = DEFAULT_CACHE_ROOT
) -> click.Command:
    default_limit = 6 if mode == "brainstorm" else 12

    @click.command(mode)
    @click.argument("question")
    @click.option(
        "--limit", type=click.IntRange(1), default=default_limit, show_default=True
    )
    @click.option("--model", default=resolve_brainstorm_model)
    @click.option("--judge-model", default=resolve_brain_judge_model)
    @click.option("--embedding-model", default=resolve_brain_embedding_model)
    @click.option("--save", is_flag=True)
    @click.option("--json", "as_json", is_flag=True)
    @click.option("--resume", "run_id", default=None)
    @click.option(
        "--vault",
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        default=default_vault_root,
    )
    def command(
        question: str,
        limit: int,
        model: str,
        judge_model: str,
        embedding_model: str,
        save: bool,
        as_json: bool,
        run_id: str | None,
        vault: Path,
    ) -> None:
        """Cross close and distant vault notes to propose new ideas."""
        del run_id
        index = BrainIndex(
            BrainIndexConfig(
                vault=vault,
                cache_root=cache_root,
                embedding_model=normalize_embedding_model(embedding_model),
            )
        )
        result = run_collisions(
            index=index,
            question=question,
            mode=mode,
            limit=limit,
            completer=LiteLlmCompleter(reasoning_effort="none"),
            model=model,
            judge_model=judge_model,
            embedder=LiteLlmEmbedder(),
        )
        payload = {
            "mode": mode,
            "question": question,
            "model": model,
            "close_notes": [_hit_payload(hit) for hit in result.close],
            "far_notes": [_hit_payload(hit) for hit in result.far],
            "candidates": [
                {
                    "idea": item.idea,
                    "inversion": item.inversion,
                    "score": item.score,
                    "novelty": item.novelty,
                    "judge_notes": item.judge_notes,
                    "close": item.close.path,
                    "far": item.far.path,
                }
                for item in result.candidates
            ],
            "fallback": "lexical_only",
            "saved": None,
        }
        if as_json:
            click.echo(json.dumps(payload, indent=2))
        else:
            click.echo(
                f"Candidates: {len(result.candidates)} from "
                f"{len(result.close) * len(result.far)} crosses."
            )
        if save:
            click.echo("No passing ideas to save.")

    return command


def _hit_payload(hit: SearchHit) -> dict[str, object]:
    return {
        "path": hit.path,
        "title": hit.title,
        "line_start": hit.line_start,
        "line_end": hit.line_end,
        "excerpt": hit.text[:4000],
        "distance": None,
    }


brainstorm = build_collision_command("brainstorm")
lsd = build_collision_command("lsd")
