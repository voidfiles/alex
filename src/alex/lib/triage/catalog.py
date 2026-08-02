"""Live area and resource catalog derived from the vault's PARA folders."""

from __future__ import annotations

from pathlib import Path

from alex.lib.triage.frontmatter import read_frontmatter, split_frontmatter
from alex.lib.triage.models import Catalog, CatalogEntry
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.storage import read_yaml_model, write_yaml_model

DISCOVERY_EVIDENCE_HEADING = "## Discovery Evidence"


def build_catalog(vault_root: Path) -> Catalog:
    areas = [
        _catalog_entry(index_path)
        for index_path in sorted((vault_root / "areas").glob("*/index.md"))
    ]
    resources_dir = vault_root / "resources"
    resource_topics: list[str] = []
    if resources_dir.is_dir():
        resource_topics = sorted(
            child.name
            for child in resources_dir.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )
    return Catalog(
        areas=areas,
        resource_topics=resource_topics,
        source_mtimes=_source_mtimes(vault_root),
    )


def load_or_build_catalog(paths: TriagePaths) -> Catalog:
    cached = read_yaml_model(paths.catalog_path, Catalog)
    current = _source_mtimes(paths.vault_root)
    if cached is not None and cached.source_mtimes == current:
        return cached
    catalog = build_catalog(paths.vault_root)
    write_yaml_model(paths.catalog_path, catalog)
    return catalog


def catalog_prompt_text(catalog: Catalog) -> str:
    lines = ["## Areas"]
    lines.extend(f"- {entry.slug}: {entry.description}" for entry in catalog.areas)
    lines.extend(["", "## Resource topics"])
    lines.extend(f"- {topic}" for topic in catalog.resource_topics)
    return "\n".join(lines)


def _catalog_entry(index_path: Path) -> CatalogEntry:
    text = index_path.read_text(encoding="utf-8")
    slug = index_path.parent.name
    description = read_frontmatter(text).get("description")
    return CatalogEntry(
        slug=slug,
        name=_first_heading(text) or slug,
        description=str(description) if description else "",
        evidence=_discovery_evidence(text),
    )


def _source_mtimes(vault_root: Path) -> dict[str, float]:
    mtimes = {
        index_path.relative_to(vault_root).as_posix(): index_path.stat().st_mtime
        for index_path in sorted((vault_root / "areas").glob("*/index.md"))
    }
    resources_dir = vault_root / "resources"
    if resources_dir.is_dir():
        mtimes["resources"] = resources_dir.stat().st_mtime
    return mtimes


def _first_heading(text: str) -> str:
    _, body = split_frontmatter(text)
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _discovery_evidence(text: str) -> list[str]:
    _, body = split_frontmatter(text)
    bullets: list[str] = []
    in_section = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line == DISCOVERY_EVIDENCE_HEADING:
            in_section = True
        elif in_section and line.startswith("## "):
            break
        elif in_section and line.startswith("- "):
            bullets.append(line[2:].strip())
    return bullets
