from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from alex.lib.document_sources import (
    DocumentMetadata,
    canonical_name_for,
    metadata_from_markdown,
)


CHUNK_LINE_LIMIT = 10_000
DEFAULT_FAST_SUMMARY_MODEL = "claude-haiku-4-5"
DEFAULT_FINAL_SUMMARY_MODEL = "claude-opus-4-8"
DEFAULT_CHUNK_SUMMARY_MAX_TOKENS = 20_000
DEFAULT_FINAL_SUMMARY_MAX_TOKENS = 8_192
DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS = 180_000
DEFAULT_SUMMARY_MAX_WORKERS = 4
DEFAULT_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_LLM_TIMEOUT_SECONDS = 900.0
MAX_SUMMARY_COMPRESSION_ITERATIONS = 8
TRANSIENT_ANTHROPIC_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
SOURCE_EXTENSIONS = frozenset({".epub", ".pdf", ".txt", *MARKDOWN_EXTENSIONS})
GENERATED_MARKDOWN_FILES = frozenset(
    {
        "headers.md",
        "summary.md",
        "chunk_summary.md",
    }
)
GENERATED_ASSET_FILES = frozenset(
    {
        "canonical_name.txt",
        "chapter_level.txt",
        "metadata.json",
        "schema.json",
        *GENERATED_MARKDOWN_FILES,
    }
)


class ProcessDocAssetError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessDocAssetConfig:
    asset_path: Path
    summarize: bool = True
    force_summary: bool = False
    max_summary_context_tokens: int = DEFAULT_MAX_SUMMARY_CONTEXT_TOKENS
    fast_summary_model: str = DEFAULT_FAST_SUMMARY_MODEL
    final_summary_model: str = DEFAULT_FINAL_SUMMARY_MODEL
    chunk_summary_max_tokens: int = DEFAULT_CHUNK_SUMMARY_MAX_TOKENS
    final_summary_max_tokens: int = DEFAULT_FINAL_SUMMARY_MAX_TOKENS
    summary_max_workers: int = DEFAULT_SUMMARY_MAX_WORKERS


@dataclass(frozen=True)
class ProcessDocAssetOutput:
    asset_dir: Path
    original_file: Path
    markdown_path: Path
    headers_path: Path
    chapter_level_path: Path
    metadata_path: Path
    canonical_name_path: Path
    chunks_dir: Path
    chunk_paths: tuple[Path, ...]
    chunk_summary_path: Path | None = None
    summary_path: Path | None = None


@dataclass(frozen=True)
class ProcessDocSummaryOutput:
    chunk_summary_path: Path | None
    summary_path: Path | None


@dataclass(frozen=True)
class MarkdownHeader:
    line_index: int
    level: int
    title: str


@dataclass(frozen=True)
class MarkdownChapter:
    title: str
    start_index: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class SummaryChunkReference:
    index: int
    filename: str
    path: str


class ProcessDocSummarizer(Protocol):
    def complete_batch(
        self,
        *,
        prompts: tuple[str, ...],
        model: str,
        max_tokens: int,
    ) -> tuple[str, ...]:
        ...

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> str:
        ...


