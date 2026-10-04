"""Idea-collision commands backed by the local brain index."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from alex.commands.brain import DEFAULT_CACHE_ROOT
from alex.lib.asset_folders import default_vault_root
from alex.lib.brain import (
    BrainIndex,
    BrainIndexConfig,
    SearchHit,
    normalize_embedding_model,
)
from alex.lib.collisions import (
    CollisionCandidate,
    CollisionResult,
    profile_for_mode,
    run_collisions,
)
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
    profile = profile_for_mode(mode)

    @click.command(mode)
    @click.argument("question")
    @click.option(
        "--limit",
        type=click.IntRange(1),
        default=None,
        help="Override the profile far-page count.",
    )
    @click.option("--model", default=resolve_brainstorm_model)
    @click.option("--judge-model", default=resolve_brain_judge_model)
    @click.option("--embedding-model", default=resolve_brain_embedding_model)
    @click.option(
        "--save/--no-save", default=profile.save_by_default, show_default=True
    )
    @click.option(
        "--max-cost", type=click.FloatRange(min=0), default=5.0, show_default=True
    )
    @click.option("--json", "as_json", is_flag=True)
    @click.option("--resume", "run_id", default=None)
    @click.option(
        "--vault",
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        default=default_vault_root,
    )
    def command(
        question: str,
        limit: int | None,
        model: str,
        judge_model: str,
        embedding_model: str,
        save: bool,
        max_cost: float,
        as_json: bool,
        run_id: str | None,
        vault: Path,
    ) -> None:
        """Cross close and distant vault pages to propose source-grounded ideas."""
        if run_id is not None:
            # The deterministic run identifier lets the caller detect mismatches now;
            # the pipeline's durable checkpoint is deliberately below the vault cache.
            click.echo(f"Resuming collision run {run_id}...", err=True)
        else:
            click.echo(
                "Searching the vault and generating collision ideas...", err=True
            )
        calibration_tags, calibration_warning = _load_calibration(vault)
        try:
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
                completer=LiteLlmCompleter(
                    reasoning_effort="none", temperature=profile.temperature
                ),
                model=model,
                judge_model=judge_model,
                embedder=LiteLlmEmbedder(),
                calibration_tags=calibration_tags,
                max_cost=max_cost,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        warnings = (
            *result.warnings,
            *((calibration_warning,) if calibration_warning else ()),
        )
        saved = (
            _save_result(vault, result, question, mode, model, judge_model, warnings)
            if save
            else None
        )
        payload = {
            "run_id": result.run_id,
            "profile": _profile_payload(result),
            "mode": mode,
            "question": question,
            "model": model,
            "judge_model": judge_model,
            "close_pages": [_hit_payload(hit) for hit in result.close],
            "far_pages": [_hit_payload(hit) for hit in result.far],
            "passing": [_candidate_payload(item) for item in result.passing],
            "rejected": [_candidate_payload(item) for item in result.rejected],
            "candidates": [_candidate_payload(item) for item in result.passing],
            "calibration": {
                "active_bias_tags": list(calibration_tags),
                "cold_start": bool(calibration_warning),
            },
            "estimated_cost": result.estimated_cost,
            "observed_cost": result.observed_cost,
            "warnings": list(warnings),
            "checkpoint_status": result.checkpoint_status,
            "saved": str(saved) if saved else None,
        }
        if as_json:
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        for item in result.passing:
            click.echo(
                f"\n[{item.score:.2f}] {item.idea}"
                if item.score is not None
                else f"\n{item.idea}"
            )
            click.echo(
                f"  close: {item.close.path}:"
                f"{item.close.line_start}-{item.close.line_end}"
            )
            click.echo(
                f"  far: {item.far.path}:{item.far.line_start}-{item.far.line_end}"
            )
            if item.inversion:
                click.echo(f"  inversion: {item.inversion}")
        if not result.passing:
            click.echo("No passing ideas.")
        if saved:
            click.echo(f"Saved: {saved}")

    return command


def _load_calibration(vault: Path) -> tuple[tuple[str, ...], str | None]:
    path = vault / ".claude" / "brain" / "calibration.yaml"
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tags = data.get("active_bias_tags") if isinstance(data, dict) else None
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError
        return tuple(tags), None
    except FileNotFoundError:
        return (), "Calibration is unavailable (cold start)."
    except (OSError, ValueError, ImportError):
        return (), "Calibration is invalid (cold start)."


def _profile_payload(result: CollisionResult) -> dict[str, Any]:
    profile = result.profile
    return {
        "name": profile.name,
        "close_count": profile.close_count,
        "far_count": profile.far_count,
        "ideas_per_cross": profile.ideas_per_cross,
        "temperature": profile.temperature,
        "threshold": profile.judge.threshold,
        "save_by_default": profile.save_by_default,
    }


def _hit_payload(hit: SearchHit) -> dict[str, object]:
    return {
        "path": hit.path,
        "title": hit.title,
        "line_start": hit.line_start,
        "line_end": hit.line_end,
        "excerpt": hit.text[:4000],
        "distance": None,
    }


def _candidate_payload(item: CollisionCandidate) -> dict[str, object]:
    return {
        "idea": item.idea,
        "original_axiom": item.original_axiom,
        "inverted_axiom": item.inversion,
        "score": item.score,
        "novelty": item.novelty,
        "axes": item.axes,
        "obviousness": item.obviousness,
        "judge_notes": item.judge_notes,
        "rejection_reason": item.rejection_reason,
        "pair_index": item.pair_index,
        "close": _hit_payload(item.close),
        "far": _hit_payload(item.far),
    }


def _save_result(
    vault: Path,
    result: CollisionResult,
    question: str,
    mode: str,
    model: str,
    judge_model: str,
    warnings: tuple[str, ...],
) -> Path:
    destination = (
        vault
        / "resources"
        / "ideas"
        / f"{datetime.now(UTC):%Y-%m-%d}-{mode}-{result.run_id}.md"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "mode": mode,
        "run_id": result.run_id,
        "question": question,
        "model": model,
        "judge_model": judge_model,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    lines = [
        "---",
        *[
            f"{key}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in frontmatter.items()
        ],
        "---",
        "",
        "# Collision ideas",
        "",
    ]
    for heading, candidates in (
        ("Passing", result.passing),
        ("Rejected", result.rejected),
    ):
        lines.extend((f"## {heading}", ""))
        for item in candidates:
            lines.extend(
                (
                    f"### {item.idea}",
                    "",
                    f"- score: {item.score}",
                    f"- close: {item.close.path}:"
                    f"{item.close.line_start}-{item.close.line_end}",
                    f"- far: {item.far.path}:{item.far.line_start}-{item.far.line_end}",
                )
            )
            if item.original_axiom:
                lines.append(f"- original axiom: {item.original_axiom}")
            if item.inversion:
                lines.append(f"- inverted axiom: {item.inversion}")
            if item.rejection_reason:
                lines.append(f"- rejection: {item.rejection_reason}")
            lines.append("")
    if warnings:
        lines.extend(("## Warnings", "", *[f"- {warning}" for warning in warnings], ""))
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=destination.parent, delete=False
    ) as handle:
        handle.write("\n".join(lines))
        temporary = Path(handle.name)
    os.replace(temporary, destination)
    return destination


brainstorm = build_collision_command("brainstorm")
lsd = build_collision_command("lsd")
