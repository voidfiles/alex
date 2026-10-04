"""Ground and merge optional enrichment without another model pass."""

from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from alex.lib.ontology_documents import (
    NormalizedText,
    document_id,
    input_metadata,
    normalize_markdown,
    parse_document_parts,
    text_representation,
)
from alex.lib.ontology_enrichment_models import (
    Alignment,
    AlignmentProposal,
    Assertion,
    BookMetadata,
    ClaimLink,
    DocumentPart,
    EnrichedOntologyResponse,
    EnrichmentProfile,
    EvidenceHint,
    ExtractionActivity,
    MetadataValue,
    OntologyEnrichment,
    Passage,
    Scope,
    TemporalReference,
    TextRepresentation,
    Theme,
    VocabularyTerm,
)
from alex.lib.ontology_models import (
    OntologyConcept,
    OntologyRelationship,
    OntologyRelationType,
    SourceEvidence,
)
from alex.lib.ontology_vocabularies import (
    absolute_iri,
    builtin_catalog,
    catalog_hash,
    validate_catalog,
)

if TYPE_CHECKING:
    from alex.lib.ontology import OntologyMergeResult, OntologyState
    from alex.lib.ontology_export import OntologyArtifact


class EvidenceLocator:
    def __init__(self, passage: str, hints: list[EvidenceHint]) -> None:
        self.passage = passage
        self.hints: dict[str, EvidenceHint] = {}
        for hint in hints:
            previous = self.hints.get(hint.quote)
            if previous is not None and previous != hint:
                raise ValueError("Conflicting locators for the same evidence quote.")
            self.hints[hint.quote] = hint
        self.cache: dict[str, tuple[int, str]] = {}

    def __call__(self, quote: str) -> tuple[int, str]:
        if quote in self.cache:
            return self.cache[quote]
        matches = list(re.finditer(re.escape(quote), self.passage))
        if not matches:
            pattern = r"\s+".join(re.escape(part) for part in quote.split())
            if not pattern:
                raise ValueError("An evidence quote must not be empty.")
            matches = list(re.finditer(pattern, self.passage))
        hint = self.hints.get(quote)
        if hint is not None:
            prefix = hint.prefix.split()
            suffix = hint.suffix.split()
            matches = [
                m
                for m in matches
                if (
                    not prefix
                    or self.passage[: m.start()].split()[-len(prefix) :] == prefix
                )
                and (
                    not suffix
                    or self.passage[m.end() :].split()[: len(suffix)] == suffix
                )
            ]
        if not matches:
            raise ValueError(
                "An evidence quote or its context is absent from the source."
            )
        if len(matches) != 1:
            raise ValueError(
                "Ambiguous repeated evidence quote; supply prefix/suffix context "
                "or a longer unique quote."
            )
        match = matches[0]
        result = (match.start(), match.group())
        self.cache[quote] = result
        return result