def process_doc_asset(
    config: ProcessDocAssetConfig,
    *,
    summarizer: ProcessDocSummarizer | None = None,
) -> ProcessDocAssetOutput:
    asset_dir = config.asset_path
    if not asset_dir.is_dir():
        raise ProcessDocAssetError(f"Asset path must be a directory: {asset_dir}")

    headers_path = find_headers_extract(asset_dir)
    markdown_path = find_markdown_extract(asset_dir)
    original_file = find_original_file(asset_dir, markdown_path)

    markdown = markdown_path.read_text(encoding="utf-8")
    headers = headers_path.read_text(encoding="utf-8")
    chapter_level = infer_chapter_level(headers=headers, markdown=markdown)

    chapter_level_path = asset_dir / "chapter_level.txt"
    chapter_level_path.write_text(f"{chapter_level}\n", encoding="utf-8")

    chunks_dir = asset_dir / "chunks"
    chunk_paths = write_chunks(
        chunks_dir=chunks_dir,
        markdown=markdown,
        markdown_filename=markdown_path.name,
        chapter_level=chapter_level,
    )

    metadata = metadata_from_markdown(markdown, markdown_path)
    metadata_path = asset_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "title": metadata.title,
                "authors": list(metadata.authors),
                "source_format": source_format_for(original_file),
                "source_file": original_file.name,
                "full_markdown": markdown_path.name,
                "headers_file": headers_path.name,
                "chapter_level": chapter_level,
                "chunks_dir": chunks_dir.name,
            },
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )

    canonical_name_path = asset_dir / "canonical_name.txt"
    canonical_name_path.write_text(
        canonical_name_for(metadata=metadata, source=markdown_path, name_override=None)
        + "\n",
        encoding="utf-8",
    )

    summary_output = ProcessDocSummaryOutput(
        chunk_summary_path=asset_dir / "chunk_summary.md"
        if (asset_dir / "chunk_summary.md").exists()
        else None,
        summary_path=asset_dir / "summary.md"
        if (asset_dir / "summary.md").exists()
        else None,
    )
    if config.summarize:
        summary_output = summarize_doc_asset(
            config=config,
            metadata=metadata,
            markdown_path=markdown_path,
            headers_path=headers_path,
            chunk_paths=chunk_paths,
            summarizer=summarizer or AnthropicMessagesSummarizer(
                max_workers=config.summary_max_workers
            ),
        )

    return ProcessDocAssetOutput(
        asset_dir=asset_dir,
        original_file=original_file,
        markdown_path=markdown_path,
        headers_path=headers_path,
        chapter_level_path=chapter_level_path,
        metadata_path=metadata_path,
        canonical_name_path=canonical_name_path,
        chunks_dir=chunks_dir,
        chunk_paths=chunk_paths,
        chunk_summary_path=summary_output.chunk_summary_path,
        summary_path=summary_output.summary_path,
    )


