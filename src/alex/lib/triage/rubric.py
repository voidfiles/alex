"""Versioned, hand-editable triage rubric stored as markdown in the vault."""

from __future__ import annotations

from pathlib import Path

from alex.lib.triage.frontmatter import (
    assemble_frontmatter,
    read_frontmatter,
    split_frontmatter,
)
from alex.lib.triage.models import Rubric
from alex.lib.triage.storage import atomic_write_text

DEFAULT_RUBRIC_TEXT = """\
## Triage rules

1. Prefer archive over force-fit. A note that matches no catalog area with
   confidence goes to archives, not into the nearest-sounding area.
2. Meetings and 1:1 notes are weak area evidence. Associate one with an area
   only when the topic is unmistakable; never justify a new area with them.
3. Prefer narrow durable domains over bundles. Two crisp areas beat one blob.
4. Work deliverables with a deadline are project material, not areas. Skip
   them for manual project filing instead of forcing an area.
5. A note about doing the job supports a work area, not a general life area.
6. Propose a new area only when several notes point at the same durable
   domain and nothing in the catalog fits.
7. Clippings that were read once and never linked go to archives/clippings,
   not resources.
8. Trash only what is empty, duplicated, or content-free. When in doubt,
   archive.

## Atomic note rules

1. One claim per note; the title states the claim.
2. The body stands alone: 2-4 short paragraphs in Alex's plain first-person
   register, own words, no long quotes.
3. Related links may only point to permanent notes that already exist.
4. Draft only from notes Alex flagged promising; volume is not the goal.
"""


def load_rubric(path: Path) -> Rubric:
    if not path.exists():
        rubric = Rubric(version=1, text=DEFAULT_RUBRIC_TEXT)
        save_rubric(path, rubric)
        return rubric
    raw = path.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw)
    version_value = read_frontmatter(raw).get("version")
    version = version_value if isinstance(version_value, int) else 1
    return Rubric(version=version, text=body)


def save_rubric(path: Path, rubric: Rubric) -> None:
    content = assemble_frontmatter(f"version: {rubric.version}", rubric.text)
    atomic_write_text(path, content)
