"""Structure-first chunking with embedding-based splits for oversized text.

Documents are chunked along their header structure when possible. Any
chapter that exceeds the chunk budget (or a document with no usable
structure at all) is split semantically instead:

    paragraphs ──► embeddings ──► similarity at each boundary
                                        │
        cut where similarity dips ◄─────┘  (greedy valley cut,
        between min/max token bounds)       deterministic, O(n))

Texts that fit the budget never touch the embedding model.
"""

from __future__ import annotations

import math
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from alex.lib.llm import Embedder, resolve_embedding_model
from alex.lib.markdown_structure import (
    MarkdownStructureError,
    chunk_content,
    infer_chapter_level,
    slugify_title,
    write_chunks,
)

MIN_PARAGRAPH_CHARS = 200
TAIL_MERGE_SLACK = 1.2
# Embedding models cap input around 8k tokens; similarity only needs the
# head of a paragraph, so probe inputs are truncated while chunks keep the
# full text.
EMBED_MAX_INPUT_CHARS = 20_000
FENCE_OPEN_PATTERN = re.compile(r"^(`{3,}|~{3,})")


class ChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class ChunkSettings:
    embedding_model: str = field(default_factory=resolve_embedding_model)
    min_chunk_tokens: int = 1_000
    max_chunk_tokens: int = 12_000
    similarity_window: int = 2


@dataclass(frozen=True)
class ChunkingResult:
    chapter_level: int | None
    chunk_paths: tuple[Path, ...]


def count_tokens_estimate(text: str) -> int:
    return len(text) // 4


def chunk_markdown_document(
    *,
    chunks_dir: Path,
    markdown: str,
    markdown_filename: str,
    headers: str,
    settings: ChunkSettings,
    embedder: Embedder,
) -> ChunkingResult:
    def splitter(text: str) -> tuple[str, ...]:
        return semantic_split(text=text, embedder=embedder, settings=settings)

    # A stale or foreign headers extract must not discard real document
    # structure, so retry from the markdown's own headers before falling
    # back to unstructured semantic chunks.
    for headers_source in (headers, ""):
        try:
            chapter_level = infer_chapter_level(
                headers=headers_source, markdown=markdown
            )
            chunk_paths = write_chunks(
                chunks_dir=chunks_dir,
                markdown=markdown,
                markdown_filename=markdown_filename,
                chapter_level=chapter_level,
                splitter=splitter,
            )
        except MarkdownStructureError:
            continue
        return ChunkingResult(chapter_level=chapter_level, chunk_paths=chunk_paths)

    return ChunkingResult(
        chapter_level=None,
        chunk_paths=write_unstructured_chunks(
            chunks_dir=chunks_dir,
            markdown=markdown,
            markdown_filename=markdown_filename,
            splitter=splitter,
        ),
    )


def write_unstructured_chunks(
    *,
    chunks_dir: Path,
    markdown: str,
    markdown_filename: str,
    splitter: Callable[[str], tuple[str, ...]],
) -> tuple[Path, ...]:
    if chunks_dir.exists():
        shutil.rmtree(chunks_dir)
    chunks_dir.mkdir(parents=True)

    chunk_paths: list[Path] = []
    for chunk_number, part in enumerate(splitter(markdown), 1):
        chunk_path = chunks_dir / f"{chunk_number:03d}_{first_line_slug(part)}.md"
        chunk_path.write_text(
            chunk_content(
                markdown_filename=markdown_filename,
                parent_headers=(),
                body=part,
            ),
            encoding="utf-8",
        )
        chunk_paths.append(chunk_path)
    return tuple(chunk_paths)


def first_line_slug(text: str) -> str:
    for line in text.splitlines():
        words = line.split()
        if words:
            return slugify_title(" ".join(words[:8]))
    return "section"


def semantic_split(
    *,
    text: str,
    embedder: Embedder,
    settings: ChunkSettings,
) -> tuple[str, ...]:
    if count_tokens_estimate(text) <= settings.max_chunk_tokens:
        return (text,)

    paragraphs = merge_small_paragraphs(split_paragraphs(text))
    if len(paragraphs) <= 1:
        return (text,)

    vectors = embedder.embed(
        texts=[paragraph[:EMBED_MAX_INPUT_CHARS] for paragraph in paragraphs],
        model=settings.embedding_model,
    )
    if len(vectors) != len(paragraphs):
        raise ChunkingError(
            f"Embedder returned {len(vectors)} vectors for "
            f"{len(paragraphs)} paragraphs."
        )

    cuts = plan_cut_boundaries(
        token_counts=tuple(count_tokens_estimate(p) for p in paragraphs),
        similarities=boundary_similarities(vectors, window=settings.similarity_window),
        min_tokens=settings.min_chunk_tokens,
        max_tokens=settings.max_chunk_tokens,
    )
    return merge_short_tail(
        join_paragraph_runs(paragraphs, cuts),
        settings=settings,
    )


