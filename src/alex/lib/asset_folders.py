"""Building vault asset folders from PDF and EPUB sources."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from alex.lib.asset_metadata import AssetMetadata
from alex.lib.converters.to_markdown import Markdowner, ToMarkdownConfig
from alex.lib.document_sources import canonicalize_name, copy_file, split_authors
from alex.lib.llm import Completer, LiteLlmCompleter, resolve_asset_naming_model
from alex.lib.markdown_structure import table_of_contents_markdown

DEFAULT_VAULT_ASSET_ROOT = Path("/Users/alex/Dropbox/obsidian/Alex3/assets")

SUPPORTED_SOURCE_EXTENSIONS = frozenset({".epub", ".pdf"})


class UnsupportedAssetSourceError(ValueError):
    pass


def validate_supported_source(source: Path) -> None:
    source_extension = source.suffix.lower()
    if source_extension in SUPPORTED_SOURCE_EXTENSIONS:
        return
    supported_extensions = ", ".join(sorted(SUPPORTED_SOURCE_EXTENSIONS))
    raise UnsupportedAssetSourceError(
        f"Unsupported file type '{source_extension}'. "
        f"Supported file types: {supported_extensions}"
    )


class AssetNamer(Protocol):
    def __call__(self, asset_input: AssetNameInput) -> AssetName: ...


class AssetDirectoryExistsError(FileExistsError):
    pass


class AssetNamingError(ValueError):
    pass


@dataclass(frozen=True)
class ToAssetConfig:
    source: Path
    asset_root: Path = DEFAULT_VAULT_ASSET_ROOT
    force: bool = False


@dataclass(frozen=True)
class ToAssetOutput:
    asset_dir: Path
    source_path: Path
    markdown_path: Path
    headers_path: Path
    metadata_path: Path | None = None
    canonical_name_path: Path | None = None


@dataclass(frozen=True)
class AssetNameInput:
    source: Path
    markdown: str
    headers: str


@dataclass(frozen=True)
class AssetName:
    title: str
    authors: tuple[str, ...]
    canonical_name: str


@dataclass(frozen=True)
class LlmAssetNamer:
    completer: Completer
    model: str = field(default_factory=resolve_asset_naming_model)
    max_tokens: int = 200

    def __call__(self, asset_input: AssetNameInput) -> AssetName:
        response = self.completer.complete(
            prompt=asset_name_prompt(asset_input),
            model=self.model,
            max_tokens=self.max_tokens,
        )
        return asset_name_from_llm_response(response)


def build_asset(
    config: ToAssetConfig,
    *,
    pdf_markdowner: Markdowner,
    epub_markdowner: Markdowner,
    asset_namer: AssetNamer,
) -> ToAssetOutput:
    markdowner = (
        epub_markdowner if config.source.suffix.lower() == ".epub" else pdf_markdowner
    )
    return build_markdown_asset(
        config=config,
        markdowner=markdowner,
        asset_namer=asset_namer,
    )


def build_markdown_asset(
    *,
    config: ToAssetConfig,
    markdowner: Markdowner,
    asset_namer: AssetNamer,
) -> ToAssetOutput:
    work_dir = temporary_asset_dir(asset_root=config.asset_root, source=config.source)
    prepare_work_dir(work_dir=work_dir, source=config.source)

    markdown_path = work_dir / f"{config.source.stem}.md"
    result = markdowner(
        ToMarkdownConfig(
            source=config.source,
            output_dir=work_dir,
            name=config.source.stem,
        )
    )
    if result.asset != markdown_path:
        copy_file(result.asset, markdown_path)

    markdown = markdown_path.read_text(encoding="utf-8")
    headers = table_of_contents_markdown(markdown)
    headers_path = work_dir / "headers.md"
    headers_path.write_text(
        headers,
        encoding="utf-8",
    )

    asset_name = asset_namer(
        AssetNameInput(source=config.source, markdown=markdown, headers=headers)
    )
    final_dir = config.asset_root / asset_name.canonical_name
    prepare_final_asset_dir(
        final_dir=final_dir,
        source=config.source,
        work_dir=work_dir,
        force=config.force,
    )
    write_asset_name_cache(work_dir=work_dir, asset_name=asset_name)
    final_markdown = rename_markdown_to_canonical_name(
        markdown_path=markdown_path,
        canonical_name=asset_name.canonical_name,
    )
    source_path = move_source_to_canonical_asset_path(
        source=config.source,
        asset_dir=work_dir,
        canonical_name=asset_name.canonical_name,
    )
    shutil.move(str(work_dir), str(final_dir))
    cleanup_tmp_parent(work_dir)

    return ToAssetOutput(
        asset_dir=final_dir,
        source_path=final_dir / source_path.name,
        markdown_path=final_dir / final_markdown.name,
        headers_path=final_dir / headers_path.name,
        metadata_path=final_dir / "metadata.json",
        canonical_name_path=final_dir / "canonical_name.txt",
    )


def llm_asset_namer(asset_input: AssetNameInput) -> AssetName:
    return LlmAssetNamer(completer=LiteLlmCompleter())(asset_input)


def asset_name_prompt(asset_input: AssetNameInput) -> str:
    preview = "\n".join(asset_input.markdown.splitlines()[:1000])
    return f"""Extract the canonical title and primary author(s) from this document.

