"""Tests for triage proposal generation, parsing, and caching."""

import json
from pathlib import Path

import pytest

from alex.lib.prompt_templates import load_prompt
from alex.lib.triage.models import (
    Batch,
    BatchProposals,
    Catalog,
    CatalogEntry,
    Inventory,
    NoteEvidence,
    Population,
    Proposal,
    Rubric,
)
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.proposals import (
    ProposalParseError,
    extract_json_object,
    generate_batch_proposals,
    load_batch_proposals,
    parse_proposal,
    proposal_prompt,
    write_batch_proposals,
)


class QueueCompleter:
    """Pops scripted replies in call order; records every prompt."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def valid_reply(target: str = "learning-science") -> str:
    return json.dumps(
        {
            "decision": "area",
            "target": target,
            "confidence": "high",
            "why": "The note is about spaced repetition.",
            "alternatives": [],
            "new_area": None,
        }
    )


def trash_reply() -> str:
    return json.dumps(
        {
            "decision": "trash",
            "target": "",
            "confidence": "medium",
            "why": "Empty accidental capture.",
            "alternatives": [],
            "new_area": None,
        }
    )


def make_note(path: str, title: str, population: Population = "root") -> NoteEvidence:
    return NoteEvidence(
        path=path,
        title=title,
        population=population,
        tags=["learning"],
        snippet="Spaced repetition beats cramming.",
    )


def make_inventory(notes: list[NoteEvidence]) -> Inventory:
    return Inventory(generated="2026-07-12T00:00:00", notes=notes)


def make_catalog() -> Catalog:
    return Catalog(
        areas=[
            CatalogEntry(
                slug="learning-science",
                name="Learning Science",
                description="How people learn and retain knowledge",
            )
        ],
        resource_topics=["permanent-notes"],
    )


def make_rubric() -> Rubric:
    return Rubric(version=3, text="## Triage rules\n1. Prefer narrow areas.")


def test_triage_proposal_prompt_has_exact_placeholder_set() -> None:
    template = load_prompt("triage_proposal")
    assert template.version == "v001"
    assert template.placeholders() == frozenset(
        {"rubric", "catalog", "cluster_label", "corrections", "evidence"}
    )


def test_extract_json_object_parses_bare_object() -> None:
    assert extract_json_object('{"decision": "trash"}') == {"decision": "trash"}


def test_extract_json_object_strips_code_fences_and_prose() -> None:
    raw = 'Sure!\n```json\n{"decision": "trash", "target": ""}\n```\n'
    assert extract_json_object(raw) == {"decision": "trash", "target": ""}


def test_extract_json_object_raises_on_reply_without_object() -> None:
    with pytest.raises(ProposalParseError):
        extract_json_object("I cannot decide where this note belongs.")


def test_extract_json_object_raises_on_json_array() -> None:
    with pytest.raises(ProposalParseError):
        extract_json_object('["not", "an", "object"]')


def test_parse_proposal_injects_note_path_and_validates() -> None:
    proposal = parse_proposal(valid_reply(), "Note A.md")
    assert proposal.note_path == "Note A.md"
    assert proposal.decision == "area"
    assert proposal.target == "learning-science"
    assert proposal.confidence == "high"
    assert proposal.new_area is None
    assert proposal.needs_manual is False


def test_parse_proposal_wraps_schema_violation_in_parse_error() -> None:
    raw = json.dumps({"decision": "banana", "target": ""})
    with pytest.raises(ProposalParseError):
        parse_proposal(raw, "Note A.md")


def test_parse_proposal_truncates_alternatives_to_first_two() -> None:
    raw = json.dumps(
        {
            "decision": "area",
            "target": "learning-science",
            "confidence": "medium",
            "why": "Learning content.",
            "alternatives": ["writing", "memory", "habits", "focus"],
            "new_area": None,
        }
    )
    proposal = parse_proposal(raw, "Note A.md")
    assert proposal.alternatives == ["writing", "memory"]


def test_proposal_prompt_renders_rubric_catalog_and_evidence() -> None:
    prompt = proposal_prompt(
        make_note("Note A.md", "Spaced repetition"),
        catalog_text="- learning-science: How people learn",
        rubric_text="1. Prefer narrow areas.",
        cluster_label="memory",
        corrections=["stop filing meetings as areas"],
    )
    assert "1. Prefer narrow areas." in prompt
    assert "- learning-science: How people learn" in prompt
    assert "memory" in prompt
    assert "- stop filing meetings as areas" in prompt
    assert "Title: Spaced repetition" in prompt
    assert "Spaced repetition beats cramming." in prompt


def test_proposal_prompt_marks_empty_label_and_corrections_as_none() -> None:
    prompt = proposal_prompt(
        make_note("Note A.md", "Spaced repetition"),
        catalog_text="- learning-science: How people learn",
        rubric_text="1. Prefer narrow areas.",
        cluster_label="",
        corrections=(),
    )
    assert prompt.count("(none)") >= 2


def test_generate_batch_proposals_parses_valid_reply_per_note() -> None:
    completer = QueueCompleter([valid_reply()])
    result = generate_batch_proposals(
        Batch(batch_id=1, note_paths=["Note A.md"]),
        make_inventory([make_note("Note A.md", "Spaced repetition")]),
        catalog=make_catalog(),
        rubric=make_rubric(),
        completer=completer,
        model="fake/model",
        max_workers=1,
    )
    assert result.batch_id == 1
    assert result.rubric_version == 3
    assert [p.note_path for p in result.proposals] == ["Note A.md"]
    assert result.proposals[0].decision == "area"
    assert result.proposals[0].target == "learning-science"
    assert "learning-science" in completer.prompts[0]


def test_generate_batch_proposals_repairs_after_one_invalid_reply() -> None:
    completer = QueueCompleter(["hmm, this looks like learning", valid_reply()])
    result = generate_batch_proposals(
        Batch(batch_id=1, note_paths=["Note A.md"]),
        make_inventory([make_note("Note A.md", "Spaced repetition")]),
        catalog=make_catalog(),
        rubric=make_rubric(),
        completer=completer,
        model="fake/model",
        max_workers=1,
    )
    proposal = result.proposals[0]
    assert proposal.decision == "area"
    assert proposal.needs_manual is False
    assert len(completer.prompts) == 2
    assert completer.prompts[1].startswith(completer.prompts[0])
    assert "Your previous reply was not valid JSON" in completer.prompts[1]
    assert completer.prompts[1].endswith("Reply with ONLY the JSON object.")


def test_generate_batch_proposals_marks_needs_manual_after_two_failures() -> None:
    completer = QueueCompleter(["no json here", "still no json"])
    result = generate_batch_proposals(
        Batch(batch_id=1, note_paths=["Note A.md"]),
        make_inventory([make_note("Note A.md", "Spaced repetition")]),
        catalog=make_catalog(),
        rubric=make_rubric(),
        completer=completer,
        model="fake/model",
        max_workers=1,
    )
    proposal = result.proposals[0]
    assert proposal.decision == "skip"
    assert proposal.confidence == "low"
    assert proposal.needs_manual is True
    assert proposal.why.startswith("needs manual: ")
    assert len(completer.prompts) == 2


def test_generate_batch_proposals_keeps_batch_order_with_one_worker() -> None:
    completer = QueueCompleter([valid_reply(), trash_reply()])
    result = generate_batch_proposals(
        Batch(batch_id=2, note_paths=["A.md", "B.md"]),
        make_inventory([make_note("A.md", "Alpha"), make_note("B.md", "Beta")]),
        catalog=make_catalog(),
        rubric=make_rubric(),
        completer=completer,
        model="fake/model",
        max_workers=1,
    )
    assert [p.note_path for p in result.proposals] == ["A.md", "B.md"]
    assert result.proposals[0].decision == "area"
    assert result.proposals[1].decision == "trash"
    assert "Title: Alpha" in completer.prompts[0]
    assert "Title: Beta" in completer.prompts[1]


def test_generate_batch_proposals_skips_paths_missing_from_inventory() -> None:
    completer = QueueCompleter([valid_reply()])
    result = generate_batch_proposals(
        Batch(batch_id=3, note_paths=["ghost.md", "A.md"]),
        make_inventory([make_note("A.md", "Alpha")]),
        catalog=make_catalog(),
        rubric=make_rubric(),
        completer=completer,
        model="fake/model",
        max_workers=1,
    )
    assert [p.note_path for p in result.proposals] == ["A.md"]


def test_generate_batch_proposals_renders_batch_label_in_prompt() -> None:
    completer = QueueCompleter([valid_reply()])
    generate_batch_proposals(
        Batch(batch_id=4, label="memory-techniques", note_paths=["Note A.md"]),
        make_inventory([make_note("Note A.md", "Spaced repetition")]),
        catalog=make_catalog(),
        rubric=make_rubric(),
        completer=completer,
        model="fake/model",
        max_workers=1,
    )
    before_corrections = completer.prompts[0].split("## Corrections")[0]
    assert "memory-techniques" in before_corrections
    assert "(none)" not in before_corrections


def test_generate_batch_proposals_coerces_annotate_only_trash_to_skip() -> None:
    completer = QueueCompleter([trash_reply(), valid_reply()])
    result = generate_batch_proposals(
        Batch(batch_id=5, note_paths=["Meetings/Standup.md", "Meetings/1-1.md"]),
        make_inventory(
            [
                make_note("Meetings/Standup.md", "Standup", "meetings"),
                make_note("Meetings/1-1.md", "One on one", "meetings"),
            ]
        ),
        catalog=make_catalog(),
        rubric=make_rubric(),
        completer=completer,
        model="fake/model",
        max_workers=1,
    )
    coerced, kept = result.proposals
    assert coerced.decision == "skip"
    assert coerced.target == ""
    assert coerced.why == "annotate-only: Empty accidental capture."
    assert coerced.alternatives == []
    assert kept.decision == "area"
    assert kept.target == "learning-science"


def test_batch_proposals_cache_roundtrip(tmp_path: Path) -> None:
    paths = TriagePaths(vault_root=tmp_path)
    proposals = BatchProposals(
        batch_id=7,
        rubric_version=2,
        proposals=[
            Proposal(
                note_path="Note A.md",
                decision="area",
                target="learning-science",
                confidence="medium",
                why="Looks like learning content.",
            )
        ],
    )
    write_batch_proposals(paths, proposals)
    cache_file = paths.proposals_path(7, 2)
    assert cache_file.is_file()
    assert cache_file.name == "batch-007.rubric-v02.yaml"
    assert load_batch_proposals(paths, 7, 2) == proposals


def test_load_batch_proposals_returns_none_when_cache_missing(tmp_path: Path) -> None:
    paths = TriagePaths(vault_root=tmp_path)
    assert load_batch_proposals(paths, 1, 1) is None
