"""Per-note triage proposals: prompt rendering, JSON parsing, batching."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from alex.lib.llm import Completer, ordered_parallel_map
from alex.lib.prompt_templates import load_prompt
from alex.lib.triage.catalog import catalog_prompt_text
from alex.lib.triage.inventory import MOVABLE_POPULATIONS
from alex.lib.triage.models import (
    Batch,
    BatchProposals,
    Catalog,
    Inventory,
    NoteEvidence,
    Proposal,
    Rubric,
)
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.storage import read_yaml_model, write_yaml_model

_PROMPT_NAME = "triage_proposal"
_PROPOSAL_MAX_TOKENS = 1024


class ProposalParseError(ValueError):
    pass


def extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        text = text.removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ProposalParseError(f"no JSON object in reply: {raw[:120]!r}")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise ProposalParseError(f"invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ProposalParseError("JSON reply is not an object")
    return data


def parse_proposal(raw: str, note_path: str) -> Proposal:
    data = extract_json_object(raw)
    data["note_path"] = note_path
    alternatives = data.get("alternatives")
    if isinstance(alternatives, list):
        data["alternatives"] = alternatives[:2]
    try:
        return Proposal.model_validate(data)
    except ValidationError as error:
        raise ProposalParseError(f"proposal failed validation: {error}") from error


def proposal_prompt(
    note: NoteEvidence,
    *,
    catalog_text: str,
    rubric_text: str,
    cluster_label: str,
    corrections: Sequence[str],
) -> str:
    return load_prompt(_PROMPT_NAME).render(
        rubric=rubric_text,
        catalog=catalog_text,
        cluster_label=cluster_label or "(none)",
        corrections=_corrections_text(corrections),
        evidence=_evidence_text(note),
    )


def generate_batch_proposals(
    batch: Batch,
    inventory: Inventory,
    *,
    catalog: Catalog,
    rubric: Rubric,
    completer: Completer,
    model: str,
    corrections: Sequence[str] = (),
    max_workers: int = 4,
) -> BatchProposals:
    catalog_text = catalog_prompt_text(catalog)
    by_path = {note.path: note for note in inventory.notes}
    # Vanished notes are ejected at batch open; without evidence there is
    # nothing to prompt with, so unknown paths are dropped here too.
    notes = [by_path[path] for path in batch.note_paths if path in by_path]

    def propose(note: NoteEvidence) -> Proposal:
        prompt = proposal_prompt(
            note,
            catalog_text=catalog_text,
            rubric_text=rubric.text,
            cluster_label=batch.label,
            corrections=corrections,
        )
        raw = completer.complete(
            prompt=prompt, model=model, max_tokens=_PROPOSAL_MAX_TOKENS
        )
        try:
            return _coerce_annotate_only(parse_proposal(raw, note.path), note)
        except ProposalParseError as error:
            repair_prompt = (
                f"{prompt}\n\nYour previous reply was not valid JSON: {error}."
                " Reply with ONLY the JSON object."
            )
        repaired = completer.complete(
            prompt=repair_prompt, model=model, max_tokens=_PROPOSAL_MAX_TOKENS
        )
        try:
            return _coerce_annotate_only(parse_proposal(repaired, note.path), note)
        except ProposalParseError as second_error:
            return Proposal(
                note_path=note.path,
                decision="skip",
                confidence="low",
                why=f"needs manual: {second_error}",
                needs_manual=True,
            )

    generated = ordered_parallel_map(notes, propose, max_workers=max_workers)
    return BatchProposals(
        batch_id=batch.batch_id,
        rubric_version=rubric.version,
        proposals=list(generated),
    )


def load_batch_proposals(
    paths: TriagePaths, batch_id: int, rubric_version: int
) -> BatchProposals | None:
    return read_yaml_model(
        paths.proposals_path(batch_id, rubric_version), BatchProposals
    )


def write_batch_proposals(paths: TriagePaths, proposals: BatchProposals) -> None:
    write_yaml_model(
        paths.proposals_path(proposals.batch_id, proposals.rubric_version), proposals
    )


def _coerce_annotate_only(proposal: Proposal, note: NoteEvidence) -> Proposal:
    """Annotate-only populations may only be area-linked or skipped."""
    if note.population in MOVABLE_POPULATIONS:
        return proposal
    if proposal.decision in ("area", "skip"):
        return proposal
    return proposal.model_copy(
        update={
            "decision": "skip",
            "target": "",
            "alternatives": [],
            "new_area": None,
            "why": f"annotate-only: {proposal.why}",
        }
    )


def _corrections_text(corrections: Sequence[str]) -> str:
    if not corrections:
        return "(none)"
    return "\n".join(f"- {correction}" for correction in corrections)


def _evidence_text(note: NoteEvidence) -> str:
    tags = ", ".join(note.tags) if note.tags else "(none)"
    wikilinks = ", ".join(note.wikilinks) if note.wikilinks else "(none)"
    return (
        f"Path: {note.path}\n"
        f"Title: {note.title}\n"
        f"Population: {note.population}\n"
        f"Tags: {tags}\n"
        f"Wikilinks: {wikilinks}\n"
        f"Word count: {note.word_count}\n"
        f"Has highlights: {note.has_highlights}\n"
        f"Snippet:\n{note.snippet}"
    )