def split_paragraphs(text: str) -> tuple[str, ...]:
    """Split on blank-line runs, keeping fenced code blocks whole.

    Fence tracking follows CommonMark: the closing fence must use the same
    character, be at least as long as the opener, and carry no info string.
    A shorter or info-stringed fence line inside the block stays inside.
    """
    blocks: list[str] = []
    current: list[str] = []
    open_fence: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if open_fence is not None:
            current.append(line)
            if re.fullmatch(rf"{re.escape(open_fence)}{open_fence[0]}*", stripped):
                open_fence = None
            continue
        fence_match = FENCE_OPEN_PATTERN.match(stripped)
        if fence_match:
            open_fence = fence_match.group(1)
            current.append(line)
            continue
        if not stripped:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)

    if current:
        blocks.append("\n".join(current))
    return tuple(blocks)


def merge_small_paragraphs(
    paragraphs: Sequence[str],
    *,
    min_chars: int = MIN_PARAGRAPH_CHARS,
) -> tuple[str, ...]:
    merged: list[str] = []
    pending = ""
    for paragraph in paragraphs:
        combined = f"{pending}\n\n{paragraph}" if pending else paragraph
        if len(combined) < min_chars:
            pending = combined
            continue
        merged.append(combined)
        pending = ""
    if pending:
        if merged:
            merged[-1] = f"{merged[-1]}\n\n{pending}"
        else:
            merged.append(pending)
    return tuple(merged)


def boundary_similarities(
    vectors: Sequence[tuple[float, ...]],
    *,
    window: int,
) -> tuple[float, ...]:
    """Cosine similarity across each paragraph boundary.

    Boundary ``b`` sits between paragraphs ``b`` and ``b + 1``; each side is
    represented by the mean of up to ``window`` paragraph vectors.
    """
    similarities: list[float] = []
    for boundary in range(len(vectors) - 1):
        left = mean_vector(vectors[max(0, boundary + 1 - window) : boundary + 1])
        right = mean_vector(vectors[boundary + 1 : boundary + 1 + window])
        similarities.append(cosine_similarity(left, right))
    return tuple(similarities)


def mean_vector(vectors: Sequence[tuple[float, ...]]) -> tuple[float, ...]:
    count = len(vectors)
    return tuple(sum(values) / count for values in zip(*vectors, strict=True))


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def plan_cut_boundaries(
    *,
    token_counts: tuple[int, ...],
    similarities: tuple[float, ...],
    min_tokens: int,
    max_tokens: int,
) -> tuple[int, ...]:
    """Pick boundaries to cut after, greedily front to back.

    Within each chunk, every boundary past ``min_tokens`` is a candidate
    until adding the next paragraph would exceed ``max_tokens``; the
    candidate with the lowest similarity (the topic valley) wins. A single
    paragraph larger than ``max_tokens`` becomes its own chunk, since
    paragraph granularity is the floor.
    """
    cuts: list[int] = []
    start = 0
    count = len(token_counts)
    while start < count:
        total = 0
        candidates: list[int] = []
        overflow_at: int | None = None
        for index in range(start, count):
            if total and total + token_counts[index] > max_tokens:
                overflow_at = index
                break
            total += token_counts[index]
            if total >= min_tokens and index < count - 1:
                candidates.append(index)
        if overflow_at is None:
            break
        cut = (
            min(candidates, key=lambda boundary: similarities[boundary])
            if candidates
            else overflow_at - 1
        )
        cuts.append(cut)
        start = cut + 1
    return tuple(cuts)


def join_paragraph_runs(
    paragraphs: tuple[str, ...],
    cuts: tuple[int, ...],
) -> tuple[str, ...]:
    chunks: list[str] = []
    start = 0
    for cut in (*cuts, len(paragraphs) - 1):
        chunks.append("\n\n".join(paragraphs[start : cut + 1]))
        start = cut + 1
    return tuple(chunks)


def merge_short_tail(
    chunks: tuple[str, ...],
    *,
    settings: ChunkSettings,
) -> tuple[str, ...]:
    if len(chunks) < 2:
        return chunks
    if count_tokens_estimate(chunks[-1]) >= settings.min_chunk_tokens:
        return chunks
    combined = f"{chunks[-2]}\n\n{chunks[-1]}"
    if count_tokens_estimate(combined) > settings.max_chunk_tokens * TAIL_MERGE_SLACK:
        return chunks
    return (*chunks[:-2], combined)
