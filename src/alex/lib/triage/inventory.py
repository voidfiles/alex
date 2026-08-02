"""Note discovery, eligibility, and evidence extraction for the triage sweep."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alex.lib.triage.frontmatter import read_frontmatter, split_frontmatter
from alex.lib.triage.models import Inventory, NoteEvidence, Population

POPULATION_DIRS: dict[Population, str] = {
    "clippings": "Clippings",
    "meetings": "Meetings",
    "weekly": "Weekly",
}
MOVABLE_POPULATIONS: frozenset[Population] = frozenset({"root", "clippings"})
SNIPPET_WORDS = 200
MAX_WIKILINKS = 20
WIKILINK_TARGET_PATTERN = re.compile(r"\[\[([^\]|#]+)")


def discover_population_files(vault_root: Path) -> list[tuple[Population, Path]]:
    files: list[tuple[Population, Path]] = []
    for path in sorted(vault_root.glob("*.md")):
        if _is_note(path, vault_root):
            files.append(("root", path))
    for population, dir_name in POPULATION_DIRS.items():
        for path in sorted((vault_root / dir_name).rglob("*.md")):
            if _is_note(path, vault_root):
                files.append((population, path))
    return files


def is_eligible(fm: dict[str, Any]) -> bool:
    if fm.get("processed") is True:
        return False
    triage = fm.get("triage")
    if isinstance(triage, dict) and triage.get("decision"):
        return False
    workflow = fm.get("workflow")
    return not (isinstance(workflow, dict) and any(workflow.values()))


def extract_evidence(
    vault_root: Path, md_path: Path, population: Population
) -> NoteEvidence:
    text = md_path.read_text(encoding="utf-8")
    frontmatter = read_frontmatter(text)
    _, body = split_frontmatter(text)
    words = body.split()
    title = frontmatter.get("title")
    return NoteEvidence(
        path=md_path.relative_to(vault_root).as_posix(),
        title=title if isinstance(title, str) and title else md_path.stem,
        population=population,
        tags=_string_list(frontmatter.get("tags")),
        wikilinks=WIKILINK_TARGET_PATTERN.findall(body)[:MAX_WIKILINKS],
        snippet=" ".join(words[:SNIPPET_WORDS]),
        has_highlights="==" in body or "**" in body,
        mtime=md_path.stat().st_mtime,
        word_count=len(words),
    )


def build_inventory(vault_root: Path, previous: Inventory | None) -> Inventory:
    prior = {note.path: note for note in previous.notes} if previous else {}
    notes: list[NoteEvidence] = []
    for population, md_path in discover_population_files(vault_root):
        rel_path = md_path.relative_to(vault_root).as_posix()
        cached = prior.get(rel_path)
        if cached is not None and cached.mtime == md_path.stat().st_mtime:
            notes.append(cached)
            continue
        frontmatter = read_frontmatter(md_path.read_text(encoding="utf-8"))
        if not is_eligible(frontmatter):
            continue
        notes.append(extract_evidence(vault_root, md_path, population))
    return Inventory(generated=datetime.now(UTC).isoformat(), notes=notes)


def _is_note(path: Path, vault_root: Path) -> bool:
    if path.is_symlink():
        return False
    parts = path.relative_to(vault_root).parts
    return all(not part.startswith(".") for part in parts)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []
