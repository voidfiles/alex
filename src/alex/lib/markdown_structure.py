"""Parsing and chunking of markdown document structure."""

from __future__ import annotations

import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

CHUNK_LINE_LIMIT = 10_000


class MarkdownStructureError(ValueError):
    pass


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


def markdown_header_match(line: str) -> re.Match[str] | None:
    return re.match(r"^(#{1,6})\s+(.+?)\s*(?:#+\s*)?$", line)


def strip_inline_markdown(text: str) -> str:
    return re.sub(r"\*\*|__|\*|_|`", "", text)


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


def parse_toc_header_levels(headers: str) -> tuple[int, ...]:
    levels: list[int] = []
    pattern = re.compile(r"\(H([1-6]),\s*line\s+\d+", re.IGNORECASE)
    for line in headers.splitlines():
        match = pattern.search(line)
        if match:
            levels.append(int(match.group(1)))
    return tuple(levels)


def infer_chapter_level(*, headers: str, markdown: str) -> int:
    levels = parse_toc_header_levels(headers)
    if not levels:
        levels = tuple(header.level for header in parse_markdown_headers(markdown))
    if not levels:
        raise MarkdownStructureError(
            "Cannot infer chapter level without markdown headers."
        )

    counts = Counter(levels)
    top_level = min(counts)
    if counts[top_level] == 1:
        for level in sorted(counts):
            if level > top_level:
                return level
    return top_level


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
        raise MarkdownStructureError(
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


def slugify_title(title: str) -> str:
    normalized = strip_inline_markdown(title).lower()
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[\s_-]+", "_", normalized)
    return normalized.strip("_")[:120] or "section"


def table_of_contents_markdown(markdown: str) -> str:
    lines = markdown.splitlines()
    headers = parse_markdown_headers(markdown)
    toc_lines = [
        table_of_contents_line(
            header=header,
            line_count=section_line_count(
                header=header,
                headers=headers,
                total_lines=len(lines),
            ),
        )
        for header in headers
    ]

    return (
        "\n".join(
            [
                "# Document Structure",
                "",
                "Table of Contents:",
                "",
                *toc_lines,
            ]
        ).rstrip()
        + "\n"
    )


def table_of_contents_line(*, header: MarkdownHeader, line_count: int) -> str:
    indent = "  " * (header.level - 1)
    line_number = header.line_index + 1
    return (
        f"{indent}- {header.title} "
        f"(H{header.level}, line {line_number}, {line_count} lines)"
    )


def section_line_count(
    *,
    header: MarkdownHeader,
    headers: tuple[MarkdownHeader, ...],
    total_lines: int,
) -> int:
    end_index = total_lines
    for next_header in headers:
        if next_header.line_index <= header.line_index:
            continue
        if next_header.level <= header.level:
            end_index = next_header.line_index
            break
    return max(end_index - header.line_index, 1)
