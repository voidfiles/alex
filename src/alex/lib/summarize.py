"""Map-reduce summarization of a chunked document asset."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path

from alex.lib.chunking import count_tokens_estimate
from alex.lib.document_sources import DocumentMetadata
from alex.lib.llm import (
    Completer,
    complete_all,
    resolve_fast_summary_model,
    resolve_final_summary_model,
)
from alex.lib.prompt_templates import PromptTemplate, load_prompt

DEFAULT_CHUNK_SUMMARY_MAX_TOKENS = 20_000
DEFAULT_FINAL_SUMMARY_MAX_TOKENS = 8_192
DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS = 180_000
DEFAULT_SUMMARY_MAX_WORKERS = 4
MAX_SUMMARY_COMPRESSION_ITERATIONS = 8


class SummarizationError(ValueError):
    pass


SUMMARY_PROMPT_NAMES = ("chunk_summary", "compression_summary", "final_summary")


@dataclass(frozen=True)
class SummaryPrompts:
    chunk_summary: PromptTemplate
    compression_summary: PromptTemplate
    final_summary: PromptTemplate

    @classmethod
    def load(
        cls,
        overrides: Mapping[str, str] | None = None,
        *,
        root: Traversable | None = None,
    ) -> SummaryPrompts:
        versions = dict(overrides or {})
        unknown = sorted(set(versions) - set(SUMMARY_PROMPT_NAMES))
        if unknown:
            raise SummarizationError(
                f"Unknown summary prompts in overrides: {', '.join(unknown)}"
            )
        return cls(
            chunk_summary=load_prompt(
                "chunk_summary", version=versions.get("chunk_summary"), root=root
            ),
            compression_summary=load_prompt(
                "compression_summary",
                version=versions.get("compression_summary"),
                root=root,
            ),
            final_summary=load_prompt(
                "final_summary", version=versions.get("final_summary"), root=root
            ),
        )


@dataclass(frozen=True)
class SummarySettings:
    fast_model: str = field(default_factory=resolve_fast_summary_model)
    final_model: str = field(default_factory=resolve_final_summary_model)
    prompts: SummaryPrompts = field(default_factory=SummaryPrompts.load)
    chunk_summary_max_tokens: int = DEFAULT_CHUNK_SUMMARY_MAX_TOKENS
    final_summary_max_tokens: int = DEFAULT_FINAL_SUMMARY_MAX_TOKENS
    max_context_tokens: int = DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS
    max_workers: int = DEFAULT_SUMMARY_MAX_WORKERS
    force: bool = False


@dataclass(frozen=True)
class SummaryOutput:
    chunk_summary_path: Path | None
    summary_path: Path | None


@dataclass(frozen=True)
class SummaryChunkReference:
    index: int
    filename: str
    path: str


def summarize_doc_asset(
    *,
    settings: SummarySettings,
    asset_dir: Path,
    metadata: DocumentMetadata,
    markdown_path: Path,
    headers_path: Path,
    chunk_paths: tuple[Path, ...],
    completer: Completer,
) -> SummaryOutput:
    summary_path = asset_dir / "summary.md"
    chunk_summary_path = asset_dir / "chunk_summary.md"
    if summary_path.exists() and not settings.force:
        return SummaryOutput(
            chunk_summary_path=(
                chunk_summary_path if chunk_summary_path.exists() else None
            ),
            summary_path=summary_path,
        )
    if not chunk_paths:
        return SummaryOutput(chunk_summary_path=None, summary_path=None)

    headers = headers_path.read_text(encoding="utf-8")
    authors = authors_for_display(metadata)
    chunk_summaries_dir = asset_dir / "chunk_summaries"
    if chunk_summaries_dir.exists():
        shutil.rmtree(chunk_summaries_dir)
    chunk_summaries_dir.mkdir()

    prompts = tuple(
        settings.prompts.chunk_summary.render(
            title=metadata.title,
            authors=authors,
            headers=headers,
            chunk=chunk_path.read_text(encoding="utf-8"),
        )
        for chunk_path in chunk_paths
    )
    chunk_summaries = complete_all(
        completer=completer,
        prompts=prompts,
        model=settings.fast_model,
        max_tokens=settings.chunk_summary_max_tokens,
        max_workers=settings.max_workers,
    )

    references = tuple(
        SummaryChunkReference(
            index=index,
            filename=chunk_path.name,
            path=f"chunks/{chunk_path.name}",
        )
        for index, chunk_path in enumerate(chunk_paths, 1)
    )
    write_individual_chunk_summaries(
        chunk_summaries_dir=chunk_summaries_dir,
        chunk_paths=chunk_paths,
        chunk_summaries=chunk_summaries,
    )
    concatenated = concatenate_chunk_summaries(chunk_summaries_dir)
    consolidated = compress_summary_until_within_context(
        content=concatenated,
        title=metadata.title,
        authors=authors,
        template=settings.prompts.compression_summary,
        max_context_tokens=settings.max_context_tokens,
        completer=completer,
        model=settings.fast_model,
        max_tokens=settings.chunk_summary_max_tokens,
        max_workers=settings.max_workers,
    )

    chunk_summary_path.write_text(
        chunk_summary_content(
            title=metadata.title,
            authors=authors,
            markdown_filename=markdown_path.name,
            references=references,
            consolidated=consolidated,
        ),
        encoding="utf-8",
    )
    shutil.rmtree(chunk_summaries_dir)

    final_summary = completer.complete(
        prompt=settings.prompts.final_summary.render(
            title=metadata.title,
            authors=authors,
            section_summaries=consolidated,
            chunk_reference_list=chunk_reference_list(references),
        ),
        model=settings.final_model,
        max_tokens=settings.final_summary_max_tokens,
    )
    summary_path.write_text(
        summary_content(
            title=metadata.title,
            authors=authors,
            markdown_filename=markdown_path.name,
            final_summary=final_summary,
            references=references,
        ),
        encoding="utf-8",
    )
    return SummaryOutput(
        chunk_summary_path=chunk_summary_path,
        summary_path=summary_path,
    )


def authors_for_display(metadata: DocumentMetadata) -> str:
    if metadata.authors:
        return ", ".join(metadata.authors)
    return "Unknown"


def write_individual_chunk_summaries(
    *,
    chunk_summaries_dir: Path,
    chunk_paths: tuple[Path, ...],
    chunk_summaries: tuple[str, ...],
) -> None:
    for chunk_path, summary in zip(chunk_paths, chunk_summaries, strict=True):
        summary_path = chunk_summaries_dir / f"{chunk_path.stem}_summary.md"
        summary_path.write_text(
            f"""# Summary: {chunk_path.name}