def summarize_doc_asset(
    *,
    config: ProcessDocAssetConfig,
    metadata: DocumentMetadata,
    markdown_path: Path,
    headers_path: Path,
    chunk_paths: tuple[Path, ...],
    summarizer: ProcessDocSummarizer,
) -> ProcessDocSummaryOutput:
    asset_dir = config.asset_path
    summary_path = asset_dir / "summary.md"
    chunk_summary_path = asset_dir / "chunk_summary.md"
    if summary_path.exists() and not config.force_summary:
        return ProcessDocSummaryOutput(
            chunk_summary_path=(
                chunk_summary_path if chunk_summary_path.exists() else None
            ),
            summary_path=summary_path,
        )
    if not chunk_paths:
        return ProcessDocSummaryOutput(chunk_summary_path=None, summary_path=None)

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
    chunk_summaries = summarizer.complete_batch(
        prompts=prompts,
        model=summary_fast_model(config),
        max_tokens=config.chunk_summary_max_tokens,
    )
    if len(chunk_summaries) != len(chunk_paths):
        raise ProcessDocAssetError(
            "Summarizer returned "
            f"{len(chunk_summaries)} chunk summaries for {len(chunk_paths)} chunks."
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
        max_context_tokens=config.max_summary_context_tokens,
        summarizer=summarizer,
        model=summary_fast_model(config),
        max_tokens=config.chunk_summary_max_tokens,
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

    final_summary = summarizer.complete(
        prompt=final_summary_prompt(
            title=metadata.title,
            authors=authors,
            section_summaries=consolidated,
            references=references,
        ),
        model=summary_final_model(config),
        max_tokens=config.final_summary_max_tokens,
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
    return ProcessDocSummaryOutput(
        chunk_summary_path=chunk_summary_path,
        summary_path=summary_path,
    )


def authors_for_display(metadata: DocumentMetadata) -> str:
    if metadata.authors:
        return ", ".join(metadata.authors)
    return "Unknown"


def summary_fast_model(config: ProcessDocAssetConfig) -> str:
    return (
        os.getenv("PROCESS_DOC_FAST_SUMMARY_MODEL")
        or os.getenv("ANTHROPIC_SMALL_FAST_MODEL")
        or config.fast_summary_model
    )


def summary_final_model(config: ProcessDocAssetConfig) -> str:
    return (
        os.getenv("PROCESS_DOC_FINAL_SUMMARY_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or config.final_summary_model
    )


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
    for chunk_path, summary in zip(chunk_paths, chunk_summaries):
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
    summarizer: ProcessDocSummarizer,
    model: str,
    max_tokens: int,
) -> str:
    if max_context_tokens <= 0:
        raise ProcessDocAssetError("max_summary_context_tokens must be positive.")

    current = content
    iterations = 0
    while count_tokens_estimate(current) > max_context_tokens:
        iterations += 1
        if iterations > MAX_SUMMARY_COMPRESSION_ITERATIONS:
            raise ProcessDocAssetError(
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
        compressed_chunks = summarizer.complete_batch(
            prompts=prompts,
            model=model,
            max_tokens=max_tokens,
        )
        if len(compressed_chunks) != len(chunks):
            raise ProcessDocAssetError(
                "Summarizer returned "
                f"{len(compressed_chunks)} compressed summaries for {len(chunks)} chunks."
            )
        compressed = "\n\n---\n\n".join(compressed_chunks)
        if len(compressed) >= len(current):
            raise ProcessDocAssetError(
                "Recursive summary compression did not reduce the summary size."
            )
        current = compressed

    return current


def split_content_for_summary_compression(
    *,
    content: str,
    max_context_tokens: int,
) -> tuple[str, ...]:
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


class AnthropicMessagesSummarizer:
    def __init__(
        self,
        *,
        max_workers: int = DEFAULT_SUMMARY_MAX_WORKERS,
        timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS,
        max_retries: int = 6,
        initial_retry_delay_seconds: float = 5.0,
    ) -> None:
        self.max_workers = max(1, max_workers)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.initial_retry_delay_seconds = initial_retry_delay_seconds

    def complete_batch(
        self,
        *,
        prompts: tuple[str, ...],
        model: str,
        max_tokens: int,
    ) -> tuple[str, ...]:
        if not prompts:
            return ()
        if self.max_workers == 1 or len(prompts) == 1:
            return tuple(
                self.complete(prompt=prompt, model=model, max_tokens=max_tokens)
                for prompt in prompts
            )

        worker_count = min(self.max_workers, len(prompts))

        def complete_prompt(prompt: str) -> str:
            return self.complete(prompt=prompt, model=model, max_tokens=max_tokens)

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            return tuple(executor.map(complete_prompt, prompts))

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> str:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            anthropic_messages_url(),
            data=body,
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "anthropic-version": DEFAULT_ANTHROPIC_VERSION,
                "x-api-key": anthropic_api_key(),
            },
            method="POST",
        )
        retry_delay = self.initial_retry_delay_seconds

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                ) as response:
                    response_body = response.read().decode("utf-8")
                return extract_anthropic_text(response_body)
            except urllib.error.HTTPError as error:
                error_body = error.read().decode("utf-8", errors="replace")
                if (
                    error.code in TRANSIENT_ANTHROPIC_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60.0)
                    continue
                raise ProcessDocAssetError(
                    "Anthropic Messages API request failed "
                    f"with HTTP {error.code}: {anthropic_error_message(error_body)}"
                ) from error
            except (TimeoutError, urllib.error.URLError) as error:
                if attempt < self.max_retries:
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60.0)
                    continue
                raise ProcessDocAssetError(
                    f"Anthropic Messages API request failed: {error}"
                ) from error

        raise ProcessDocAssetError("Anthropic Messages API request failed.")


def anthropic_api_key() -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ProcessDocAssetError(
            "ANTHROPIC_API_KEY is required to generate process-doc summaries."
        )
    return api_key


def anthropic_messages_url() -> str:
    explicit_url = os.getenv("ANTHROPIC_MESSAGES_URL")
    if explicit_url:
        return explicit_url
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    if base_url:
        return f"{base_url.rstrip('/')}/v1/messages"
    return DEFAULT_ANTHROPIC_MESSAGES_URL