@dataclass
class EnrichmentState:
    source_sha256: str
    markdown: str
    catalog: list[VocabularyTerm]
    scope: Scope
    application_iri: str
    metadata: list[MetadataValue]
    documents: list[DocumentPart]
    normalized: NormalizedText
    representation: TextRepresentation
    passages: dict[str, Passage] = field(default_factory=dict)
    activities: list[ExtractionActivity] = field(default_factory=list)
    alignments: dict[tuple[str, str, str], Alignment] = field(default_factory=dict)
    themes: dict[str, Theme] = field(default_factory=dict)
    assertions: dict[str, Assertion] = field(default_factory=dict)
    temporal_references: dict[str, TemporalReference] = field(default_factory=dict)
    claim_links: list[ClaimLink] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        markdown: str,
        source_sha256: str,
        catalog: list[VocabularyTerm],
        scope: Scope,
        metadata: BookMetadata | None,
        application_iri: str,
    ) -> EnrichmentState:
        values, assumptions = input_metadata(markdown, metadata)
        scope = scope.model_copy(
            update={"assumptions": [*scope.assumptions, *assumptions]}
        )
        title = next((v.value for v in values if v.field == "title"), None)
        normalized = normalize_markdown(markdown)
        result = cls(
            source_sha256,
            markdown,
            catalog,
            scope,
            absolute_iri(application_iri),
            values,
            parse_document_parts(markdown, source_sha256, title),
            normalized,
            text_representation(normalized),
        )
        if any(value.origin == "frontmatter" for value in values):
            match = re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", markdown, re.DOTALL)
            if match is not None:
                record = result.evidence(
                    match.group(), EvidenceLocator(markdown, []), 0
                )
                passage_id = result.add_passage(record)
                for value in values:
                    if value.origin == "frontmatter":
                        value.passage_ids.append(passage_id)
        return result

    def evidence(
        self, quote: str, locator: EvidenceLocator, start: int
    ) -> SourceEvidence:
        offset, exact = locator(quote)
        begin = start + offset
        end = begin + len(exact)
        lines = [0, *(m.end() for m in re.finditer("\n", self.markdown))]
        return SourceEvidence(
            exact,
            begin,
            end,
            bisect_right(lines, begin),
            bisect_right(lines, end - 1),
            quote if quote != exact else None,
            "whitespace_normalized" if quote != exact else "exact",
        )

    def add_passage(self, evidence: SourceEvidence) -> str:
        key = document_id(
            "passage",
            self.source_sha256,
            str(evidence.char_start),
            str(evidence.char_end),
        )
        containing = [
            part
            for part in self.documents
            if part.kind != "book"
            and part.char_start <= evidence.char_start
            and part.char_end >= evidence.char_end
        ]
        parent = min(containing, key=lambda part: part.char_end - part.char_start)
        span = self.normalized.span(evidence.char_start, evidence.char_end)
        self.passages[key] = Passage(
            id=key,
            document_id=parent.id,
            evidence=evidence,
            representation_id=self.representation.id,
            text_start=span[0] if span else None,
            text_end=span[1] if span else None,
            text_quote=span[2] if span else None,
        )
        return key

    def merge(
        self,
        response: EnrichedOntologyResponse,
        result: OntologyMergeResult,
        state: OntologyState,
        locator: EvidenceLocator,
        activity: ExtractionActivity,
    ) -> None:
        extra = response.enrichment
        self.activities.append(activity)

        def passages(quotes: list[str]) -> list[str]:
            return list(
                dict.fromkeys(
                    self.add_passage(self.evidence(q, locator, activity.char_start))
                    for q in quotes
                )
            )

        def concept(reference: str) -> str:
            if reference not in result.concept_ids:
                raise ValueError(f"Unknown enrichment concept: {reference}")
            return result.concept_ids[reference]

        def edge(index: int) -> str:
            if index not in result.relationship_ids:
                raise ValueError(f"Unknown enrichment relationship index: {index}")
            return result.relationship_ids[index]

        if extra.book_concept is not None:
            key = concept(extra.book_concept)
            if state.concepts[key].kind != "instance":
                raise ValueError("The source book must be a named instance.")
            root = self.documents[0]
            if root.concept_id is not None and root.concept_id != key:
                raise ValueError("Source passes disagree on the primary book.")
            root.concept_id = key
        items: tuple[
            OntologyConcept | OntologyRelationType | OntologyRelationship, ...
        ] = (
            *state.concepts.values(),
            *state.relation_types.values(),
            *state.relationships.values(),
        )
        for item in items:
            for record in item.evidence:
                self.add_passage(record)
        for metadata_proposal in extra.metadata:
            ids = passages(metadata_proposal.evidence)
            existing = [v for v in self.metadata if v.field == metadata_proposal.field]
            if any(v.origin in {"user", "frontmatter"} for v in existing):
                if not any(v.value == metadata_proposal.value for v in existing):
                    message = (
                        f"Supplied metadata overrides {metadata_proposal.field}: "
                        f"{metadata_proposal.value}."
                    )
                    if message not in self.scope.assumptions:
                        self.scope.assumptions.append(message)
                continue
            if metadata_proposal.field in {"issued", "created"}:
                validate_date(metadata_proposal.value)
            if not any(v.value == metadata_proposal.value for v in existing):
                self.metadata.append(
                    MetadataValue(
                        field=metadata_proposal.field,
                        value=metadata_proposal.value,
                        origin="source",
                        passage_ids=ids,
                    )
                )
        title = next((v.value for v in self.metadata if v.field == "title"), None)
        self.documents[0].title = title
        self.documents[1].title = title
        catalog = {item.key: item for item in self.catalog}
        builtin_keys = {item.key for item in builtin_catalog()}
        proposals = list(extra.alignments)
        for concept_response in response.concepts:
            types = concept_response.type
            if types is None:
                continue
            if len(types) != len(set(types)):
                raise ValueError("Duplicate semantic types on a concept.")
            if concept_response.kind == "class":
                if types not in ([], ["owl:Class"]):
                    raise ValueError(
                        "A formal class uses owl:Class as its type; propose a "
                        "subclass alignment for its domain category."
                    )
                continue
            for key in types:
                if key == "owl:NamedIndividual":
                    continue
                term = catalog.get(key)
                if term is None or not term.automatic:
                    raise ValueError(
                        "Native semantic types require an approved catalog class; "
                        "use an alignment proposal for uncertain mappings."
                    )
                validate_mapping("instance", "rdf_type", term)
                proposals.append(
                    AlignmentProposal(
                        item=concept_response.id,
                        term=key,
                        operation="rdf_type",
                        rationale="Source-grounded type selected on the JSON entity.",
                        evidence=concept_response.evidence,
                    )
                )
        for alignment_proposal in proposals:
            term = catalog.get(alignment_proposal.term)
            if term is None:
                raise ValueError(f"Unknown vocabulary term: {alignment_proposal.term}")
            if alignment_proposal.item in result.concept_ids:
                item_id = concept(alignment_proposal.item)
                role: str = state.concepts[item_id].kind
            elif alignment_proposal.item in result.relation_ids:
                item_id = result.relation_ids[alignment_proposal.item]
                role = "relation"
            else:
                raise ValueError(f"Unknown alignment item: {alignment_proposal.item}")
            validate_mapping(role, alignment_proposal.operation, term)
            automatic = term.automatic and (
                term.key not in builtin_keys
                or alignment_proposal.operation == "rdf_type"
            )
            status: Literal["accepted", "proposed"] = (
                "accepted" if automatic else "proposed"
            )
            authority: Literal["catalog_rule", "curated_catalog"] = (
                "catalog_rule" if term.key in builtin_keys else "curated_catalog"
            )
            alignment = Alignment(
                item_id=item_id,
                term=term.key,
                iri=term.iri,
                operation=alignment_proposal.operation,
                status=status,
                rationale=alignment_proposal.rationale,
                passage_ids=passages(alignment_proposal.evidence),
                authority=authority if status == "accepted" else "model_proposal",
            )
            key_tuple = (item_id, term.iri, alignment_proposal.operation)
            previous = self.alignments.get(key_tuple)
            if previous is not None:
                alignment.passage_ids = list(
                    dict.fromkeys([*previous.passage_ids, *alignment.passage_ids])
                )
            self.alignments[key_tuple] = alignment
        for theme_proposal in extra.themes:
            concept_id = (
                concept(theme_proposal.concept) if theme_proposal.concept else None
            )
            shared_iri = None
            if theme_proposal.shared_term is not None:
                term = catalog.get(theme_proposal.shared_term)
                if term is None or term.kind != "concept" or "topic" not in term.roles:
                    raise ValueError(
                        "A shared theme must reference a catalog controlled concept."
                    )
                if term.automatic:
                    shared_iri = term.iri
            key = document_id(
                "theme", theme_proposal.label.casefold(), theme_proposal.definition
            )
            ids = passages(theme_proposal.evidence)
            previous_theme = self.themes.get(key)
            if previous_theme:
                ids = list(dict.fromkeys([*previous_theme.passage_ids, *ids]))
            self.themes[key] = Theme(
                id=key,
                label=theme_proposal.label,
                definition=theme_proposal.definition,
                concept_id=concept_id,
                shared_iri=shared_iri,
                passage_ids=ids,
            )
        origins = {
            proposal.relationship_index: proposal for proposal in extra.assertions
        }
        if len(origins) != len(extra.assertions):
            raise ValueError("Duplicate assertion origin indices.")
        for index in origins:
            edge(index)
        for index, key in result.relationship_ids.items():
            assertion_proposal = origins.get(index)
            origin = assertion_proposal.origin if assertion_proposal else "explicit"
            if origin != "explicit":
                raise ValueError(
                    "Source-only extraction cannot inject inferred or external claims."
                )
            confidence = assertion_proposal.confidence if assertion_proposal else None
            basis = assertion_proposal.confidence_basis if assertion_proposal else None
            if confidence is not None and basis is None:
                raise ValueError("Extraction confidence requires an estimation basis.")
            previous_assertion = self.assertions.get(key)
            activity_ids = list(
                dict.fromkeys(
                    [
                        *(
                            previous_assertion.activity_ids
                            if previous_assertion
                            else []
                        ),
                        activity.id,
                    ]
                )
            )
            self.assertions[key] = Assertion(
                relationship_id=key,
                origin=origin,
                passage_ids=[
                    self.add_passage(e) for e in state.relationships[key].evidence
                ],
                activity_ids=activity_ids,
                confidence=confidence,
                confidence_basis=basis,
            )
        for temporal_proposal in extra.temporal_references:
            if (temporal_proposal.concept is None) == (
                temporal_proposal.relationship_index is None
            ):
                raise ValueError(
                    "A temporal reference needs exactly one concept or claim."
                )
            item_id = (
                concept(temporal_proposal.concept)
                if temporal_proposal.concept
                else edge(
                    temporal_proposal.relationship_index
                    if temporal_proposal.relationship_index is not None
                    else -1
                )
            )
            validate_temporal(
                temporal_proposal.precision,
                temporal_proposal.start,
                temporal_proposal.end,
            )
            key = document_id(
                "time",
                item_id,
                temporal_proposal.expression,
                temporal_proposal.start or "",
                temporal_proposal.end or "",
            )
            self.temporal_references[key] = TemporalReference(
                id=key,
                item_id=item_id,
                expression=temporal_proposal.expression,
                precision=temporal_proposal.precision,
                start=temporal_proposal.start,
                end=temporal_proposal.end,
                passage_ids=passages(temporal_proposal.evidence),
            )
        for link_proposal in extra.claim_links:
            self.claim_links.append(
                ClaimLink(
                    source_id=edge(link_proposal.source_index),
                    target_id=edge(link_proposal.target_index),
                    relation=link_proposal.relation,
                    passage_ids=passages(link_proposal.evidence),
                )
            )
        state.concepts = {
            item.id: item
            for item in project_native_concepts(
                list(state.concepts.values()), self.artifact()
            )
        }

    def artifact(self) -> OntologyEnrichment:
        return OntologyEnrichment(
            source_sha256=self.source_sha256,
            profile=EnrichmentProfile(
                application_iri=self.application_iri,
                catalog_sha256=catalog_hash(self.catalog),
                catalog=self.catalog,
            ),
            scope=self.scope,
            metadata=self.metadata,
            documents=self.documents,
            representations=[self.representation],
            passages=list(self.passages.values()),
            activities=self.activities,
            alignments=list(self.alignments.values()),
            themes=list(self.themes.values()),
            assertions=list(self.assertions.values()),
            temporal_references=list(self.temporal_references.values()),
            claim_links=self.claim_links,
        )


