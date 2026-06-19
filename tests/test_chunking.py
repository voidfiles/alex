from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from alex.lib.chunking import (
    EMBED_MAX_INPUT_CHARS,
    EMBED_MAX_INPUT_TOKENS,
    ChunkingError,
    ChunkSettings,
    chunk_markdown_document,
    embedding_probe_text,
    merge_short_tail,
    merge_small_paragraphs,
    semantic_split,
    split_paragraphs,
)
from alex.lib.markdown_structure import write_chunks

ALPHA_VECTOR = (1.0, 0.0)
BETA_VECTOR = (0.0, 1.0)


@dataclass
class FakeEmbedder:
    """Maps keyword-tagged paragraphs to fixed 2-D vectors."""

    vectors_by_keyword: dict[str, tuple[float, ...]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
    ) -> tuple[tuple[float, ...], ...]:
        self.calls.append(list(texts))
        return tuple(self.vector_for(text) for text in texts)

    def vector_for(self, text: str) -> tuple[float, ...]:
        for keyword, vector in self.vectors_by_keyword.items():
            if keyword in text:
                return vector
        return ALPHA_VECTOR


def paragraph(topic: str, index: int) -> str:
    # ~260 chars (~65 estimated tokens), above the small-paragraph merge
    # threshold so each paragraph stays its own embedding unit. The short
    # first line keeps unstructured chunk slugs predictable.
    return f"{topic} paragraph {index}.\n" + f"More {topic} prose. " * 13


def topic_embedder() -> FakeEmbedder:
    return FakeEmbedder(vectors_by_keyword={"alpha": ALPHA_VECTOR, "beta": BETA_VECTOR})


def test_semantic_split_returns_short_text_without_embedding() -> None:
    embedder = topic_embedder()
    settings = ChunkSettings(min_chunk_tokens=10, max_chunk_tokens=1_000)

    result = semantic_split(
        text="A short document.",
        embedder=embedder,
        settings=settings,
    )

    assert result == ("A short document.",)
    assert embedder.calls == []


def test_semantic_split_cuts_at_the_topic_boundary() -> None:
    paragraphs = [
        paragraph("alpha", 1),
        paragraph("alpha", 2),
        paragraph("beta", 1),
        paragraph("beta", 2),
    ]
    text = "\n\n".join(paragraphs)
    embedder = topic_embedder()
    settings = ChunkSettings(
        min_chunk_tokens=100,
        max_chunk_tokens=150,
        similarity_window=1,
    )

    chunks = semantic_split(text=text, embedder=embedder, settings=settings)

    assert chunks == (
        f"{paragraphs[0]}\n\n{paragraphs[1]}",
        f"{paragraphs[2]}\n\n{paragraphs[3]}",
    )
    assert embedder.calls == [paragraphs]


def test_semantic_split_prefers_the_lowest_similarity_valley() -> None:
    # Both boundaries are size-eligible; the alpha/beta valley must win even
    # though cutting later would pack the first chunk fuller.
    paragraphs = [paragraph("alpha", 1), paragraph("beta", 1), paragraph("beta", 2)]
    text = "\n\n".join(paragraphs)
    settings = ChunkSettings(
        min_chunk_tokens=50,
        max_chunk_tokens=150,
        similarity_window=1,
    )

    chunks = semantic_split(text=text, embedder=topic_embedder(), settings=settings)

    assert chunks == (
        paragraphs[0],
        f"{paragraphs[1]}\n\n{paragraphs[2]}",
    )


def test_semantic_split_gives_oversized_paragraphs_their_own_chunk() -> None:
    paragraphs = ["alpha " * 200, "beta " * 200]
    text = "\n\n".join(paragraphs)
    settings = ChunkSettings(min_chunk_tokens=50, max_chunk_tokens=150)

    chunks = semantic_split(text=text, embedder=topic_embedder(), settings=settings)

    assert chunks == (paragraphs[0], paragraphs[1])


def test_semantic_split_rejects_embedder_vector_count_mismatch() -> None:
    class BrokenEmbedder:
        def embed(
            self,
            *,
            texts: Sequence[str],
            model: str,
        ) -> tuple[tuple[float, ...], ...]:
            return (ALPHA_VECTOR,)

    text = "\n\n".join(paragraph("alpha", index) for index in range(4))

    with pytest.raises(ChunkingError, match="1 vectors for 4 paragraphs"):
        semantic_split(
            text=text,
            embedder=BrokenEmbedder(),
            settings=ChunkSettings(min_chunk_tokens=10, max_chunk_tokens=20),
        )


