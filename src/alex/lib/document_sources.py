from __future__ import annotations

import posixpath
import re
import shutil
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree


class UnsupportedDocumentSourceError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentMetadata:
    title: str
    authors: tuple[str, ...] = ()


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        return
    shutil.copy2(source, destination)


def metadata_from_markdown(markdown: str, source: Path) -> DocumentMetadata:
    frontmatter = parse_frontmatter(markdown)
    title = (
        frontmatter.get("title")
        or first_markdown_heading(markdown)
        or title_from_stem(source)
    )
    authors = split_authors(
        frontmatter.get("authors")
        or frontmatter.get("author")
        or first_markdown_byline(markdown)
        or ""
    )
    return DocumentMetadata(title=title, authors=authors)


def parse_frontmatter(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    values: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return values
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip().strip("'\"")
        if normalized_key and normalized_value:
            values[normalized_key] = normalized_value
    return {}


def first_markdown_heading(markdown: str) -> str | None:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return strip_inline_markdown(match.group(1)).strip()
    return None


def first_markdown_byline(markdown: str) -> str | None:
    for line in markdown.splitlines()[:40]:
        stripped = strip_inline_markdown(line).strip()
        if stripped.lower().startswith("by "):
            return stripped[3:].strip()
    return None


def strip_inline_markdown(text: str) -> str:
    return re.sub(r"\*\*|__|\*|_|`", "", text)


def split_authors(authors: str) -> tuple[str, ...]:
    if not authors:
        return ()
    normalized = re.sub(r"\s+and\s+", ",", authors)
    return tuple(author.strip() for author in normalized.split(",") if author.strip())


def title_from_stem(source: Path) -> str:
    return source.stem.replace("-", " ").replace("_", " ").strip().title()


def canonical_name_for(
    *,
    metadata: DocumentMetadata,
    source: Path,
    name_override: str | None,
) -> str:
    if name_override:
        return canonicalize_name([name_override])

    parts = [metadata.title or title_from_stem(source), *metadata.authors]
    return canonicalize_name(parts)


def canonicalize_name(parts: Iterable[str]) -> str:
    combined = "_".join(part.strip() for part in parts if part.strip())
    normalized = combined.lower()
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[\s_-]+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized[:150] or "document"


def read_epub_source(source: Path) -> tuple[DocumentMetadata, str]:
    try:
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            if "META-INF/encryption.xml" in names:
                raise UnsupportedDocumentSourceError(
                    "Encrypted EPUB files are not supported."
                )

            opf_path = read_opf_path(archive)
            opf_root = ElementTree.fromstring(read_archive_text(archive, opf_path))
            metadata = metadata_from_opf(opf_root, source)
            document_paths = spine_document_paths(opf_root, opf_path)
            body_parts = [
                html_to_markdown(read_archive_text(archive, document_path))
                for document_path in document_paths
            ]
    except zipfile.BadZipFile as error:
        raise UnsupportedDocumentSourceError(f"Invalid EPUB file: {source}") from error
    except ElementTree.ParseError as error:
        raise UnsupportedDocumentSourceError(
            f"Invalid EPUB metadata: {source}"
        ) from error

    heading = f"# {metadata.title}\n\n"
    byline = f"By {', '.join(metadata.authors)}\n\n" if metadata.authors else ""
    markdown = heading + byline + "\n\n".join(part for part in body_parts if part)
    if markdown and not markdown.endswith("\n"):
        markdown += "\n"
    return metadata, markdown


def read_opf_path(archive: zipfile.ZipFile) -> str:
    container = ElementTree.fromstring(
        read_archive_text(archive, "META-INF/container.xml")
    )
    for element in container.iter():
        if local_name(element.tag) == "rootfile":
            opf_path = element.attrib.get("full-path")
            if opf_path:
                return normalize_archive_path(opf_path)
    raise UnsupportedDocumentSourceError(
        "EPUB container does not declare an OPF package."
    )


def metadata_from_opf(root: ElementTree.Element, source: Path) -> DocumentMetadata:
    title = first_descendant_text(root, "title") or title_from_stem(source)
    authors = tuple(
        text
        for element in root.iter()
        if local_name(element.tag) == "creator"
        if (text := text_content(element))
    )
    return DocumentMetadata(title=title, authors=authors)


def spine_document_paths(root: ElementTree.Element, opf_path: str) -> list[str]:
    manifest: dict[str, str] = {}
    for element in root.iter():
        if local_name(element.tag) != "item":
            continue
        item_id = element.attrib.get("id")
        href = element.attrib.get("href")
        media_type = element.attrib.get("media-type", "")
        if item_id and href and media_type in {"application/xhtml+xml", "text/html"}:
            manifest[item_id] = resolve_archive_href(opf_path, href)

    spine_paths = [
        manifest[idref]
        for element in root.iter()
        if local_name(element.tag) == "itemref"
        if (idref := element.attrib.get("idref")) in manifest
    ]
    if spine_paths:
        return spine_paths
    return list(manifest.values())


def resolve_archive_href(opf_path: str, href: str) -> str:
    base_path = posixpath.dirname(opf_path)
    return normalize_archive_path(posixpath.join(base_path, href))


def normalize_archive_path(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/")).lstrip("/")
    if normalized == "." or normalized.startswith("../") or "/../" in normalized:
        raise UnsupportedDocumentSourceError(f"Unsafe EPUB archive path: {path}")
    return normalized


def read_archive_text(archive: zipfile.ZipFile, path: str) -> str:
    try:
        return archive.read(path).decode("utf-8")
    except KeyError as error:
        raise UnsupportedDocumentSourceError(
            f"EPUB archive is missing {path}."
        ) from error
    except UnicodeDecodeError as error:
        raise UnsupportedDocumentSourceError(
            f"EPUB text is not UTF-8: {path}"
        ) from error


def first_descendant_text(root: ElementTree.Element, name: str) -> str | None:
    for element in root.iter():
        if local_name(element.tag) == name:
            return text_content(element)
    return None


def text_content(element: ElementTree.Element) -> str | None:
    text = "".join(element.itertext()).strip()
    return text or None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class MarkdownHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", normalized):
            self.ensure_blank_line()
            self.parts.append(f"{'#' * int(normalized[1])} ")
        elif normalized in {"p", "div", "section", "article", "blockquote"}:
            self.ensure_blank_line()
        elif normalized == "br":
            self.parts.append("\n")
        elif normalized == "li":
            self.ensure_blank_line()
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", normalized) or normalized in {
            "p",
            "div",
            "section",
            "article",
            "blockquote",
            "li",
        }:
            self.ensure_blank_line()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", unescape(data))
        if text.strip():
            self.parts.append(text)

    def ensure_blank_line(self) -> None:
        current = "".join(self.parts)
        if not current:
            return
        if current.endswith("\n\n"):
            return
        if current.endswith("\n"):
            self.parts.append("\n")
            return
        self.parts.append("\n\n")

    def get_markdown(self) -> str:
        markdown = "".join(self.parts)
        markdown = re.sub(r"[ \t]+\n", "\n", markdown)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        return markdown.strip()


def html_to_markdown(html: str) -> str:
    parser = MarkdownHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.get_markdown()