def project_native_concepts(
    concepts: list[OntologyConcept], extra: OntologyEnrichment
) -> list[OntologyConcept]:
    """Expose approved standard terms and metadata directly on JSON records."""
    types: dict[str, set[str]] = {}
    for alignment in extra.alignments:
        if alignment.status == "accepted" and alignment.operation == "rdf_type":
            types.setdefault(alignment.item_id, set()).add(alignment.term)
    book_id = next(d.concept_id for d in extra.documents if d.kind == "book")
    title = next((v.value for v in extra.metadata if v.field == "title"), None)
    return [
        replace(
            item,
            type=tuple(sorted(types[item.id]))
            if item.id in types
            else ("owl:Class",)
            if item.kind == "class"
            else ("owl:NamedIndividual",),
            name=item.label,
            title=title if item.id == book_id else None,
        )
        for item in concepts
    ]


def validate_native_concepts(artifact: OntologyArtifact) -> None:
    expected = (
        {
            c.id: c
            for c in project_native_concepts(artifact.concepts, artifact.enrichment)
        }
        if artifact.enrichment is not None
        else {}
    )
    for concept in artifact.concepts:
        if concept.name is not None and concept.name != concept.label:
            raise ValueError("The native name must match the source-grounded label.")
        if concept.title is not None and (
            concept.id not in expected or concept.title != expected[concept.id].title
        ):
            raise ValueError("A native title requires matching book metadata.")
        if concept.type is not None:
            valid = (
                expected[concept.id].type
                if concept.id in expected
                else ("owl:Class",)
                if concept.kind == "class"
                else ("owl:NamedIndividual",)
            )
            if len(concept.type) != len(set(concept.type)) or set(concept.type) != set(
                valid or ()
            ):
                raise ValueError(
                    "Native types must match approved source-grounded alignments."
                )