**Source Chunk:** `chunks/{chunk_path.name}`

{summary}
""",
            encoding="utf-8",
        )


def concatenate_chunk_summaries(chunk_summaries_dir: Path) -> str:
    return "\n\n---\n\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(chunk_summaries_dir.glob("*.md"))
    )


def compress_summary_until_within_context(
    *,
    content: str,
    title: str,
    authors: str,
    template: PromptTemplate,
    max_context_tokens: int,
    completer: Completer,
    model: str,
    max_tokens: int,
    max_workers: int,
) -> str:
    if max_context_tokens <= 0:
        raise SummarizationError("max_context_tokens must be positive.")

    current = content
    iterations = 0
    while count_tokens_estimate(current) > max_context_tokens:
        iterations += 1
        if iterations > MAX_SUMMARY_COMPRESSION_ITERATIONS:
            raise SummarizationError(
                "Recursive summary compression did not fit within the context limit."
            )

        chunks = split_content_for_summary_compression(
            content=current,
            max_context_tokens=max_context_tokens,
        )
        prompts = tuple(
            template.render(title=title, authors=authors, content=chunk)
            for chunk in chunks
        )
        compressed_chunks = complete_all(
            completer=completer,
            prompts=prompts,
            model=model,
            max_tokens=max_tokens,
            max_workers=max_workers,
        )
        compressed = "\n\n---\n\n".join(compressed_chunks)
        if len(compressed) >= len(current):
            raise SummarizationError(
                "Recursive summary compression did not reduce the summary size."
            )
        current = compressed

    return current


def split_content_for_summary_compression(
    *,
    content: str,
    max_context_tokens: int,
) -> tuple[str, ...]:
    # count_tokens_estimate assumes ~4 chars per token; splitting at 3 chars
    # per token leaves headroom for the compression prompt wrapped around
    # each chunk.
    chunk_size = max(1, max_context_tokens * 3)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for line in content.splitlines():
        line_length = len(line) + 1
        if current_chunk and current_length + line_length > chunk_size:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = line_length
            continue
        current_chunk.append(line)
        current_length += line_length

    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return tuple(chunks)


def chunk_summary_content(
    *,
    title: str,
    authors: str,
    markdown_filename: str,
    references: tuple[SummaryChunkReference, ...],
    consolidated: str,
) -> str:
    chunk_index = "\n".join(
        f"{reference.index}. [{reference.filename}]({reference.path})"
        for reference in references
    )
    return f"""# Chunk Summary: {title}
**Author(s):** {authors}

[Back to full document]({markdown_filename})

This document contains consolidated summaries of all chunks from the source material.

## Available Chunks

{chunk_index}

---

{consolidated}
"""


def chunk_reference_list(references: tuple[SummaryChunkReference, ...]) -> str:
    return "\n".join(
        f"{reference.index}. {reference.filename} "
        f"-> Link as: `[text]({reference.path})`"
        for reference in references
    )


def summary_content(
    *,
    title: str,
    authors: str,
    markdown_filename: str,
    final_summary: str,
    references: tuple[SummaryChunkReference, ...],
) -> str:
    chunk_index = "\n".join(
        f"{reference.index}. [{reference.filename}]({reference.path})"
        for reference in references
    )
    return f"""# Summary: {title}
**Author(s):** {authors}

[Back to full document]({markdown_filename}) | [View chunk summary](chunk_summary.md)

---

{final_summary}

---

## Explore by Section

For detailed exploration of specific sections, see the individual chunks:

{chunk_index}
"""
