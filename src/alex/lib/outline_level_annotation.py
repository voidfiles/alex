from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

type ChapterLabel = Literal["H1", "H2", "H3", "H4", "H5", "H6"]
type PendingValue = Literal["TODO"]
type LevelValue = ChapterLabel | PendingValue
type LineValue = Annotated[int, Field(gt=0)] | PendingValue
type HeadingValue = Annotated[str, Field(min_length=1)]

CHAPTER_LABELS: Final[tuple[ChapterLabel, ...]] = (
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
)

PENDING_FRONTMATTER: Final[bytes] = (
    b"---\n"
    b"document:\n"
    b"  title: TODO\n"
    b"  level: TODO\n"
    b"  line: TODO\n\n"
    b"section:\n"
    b"  level: TODO\n"
    b"  first_heading: TODO\n"
    b"  line: TODO\n\n"
    b"chapter:\n"
    b"  level: TODO\n"
    b"  first_heading: TODO\n"
    b"  line: TODO\n\n"
    b"subchapter:\n"
    b"  level: TODO\n"
    b"  first_heading: TODO\n"
    b"  line: TODO\n"
    b"---\n"
)


class OutlineLevelEvalError(ValueError):
    __slots__ = ("path", "problem")

    def __init__(self, path: Path, problem: str) -> None:
        self.path = path
        self.problem = problem
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.path}: {self.problem}"


class _FrozenAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DocumentAnnotation(_FrozenAnnotation):
    title: HeadingValue
    level: LevelValue
    line: LineValue


class HeadingAnnotation(_FrozenAnnotation):
    level: LevelValue
    first_heading: HeadingValue
    line: LineValue


class OutlineLevelAnnotation(_FrozenAnnotation):
    document: DocumentAnnotation
    section: HeadingAnnotation
    chapter: HeadingAnnotation
    subchapter: HeadingAnnotation


def render_pending_outline_level_output(input_bytes: bytes) -> bytes:
    return PENDING_FRONTMATTER + input_bytes


def parse_outline_level_output(
    *, output_path: Path, output_bytes: bytes, input_bytes: bytes
) -> OutlineLevelAnnotation:
    if not output_bytes.endswith(input_bytes):
        raise OutlineLevelEvalError(
            output_path, "output body does not retain exact input"
        )
    prefix = output_bytes[: len(output_bytes) - len(input_bytes)]
    try:
        lines = prefix.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise OutlineLevelEvalError(
            output_path, "frontmatter must be valid UTF-8"
        ) from error
    if len(lines) != 21:
        raise OutlineLevelEvalError(
            output_path, "canonical frontmatter requires exactly 21 lines"
        )

    expected_lines = {
        0: "---",
        1: "document:",
        5: "",
        6: "section:",
        10: "",
        11: "chapter:",
        15: "",
        16: "subchapter:",
        20: "---",
    }
    for index, expected in expected_lines.items():
        _require_line(lines[index], expected, output_path)

    annotation = OutlineLevelAnnotation(
        document=DocumentAnnotation(
            title=_parse_heading(
                _scalar(lines[2], "  title: ", output_path),
                output_path,
                "document.title",
            ),
            level=_parse_level(
                _scalar(lines[3], "  level: ", output_path),
                output_path,
                "document.level",
            ),
            line=_parse_line(
                _scalar(lines[4], "  line: ", output_path),
                output_path,
                "document.line",
            ),
        ),
        section=_parse_heading_map(lines[7:10], output_path, "section"),
        chapter=_parse_heading_map(lines[12:15], output_path, "chapter"),
        subchapter=_parse_heading_map(lines[17:20], output_path, "subchapter"),
    )
    if not prefix.startswith(b"---\n") or not prefix.endswith(b"---\n"):
        raise OutlineLevelEvalError(output_path, "frontmatter delimiters must use LF")
    return annotation


def _parse_heading_map(lines: list[str], path: Path, name: str) -> HeadingAnnotation:
    return HeadingAnnotation(
        level=_parse_level(_scalar(lines[0], "  level: ", path), path, f"{name}.level"),
        first_heading=_parse_heading(
            _scalar(lines[1], "  first_heading: ", path),
            path,
            f"{name}.first_heading",
        ),
        line=_parse_line(_scalar(lines[2], "  line: ", path), path, f"{name}.line"),
    )


def _require_line(actual: str, expected: str, path: Path) -> None:
    if actual != expected:
        label = expected or "blank line"
        raise OutlineLevelEvalError(path, f"expected {label}, found {actual!r}")


def _scalar(line: str, prefix: str, path: Path) -> str:
    if not line.startswith(prefix):
        raise OutlineLevelEvalError(path, f"expected field {prefix.strip()!r}")
    raw = line.removeprefix(prefix)
    if not raw.strip():
        raise OutlineLevelEvalError(path, f"blank scalar for {prefix.strip()!r}")
    return raw


def _parse_heading(raw: str, path: Path, field: str) -> HeadingValue:
    if not raw.startswith('"'):
        return raw.strip()
    try:
        decoded: str = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OutlineLevelEvalError(
            path, f"invalid quoted string for {field}"
        ) from error
    if not decoded:
        raise OutlineLevelEvalError(path, f"blank scalar for {field}")
    return decoded


def _parse_level(raw: str, path: Path, field: str) -> LevelValue:
    if raw == "TODO":
        return "TODO"
    match = re.fullmatch(r"H([1-6])", raw)
    if match is None:
        raise OutlineLevelEvalError(path, f"{field} must be TODO or H1-H6")
    return CHAPTER_LABELS[int(match.group(1)) - 1]


def _parse_line(raw: str, path: Path, field: str) -> LineValue:
    if raw == "TODO":
        return "TODO"
    if re.fullmatch(r"[0-9]+", raw) is None or int(raw) <= 0:
        raise OutlineLevelEvalError(path, f"{field} must be TODO or a positive integer")
    return int(raw)
