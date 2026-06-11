"""Map-reduce summarization of a chunked document asset."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from alex.lib.document_sources import DocumentMetadata
from alex.lib.llm import (
    Completer,
    complete_all,
    resolve_fast_summary_model,
    resolve_final_summary_model,
)

DEFAULT_CHUNK_SUMMARY_MAX_TOKENS = 20_000
DEFAULT_FINAL_SUMMARY_MAX_TOKENS = 8_192
DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS = 180_000
DEFAULT_SUMMARY_MAX_WORKERS = 4
MAX_SUMMARY_COMPRESSION_ITERATIONS = 8


class SummarizationError(ValueError):
    pass


@dataclass(frozen=True)
class SummarySettings:
    fast_model: str = field(default_factory=resolve_fast_summary_model)
    final_model: str = field(default_factory=resolve_final_summary_model)
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
        chunk_summary_prompt(
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
        prompt=final_summary_prompt(
            title=metadata.title,
            authors=authors,
            section_summaries=consolidated,
            references=references,
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


def chunk_summary_prompt(
    *,
    title: str,
    authors: str,
    headers: str,
    chunk: str,
) -> str:
    return f"""You are a PhD-level domain expert with deep knowledge of academic literature. Your task is to create a rigorous, comprehensive summary of a section from an academic document.

<document_metadata>
Title: {title}
Authors: {authors}
</document_metadata>

<document_structure>
{headers}
</document_structure>

<section_content>
{chunk}
</section_content>

Before writing your summary, think through:
- What are the core arguments and evidence presented?
- How does this section fit within the broader document structure?
- What theoretical frameworks or methodologies are employed?
- What are the key technical terms, definitions, or concepts introduced?
- What assumptions or limitations should be noted?
- What key passages explain core ideas or are particularly well-articulated and should be kept in the final summary?

Now create a PhD-level summary that:

1. Captures core arguments: Identify the central thesis and supporting claims with precision
2. Analyzes evidence and methodology: Explain how the authors support their arguments
3. Maintains academic rigor: Use appropriate technical terminology and preserve nuance
4. Contextualizes within the work: Show how this section relates to the document's overall structure and argument
5. Identifies key insights: Highlight novel contributions, significant findings, or important implications
6. Notes critical details: Include specific examples, data points, or concepts that are essential for deep understanding
7. Highlights key passages: Include passages that should be retained for later synthesis

Your summary should demonstrate the analytical depth expected in graduate-level academic discourse. Write as if summarizing for fellow researchers who need to understand not just what was said, but how and why.

Summary:"""


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
            compression_summary_prompt(title=title, authors=authors, content=chunk)
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


def compression_summary_prompt(*, title: str, authors: str, content: str) -> str:
    return f"""Summarize the following collection of section summaries from "{title}" by {authors}.

These are summaries of different sections. Consolidate them into a comprehensive summary that:
1. Captures all key ideas and main points
2. Maintains logical flow and connections between ideas
3. Preserves important details and examples
4. Is thorough but more concise than the input

CONTENT:
---
{content}
---

Consolidated summary:"""


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


def final_summary_prompt(
    *,
    title: str,
    authors: str,
    section_summaries: str,
    references: tuple[SummaryChunkReference, ...],
) -> str:
    chunk_reference_list = "\n".join(
        f"{reference.index}. {reference.filename} -> Link as: `[text]({reference.path})`"
        for reference in references
    )
    return f"""You are a senior academic researcher preparing a comprehensive analytical overview for fellow scholars. Your task is to synthesize multiple detailed section summaries into a cohesive, high-level summary of the entire work.

<document_metadata>
Title: {title}
Authors: {authors}
</document_metadata>

<section_summaries>
{section_summaries}
</section_summaries>

<chunk_reference_guide>
The source material is divided into chunks. When discussing specific sections or topics, link to the relevant chunk for deeper reading. Available chunks:

{chunk_reference_list}

Use standard Markdown links. Link when referencing specific chapters, sections, major topics, or details that benefit from deeper exploration. Use links strategically so they improve readability.
</chunk_reference_guide>

Before writing your synthesis, analyze:
- What is the overarching thesis or research question?
- How do the sections build upon each other to form a coherent argument?
- What are the major theoretical contributions or empirical findings?
- What methodological approaches or frameworks are central to the work?
- How does this work position itself within existing scholarship?
- What are the key limitations or areas for future research?
- How do the key passages included in the section summaries illuminate core ideas?

Now create a comprehensive synthesis that:

1. Provides a clear executive overview of the work's central purpose, scope, and contribution
2. Articulates the core thesis and arguments with precision and nuance
3. Identifies the theoretical and methodological framework
4. Explains the structure and progression, with inline links to relevant chunks where appropriate
5. Highlights key findings and insights, linking to specific chunks where useful
6. Notes strengths, limitations, assumptions, and areas of particular significance
7. Contextualizes the work's contribution to ongoing scholarly conversations
8. Integrates key passages from the section summaries to enrich the synthesis

Write this summary for researchers deciding whether this work is relevant, graduate students using it in literature reviews, and scholars who need a sophisticated refresher.

High-level summary:"""


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


def count_tokens_estimate(text: str) -> int:
    return len(text) // 4
