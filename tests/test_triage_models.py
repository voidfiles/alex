"""Tests for triage models, storage helpers, and filesystem layout."""

import hashlib
from pathlib import Path

import yaml

from alex.lib.triage.models import (
    Inventory,
    NewAreaProposal,
    NoteEvidence,
    PendingAreas,
    Proposal,
    TriageBlock,
)
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.storage import (
    atomic_write_text,
    read_yaml_model,
    write_yaml_model,
)


def test_triage_block_defaults_to_no_decision() -> None:
    block = TriageBlock()
    assert block.decision is None
    assert block.target == ""
    assert block.promising is False
    assert block.status is None
    assert block.decided == ""
    assert block.applied == ""


def test_proposal_serializes_to_plain_json_types() -> None:
    proposal = Proposal(
        note_path="Some Note.md",
        decision="area",
        target="learning-science",
        confidence="high",
        why="Clearly about spaced repetition.",
    )

    dumped = proposal.model_dump(mode="json")

    assert dumped["decision"] == "area"
    assert dumped["new_area"] is None
    assert dumped["alternatives"] == []
    assert dumped["needs_manual"] is False


def test_atomic_write_text_creates_parents_and_leaves_no_temp_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state" / "deep" / "inventory.yaml"

    atomic_write_text(target, "generated: now\n")

    assert target.read_text(encoding="utf-8") == "generated: now\n"
    assert list(target.parent.iterdir()) == [target]


def test_atomic_write_text_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "file.yaml"
    atomic_write_text(target, "first")

    atomic_write_text(target, "second")

    assert target.read_text(encoding="utf-8") == "second"


def test_read_yaml_model_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert read_yaml_model(tmp_path / "absent.yaml", Inventory) is None


def test_read_yaml_model_returns_none_for_corrupt_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("{unclosed: [", encoding="utf-8")

    assert read_yaml_model(path, Inventory) is None


def test_read_yaml_model_returns_none_for_wrong_shape(tmp_path: Path) -> None:
    path = tmp_path / "wrong.yaml"
    path.write_text("notes: not-a-list\n", encoding="utf-8")

    assert read_yaml_model(path, Inventory) is None


def test_yaml_model_roundtrip_preserves_note_evidence(tmp_path: Path) -> None:
    inventory = Inventory(
        generated="2026-07-12T09:00:00",
        notes=[
            NoteEvidence(
                path="Ideas about spaced repetition.md",
                title="Ideas about spaced repetition",
                population="root",
                tags=["learning"],
                wikilinks=["areas/learning-science/index"],
                snippet="Spaced repetition works because recall effort is the point.",
                has_highlights=True,
                mtime=123.5,
                word_count=87,
            )
        ],
    )
    path = tmp_path / "inventory.yaml"

    write_yaml_model(path, inventory)

    assert read_yaml_model(path, Inventory) == inventory


def test_write_yaml_model_keeps_field_order_and_unicode(tmp_path: Path) -> None:
    pending = PendingAreas(
        areas=[
            NewAreaProposal(
                slug="cafe-notes",
                name="Café Notes",
                description="Notes about café culture",
            )
        ]
    )
    path = tmp_path / "pending-areas.yaml"

    write_yaml_model(path, pending)

    raw = path.read_text(encoding="utf-8")
    assert "Café" in raw
    data = yaml.safe_load(raw)
    assert list(data["areas"][0]) == ["slug", "name", "description"]


def test_triage_paths_derive_from_vault_root(tmp_path: Path) -> None:
    paths = TriagePaths(vault_root=tmp_path)

    assert paths.state_dir == tmp_path / ".claude" / "triage"
    assert paths.inventory_path == paths.state_dir / "inventory.yaml"
    assert paths.cluster_map_path == paths.state_dir / "cluster-map.yaml"
    assert paths.catalog_path == paths.state_dir / "catalog.yaml"
    assert paths.embeddings_cache_path == paths.state_dir / "embeddings.jsonl"
    assert paths.proposals_dir == paths.state_dir / "proposals"
    assert paths.session_path == paths.state_dir / "session.yaml"
    assert paths.pending_areas_path == paths.state_dir / "pending-areas.yaml"
    assert paths.project_dir == tmp_path / "projects" / "vault-triage"
    assert paths.ledger_path == paths.project_dir / "ledger.jsonl"
    assert paths.rubric_path == paths.project_dir / "rubric.md"
    assert paths.processing_log_path == tmp_path / "_meta" / "processing-log.md"


def test_triage_lock_path_lives_in_user_cache_keyed_by_vault_root(
    tmp_path: Path,
) -> None:
    paths = TriagePaths(vault_root=tmp_path)
    digest = hashlib.sha256(str(tmp_path.resolve()).encode()).hexdigest()[:12]

    assert paths.lock_path == (
        Path.home() / ".cache" / "alex" / f"triage-{digest}.lock"
    )


def test_triage_lock_path_differs_per_vault(tmp_path: Path) -> None:
    lock_a = TriagePaths(vault_root=tmp_path / "vault-a").lock_path
    lock_b = TriagePaths(vault_root=tmp_path / "vault-b").lock_path

    assert lock_a != lock_b


def test_proposals_path_encodes_batch_and_rubric_version(tmp_path: Path) -> None:
    paths = TriagePaths(vault_root=tmp_path)

    assert paths.proposals_path(3, 2) == (
        paths.proposals_dir / "batch-003.rubric-v02.yaml"
    )
