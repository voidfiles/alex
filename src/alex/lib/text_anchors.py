"""Model-facing text anchors and deterministic, stand-off quote extraction.

All offsets address the supplied immutable Python string (Unicode code points,
start inclusive, end exclusive). No normalization or LLM calls occur here.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from alex.lib.prompt_templates import load_prompt


class AnchorError(ValueError):
    """An anchor cannot be safely resolved."""


class SourceMismatchError(AnchorError):
    """Document, revision, or representation does not match."""


class UnknownUnitError(AnchorError):
    """A unit ID is unknown or outside the approved window."""


class AnchorNotFoundError(AnchorError):
    """No exact match exists in the requested scope."""


class AmbiguousAnchorError(AnchorError):
    """More than one valid source span matches."""


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UnitSelection(_Record):
    """Select complete units, including both named endpoints."""

    kind: Literal["units"]
    first_unit_id: str = Field(min_length=1)
    last_unit_id_inclusive: str = Field(min_length=1)
    purpose: str = ""


class BoundarySelection(_Record):
    """Select from the start of start_text through the end of end_text."""

    kind: Literal["boundaries"]
    start_unit_id: str = Field(min_length=1)
    start_text: str = Field(min_length=1)
    end_unit_id: str = Field(min_length=1)
    end_text: str = Field(min_length=1)
    purpose: str = ""


type TextSelection = Annotated[
    UnitSelection | BoundarySelection, Field(discriminator="kind")
]


class AnchorSelections(_Record):
    """Strict JSON response contract; identity fields are copied from the view."""

    document_id: str = Field(min_length=1)
    source_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    representation_id: str = Field(min_length=1)
    selections: tuple[TextSelection, ...]


class AnchoredQuote(_Record):
    """Source-derived quotation that can be serialized separately from the source."""

    document_id: str = Field(min_length=1)
    source_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    representation_id: str = Field(min_length=1)
    offset_unit: Literal["unicode-code-points"] = "unicode-code-points"
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    exact: str = Field(min_length=1)
    prefix: str = ""
    suffix: str = ""
    resolved_by: Literal["units", "boundaries"]
    purpose: str = ""

    @model_validator(mode="after")
    def check_span(self) -> AnchoredQuote:
        if self.end - self.start != len(self.exact):
            raise ValueError("Quote bounds must describe the exact text length.")
        return self

    @property
    def quote_id(self) -> str:
        coordinates = json.dumps(
            [
                self.document_id,
                self.source_revision,
                self.representation_id,
                self.start,
                self.end,
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return "q_" + _sha256(coordinates)

    def selectors(self) -> list[dict[str, str | int]]:
        """W3C-shaped selectors addressing this record's text representation."""
        return [
            {"type": "TextPositionSelector", "start": self.start, "end": self.end},
            {
                "type": "TextQuoteSelector",
                "exact": self.exact,
                "prefix": self.prefix,
                "suffix": self.suffix,
            },
        ]

    def validate_source(self, document: TextAnchorDocument) -> None:
        """Verify a stored record against the intended source snapshot."""
        _check_identity(self, document)
        source = document.text
        if (
            self.end > len(source)
            or source[self.start : self.end] != self.exact
            or self.start < len(self.prefix)
            or source[self.start - len(self.prefix) : self.start] != self.prefix
            or source[self.end : self.end + len(self.suffix)] != self.suffix
        ):
            raise SourceMismatchError("Quote text, context, or bounds do not match.")


@dataclass(frozen=True)
class TextUnit:
    unit_id: str
    start: int
    end: int


