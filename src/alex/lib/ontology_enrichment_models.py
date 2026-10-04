"""Optional, independently versioned standard-vocabulary extraction records."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from alex.lib.ontology_models import (
    OntologyResponse,
    OntologyResponseModel,
    SourceEvidence,
    Text,
)

type MappingOperation = Literal[
    "rdf_type",
    "subclass_of",
    "reuse_property",
    "close_match",
    "exact_match",
    "broad_match",
    "related_match",
]
type AssertionOrigin = Literal[
    "explicit", "interpretive", "speculative", "external", "unknown"
]
type MetadataField = Literal[
    "title", "creator", "identifier", "language", "issued", "created"
]
type Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class VocabularyTerm(OntologyResponseModel):
    key: Text
    iri: Text
    kind: Literal["class", "object_property", "datatype_property", "concept"]
    definition: Text
    operations: list[MappingOperation]
    roles: list[Literal["class", "instance", "relation", "topic"]]
    automatic: bool = False


class EvidenceHint(OntologyResponseModel):
    quote: Text
    prefix: str = ""
    suffix: str = ""


class MetadataProposal(OntologyResponseModel):
    field: MetadataField
    value: Text
    evidence: list[Text] = Field(min_length=1)


class AlignmentProposal(OntologyResponseModel):
    item: Text
    term: Text
    operation: MappingOperation
    rationale: Text
    evidence: list[Text] = Field(min_length=1)


class ThemeProposal(OntologyResponseModel):
    label: Text
    definition: Text
    evidence: list[Text] = Field(min_length=1)
    concept: Text | None = None
    shared_term: Text | None = None


class AssertionProposal(OntologyResponseModel):
    relationship_index: Annotated[int, Field(ge=0)]
    origin: AssertionOrigin = "explicit"
    confidence: Confidence | None = None
    confidence_basis: Text | None = None


class TemporalProposal(OntologyResponseModel):
    concept: Text | None = None
    relationship_index: Annotated[int, Field(ge=0)] | None = None
    expression: Text
    precision: Literal["year", "date", "datetime", "interval", "unknown"]
    start: Text | None = None
    end: Text | None = None
    evidence: list[Text] = Field(min_length=1)


class ClaimLinkProposal(OntologyResponseModel):
    source_index: Annotated[int, Field(ge=0)]
    target_index: Annotated[int, Field(ge=0)]
    relation: Literal["supports", "contradicts"]
    evidence: list[Text] = Field(min_length=1)


class ExtractionEnrichment(OntologyResponseModel):
    book_concept: Text | None = None
    metadata: list[MetadataProposal] = Field(default_factory=list)
    alignments: list[AlignmentProposal] = Field(default_factory=list)
    themes: list[ThemeProposal] = Field(default_factory=list)
    assertions: list[AssertionProposal] = Field(default_factory=list)
    temporal_references: list[TemporalProposal] = Field(default_factory=list)
    claim_links: list[ClaimLinkProposal] = Field(default_factory=list)
    evidence_hints: list[EvidenceHint] = Field(default_factory=list)
    senses: dict[str, Text] = Field(default_factory=dict)


class EnrichedOntologyResponse(OntologyResponse):
    enrichment: ExtractionEnrichment


class Scope(OntologyResponseModel):
    purpose: Text = "Source-grounded scholarly book knowledge graph."
    boundaries: list[Text] = Field(
        default_factory=lambda: [
            "Supplied source text and explicitly supplied metadata only."
        ]
    )
    competency_questions: list[Text] = Field(
        default_factory=lambda: [
            "Which passages support each claim?",
            "Which people, organizations, and themes are discussed?",
            "Which activity and model extracted each assertion?",
            "Which accepted shared concepts occur across books?",
        ]
    )
    assumptions: list[Text] = Field(default_factory=list)


class BookMetadata(OntologyResponseModel):
    title: Text | None = None
    creator: list[Text] = Field(default_factory=list)
    identifier: list[Text] = Field(default_factory=list)
    language: Text | None = None
    issued: Text | None = None
    created: Text | None = None


class MetadataValue(OntologyResponseModel):
    field: MetadataField
    value: Text
    origin: Literal["user", "frontmatter", "source"]
    passage_ids: list[Text] = Field(default_factory=list)


class DocumentPart(OntologyResponseModel):
    id: Text
    kind: Literal["book", "source", "chapter", "section", "appendix", "figure", "table"]
    title: Text | None = None
    parent: Text | None = None
    concept_id: Text | None = None
    char_start: Annotated[int, Field(ge=0)]
    char_end: Annotated[int, Field(ge=0)]
    line_start: Annotated[int, Field(ge=1)]
    line_end: Annotated[int, Field(ge=1)]


class TextRepresentation(OntologyResponseModel):
    id: Text
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    normalization: Literal["alex-markdown-text-v001"]
    text: str


class Passage(OntologyResponseModel):
    id: Text
    document_id: Text
    evidence: SourceEvidence
    representation_id: Text
    text_start: Annotated[int, Field(ge=0)] | None = None
    text_end: Annotated[int, Field(ge=0)] | None = None
    text_quote: Text | None = None


class ExtractionActivity(OntologyResponseModel):
    id: Text
    pass_number: Annotated[int, Field(ge=1)]
    model: Text
    prompt_name: Text
    prompt_version: Text
    prompt_sha256: Text
    started_at: Text
    ended_at: Text
    char_start: Annotated[int, Field(ge=0)]
    char_end: Annotated[int, Field(ge=0)]


class Alignment(OntologyResponseModel):
    item_id: Text
    term: Text
    iri: Text
    operation: MappingOperation
    status: Literal["accepted", "proposed", "rejected"]
    rationale: Text
    passage_ids: list[Text] = Field(min_length=1)
    authority: Literal["catalog_rule", "model_proposal", "curated_catalog"]


class Theme(OntologyResponseModel):
    id: Text
    label: Text
    definition: Text
    concept_id: Text | None = None
    shared_iri: Text | None = None
    passage_ids: list[Text] = Field(min_length=1)


class Assertion(OntologyResponseModel):
    relationship_id: Text
    origin: AssertionOrigin
    passage_ids: list[Text] = Field(min_length=1)
    activity_ids: list[Text] = Field(min_length=1)
    confidence: Confidence | None = None
    confidence_basis: Text | None = None


class TemporalReference(OntologyResponseModel):
    id: Text
    item_id: Text
    expression: Text
    precision: Literal["year", "date", "datetime", "interval", "unknown"]
    start: Text | None
    end: Text | None
    passage_ids: list[Text] = Field(min_length=1)


class ClaimLink(OntologyResponseModel):
    source_id: Text
    target_id: Text
    relation: Literal["supports", "contradicts"]
    passage_ids: list[Text] = Field(min_length=1)


class EnrichmentProfile(OntologyResponseModel):
    application_iri: Text = "urn:alex:ontology:book:"
    application_version: Literal["v001"] = "v001"
    catalog_version: Literal[1] = 1
    catalog_sha256: Text
    catalog: list[VocabularyTerm]


class OntologyEnrichment(OntologyResponseModel):
    schema_version: Literal[1] = 1
    source_sha256: Text
    profile: EnrichmentProfile
    scope: Scope
    metadata: list[MetadataValue]
    documents: list[DocumentPart]
    representations: list[TextRepresentation]
    passages: list[Passage]
    activities: list[ExtractionActivity]
    alignments: list[Alignment]
    themes: list[Theme]
    assertions: list[Assertion]
    temporal_references: list[TemporalReference]
    claim_links: list[ClaimLink]
    interpretations: list[Text] = Field(default_factory=list)
