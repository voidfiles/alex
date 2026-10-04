"""A bounded, offline catalog of established terms for book graphs."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import Field

from alex.lib.ontology_enrichment_models import VocabularyTerm
from alex.lib.ontology_models import OntologyResponseModel

NAMESPACES = {
    "dcterms": "http://purl.org/dc/terms/",
    "schema": "https://schema.org/",
    "prov": "http://www.w3.org/ns/prov#",
    "oa": "http://www.w3.org/ns/oa#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "time": "http://www.w3.org/2006/time#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


def absolute_iri(value: str) -> str:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) is None or re.search(
        r'[\s<>"{}|^`\\]', value
    ):
        raise ValueError(f"Not an absolute IRI: {value}")
    return value


def builtin_catalog() -> list[VocabularyTerm]:
    terms: list[VocabularyTerm] = []
    for prefix, names in {
        "schema": {
            "Book": "A book, supported by the document or supplied metadata.",
            "Person": "A particular person; do not use for a class of people.",
            "Organization": "A named organization, not a person or abstract process.",
            "CreativeWork": "An identifiable authored creative work.",
            "Article": "An identifiable article, not an arbitrary passage.",
            "Chapter": "An explicitly identified chapter of a creative work.",
            "Event": "A particular event or occurrence described in the source.",
            "Place": "An identified location with a physical extent.",
            "Product": "An identified product or service, including equipment.",
            "Dataset": "An identified body of structured information.",
            "DefinedTerm": (
                "An individual word, phrase, theory name, or acronym with a "
                "definition; not the class of things it denotes."
            ),
            "DefinedTermSet": "A defined collection of terms, such as a glossary.",
            "Action": (
                "A particular action performed by an agent; not every "
                "abstract mechanism or biological process."
            ),
            "LearningResource": (
                "A creative work explicitly intended for learning; use alongside "
                "its primary type, such as Book."
            ),
            "PodcastSeries": "An identified series of audio or video podcast episodes.",
            "SportsEvent": "A particular sporting event or competition.",
            "EducationEvent": "A particular event with an educational purpose.",
            "SportsOrganization": "An identified organization concerned with sports.",
        },
        "prov": {
            "Entity": "An identifiable thing with provenance.",
            "Activity": "An activity that uses or generates entities.",
            "SoftwareAgent": "Software responsible for an activity.",
        },
        "oa": {
            "Annotation": "An annotation connecting a body to a target.",
            "SpecificResource": "A selected part of a source representation.",
            "TextQuoteSelector": "Normalized exact text identifying a selection.",
            "TextPositionSelector": "A normalized-text range with exclusive end.",
        },
        "skos": {
            "Concept": "A controlled topic or classification, not a formal class.",
            "ConceptScheme": "A scheme containing controlled concepts.",
        },
        "time": {
            "Instant": "A temporal instant, with only source-supported precision.",
            "Interval": "A temporal interval, without invented boundaries.",
        },
    }.items():
        for name, definition in names.items():
            terms.append(
                VocabularyTerm(
                    key=f"{prefix}:{name}",
                    iri=NAMESPACES[prefix] + name,
                    kind="class",
                    definition=definition,
                    operations=["rdf_type", "subclass_of"],
                    roles=["instance", "class"],
                    automatic=prefix == "schema"
                    or (prefix == "skos" and name == "Concept"),
                )
            )
            if prefix == "skos" and name in {"Concept", "ConceptScheme"}:
                terms[-1].operations = ["rdf_type"]
                terms[-1].roles = ["instance"]
    properties = {
        "dcterms": {
            "title": ("The title of a document.", "datatype_property"),
            "creator": (
                "A person or organization responsible for the document.",
                "object_property",
            ),
            "identifier": ("A supplied document identifier.", "datatype_property"),
            "language": ("A supplied language identifier.", "datatype_property"),
            "hasPart": (
                "Document containment; not physical or biological composition.",
                "object_property",
            ),
            "isPartOf": ("A document part's containing document.", "object_property"),
            "subject": ("A document's controlled topic.", "object_property"),
            "created": (
                "Creation of this document, not an event described by it.",
                "datatype_property",
            ),
            "issued": (
                "Document issuance or publication, not copyright.",
                "datatype_property",
            ),
        },
        "schema": {
            "author": ("An author of the creative work.", "object_property"),
            "name": ("The name of the identified entity.", "datatype_property"),
            "description": (
                "A description of the identified entity.",
                "datatype_property",
            ),
            "alternateName": (
                "An alias for the identified entity.",
                "datatype_property",
            ),
        },
        "prov": {
            "used": ("An extraction activity's input entity.", "object_property"),
            "wasGeneratedBy": (
                "The activity producing an extracted entity.",
                "object_property",
            ),
            "wasDerivedFrom": ("An entity's source entity.", "object_property"),
            "wasAssociatedWith": (
                "An activity's responsible agent.",
                "object_property",
            ),
        },
        "oa": {
            "hasBody": ("An annotation's body.", "object_property"),
            "hasTarget": ("An annotation's target.", "object_property"),
            "hasSource": (
                "A selected resource's source representation.",
                "object_property",
            ),
            "hasSelector": ("A selected resource's selector.", "object_property"),
        },
        "skos": {
            "broader": (
                "A broader controlled concept; not OWL subsumption.",
                "object_property",
            ),
            "related": (
                "A related controlled concept, not a causal relationship.",
                "object_property",
            ),
            "inScheme": ("A concept's containing scheme.", "object_property"),
        },
        "time": {
            "hasTime": (
                "Temporal reference of the described entity.",
                "object_property",
            ),
            "hasBeginning": (
                "The beginning instant of an interval.",
                "object_property",
            ),
            "hasEnd": ("The ending instant of an interval.", "object_property"),
        },
    }
    for prefix, values in properties.items():
        for name, (definition, kind) in values.items():
            terms.append(
                VocabularyTerm(
                    key=f"{prefix}:{name}",
                    iri=NAMESPACES[prefix] + name,
                    kind="object_property"
                    if kind == "object_property"
                    else "datatype_property",
                    definition=definition,
                    operations=["reuse_property"],
                    roles=["relation"],
                )
            )
    return terms


class VocabularyCatalog(OntologyResponseModel):
    schema_version: int = 1
    terms: list[VocabularyTerm] = Field(default_factory=list)


def load_catalog(path: Path | None = None) -> list[VocabularyTerm]:
    terms = builtin_catalog()
    if path is not None:
        custom = VocabularyCatalog.model_validate_json(path.read_text())
        if custom.schema_version != 1:
            raise ValueError("Vocabulary catalog requires schema_version 1.")
        terms.extend(custom.terms)
    validate_catalog(terms)
    return terms


def validate_catalog(terms: list[VocabularyTerm]) -> None:
    seen: set[str] = set()
    for term in terms:
        if term.key in seen:
            raise ValueError(f"Duplicate vocabulary key: {term.key}")
        seen.add(term.key)
        absolute_iri(term.iri)
        if term.iri in {
            NAMESPACES["owl"] + "sameAs",
            NAMESPACES["owl"] + "equivalentClass",
            NAMESPACES["owl"] + "equivalentProperty",
        }:
            raise ValueError(
                "Identity/equivalence assertions are outside this catalog profile."
            )
        if not term.operations or not term.roles:
            raise ValueError(
                "Vocabulary terms require operations and compatible roles."
            )
        if term.automatic and term.kind == "concept" and "topic" not in term.roles:
            raise ValueError("An accepted controlled concept requires the topic role.")


def catalog_json(terms: list[VocabularyTerm]) -> str:
    return json.dumps(
        [t.model_dump(mode="json") for t in terms],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def catalog_hash(terms: list[VocabularyTerm]) -> str:
    return hashlib.sha256(catalog_json(terms).encode()).hexdigest()
