"""Deterministic document parts and raw-to-normalized text coordinates."""

from __future__ import annotations

import hashlib
import html
import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from alex.lib.ontology_enrichment_models import (
    BookMetadata,
    DocumentPart,
    MetadataField,
    MetadataValue,
    TextRepresentation,
)


def document_id(prefix: str, *parts: str) -> str:
    return prefix + "_" + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class NormalizedText:
    text: str
    raw_ranges: tuple[tuple[int, int], ...]

    def span(self, start: int, end: int) -> tuple[int, int, str] | None:
        begin = bisect_left(self.raw_ranges, start, key=lambda item: item[0])
        finish = bisect_right(self.raw_ranges, end, key=lambda item: item[1])
        if begin >= finish or self.raw_ranges[begin][0] < start:
            return None
        quote = self.text[begin:finish]
        return (begin, finish, quote) if quote.strip() else None


def normalize_markdown(markdown: str) -> NormalizedText:
    """Normalize markup/entities without modifying the grounding source.

    Every retained character carries its original range; decoded entities carry
    their entire raw range. Offsets are Unicode code points, never UTF-8 bytes.
    """
    text = markdown
    ranges = [(index, index + 1) for index in range(len(markdown))]

    def transform(
        pattern: str,
        replacement: Callable[[re.Match[str]], str],
        *,
        group: int | None = None,
    ) -> None:
        nonlocal text, ranges
        output: list[str] = []
        mapped: list[tuple[int, int]] = []
        cursor = 0
        for match in re.finditer(pattern, text, re.MULTILINE):
            output.append(text[cursor : match.start()])
            mapped.extend(ranges[cursor : match.start()])
            value = replacement(match)
            output.append(value)
            if group is not None:
                mapped.extend(ranges[match.start(group) : match.end(group)])
            elif value:
                raw_range = (ranges[match.start()][0], ranges[match.end() - 1][1])
                mapped.extend([raw_range] * len(value))
            cursor = match.end()
        output.append(text[cursor:])
        mapped.extend(ranges[cursor:])
        text, ranges = "".join(output), mapped

    transform(r"<!--(?s:.*?)-->|</?[A-Za-z][^>\n]*>", lambda _: "")
    transform(
        r"&(?:#x[0-9a-fA-F]+|#\d+|[A-Za-z][A-Za-z0-9]+);",
        lambda match: html.unescape(match.group()),
    )
    transform(r"!?\[([^\]\n]+)\]\([^\)\n]+\)", lambda m: m.group(1), group=1)
    transform(r"^ {0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)", lambda _: "")
    transform(r"^ {0,3}(?:`{3,}|~{3,})[^\n]*", lambda _: "")
    transform(r"(?<!\w)[*_]{1,2}(?=\S)|(?<=\S)[*_]{1,2}(?!\w)|`", lambda _: "")
    return NormalizedText(text, tuple(ranges))


def text_representation(normalized: NormalizedText) -> TextRepresentation:
    digest = hashlib.sha256(normalized.text.encode()).hexdigest()
    return TextRepresentation(
        id=document_id("text", digest, "alex-markdown-text-v001"),
        sha256=digest,
        normalization="alex-markdown-text-v001",
        text=normalized.text,
    )