@dataclass(frozen=True)
class TextAnchorDocument:
    """Preassign paragraph IDs without changing the supplied text.

    Blank lines separate units. Leading/trailing whitespace lies outside each
    unit; internal text, whitespace, and newlines remain untouched. IDs are local
    to this document revision and paragraph segmentation version.
    """

    text: str = field(repr=False)
    document_id: str
    representation_id: str = "plain-text-v1"
    source_revision: str = field(init=False)
    units: tuple[TextUnit, ...] = field(init=False)
    _indices: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.document_id or not self.representation_id:
            raise AnchorError("Document and representation IDs must be nonempty.")
        units = tuple(
            TextUnit(f"p{index:06d}", start, end)
            for index, (start, end) in enumerate(_paragraph_spans(self.text), 1)
        )
        object.__setattr__(self, "source_revision", _sha256(self.text))
        object.__setattr__(self, "units", units)
        object.__setattr__(
            self,
            "_indices",
            MappingProxyType({unit.unit_id: i for i, unit in enumerate(units)}),
        )

    def _index(self, unit_id: str) -> int:
        try:
            return self._indices[unit_id]
        except KeyError as error:
            raise UnknownUnitError(f"Unknown source unit: {unit_id!r}.") from error

    def window(
        self,
        first_unit_id: str | None = None,
        last_unit_id_inclusive: str | None = None,
    ) -> TextAnchorWindow:
        """Prepare a contiguous model-visible window with global unit IDs."""
        first = self._index(first_unit_id) if first_unit_id is not None else 0
        stop = (
            self._index(last_unit_id_inclusive) + 1
            if last_unit_id_inclusive is not None
            else len(self.units)
        )
        return TextAnchorWindow(self, first, stop)


