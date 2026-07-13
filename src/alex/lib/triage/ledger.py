"""Append-only corrections ledger stored as jsonl inside the vault."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from alex.lib.triage.models import LedgerEvent


def append_event(ledger_path: Path, event: LedgerEvent) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.model_dump(mode="json")) + "\n")


def read_events(
    ledger_path: Path, *, since_version: int | None = None
) -> list[LedgerEvent]:
    if not ledger_path.exists():
        return []
    events: list[LedgerEvent] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = LedgerEvent.model_validate_json(line)
        except ValidationError:
            continue
        if since_version is not None and event.rubric_version < since_version:
            continue
        events.append(event)
    return events