def prepare_enriched_response(response: EnrichedOntologyResponse) -> None:
    """Explicit sense discriminators avoid normalized-label homonym merging."""
    senses = response.enrichment.senses
    known = {item.id for item in response.concepts} | {
        item.id for item in response.relation_types
    }
    if set(senses) - known:
        raise ValueError("Sense discriminator references an unknown response item.")
    for concept in response.concepts:
        if concept.id in senses:
            concept.label = f"{concept.label} ({senses[concept.id]})"
    for relation in response.relation_types:
        if relation.id in senses:
            suffix = re.sub(r"[^a-z0-9]+", "_", senses[relation.id].casefold()).strip(
                "_"
            )
            if not suffix:
                raise ValueError("Relation sense must include letters or digits.")
            relation.label = f"{relation.label}_{suffix}"
    from alex.lib.ontology import normalize_term

    labels: set[tuple[str, str]] = set()
    for concept in response.concepts:
        identity = (concept.kind, normalize_term(concept.label))
        if identity in labels:
            raise ValueError(
                "Repeated entity labels need one reused ID or explicit senses."
            )
        labels.add(identity)
    relation_labels = [r.label for r in response.relation_types]
    if len(set(relation_labels)) != len(relation_labels):
        raise ValueError("Different predicates require disambiguated labels or senses.")