DOCUMENT PREVIEW (first portion):
---
{preview}
---

TABLE OF CONTENTS:
---
{asset_input.headers}
---

Extract:
1. The official title of this book/document
2. The primary author(s) name(s)

Respond with ONLY a JSON object in this exact format:
{{
  "title": "The Official Book Title",
  "authors": "Author Name"
}}

If there are multiple authors, include all primary authors in the authors field (e.g., "John Doe and Jane Smith").
Do not include any explanation, only the JSON object."""


def asset_name_from_llm_response(response: str) -> AssetName:
    payload = parse_asset_name_response_json(response)
    title_value = payload.get("title")
    authors_value = payload.get("authors")
    if not isinstance(title_value, str) or not title_value.strip():
        raise AssetNamingError("LLM asset naming response did not include a title.")

    authors = authors_from_response(authors_value)
    title = title_value.strip()
    canonical = canonicalize_name([title, *authors])
    return AssetName(title=title, authors=authors, canonical_name=canonical)


def parse_asset_name_response_json(response: str) -> dict[str, object]:
    stripped = response.strip()
    if not stripped.startswith("{"):
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if match:
            stripped = match.group(0)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise AssetNamingError(
            f"Could not parse LLM asset naming response as JSON: {response}"
        ) from error
    if not isinstance(payload, dict):
        raise AssetNamingError("LLM asset naming response must be a JSON object.")
    return payload


def authors_from_response(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return split_authors(value)
    if isinstance(value, list):
        return tuple(author.strip() for author in value if isinstance(author, str))
    return ()


def write_asset_name_cache(*, work_dir: Path, asset_name: AssetName) -> None:
    AssetMetadata(
        title=asset_name.title,
        authors=asset_name.authors,
    ).write(work_dir / "metadata.json")
    (work_dir / "canonical_name.txt").write_text(
        f"{asset_name.canonical_name}\n",
        encoding="utf-8",
    )


def temporary_asset_dir(*, asset_root: Path, source: Path) -> Path:
    digest = hashlib.md5(str(source.resolve()).encode("utf-8")).hexdigest()[:12]
    return asset_root / ".tmp" / digest


def prepare_work_dir(*, work_dir: Path, source: Path) -> None:
    if work_dir.exists():
        if path_contains(parent=work_dir, child=source):
            raise ValueError(
                "Cannot replace temporary asset directory that contains "
                f"the source file: {work_dir}"
            )
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)


def prepare_final_asset_dir(
    *,
    final_dir: Path,
    source: Path,
    work_dir: Path,
    force: bool,
) -> None:
    if not final_dir.exists():
        return
    if not force:
        shutil.rmtree(work_dir)
        cleanup_tmp_parent(work_dir)
        raise AssetDirectoryExistsError(f"Asset directory already exists: {final_dir}")
    if path_contains(parent=final_dir, child=source):
        raise ValueError(
            f"Cannot replace asset directory that contains the source file: {final_dir}"
        )
    shutil.rmtree(final_dir)


def rename_markdown_to_canonical_name(
    *,
    markdown_path: Path,
    canonical_name: str,
) -> Path:
    canonical_path = markdown_path.with_name(f"{canonical_name}.md")
    if markdown_path != canonical_path:
        markdown_path.rename(canonical_path)
    return canonical_path


def move_source_to_canonical_asset_path(
    *,
    source: Path,
    asset_dir: Path,
    canonical_name: str,
) -> Path:
    destination = asset_dir / f"{canonical_name}{source.suffix}"
    if source.resolve() == destination.resolve():
        return destination
    if destination.exists():
        raise FileExistsError(f"Asset source already exists: {destination}")

    shutil.move(str(source), str(destination))
    return destination


def cleanup_tmp_parent(work_dir: Path) -> None:
    tmp_parent = work_dir.parent
    if tmp_parent.exists() and not list(tmp_parent.iterdir()):
        tmp_parent.rmdir()


def path_contains(*, parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True