def test_split_paragraphs_keeps_fenced_code_blocks_whole() -> None:
    text = (
        "Intro paragraph.\n"
        "\n"
        "```python\n"
        "\n"
        "code line 1\n"
        "\n"
        "code line 2\n"
        "```\n"
        "\n"
        "Outro paragraph."
    )

    assert split_paragraphs(text) == (
        "Intro paragraph.",
        "```python\n\ncode line 1\n\ncode line 2\n```",
        "Outro paragraph.",
    )


def test_split_paragraphs_keeps_longer_fences_with_nested_fences_whole() -> None:
    text = (
        "Intro.\n"
        "\n"
        "````markdown\n"
        "```python\n"
        "code\n"
        "```\n"
        "\n"
        "prose inside outer fence\n"
        "````\n"
        "\n"
        "Outro."
    )

    assert split_paragraphs(text) == (
        "Intro.",
        "````markdown\n```python\ncode\n```\n\nprose inside outer fence\n````",
        "Outro.",
    )


def test_split_paragraphs_ignores_info_string_lines_as_fence_closers() -> None:
    # Per CommonMark a closing fence carries no info string, so a stray
    # "```python" line inside an open block must not close it.
    text = "```\nliteral example:\n```python\nstill inside\n```\n\nAfter."

    assert split_paragraphs(text) == (
        "```\nliteral example:\n```python\nstill inside\n```",
        "After.",
    )


def test_semantic_split_truncates_oversized_embedding_inputs() -> None:
    huge = "alpha " + "x" * (EMBED_MAX_INPUT_CHARS + 5_000)
    other = "beta " + "y" * (EMBED_MAX_INPUT_CHARS + 5_000)
    text = f"{huge}\n\n{other}"
    embedder = topic_embedder()
    settings = ChunkSettings(min_chunk_tokens=50, max_chunk_tokens=150)

    chunks = semantic_split(text=text, embedder=embedder, settings=settings)

    assert chunks == (huge, other)
    assert all(len(probe) <= EMBED_MAX_INPUT_CHARS for probe in embedder.calls[0])


def test_embedding_probe_text_truncates_token_dense_inputs() -> None:
    import tiktoken

    text = "alpha " + ("😀" * 9_000)
    probe = embedding_probe_text(text, model="openai/text-embedding-3-small")
    encoding = tiktoken.encoding_for_model("text-embedding-3-small")

    assert len(text) < EMBED_MAX_INPUT_CHARS
    assert len(encoding.encode(text)) > 8_192
    assert len(encoding.encode(probe)) <= EMBED_MAX_INPUT_TOKENS


def test_merge_small_paragraphs_folds_short_runs_into_their_successor() -> None:
    short_one = "Tiny."
    short_two = "Also tiny."
    long_one = "x" * 250

    merged = merge_small_paragraphs((short_one, short_two, long_one))

    assert merged == (f"{short_one}\n\n{short_two}\n\n{long_one}",)


def test_merge_small_paragraphs_appends_trailing_short_run_to_last_chunk() -> None:
    long_one = "x" * 250
    short_tail = "Tiny tail."

    merged = merge_small_paragraphs((long_one, short_tail))

    assert merged == (f"{long_one}\n\n{short_tail}",)


def test_merge_short_tail_folds_small_tail_into_previous_chunk() -> None:
    settings = ChunkSettings(min_chunk_tokens=50, max_chunk_tokens=100)
    big = "a" * 360  # 90 tokens
    tiny = "b" * 80  # 20 tokens, under min

    assert merge_short_tail((big, tiny), settings=settings) == (f"{big}\n\n{tiny}",)


def test_merge_short_tail_keeps_tail_when_merge_would_blow_the_budget() -> None:
    settings = ChunkSettings(min_chunk_tokens=50, max_chunk_tokens=100)
    big = "a" * 460  # 115 tokens; merging would exceed max * 1.2
    tiny = "b" * 80

    assert merge_short_tail((big, tiny), settings=settings) == (big, tiny)


