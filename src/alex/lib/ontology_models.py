"""The versioned JSON ontology contract and source evidence records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
ConceptKind = Literal["class", "instance"]
SubjectQuantifier = Literal["all", "some", "individual", "unspecified"]
ObjectQuantifier = Literal["some", "only", "value", "unspecified"]
StatementStrength = Literal["categorical", "typical", "possible", "conditional"]


@dataclass(frozen=True)
class OntologyLogic:
    subject_quantifier: SubjectQuantifier
    object_quantifier: ObjectQuantifier
    polarity: Literal["positive", "negative"]
    strength: StatementStrength
    condition: Text | None
    rationale: Text


class OntologyResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConceptResponse(OntologyResponseModel):
    id: Text
    label: Text
    kind: ConceptKind
    definition: Text
    aliases: list[Text]
    evidence: list[Text] = Field(min_length=1)
    type: list[Text] | None = None


class RelationTypeResponse(OntologyResponseModel):
    id: Text
    label: Text
    definition: Text
    domain: list[Text]
    range: list[Text]
    evidence: list[Text] = Field(min_length=1)


class RelationshipResponse(OntologyResponseModel):
    source: Text
    relation: Text
    target: Text
    description: Text
    logic: OntologyLogic
    evidence: list[Text] = Field(min_length=1)


class OntologyResponse(OntologyResponseModel):
    concepts: list[ConceptResponse]
    relation_types: list[RelationTypeResponse]
    relationships: list[RelationshipResponse]


@dataclass(frozen=True)
class SourceEvidence:
    quote: str
    char_start: int
    char_end: int
    line_start: int
    line_end: int
    model_quote: str | None = None
    match_mode: Literal["exact", "whitespace_normalized"] = "exact"


@dataclass(frozen=True)
class OntologyConcept:
    id: str
    label: str
    kind: ConceptKind
    definition: str
    aliases: tuple[str, ...]
    evidence: tuple[SourceEvidence, ...]
    type: tuple[Text, ...] | None = None
    name: Text | None = None
    title: Text | None = None


@dataclass(frozen=True)
class OntologyRelationType:
    id: str
    label: str
    definition: str
    domain: tuple[str, ...]
    range: tuple[str, ...]
    evidence: tuple[SourceEvidence, ...]


@dataclass(frozen=True)
class OntologyRelationship:
    id: str
    source: str
    relation: str
    target: str
    description: str
    evidence: tuple[SourceEvidence, ...]
    logic: OntologyLogic


@dataclass(frozen=True)
class OntologyPass:
    number: int
    char_start: int
    char_end: int
    line_start: int
    line_end: int
    prompt_tokens: int


@dataclass(frozen=True)
class OntologyBudget:
    context_window: int
    max_output_tokens: int
    safety_margin: int
    input_budget: int


@dataclass(frozen=True)
class OntologyOutput:
    output_path: Path | None
    model: str
    budget: OntologyBudget
    passes: tuple[OntologyPass, ...]
    concept_count: int
    relation_type_count: int
    relationship_count: int