def extract_anthropic_text(response_body: str) -> str:
    payload = json.loads(response_body)
    if not isinstance(payload, dict):
        raise ProcessDocAssetError("Anthropic Messages API returned invalid JSON.")
    content = payload.get("content")
    if not isinstance(content, list):
        raise ProcessDocAssetError("Anthropic Messages API response has no content.")

    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if isinstance(text, str):
            text_parts.append(text)
    return "".join(text_parts)


def anthropic_error_message(response_body: str) -> str:
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        return response_body.strip() or "unknown error"
    if not isinstance(payload, dict):
        return response_body.strip() or "unknown error"
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return response_body.strip() or "unknown error"


def find_headers_extract(asset_dir: Path) -> Path:
    headers_path = asset_dir / "headers.md"
    if not headers_path.is_file():
        raise ProcessDocAssetError(
            f"Expected table of contents extract at {headers_path}"
        )
    return headers_path


def find_markdown_extract(asset_dir: Path) -> Path:
    markdown_files = tuple(
        path
        for path in sorted(asset_dir.iterdir())
        if path.is_file()
        and path.suffix.lower() in MARKDOWN_EXTENSIONS
        and path.name not in GENERATED_MARKDOWN_FILES
    )
    if not markdown_files:
        raise ProcessDocAssetError(
            f"Expected one markdown extract in asset folder: {asset_dir}"
        )
    if len(markdown_files) > 1:
        names = ", ".join(path.name for path in markdown_files)
        raise ProcessDocAssetError(
            f"Expected one markdown extract, found multiple: {names}"
        )
    return markdown_files[0]


def find_original_file(asset_dir: Path, markdown_path: Path) -> Path:
    source_files = tuple(
        path
        for path in sorted(asset_dir.iterdir())
        if path.is_file()
        and path.suffix.lower() in SOURCE_EXTENSIONS
        and path.name not in GENERATED_ASSET_FILES
        and path != markdown_path
    )
    if len(source_files) > 1:
        names = ", ".join(path.name for path in source_files)
        raise ProcessDocAssetError(
            f"Expected one original file, found multiple original files: {names}"
        )
    if source_files:
        return source_files[0]

    if markdown_path.suffix.lower() in MARKDOWN_EXTENSIONS:
        return markdown_path

    raise ProcessDocAssetError(f"Expected original file in asset folder: {asset_dir}")


def source_format_for(source: Path) -> str:
    extension = source.suffix.lower()
    if extension == ".markdown":
        return "markdown"
    if extension == ".md":
        return "markdown"
    return extension.removeprefix(".")


def infer_chapter_level(*, headers: str, markdown: str) -> int:
    levels = parse_toc_header_levels(headers)
    if not levels:
        levels = tuple(header.level for header in parse_markdown_headers(markdown))
    if not levels:
        raise ProcessDocAssetError("Cannot infer chapter level without markdown headers.")

    counts = Counter(levels)
    top_level = min(counts)
    if counts[top_level] == 1:
        for level in sorted(counts):
            if level > top_level:
                return level
    return top_level


def parse_toc_header_levels(headers: str) -> tuple[int, ...]:
    levels: list[int] = []
    pattern = re.compile(r"\(H([1-6]),\s*line\s+\d+", re.IGNORECASE)
    for line in headers.splitlines():
        match = pattern.search(line)
        if match:
            levels.append(int(match.group(1)))
    return tuple(levels)


def parse_markdown_headers(markdown: str) -> tuple[MarkdownHeader, ...]:
    headers: list[MarkdownHeader] = []
    for line_index, line in enumerate(markdown.splitlines()):
        match = markdown_header_match(line)
        if not match:
            continue
        headers.append(
            MarkdownHeader(
                line_index=line_index,
                level=len(match.group(1)),
                title=strip_inline_markdown(match.group(2)).strip(),
            )
        )
    return tuple(headers)