def test_write_chunks_with_identity_splitter_preserves_chapter_chunks(
    tmp_path: Path,
) -> None:
    markdown = "\n".join(
        [
            "# Book",
            "",
            "## One",
            "",
            "Body one.",
            "",
            "## Two",
            "",
            "Body two.",
            "",
        ]
    )

    chunk_paths = write_chunks(
        chunks_dir=tmp_path / "chunks",
        markdown=markdown,
        markdown_filename="book.md",
        chapter_level=2,
        splitter=lambda text: (text,),
    )

    assert tuple(path.name for path in chunk_paths) == ("001_one.md", "002_two.md")
    one = chunk_paths[0].read_text(encoding="utf-8")
    assert one == (
        "[Back to full document](../book.md)\n\n# Book\n\n## One\n\nBody one.\n"
    )


def test_write_chunks_names_multi_part_chapters(tmp_path: Path) -> None:
    markdown = "# Book\n\n## One\n\nBody one.\n\n## Two\n\nBody two.\n"

    def splitter(text: str) -> tuple[str, ...]:
        if "## One" in text:
            return ("one part a", "one part b")
        return (text,)

    chunk_paths = write_chunks(
        chunks_dir=tmp_path / "chunks",
        markdown=markdown,
        markdown_filename="book.md",
        chapter_level=2,
        splitter=splitter,
    )

    assert tuple(path.name for path in chunk_paths) == (
        "001_one_part_1.md",
        "002_one_part_2.md",
        "003_two.md",
    )
    part_two = chunk_paths[1].read_text(encoding="utf-8")
    assert part_two == ("[Back to full document](../book.md)\n\n# Book\n\none part b\n")


def test_chunk_markdown_document_uses_header_structure_when_present(
    tmp_path: Path,
) -> None:
    markdown = "# Book\n\n## One\n\nBody one.\n\n## Two\n\nBody two.\n"
    headers = (
        "- Book (H1, line 1, 9 lines)\n"
        "  - One (H2, line 3, 4 lines)\n"
        "  - Two (H2, line 7, 3 lines)\n"
    )
    embedder = topic_embedder()

    result = chunk_markdown_document(
        chunks_dir=tmp_path / "chunks",
        markdown=markdown,
        markdown_filename="book.md",
        headers=headers,
        settings=ChunkSettings(),
        embedder=embedder,
    )

    assert result.chapter_level == 2
    assert tuple(path.name for path in result.chunk_paths) == (
        "001_one.md",
        "002_two.md",
    )
    assert embedder.calls == []


def test_chunk_markdown_document_recovers_structure_from_stale_headers(
    tmp_path: Path,
) -> None:
    markdown = "# Book\n\n## One\n\nBody one.\n\n## Two\n\nBody two.\n"
    # The headers extract claims an H4 structure the markdown does not
    # have; the document's own headers must win over an unstructured
    # fallback.
    stale_headers = "- Ghost Chapter (H4, line 1, 2 lines)\n"
    embedder = topic_embedder()

    result = chunk_markdown_document(
        chunks_dir=tmp_path / "chunks",
        markdown=markdown,
        markdown_filename="book.md",
        headers=stale_headers,
        settings=ChunkSettings(),
        embedder=embedder,
    )

    assert result.chapter_level == 2
    assert tuple(path.name for path in result.chunk_paths) == (
        "001_one.md",
        "002_two.md",
    )
    assert embedder.calls == []


def test_chunk_markdown_document_falls_back_to_semantic_chunks_without_headers(
    tmp_path: Path,
) -> None:
    paragraphs = [
        paragraph("alpha", 1),
        paragraph("alpha", 2),
        paragraph("beta", 1),
        paragraph("beta", 2),
    ]
    markdown = "\n\n".join(paragraphs)

    result = chunk_markdown_document(
        chunks_dir=tmp_path / "chunks",
        markdown=markdown,
        markdown_filename="notes.md",
        headers="# Document Structure\n\nTable of Contents:\n",
        settings=ChunkSettings(
            min_chunk_tokens=100,
            max_chunk_tokens=150,
            similarity_window=1,
        ),
        embedder=topic_embedder(),
    )

    assert result.chapter_level is None
    assert tuple(path.name for path in result.chunk_paths) == (
        "001_alpha_paragraph_1.md",
        "002_beta_paragraph_1.md",
    )
    first = result.chunk_paths[0].read_text(encoding="utf-8")
    assert first.startswith("[Back to full document](../notes.md)\n\n")
    assert "alpha paragraph 2." in first