def parse_document_parts(
    markdown: str, source_sha256: str, title: str | None
) -> list[DocumentPart]:
    from markdown_it import MarkdownIt

    offsets = [0, *(m.end() for m in re.finditer("\n", markdown))]
    book_id = document_id("book", source_sha256)
    source_id = document_id("source", source_sha256)
    last_line = max(1, bisect_right(offsets, len(markdown) - 1))
    parts = [
        DocumentPart(
            id=book_id,
            kind="book",
            title=title,
            char_start=0,
            char_end=len(markdown),
            line_start=1,
            line_end=last_line,
        ),
        DocumentPart(
            id=source_id,
            kind="source",
            title=title,
            parent=book_id,
            char_start=0,
            char_end=len(markdown),
            line_start=1,
            line_end=last_line,
        ),
    ]
    tokens = MarkdownIt("commonmark").enable("table").parse(markdown)
    headings: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.map is not None:
            headings.append(
                (token.map[0], int(token.tag[1:]), tokens[index + 1].content)
            )
    stack: list[tuple[int, str]] = []
    for index, (line, level, heading) in enumerate(headings):
        end_line = next(
            (
                next_line
                for next_line, depth, _ in headings[index + 1 :]
                if depth <= level
            ),
            len(offsets),
        )
        start = offsets[line]
        end = offsets[end_line] if end_line < len(offsets) else len(markdown)
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else source_id
        part_id = document_id("part", source_sha256, str(start), str(end))
        kind: Literal["section", "chapter", "appendix", "figure", "table"] = "section"
        if re.match(r"(?i)^(chapter\b|\d+[.:)]\s)", heading):
            kind = "chapter"
        elif re.match(r"(?i)^appendix\b", heading):
            kind = "appendix"
        elif re.match(r"(?i)^figure\s+\d", heading):
            kind = "figure"
        elif re.match(r"(?i)^table\s+\d", heading):
            kind = "table"
        parts.append(
            DocumentPart(
                id=part_id,
                kind=kind,
                title=heading,
                parent=parent,
                char_start=start,
                char_end=end,
                line_start=line + 1,
                line_end=max(line + 1, bisect_right(offsets, max(start, end - 1))),
            )
        )
        stack.append((level, part_id))
    # EPUB conversions often retain explicit chapter numbers/titles as plain
    # text after part markers. A marker is a boundary, never a page number.
    markers = list(re.finditer(r"(?m)^part\d{4,}[ \t]*\r?$", markdown))
    lines = markdown.splitlines(keepends=True)
    for index, marker in enumerate(markers):
        boundary = (
            markers[index + 1].start() if index + 1 < len(markers) else len(markdown)
        )
        first_line = bisect_right(offsets, marker.end()) - 1
        candidates = [
            (line_number, lines[line_number].strip())
            for line_number in range(first_line + 1, len(lines))
            if offsets[line_number] < boundary and lines[line_number].strip()
        ]
        if not candidates:
            continue
        number_line, first = candidates[0]
        extracted_kind: Literal["chapter", "section", "appendix"] | None = None
        extracted_title = first
        if re.fullmatch(r"\d{1,3}", first) and len(candidates) > 1:
            _, heading_title = candidates[1]
            if len(heading_title) <= 200:
                extracted_kind, extracted_title = "chapter", f"{first}. {heading_title}"
        elif re.match(r"(?i)^appendix\b", first):
            extracted_kind = "appendix"
        elif re.match(
            r"(?i)^(preface|references|bibliography|acknowledg(?:e)?ments|"
            r"about the author)\b",
            first,
        ):
            extracted_kind = "section"
        if extracted_kind is None:
            continue
        begin = offsets[number_line]
        parent_part = min(
            (
                part
                for part in parts
                if part.kind in {"source", "section"}
                and part.char_start <= begin
                and part.char_end >= boundary
            ),
            key=lambda part: part.char_end - part.char_start,
        )
        parts.append(
            DocumentPart(
                id=document_id(
                    "part", source_sha256, extracted_kind, str(begin), str(boundary)
                ),
                kind=extracted_kind,
                title=extracted_title,
                parent=parent_part.id,
                char_start=begin,
                char_end=boundary,
                line_start=number_line + 1,
                line_end=max(number_line + 1, bisect_right(offsets, boundary - 1)),
            )
        )
    for token_index, token in enumerate(tokens):
        if token.map is None:
            continue
        block_kind: Literal["table", "figure"] | None = None
        block_title = None
        if token.type == "table_open":
            block_kind = "table"
        elif token.type == "inline" and token.children is not None:
            image = next(
                (child for child in token.children if child.type == "image"), None
            )
            if image is not None:
                block_kind, block_title = "figure", image.content or None
        if block_kind is None:
            continue
        start_line, end_line = token.map
        begin = offsets[start_line]
        finish = offsets[end_line] if end_line < len(offsets) else len(markdown)
        parent_part = min(
            (
                part
                for part in parts
                if part.kind != "book"
                and part.char_start <= begin
                and part.char_end >= finish
            ),
            key=lambda part: part.char_end - part.char_start,
        )
        parts.append(
            DocumentPart(
                id=document_id(
                    "part", source_sha256, block_kind, str(token_index), str(begin)
                ),
                kind=block_kind,
                title=block_title,
                parent=parent_part.id,
                char_start=begin,
                char_end=finish,
                line_start=start_line + 1,
                line_end=max(
                    start_line + 1, bisect_right(offsets, max(begin, finish - 1))
                ),
            )
        )
    return parts


def input_metadata(
    markdown: str, supplied: BookMetadata | None
) -> tuple[list[MetadataValue], list[str]]:
    import yaml

    values: list[MetadataValue] = []
    assumptions: list[str] = []
    frontmatter: BookMetadata | None = None
    match = re.match(
        r"\A---\r?\n(?P<yaml>.*?)\r?\n---(?:\r?\n|\Z)", markdown, re.DOTALL
    )
    if match:
        raw = yaml.safe_load(match.group("yaml"))
        if isinstance(raw, dict):
            data: dict[str, object] = {}
            for field in BookMetadata.model_fields:
                value = raw.get(field)
                if value is not None:
                    if field in {"created", "issued"} and hasattr(value, "isoformat"):
                        value = value.isoformat()
                    if field in {"creator", "identifier"} and isinstance(value, str):
                        value = [value]
                    data[field] = value
            frontmatter = BookMetadata.model_validate(data)
    for origin, metadata in (("frontmatter", frontmatter), ("user", supplied)):
        if metadata is None:
            continue
        for field, value in metadata.model_dump().items():
            if value is None or value == []:
                continue
            if supplied is not None and origin == "frontmatter":
                override = getattr(supplied, field)
                if override is not None and override != []:
                    if override != value:
                        assumptions.append(
                            f"User metadata overrides frontmatter {field}."
                        )
                    continue
            items = value if isinstance(value, list) else [value]
            for item in items:
                values.append(
                    MetadataValue(
                        field=_metadata_field(field),
                        value=str(item),
                        origin="user" if origin == "user" else "frontmatter",
                    )
                )
    return values, assumptions


def _metadata_field(field: str) -> MetadataField:
    # Pydantic checks the Literal and preserves a narrow return type for MyPy.
    return MetadataValue(field=field, value="placeholder", origin="user").field  # type: ignore[arg-type]