def write_chunks(
    *,
    chunks_dir: Path,
    markdown: str,
    markdown_filename: str,
    chapter_level: int,
) -> tuple[Path, ...]:
    if chunks_dir.exists():
        shutil.rmtree(chunks_dir)
    chunks_dir.mkdir(parents=True)

    lines = markdown.splitlines()
    headers = parse_markdown_headers(markdown)
    chapters = split_chapters(lines=lines, chapter_level=chapter_level)
    if not chapters:
        raise ProcessDocAssetError(
            f"No H{chapter_level} chapter headings found in markdown extract."
        )

    chunk_paths: list[Path] = []
    chunk_number = 1
    for chapter in chapters:
        parent_headers = parents_for_chapter(
            headers=headers,
            chapter_start_index=chapter.start_index,
            chapter_level=chapter_level,
        )
        parts = split_chapter_lines(chapter.lines)
        for part_index, part_lines in enumerate(parts, 1):
            suffix = ""
            if len(parts) > 1:
                suffix = f"_part_{part_index}"
            chunk_path = chunks_dir / (
                f"{chunk_number:03d}_{slugify_title(chapter.title)}{suffix}.md"
            )
            chunk_path.write_text(
                chunk_content(
                    markdown_filename=markdown_filename,
                    parent_headers=parent_headers,
                    chapter_lines=part_lines,
                ),
                encoding="utf-8",
            )
            chunk_paths.append(chunk_path)
            chunk_number += 1

    return tuple(chunk_paths)


def split_chapters(
    *,
    lines: list[str],
    chapter_level: int,
) -> tuple[MarkdownChapter, ...]:
    chapters: list[MarkdownChapter] = []
    current_title: str | None = None
    current_start_index: int | None = None
    current_lines: list[str] = []

    for line_index, line in enumerate(lines):
        match = markdown_header_match(line)
        if match and len(match.group(1)) == chapter_level:
            if current_title is not None and current_start_index is not None:
                chapters.append(
                    MarkdownChapter(
                        title=current_title,
                        start_index=current_start_index,
                        lines=tuple(current_lines),
                    )
                )
            current_title = strip_inline_markdown(match.group(2)).strip()
            current_start_index = line_index
            current_lines = [line]
            continue

        if current_title is not None:
            current_lines.append(line)

    if current_title is not None and current_start_index is not None:
        chapters.append(
            MarkdownChapter(
                title=current_title,
                start_index=current_start_index,
                lines=tuple(current_lines),
            )
        )

    return tuple(chapters)


def parents_for_chapter(
    *,
    headers: tuple[MarkdownHeader, ...],
    chapter_start_index: int,
    chapter_level: int,
) -> tuple[str, ...]:
    parents_by_level: dict[int, str] = {}
    for header in headers:
        if header.line_index >= chapter_start_index:
            break
        if header.level >= chapter_level:
            continue
        parents_by_level = {
            level: title
            for level, title in parents_by_level.items()
            if level < header.level
        }
        parents_by_level[header.level] = header.title

    return tuple(
        f"{'#' * level} {title}" for level, title in sorted(parents_by_level.items())
    )


def split_chapter_lines(chapter_lines: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    if len(chapter_lines) <= CHUNK_LINE_LIMIT:
        return (chapter_lines,)

    return tuple(
        chapter_lines[index : index + CHUNK_LINE_LIMIT]
        for index in range(0, len(chapter_lines), CHUNK_LINE_LIMIT)
    )


def chunk_content(
    *,
    markdown_filename: str,
    parent_headers: tuple[str, ...],
    chapter_lines: tuple[str, ...],
) -> str:
    parts = [f"[Back to full document](../{markdown_filename})"]
    if parent_headers:
        parts.append("\n".join(parent_headers))
    parts.append("\n".join(chapter_lines))
    return fix_image_paths_for_chunks("\n\n".join(parts).rstrip() + "\n")


def fix_image_paths_for_chunks(content: str) -> str:
    def replace_path(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        image_path = match.group(2)
        if image_path.startswith("images/"):
            return f"![{alt_text}](../{image_path})"
        return match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_path, content)


def markdown_header_match(line: str) -> re.Match[str] | None:
    return re.match(r"^(#{1,6})\s+(.+?)\s*(?:#+\s*)?$", line)


def strip_inline_markdown(text: str) -> str:
    return re.sub(r"\*\*|__|\*|_|`", "", text)


def slugify_title(title: str) -> str:
    normalized = strip_inline_markdown(title).lower()
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[\s_-]+", "_", normalized)
    return normalized.strip("_")[:120] or "section"