@dataclass(frozen=True)
class TextAnchorWindow:
    document: TextAnchorDocument
    first_index: int
    stop_index: int

    def __post_init__(self) -> None:
        if not 0 <= self.first_index <= self.stop_index <= len(self.document.units) or (
            self.first_index == self.stop_index and self.document.units
        ):
            raise AnchorError("Invalid or reversed source window.")

    @property
    def units(self) -> tuple[TextUnit, ...]:
        return self.document.units[self.first_index : self.stop_index]

    def render(self) -> str:
        """JSON view: source text cannot impersonate generated unit labels."""
        return json.dumps(
            {
                "document_id": self.document.document_id,
                "source_revision": self.document.source_revision,
                "representation_id": self.document.representation_id,
                "unit_scheme": "blank-line-paragraphs-v1",
                "units": [
                    {
                        "unit_id": unit.unit_id,
                        "text": self.document.text[unit.start : unit.end],
                    }
                    for unit in self.units
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    def prompt(
        self, topic: str, *, count: int = 3, prompt_version: str | None = None
    ) -> str:
        """Reusable selection instructions; the caller chooses how to call an LLM."""
        if count < 1:
            raise AnchorError("Selection count must be positive.")
        return load_prompt("text_anchor_selection", version=prompt_version).render(
            topic=topic,
            count=str(count),
            schema=json.dumps(AnchorSelections.model_json_schema(), indent=2),
            source=self.render(),
        )

    def _unit(self, unit_id: str) -> TextUnit:
        index = self.document._index(unit_id)
        if not self.first_index <= index < self.stop_index:
            raise UnknownUnitError(f"Source unit {unit_id!r} is outside this window.")
        return self.document.units[index]

    def resolve(
        self,
        selection: UnitSelection | BoundarySelection,
        *,
        max_quote_chars: int | None = 20_000,
        context_chars: int = 64,
    ) -> AnchoredQuote:
        """Resolve exactly one span, then slice the original source string."""
        _check_limits(max_quote_chars, context_chars)
        if isinstance(selection, UnitSelection):
            first = self._unit(selection.first_unit_id)
            last = self._unit(selection.last_unit_id_inclusive)
            start, end = first.start, last.end
            if first.start > last.start:
                raise AnchorError("Selection units are reversed.")
        else:
            first = self._unit(selection.start_unit_id)
            last = self._unit(selection.end_unit_id)
            if first.start > last.start:
                raise AnchorError("Selection units are reversed.")
            start, end = _locate_boundaries(self.document.text, selection, first, last)
        if max_quote_chars is not None and end - start > max_quote_chars:
            raise AnchorError("Selected quote exceeds the maximum quote size.")
        source = self.document.text
        return AnchoredQuote(
            document_id=self.document.document_id,
            source_revision=self.document.source_revision,
            representation_id=self.document.representation_id,
            start=start,
            end=end,
            exact=source[start:end],
            prefix=source[max(0, start - context_chars) : start],
            suffix=source[end : end + context_chars],
            resolved_by=selection.kind,
            purpose=selection.purpose,
        )

    def extract(
        self,
        response: str,
        *,
        max_selections: int = 10,
        max_quote_chars: int | None = 20_000,
        context_chars: int = 64,
    ) -> tuple[AnchoredQuote, ...]:
        """Validate strict model JSON, identity, scope, and all selections.

        Overlapping annotations are allowed. Each selection is one contiguous
        span; an invalid selection rejects the response rather than returning a
        partial result. Markdown code fences are not part of the JSON contract.
        """
        if max_selections < 0:
            raise AnchorError("Maximum selection count must be nonnegative.")
        _check_limits(max_quote_chars, context_chars)
        try:
            payload = AnchorSelections.model_validate_json(response)
        except ValidationError as error:
            raise AnchorError("Invalid text-anchor selection JSON.") from error
        _check_identity(payload, self.document)
        if len(payload.selections) > max_selections:
            raise AnchorError("Response exceeds the maximum selection count.")
        return tuple(
            self.resolve(
                selection,
                max_quote_chars=max_quote_chars,
                context_chars=context_chars,
            )
            for selection in payload.selections
        )


def locate_exact_quote(
    source: str,
    quote: str,
    *,
    window: tuple[int, int] | None = None,
    prefix: str = "",
    suffix: str = "",
) -> tuple[int, int]:
    """Find one verbatim occurrence; context may extend outside the window.

    The window limits the selected span. The caller is responsible for source
    identity. Overlapping occurrences count separately; no normalization occurs.
    """
    if not quote:
        raise AnchorError("Empty quote.")
    lo, hi = window if window is not None else (0, len(source))
    if not 0 <= lo <= hi <= len(source):
        raise AnchorError("Invalid source window.")
    match = None
    for start in _occurrences(source, quote, lo, hi):
        end = start + len(quote)
        if (
            start >= len(prefix)
            and source[start - len(prefix) : start] == prefix
            and source[end : end + len(suffix)] == suffix
        ):
            if match is not None:
                raise AmbiguousAnchorError("Multiple exact quote occurrences.")
            match = (start, end)
    if match is None:
        raise AnchorNotFoundError("No exact quote in the specified source window.")
    return match


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_limits(max_quote_chars: int | None, context_chars: int) -> None:
    if max_quote_chars is not None and max_quote_chars < 1:
        raise AnchorError("Maximum quote size must be positive or None.")
    if context_chars < 0:
        raise AnchorError("Context size must be nonnegative.")


def _check_identity(
    record: AnchorSelections | AnchoredQuote, document: TextAnchorDocument
) -> None:
    if (
        record.document_id != document.document_id
        or record.source_revision != document.source_revision
        or record.representation_id != document.representation_id
    ):
        raise SourceMismatchError(
            "Document, source revision, or representation mismatch."
        )


def _paragraph_spans(source: str) -> Iterator[tuple[int, int]]:
    offset = 0
    start: int | None = None
    end = 0
    for line in source.splitlines(keepends=True):
        if line.strip():
            if start is None:
                start = offset + len(line) - len(line.lstrip())
            end = offset + len(line.rstrip())
        elif start is not None:
            yield start, end
            start = None
        offset += len(line)
    if start is not None:
        yield start, end


def _occurrences(source: str, snippet: str, lo: int, hi: int) -> Iterator[int]:
    start = source.find(snippet, lo, hi)
    while start != -1:
        yield start
        start = source.find(snippet, start + 1, hi)


def _locate_boundaries(
    source: str,
    selection: BoundarySelection,
    first: TextUnit,
    last: TextUnit,
) -> tuple[int, int]:
    starts = _occurrences(source, selection.start_text, first.start, first.end)
    ends = list(_occurrences(source, selection.end_text, last.start, last.end))
    match = None
    for start in starts:
        # Both snippets must be inside the resulting span. They may overlap.
        earliest_end = max(
            start, start + len(selection.start_text) - len(selection.end_text)
        )
        index = bisect_left(ends, earliest_end)
        if index == len(ends):
            continue
        if match is not None or index + 1 < len(ends):
            raise AmbiguousAnchorError(
                "Multiple valid boundary pairs; extend snippets or narrow the units."
            )
        match = (start, ends[index] + len(selection.end_text))
    if match is None:
        raise AnchorNotFoundError(
            "No ordered exact boundary pair in the specified units."
        )
    return match
