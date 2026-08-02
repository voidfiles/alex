"""Catalog derivation from areas/*/index.md and resources/ topic folders."""

import os
from pathlib import Path

from alex.lib.triage.catalog import (
    build_catalog,
    catalog_prompt_text,
    load_or_build_catalog,
)
from alex.lib.triage.models import Catalog, CatalogEntry
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.storage import read_yaml_model, write_yaml_model


def write_area_index(
    vault: Path,
    slug: str,
    *,
    description: str,
    name: str | None = None,
    evidence: list[str] | None = None,
) -> Path:
    index = vault / "areas" / slug / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: area",
        "created: 2026-06-05",
        f"description: {description}",
        "---",
        "",
    ]
    if name is not None:
        lines.extend([f"# {name}", ""])
    if evidence is not None:
        lines.extend(["## Discovery Evidence", ""])
        lines.extend(f"- {bullet}" for bullet in evidence)
        lines.extend(["", "## Notes", "", "- [[A filed note]]"])
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index


def test_build_catalog_reads_slug_name_description_and_evidence(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(
        vault,
        "organizational-design",
        description="How teams coordinate work across boundaries",
        name="Organizational Design",
        evidence=[
            "[[Meeting with platform team]] raised ownership boundaries",
            "14 root notes reference team topology tradeoffs",
        ],
    )
    write_area_index(vault, "learning-science", description="How people learn")

    catalog = build_catalog(vault)

    assert [entry.slug for entry in catalog.areas] == [
        "learning-science",
        "organizational-design",
    ]
    org = catalog.areas[1]
    assert org.name == "Organizational Design"
    assert org.description == "How teams coordinate work across boundaries"
    assert org.evidence == [
        "[[Meeting with platform team]] raised ownership boundaries",
        "14 root notes reference team topology tradeoffs",
    ]
    fallback = catalog.areas[0]
    assert fallback.name == "learning-science"
    assert fallback.evidence == []


def test_build_catalog_lists_resource_dirs_and_skips_files_and_dotdirs(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / "resources" / "permanent-notes").mkdir(parents=True)
    (vault / "resources" / "learning-science").mkdir()
    (vault / "resources" / ".obsidian-cache").mkdir()
    (vault / "resources" / "index.md").write_text("# Resources\n", encoding="utf-8")

    catalog = build_catalog(vault)

    assert catalog.resource_topics == ["learning-science", "permanent-notes"]
    assert catalog.areas == []


def test_build_catalog_records_source_mtimes_for_cache_invalidation(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    index = write_area_index(vault, "writing", description="Craft of writing")
    (vault / "resources" / "books").mkdir(parents=True)

    catalog = build_catalog(vault)

    assert catalog.source_mtimes == {
        "areas/writing/index.md": index.stat().st_mtime,
        "resources": (vault / "resources").stat().st_mtime,
    }


def test_build_catalog_handles_a_vault_without_areas_or_resources(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    assert build_catalog(vault) == Catalog()


def test_catalog_prompt_text_lists_areas_then_resource_topics() -> None:
    catalog = Catalog(
        areas=[
            CatalogEntry(
                slug="writing",
                name="Writing",
                description="Craft of writing",
            )
        ],
        resource_topics=["books", "permanent-notes"],
    )

    assert catalog_prompt_text(catalog) == (
        "## Areas\n"
        "- writing: Craft of writing\n"
        "\n"
        "## Resource topics\n"
        "- books\n"
        "- permanent-notes"
    )


def test_load_or_build_catalog_builds_and_writes_cache_when_missing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)

    catalog = load_or_build_catalog(paths)

    assert [entry.slug for entry in catalog.areas] == ["writing"]
    assert read_yaml_model(paths.catalog_path, Catalog) == catalog


def test_load_or_build_catalog_returns_cache_when_sources_are_unchanged(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)
    load_or_build_catalog(paths)

    cached = read_yaml_model(paths.catalog_path, Catalog)
    assert cached is not None
    cached.areas[0].description = "sentinel only present in the cache"
    write_yaml_model(paths.catalog_path, cached)

    catalog = load_or_build_catalog(paths)

    assert catalog.areas[0].description == "sentinel only present in the cache"


def test_load_or_build_catalog_rebuilds_when_an_index_mtime_changes(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    index = write_area_index(vault, "writing", description="Old description")
    paths = TriagePaths(vault_root=vault)
    load_or_build_catalog(paths)

    write_area_index(vault, "writing", description="New description")
    bumped = index.stat().st_mtime + 10
    os.utime(index, (bumped, bumped))

    catalog = load_or_build_catalog(paths)

    assert catalog.areas[0].description == "New description"
    refreshed = read_yaml_model(paths.catalog_path, Catalog)
    assert refreshed is not None
    assert refreshed.areas[0].description == "New description"


def test_load_or_build_catalog_rebuilds_when_a_new_area_appears(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)
    load_or_build_catalog(paths)

    write_area_index(vault, "learning-science", description="How people learn")

    catalog = load_or_build_catalog(paths)

    assert [entry.slug for entry in catalog.areas] == ["learning-science", "writing"]


def test_load_or_build_catalog_rebuilds_when_cache_is_corrupt(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)
    paths.catalog_path.parent.mkdir(parents=True)
    paths.catalog_path.write_text("{broken yaml: [", encoding="utf-8")

    catalog = load_or_build_catalog(paths)

    assert [entry.slug for entry in catalog.areas] == ["writing"]