def validate_mapping(role: str, operation: str, term: VocabularyTerm) -> None:
    if role not in term.roles or operation not in term.operations:
        raise ValueError(f"Incompatible mapping to {term.key}.")
    if operation == "rdf_type" and (role != "instance" or term.kind != "class"):
        raise ValueError("rdf_type requires an instance and a catalog class.")
    if operation == "subclass_of" and (role != "class" or term.kind != "class"):
        raise ValueError("subclass_of requires two formal classes.")
    if operation == "reuse_property" and (
        role != "relation" or term.kind != "object_property"
    ):
        raise ValueError("Core relations can only reuse object-valued properties.")
    if operation.endswith("match") and (role != "instance" or term.kind != "concept"):
        raise ValueError("SKOS matches require controlled concept individuals.")


def validate_date(value: str) -> str:
    if re.fullmatch(r"\d{4}", value):
        if not 1 <= int(value) <= 9999:
            raise ValueError("Invalid year.")
        return "gYear"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        datetime.strptime(value, "%Y-%m-%d")
        return "date"
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None or "T" not in value:
        raise ValueError(
            "Date-times require a time and timezone; do not invent precision."
        )
    return "dateTime"


def validate_temporal(precision: str, start: str | None, end: str | None) -> None:
    if precision == "unknown":
        if start is not None or end is not None:
            raise ValueError(
                "Unknown temporal precision cannot have normalized bounds."
            )
        return
    if start is None:
        raise ValueError("A normalized temporal reference requires its start value.")
    datatype = validate_date(start)
    expected = {"year": "gYear", "date": "date", "datetime": "dateTime"}
    if precision in expected and (datatype != expected[precision] or end is not None):
        raise ValueError("Temporal values disagree with their declared precision.")
    if end is not None:
        if validate_date(end) != datatype:
            raise ValueError("Temporal interval bounds disagree in precision.")
        reversed_bounds = (
            datetime.fromisoformat(end) < datetime.fromisoformat(start)
            if datatype == "dateTime"
            else end < start
        )
        if reversed_bounds:
            raise ValueError("Temporal interval bounds are reversed.")


