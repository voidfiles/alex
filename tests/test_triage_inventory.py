"""Discovery, eligibility, and evidence extraction over a fixture vault."""

import os
from pathlib import Path

from alex.lib.triage.inventory import (
    MOVABLE_POPULATIONS,
    build_inventory,
    discover_population_files,
    extract_evidence,
    is_eligible,
)


def write_note(
    path: Path, *, frontmatter: str = "", body: str = "A note body."
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{frontmatter}\n---\n\n{body}\n" if frontmatter else f"{body}\n"
    path.write_text(text, encoding="utf-8")
    return path


def test_discover_scans_root_nonrecursively_and_population_dirs_recursively(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_note(vault / "Loose idea.md")
    write_note(vault / "areas" / "writing" / "index.md")
    write_note(vault / "Clippings" / "2026" / "Saved article.md")
    write_note(vault / "Meetings" / "Platform sync.md")
    write_note(vault / "Weekly" / "2026-W27.md")
    write_note(vault / ".hidden draft.md")
    (vault / "Symlinked.md").symlink_to(vault / "Loose idea.md")

    discovered = discover_population_files(vault)

    assert discovered == [
        ("root", vault / "Loose idea.md"),
        ("clippings", vault / "Clippings" / "2026" / "Saved article.md"),
        ("meetings", vault / "Meetings" / "Platform sync.md"),
        ("weekly", vault / "Weekly" / "2026-W27.md"),
    ]


def test_movable_populations_are_root_and_clippings() -> None:
    assert frozenset({"root", "clippings"}) == MOVABLE_POPULATIONS


def test_is_eligible_skips_processed_notes() -> None:
    assert is_eligible({"processed": True}) is False
    assert is_eligible({"processed": False}) is True
    assert is_eligible({}) is True


def test_is_eligible_skips_notes_with_a_triage_decision() -> None:
    assert is_eligible({"triage": {"decision": "area", "target": "writing"}}) is False
    assert is_eligible({"triage": {"promising": True}}) is True


def test_is_eligible_skips_notes_with_any_workflow_state() -> None:
    assert is_eligible({"workflow": {"extracted": True}}) is False
    assert is_eligible({"workflow": {"extracted": "2026-07-01"}}) is False
    assert is_eligible({"workflow": {"highlighted": True}}) is False
    assert is_eligible({"workflow": {"processed": True}}) is False
    assert is_eligible({"workflow": {"highlighted": False, "extracted": False}}) is True
    assert is_eligible({"workflow": {}}) is True


def test_extract_evidence_builds_snippet_links_tags_and_counts(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    body = (
        "The ==key insight== is that **narrow areas** beat bundles.\n\n"
        "See [[areas/organizational-design/index|org design]] and "
        "[[Learning By Writing#Draft first]].\n"
    )
    note = write_note(
        vault / "Loose idea.md",
        frontmatter="title: Narrow areas beat bundles\ntags:\n  - pkm\n  - areas",
        body=body,
    )

    evidence = extract_evidence(vault, note, "root")

    assert evidence.path == "Loose idea.md"
    assert evidence.title == "Narrow areas beat bundles"
    assert evidence.population == "root"
    assert evidence.tags == ["pkm", "areas"]
    assert evidence.wikilinks == [
        "areas/organizational-design/index",
        "Learning By Writing",
    ]
    assert evidence.has_highlights is True
    assert evidence.mtime == note.stat().st_mtime
    assert evidence.word_count == len(body.split())
    assert evidence.snippet.startswith("The ==key insight==")
    assert "title:" not in evidence.snippet


def test_extract_evidence_caps_snippet_at_200_words_and_links_at_20(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    words = " ".join(f"word{i}" for i in range(250))
    links = " ".join(f"[[note-{i:02d}]]" for i in range(25))
    note = write_note(vault / "Big note.md", body=f"{words}\n\n{links}\n")

    evidence = extract_evidence(vault, note, "root")

    assert len(evidence.snippet.split()) == 200
    assert evidence.snippet.split()[-1] == "word199"
    assert len(evidence.wikilinks) == 20
    assert evidence.wikilinks[0] == "note-00"
    assert evidence.wikilinks[-1] == "note-19"
    assert evidence.title == "Big note"
    assert evidence.has_highlights is False
    assert evidence.tags == []


def test_extract_evidence_accepts_a_scalar_tags_value(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = write_note(
        vault / "Clippings" / "Tagged clip.md",
        frontmatter="tags: clipping",
        body="Saved article body.",
    )

    evidence = extract_evidence(vault, note, "clippings")

    assert evidence.tags == ["clipping"]
    assert evidence.population == "clippings"
    assert evidence.path == "Clippings/Tagged clip.md"


def test_build_inventory_includes_only_eligible_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_note(vault / "Fresh capture.md", body="An unprocessed thought.")
    write_note(
        vault / "Old import.md",
        frontmatter="processed: true",
        body="Already ran through the pipeline.",
    )
    write_note(
        vault / "Clippings" / "Mid-flight clip.md",
        frontmatter="workflow:\n  highlighted: true\n  extracted: true",
        body="Extraction suggestions pending.",
    )
    write_note(
        vault / "Already filed.md",
        frontmatter="triage:\n  decision: area\n  target: writing\n  status: decided",
        body="Decided last week.",
    )
    write_note(vault / "Meetings" / "Platform sync.md", body="Notes from the sync.")

    inventory = build_inventory(vault, None)

    assert [note.path for note in inventory.notes] == [
        "Fresh capture.md",
        "Meetings/Platform sync.md",
    ]
    assert inventory.notes[0].population == "root"
    assert inventory.notes[1].population == "meetings"
    assert inventory.generated != ""


def test_build_inventory_reuses_prior_evidence_when_mtime_is_unchanged(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    note = write_note(vault / "Stable note.md", body="Original body text.")
    original_ns = note.stat().st_mtime_ns
    first = build_inventory(vault, None)
    assert first.notes[0].snippet == "Original body text."

    note.write_text("Rewritten body that must not be re-read.\n", encoding="utf-8")
    os.utime(note, ns=(original_ns, original_ns))

    second = build_inventory(vault, first)

    assert [note.path for note in second.notes] == ["Stable note.md"]
    assert second.notes[0].snippet == "Original body text."


def test_build_inventory_refreshes_evidence_when_mtime_changes(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    note = write_note(vault / "Edited note.md", body="First version.")
    first = build_inventory(vault, None)

    note.write_text("Second version with new thinking.\n", encoding="utf-8")
    bumped = note.stat().st_mtime + 10
    os.utime(note, (bumped, bumped))

    second = build_inventory(vault, first)

    assert second.notes[0].snippet == "Second version with new thinking."
    assert second.notes[0].mtime != first.notes[0].mtime


def test_build_inventory_drops_newly_decided_and_vanished_notes(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    decided = write_note(vault / "Now decided.md", body="Decided body.")
    write_note(vault / "Now gone.md", body="Gone body.")
    first = build_inventory(vault, None)
    assert len(first.notes) == 2

    write_note(
        vault / "Now decided.md",
        frontmatter=(
            "triage:\n  decision: trash\n  status: decided\n  decided: 2026-07-12"
        ),
        body="Decided body.",
    )
    bumped = decided.stat().st_mtime + 10
    os.utime(decided, (bumped, bumped))
    (vault / "Now gone.md").unlink()

    second = build_inventory(vault, first)

    assert second.notes == []
