import json
from pathlib import Path

from alex.lib.triage.ledger import append_event, read_events
from alex.lib.triage.models import LedgerEvent, LedgerEventKind


def make_event(
    *,
    note: str = "note.md",
    rubric_version: int = 1,
    event: LedgerEventKind = "approve",
) -> LedgerEvent:
    return LedgerEvent(
        ts="2026-07-12T10:00:00",
        note=note,
        batch=3,
        rubric_version=rubric_version,
        event=event,
        proposal={"decision": "area", "target": "learning-science"},
        correction=None,
        reason="",
    )


def test_append_event_creates_parent_dirs_and_round_trips(tmp_path: Path) -> None:
    ledger = tmp_path / "projects" / "vault-triage" / "ledger.jsonl"
    first = make_event(note="a.md")
    second = make_event(note="b.md", event="reject")

    append_event(ledger, first)
    append_event(ledger, second)

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["note"] == "a.md"
    assert read_events(ledger) == [first, second]


def test_read_events_returns_empty_list_when_ledger_missing(tmp_path: Path) -> None:
    assert read_events(tmp_path / "absent.jsonl") == []


def test_read_events_skips_malformed_lines(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    good = make_event(note="keep.md")
    lines = [
        good.model_dump_json(),
        "{ this is not json",
        json.dumps({"ts": "2026-07-12", "note": "half.md"}),
        json.dumps(["a", "list", "not", "an", "object"]),
        "",
    ]
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert read_events(ledger) == [good]


def test_read_events_since_version_keeps_only_matching_rubric_versions(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    for version in (1, 2, 3):
        append_event(ledger, make_event(note=f"v{version}.md", rubric_version=version))

    since_two = read_events(ledger, since_version=2)

    assert [event.note for event in since_two] == ["v2.md", "v3.md"]
    assert [event.note for event in read_events(ledger)] == [
        "v1.md",
        "v2.md",
        "v3.md",
    ]