def validate_enrichment(artifact: OntologyArtifact) -> None:
    extra = artifact.enrichment
    if extra is None:
        return
    if extra.source_sha256 != artifact.source.sha256:
        raise ValueError("Enrichment source hash does not match the core source.")
    absolute_iri(extra.profile.application_iri)
    validate_catalog(extra.profile.catalog)
    if catalog_hash(extra.profile.catalog) != extra.profile.catalog_sha256:
        raise ValueError("Vocabulary catalog hash mismatch.")
    concepts = {item.id: item for item in artifact.concepts}
    relations = {item.id: item for item in artifact.relation_types}
    edges = {item.id: item for item in artifact.relationships}

    def unique_ids(
        items: list[DocumentPart]
        | list[Passage]
        | list[ExtractionActivity]
        | list[TextRepresentation]
        | list[Theme],
    ) -> set[str]:
        ids = {item.id for item in items}
        if len(ids) != len(items):
            raise ValueError("Duplicate enrichment IDs.")
        return ids

    docs = unique_ids(extra.documents)
    passage_ids = unique_ids(extra.passages)
    activities = unique_ids(extra.activities)
    representations = unique_ids(extra.representations)
    unique_ids(extra.themes)
    if sum(d.kind == "book" for d in extra.documents) != 1:
        raise ValueError("Enrichment requires exactly one primary book.")
    if sum(d.kind == "source" for d in extra.documents) != 1:
        raise ValueError("Enrichment requires exactly one source representation.")
    document_records = {part.id: part for part in extra.documents}
    for part in extra.documents:
        if part.parent is not None and part.parent not in docs:
            raise ValueError("Unknown parent document.")
        if not 0 <= part.char_start <= part.char_end <= artifact.source.characters:
            raise ValueError("Invalid document part coordinates.")
        if part.line_end < part.line_start:
            raise ValueError("Invalid document part line range.")
        ancestors: set[str] = {part.id}
        parent_id = part.parent
        while parent_id is not None:
            if parent_id not in document_records:
                raise ValueError("Unknown ancestor document.")
            if parent_id in ancestors:
                raise ValueError("Document containment contains a cycle.")
            ancestors.add(parent_id)
            parent = document_records[parent_id]
            if (
                not parent.char_start
                <= part.char_start
                <= part.char_end
                <= parent.char_end
            ):
                raise ValueError("Document part is outside its containing document.")
            parent_id = parent.parent
        if part.concept_id is not None and (
            part.concept_id not in concepts
            or concepts[part.concept_id].kind != "instance"
        ):
            raise ValueError("A document concept must be an existing instance.")
    texts = {r.id: r.text for r in extra.representations}
    for representation in extra.representations:
        if (
            hashlib.sha256(representation.text.encode()).hexdigest()
            != representation.sha256
        ):
            raise ValueError("Normalized representation hash mismatch.")
    for passage in extra.passages:
        e = passage.evidence
        if (
            passage.document_id not in docs
            or passage.representation_id not in representations
        ):
            raise ValueError("Unknown passage document or text representation.")
        if not 0 <= e.char_start < e.char_end <= artifact.source.characters or (
            e.char_end - e.char_start != len(e.quote)
            or e.line_start < 1
            or e.line_end < e.line_start
        ):
            raise ValueError("Invalid enrichment evidence coordinates.")
        containing = document_records[passage.document_id]
        if (
            not containing.char_start
            <= e.char_start
            < e.char_end
            <= containing.char_end
        ):
            raise ValueError("A passage is outside its containing document.")
        if e.match_mode == "whitespace_normalized" and (
            e.model_quote is None or e.model_quote.split() != e.quote.split()
        ):
            raise ValueError(
                "Enriched evidence alignment changes words or punctuation."
            )
        selectors = (passage.text_start, passage.text_end, passage.text_quote)
        if any(v is not None for v in selectors):
            if (
                passage.text_start is None
                or passage.text_end is None
                or passage.text_quote is None
            ):
                raise ValueError("Incomplete normalized text selector.")
            text = texts[passage.representation_id]
            if not 0 <= passage.text_start < passage.text_end <= len(text) or (
                text[passage.text_start : passage.text_end] != passage.text_quote
            ):
                raise ValueError(
                    "Normalized selector does not match its text representation."
                )

    def references(ids: list[str]) -> None:
        if not set(ids) <= passage_ids:
            raise ValueError("Unknown source passage reference.")

    for activity in extra.activities:
        start = datetime.fromisoformat(activity.started_at)
        end = datetime.fromisoformat(activity.ended_at)
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError("Invalid extraction activity timestamps.")
        if (
            not 0
            <= activity.char_start
            < activity.char_end
            <= artifact.source.characters
        ):
            raise ValueError("Invalid extraction activity source span.")
    catalog = {term.key: term for term in extra.profile.catalog}
    builtins = {term.key for term in builtin_catalog()}
    for alignment in extra.alignments:
        term = catalog.get(alignment.term)
        if term is None or term.iri != alignment.iri:
            raise ValueError("Unknown or altered catalog alignment.")
        role = (
            concepts[alignment.item_id].kind
            if alignment.item_id in concepts
            else "relation"
        )
        if alignment.item_id not in concepts and alignment.item_id not in relations:
            raise ValueError("Unknown aligned item.")
        validate_mapping(role, alignment.operation, term)
        if alignment.status == "accepted" and not term.automatic:
            raise ValueError("An accepted mapping requires a curated catalog rule.")
        if (
            alignment.status == "accepted"
            and term.key in builtins
            and alignment.operation != "rdf_type"
        ):
            raise ValueError("Nontrivial built-in mappings must remain proposals.")
        references(alignment.passage_ids)
    named_types: dict[str, set[str]] = {}
    for alignment in extra.alignments:
        if alignment.status == "accepted" and alignment.operation == "rdf_type":
            named_types.setdefault(alignment.item_id, set()).add(alignment.term)
    for types in named_types.values():
        if "schema:Person" in types and types.intersection(
            {"schema:Organization", "schema:SportsOrganization"}
        ):
            raise ValueError(
                "A person/organization homonym requires separate local identities."
            )
    topic_ids = {
        theme.concept_id for theme in extra.themes if theme.concept_id is not None
    }
    topic_ids.update(
        a.item_id
        for a in extra.alignments
        if a.status == "accepted"
        and a.operation == "rdf_type"
        and a.term == "skos:Concept"
    )
    for alignment in extra.alignments:
        if alignment.operation.endswith("match") and alignment.item_id not in topic_ids:
            raise ValueError("SKOS matching requires a declared controlled topic.")
    activities_by_id = {a.id: a for a in extra.activities}
    passages_by_id = {p.id: p for p in extra.passages}
    seen_edges: set[str] = set()
    for assertion in extra.assertions:
        if (
            assertion.relationship_id not in edges
            or assertion.relationship_id in seen_edges
        ):
            raise ValueError("Unknown or duplicate enriched assertion.")
        seen_edges.add(assertion.relationship_id)
        references(assertion.passage_ids)
        if not set(assertion.activity_ids) <= activities:
            raise ValueError("Unknown assertion extraction activity.")
        grounded = {
            (
                passages_by_id[p].evidence.char_start,
                passages_by_id[p].evidence.char_end,
                passages_by_id[p].evidence.quote,
            )
            for p in assertion.passage_ids
        }
        required = {
            (e.char_start, e.char_end, e.quote)
            for e in edges[assertion.relationship_id].evidence
        }
        if not required <= grounded:
            raise ValueError(
                "Assertion provenance omits or alters core source evidence."
            )
        for passage_id in assertion.passage_ids:
            evidence = passages_by_id[passage_id].evidence
            if not any(
                activities_by_id[a].char_start <= evidence.char_start
                and activities_by_id[a].char_end >= evidence.char_end
                for a in assertion.activity_ids
            ):
                raise ValueError(
                    "Assertion evidence is outside its extraction activities."
                )
        if assertion.confidence is not None and not assertion.confidence_basis:
            raise ValueError("Confidence requires its extraction-estimation basis.")
    if seen_edges != set(edges):
        raise ValueError(
            "Every core relationship requires enriched assertion provenance."
        )
    for theme in extra.themes:
        references(theme.passage_ids)
        if theme.concept_id is not None and theme.concept_id not in concepts:
            raise ValueError("Unknown theme concept.")
        if theme.shared_iri is not None and not any(
            t.iri == theme.shared_iri and t.kind == "concept" and t.automatic
            for t in catalog.values()
        ):
            raise ValueError("Shared themes require an accepted catalog concept.")
    for value in extra.metadata:
        references(value.passage_ids)
        if value.origin in {"source", "frontmatter"} and not value.passage_ids:
            raise ValueError("Extracted metadata requires source evidence.")
        if value.field in {"created", "issued"}:
            validate_date(value.value)
    for reference in extra.temporal_references:
        if reference.item_id not in concepts and reference.item_id not in edges:
            raise ValueError("Unknown temporally described item.")
        references(reference.passage_ids)
        validate_temporal(reference.precision, reference.start, reference.end)
    for link in extra.claim_links:
        if link.source_id not in edges or link.target_id not in edges:
            raise ValueError("Unknown argumentative claim reference.")
        references(link.passage_ids)
    if extra.interpretations:
        raise ValueError(
            "Interpretation generation is not enabled in the source-only profile."
        )


def enrichment_prompt_context(
    catalog: list[VocabularyTerm], metadata: BookMetadata | None, scope: Scope
) -> str:
    return json.dumps(
        {
            "catalog": [t.model_dump(mode="json") for t in catalog],
            "metadata": metadata.model_dump(mode="json") if metadata else {},
            "scope": scope.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
