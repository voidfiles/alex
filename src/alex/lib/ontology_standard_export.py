"""Standard book/provenance graph projection, kept separate from legacy OWL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from alex.lib.ontology_enrichment import validate_date
from alex.lib.ontology_vocabularies import NAMESPACES

if TYPE_CHECKING:
    from rdflib import Graph, URIRef

    from alex.lib.ontology_export import OntologyArtifact


def application_namespace(value: str) -> str:
    return value if value.endswith(("#", "/", ":")) else value + "#"


METADATA_DEFINITIONS = {
    "sourceSha256": ("SHA-256 of the identified source representation.", "string"),
    "sourcePath": ("The local source path recorded by extraction.", "string"),
    "charStart": ("Zero-based raw Markdown character start, inclusive.", "integer"),
    "charEnd": ("Zero-based raw Markdown character end, exclusive.", "integer"),
    "lineStart": ("One-based raw-source starting line, inclusive.", "integer"),
    "lineEnd": ("One-based raw-source ending line, inclusive.", "integer"),
    "quote": ("The exact, contiguous raw-source quotation.", "string"),
    "evidenceMatchMode": (
        "Whether exact matching or whitespace-only alignment located evidence.",
        "string",
    ),
    "modelQuote": (
        "Original model quotation before whitespace-only alignment.",
        "string",
    ),
    "selectorUnavailable": (
        "A normalized selector could not be produced reliably.",
        "boolean",
    ),
    "normalization": (
        "The versioned source-to-plain-text normalization algorithm.",
        "string",
    ),
    "promptName": ("The prompt family used by this extraction activity.", "string"),
    "promptVersion": ("The immutable prompt version used by extraction.", "string"),
    "promptSha256": ("SHA-256 of the immutable prompt template.", "string"),
    "confidenceBasis": (
        "Basis for estimating extraction fidelity, not objective truth.",
        "string",
    ),
    "jsonId": ("The corresponding local identifier in the JSON artifact.", "string"),
    "logic": (
        "JSON encoding of source-supported quantifiers, polarity, strength, "
        "condition, and rationale.",
        "string",
    ),
    "candidateDomain": (
        "A possible source class, not an asserted global domain constraint.",
        "Resource",
    ),
    "candidateRange": (
        "A possible target class, not an asserted global range constraint.",
        "Resource",
    ),
    "mappingStatus": (
        "Whether an alignment is proposed, accepted, or rejected.",
        "string",
    ),
    "mappingOperation": (
        "The semantic operation proposed by a vocabulary alignment.",
        "string",
    ),
    "mappingAuthority": (
        "The catalog rule, curated catalog, or model proposal behind an alignment.",
        "string",
    ),
    "temporalPrecision": (
        "The precision actually supported by a temporal expression.",
        "string",
    ),
}


def application_graph(application_iri: str, instances: Graph | None = None) -> Graph:
    from rdflib import Graph, Literal, Namespace
    from rdflib.namespace import OWL, RDF, RDFS, XSD

    from alex.lib.ontology_export import META_IRI

    data = (files("alex") / "ontologies" / "book" / "v001.ttl").read_text()
    result = Graph().parse(
        data=data.replace(
            "urn:alex:ontology:book:", application_namespace(application_iri)
        ),
        format="turtle",
    )
    if instances is not None:
        meta = Namespace(META_IRI)
        app = Namespace(application_namespace(application_iri))
        used = set(instances.predicates())
        for name, (definition, range_name) in METADATA_DEFINITIONS.items():
            term = meta[name]
            if term not in used:
                continue
            result.add((term, RDF.type, OWL.AnnotationProperty))
            result.add((term, RDFS.label, Literal(name)))
            result.add((term, RDFS.comment, Literal(definition)))
            result.add((term, RDFS.domain, RDFS.Resource))
            result.add(
                (
                    term,
                    RDFS.range,
                    RDFS.Resource if range_name == "Resource" else XSD[range_name],
                )
            )
            result.add((term, app.termPurpose, Literal("annotation and provenance")))
    return result


def standard_graph(artifact: OntologyArtifact, base_iri: str) -> tuple[Graph, int]:
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

    from alex.lib.ontology_export import META_IRI, formalize_relationship

    extra = artifact.enrichment
    if extra is None:
        raise ValueError("The standard profile requires an enriched ontology artifact.")
    graph = Graph()
    app = Namespace(application_namespace(extra.profile.application_iri))
    meta = Namespace(META_IRI)
    schema = Namespace(NAMESPACES["schema"])
    prov = Namespace(NAMESPACES["prov"])
    oa = Namespace(NAMESPACES["oa"])
    time = Namespace(NAMESPACES["time"])
    for prefix, iri in NAMESPACES.items():
        graph.bind(prefix, Namespace(iri))
    graph.bind("book", app)
    graph.bind("alex", meta)
    graph.bind("ex", Namespace(base_iri + "#"))

    def node(category: str, key: str) -> URIRef:
        return URIRef(base_iri + "#" + category + "/" + quote(key, safe=""))

    concepts = {c.id: node("concept", c.id) for c in artifact.concepts}
    docs = {d.id: node("document", d.id) for d in extra.documents}
    root = next(d for d in extra.documents if d.kind == "book")
    if root.concept_id is not None:
        docs[root.id] = concepts[root.concept_id]
    book_node = docs[root.id]
    source_node = docs[next(d.id for d in extra.documents if d.kind == "source")]
    passages = {p.id: node("passage", p.id) for p in extra.passages}
    activities = {a.id: node("activity", a.id) for a in extra.activities}
    representations = {
        r.id: node("representation", r.id) for r in extra.representations
    }
    statements = {e.id: node("book-claim", e.id) for e in artifact.relationships}
    relation_iris = {r.id: node("relation", r.id) for r in artifact.relation_types}
    catalog = {t.key: t for t in extra.profile.catalog}
    for alignment in extra.alignments:
        if alignment.status == "accepted" and alignment.operation == "reuse_property":
            relation_iris[alignment.item_id] = URIRef(alignment.iri)
    graph.add((URIRef(base_iri), RDF.type, OWL.Ontology))
    graph.add(
        (
            URIRef(base_iri),
            DCTERMS.created,
            Literal(artifact.created_at, datatype=XSD.dateTime),
        )
    )
    graph.add((URIRef(base_iri), prov.wasDerivedFrom, source_node))
    graph.add((source_node, meta.sourceSha256, Literal(artifact.source.sha256)))
    graph.add((source_node, meta.sourcePath, Literal(artifact.source.path)))
    graph.add((source_node, DCTERMS.format, Literal("text/markdown")))

    for part in extra.documents:
        resource = docs[part.id]
        graph.add((resource, RDF.type, prov.Entity))
        graph.add(
            (
                resource,
                RDF.type,
                schema.Book
                if part.kind == "book"
                else schema.Chapter
                if part.kind == "chapter"
                else schema.CreativeWork,
            )
        )
        if part.title is not None:
            graph.add((resource, DCTERMS.title, Literal(part.title)))
        if part.parent is not None:
            graph.add((resource, DCTERMS.isPartOf, docs[part.parent]))
            graph.add((docs[part.parent], DCTERMS.hasPart, resource))
        for predicate, value in (
            (meta.charStart, part.char_start),
            (meta.charEnd, part.char_end),
            (meta.lineStart, part.line_start),
            (meta.lineEnd, part.line_end),
        ):
            graph.add((resource, predicate, Literal(value)))
    accepted_entity_types = {
        a.item_id
        for a in extra.alignments
        if a.status == "accepted"
        and a.operation == "rdf_type"
        and a.term in {"schema:Person", "schema:Organization"}
    }
    for metadata_value in extra.metadata:
        predicate = DCTERMS[metadata_value.field]
        if metadata_value.field == "creator":
            candidates = [
                c.id
                for c in artifact.concepts
                if c.id in accepted_entity_types
                and metadata_value.value in (c.label, *c.aliases)
            ]
            creator = (
                concepts[candidates[0]]
                if len(candidates) == 1
                else node(
                    "creator",
                    hashlib.sha256(metadata_value.value.encode()).hexdigest()[:16],
                )
            )
            graph.add((creator, RDF.type, prov.Agent))
            graph.add((creator, RDFS.label, Literal(metadata_value.value)))
            graph.add((book_node, predicate, creator))
            graph.add((book_node, schema.author, creator))
        else:
            literal = (
                Literal(
                    metadata_value.value,
                    datatype=XSD[validate_date(metadata_value.value)],
                )
                if (metadata_value.field in {"created", "issued"})
                else Literal(metadata_value.value)
            )
            graph.add((book_node, predicate, literal))
        for passage_id in metadata_value.passage_ids:
            graph.add((book_node, prov.wasDerivedFrom, passages[passage_id]))
    for representation in extra.representations:
        resource = representations[representation.id]
        graph.add((resource, RDF.type, prov.Entity))
        graph.add((resource, prov.wasDerivedFrom, source_node))
        graph.add((resource, DCTERMS.format, Literal("text/plain")))
        graph.add((resource, prov.value, Literal(representation.text)))
        graph.add((resource, meta.normalization, Literal(representation.normalization)))
        graph.add((resource, meta.sourceSha256, Literal(representation.sha256)))
    for passage in extra.passages:
        resource = passages[passage.id]
        graph.add((resource, RDF.type, prov.Entity))
        graph.add((resource, RDF.type, oa.SpecificResource))
        graph.add((resource, DCTERMS.isPartOf, docs[passage.document_id]))
        graph.add((resource, prov.wasDerivedFrom, source_node))
        graph.add((resource, meta.quote, Literal(passage.evidence.quote)))
        for name in ("char_start", "char_end", "line_start", "line_end"):
            predicate = {
                "char_start": meta.charStart,
                "char_end": meta.charEnd,
                "line_start": meta.lineStart,
                "line_end": meta.lineEnd,
            }[name]
            graph.add((resource, predicate, Literal(getattr(passage.evidence, name))))
        graph.add(
            (resource, meta.evidenceMatchMode, Literal(passage.evidence.match_mode))
        )
        if passage.evidence.model_quote is not None:
            graph.add(
                (resource, meta.modelQuote, Literal(passage.evidence.model_quote))
            )
        if passage.text_quote is not None:
            graph.add(
                (resource, oa.hasSource, representations[passage.representation_id])
            )
            quote_selector = node("quote-selector", passage.id)
            position_selector = node("position-selector", passage.id)
            graph.add((resource, oa.hasSelector, quote_selector))
            graph.add((resource, oa.hasSelector, position_selector))
            graph.add((quote_selector, RDF.type, oa.TextQuoteSelector))
            graph.add((quote_selector, oa.exact, Literal(passage.text_quote)))
            graph.add((position_selector, RDF.type, oa.TextPositionSelector))
            graph.add((position_selector, oa.start, Literal(passage.text_start)))
            graph.add((position_selector, oa.end, Literal(passage.text_end)))
        else:
            graph.add((resource, oa.hasSource, source_node))
            graph.add((resource, meta.selectorUnavailable, Literal(True)))
    for activity in extra.activities:
        resource = activities[activity.id]
        agent = URIRef(
            "urn:alex:ontology:agent:"
            + hashlib.sha256(activity.model.encode()).hexdigest()
        )
        graph.add((agent, RDF.type, prov.SoftwareAgent))
        graph.add((agent, RDFS.label, Literal(activity.model)))
        graph.add((resource, RDF.type, prov.Activity))
        graph.add((resource, prov.used, source_node))
        graph.add((resource, prov.wasAssociatedWith, agent))
        graph.add(
            (
                resource,
                prov.startedAtTime,
                Literal(activity.started_at, datatype=XSD.dateTime),
            )
        )
        graph.add(
            (
                resource,
                prov.endedAtTime,
                Literal(activity.ended_at, datatype=XSD.dateTime),
            )
        )
        graph.add((resource, meta.promptName, Literal(activity.prompt_name)))
        graph.add((resource, meta.promptVersion, Literal(activity.prompt_version)))
        graph.add((resource, meta.promptSha256, Literal(activity.prompt_sha256)))
        processor = URIRef("urn:alex:software:alex")
        graph.add((processor, RDF.type, prov.SoftwareAgent))
        graph.add((processor, RDFS.label, Literal("alex ontology extractor")))
        graph.add((resource, prov.wasAssociatedWith, processor))

    passage_coords = {
        (p.evidence.char_start, p.evidence.char_end): p.id for p in extra.passages
    }

    def derived(
        resource: URIRef,
        ids: list[str],
        body_id: str,
        confidence: float | None = None,
        basis: str | None = None,
    ) -> None:
        for passage_id in ids:
            graph.add((resource, prov.wasDerivedFrom, passages[passage_id]))
            annotation = node("annotation", body_id + "/" + passage_id)
            graph.add((annotation, RDF.type, oa.Annotation))
            graph.add((annotation, oa.hasBody, resource))
            graph.add((annotation, oa.hasTarget, passages[passage_id]))
            graph.add((annotation, oa.motivatedBy, oa.describing))
            graph.add((annotation, RDF.type, prov.Entity))
            graph.add((annotation, prov.wasDerivedFrom, passages[passage_id]))
            evidence = next(p.evidence for p in extra.passages if p.id == passage_id)
            for activity in extra.activities:
                if (
                    activity.char_start <= evidence.char_start
                    and activity.char_end >= evidence.char_end
                ):
                    graph.add(
                        (annotation, prov.wasGeneratedBy, activities[activity.id])
                    )
            graph.add(
                (
                    annotation,
                    DCTERMS.created,
                    Literal(artifact.created_at, datatype=XSD.dateTime),
                )
            )
            if confidence is not None:
                graph.add(
                    (
                        annotation,
                        app.extractionConfidence,
                        Literal(Decimal(str(confidence))),
                    )
                )
                graph.add((annotation, meta.confidenceBasis, Literal(basis)))

    for concept in artifact.concepts:
        resource = concepts[concept.id]
        graph.add(
            (
                resource,
                RDF.type,
                OWL.Class if concept.kind == "class" else OWL.NamedIndividual,
            )
        )
        graph.add((resource, RDFS.label, Literal(concept.label)))
        graph.add((resource, SKOS.definition, Literal(concept.definition)))
        graph.add((resource, meta.jsonId, Literal(concept.id)))
        if concept.name is not None:
            graph.add((resource, schema.name, Literal(concept.name)))
        for alias in concept.aliases:
            graph.add((resource, SKOS.altLabel, Literal(alias)))
        derived(
            resource,
            [passage_coords[(e.char_start, e.char_end)] for e in concept.evidence],
            concept.id,
        )
    for relation in artifact.relation_types:
        resource = relation_iris[relation.id]
        if resource == node("relation", relation.id):
            graph.add(
                (
                    resource,
                    RDF.type,
                    OWL.AnnotationProperty
                    if relation.label in {"subclass_of", "instance_of"}
                    else OWL.ObjectProperty,
                )
            )
            graph.add((resource, RDFS.label, Literal(relation.label)))
            graph.add((resource, SKOS.definition, Literal(relation.definition)))
        for predicate, references in (
            (meta.candidateDomain, relation.domain),
            (meta.candidateRange, relation.range),
        ):
            for reference in references:
                graph.add((resource, predicate, concepts[reference]))
        derived(
            resource,
            [passage_coords[(e.char_start, e.char_end)] for e in relation.evidence],
            relation.id,
        )
    for index, alignment in enumerate(extra.alignments):
        resource = node("alignment", str(index))
        subject = concepts.get(alignment.item_id, relation_iris.get(alignment.item_id))
        assert subject is not None
        target = URIRef(alignment.iri)
        graph.add((resource, RDF.type, prov.Entity))
        graph.add((resource, RDF.subject, subject))
        graph.add((resource, RDF.object, target))
        graph.add((resource, meta.mappingStatus, Literal(alignment.status)))
        graph.add((resource, meta.mappingOperation, Literal(alignment.operation)))
        graph.add((resource, meta.mappingAuthority, Literal(alignment.authority)))
        graph.add((resource, RDFS.comment, Literal(alignment.rationale)))
        derived(resource, alignment.passage_ids, "alignment-" + str(index))
        if alignment.status == "accepted":
            alignment_predicate = {
                "rdf_type": RDF.type,
                "subclass_of": RDFS.subClassOf,
                "close_match": SKOS.closeMatch,
                "exact_match": SKOS.exactMatch,
                "broad_match": SKOS.broadMatch,
                "related_match": SKOS.relatedMatch,
            }.get(alignment.operation)
            if alignment_predicate is not None:
                graph.add((subject, alignment_predicate, target))

    status_scheme = URIRef(str(app) + "epistemic-status-scheme")
    graph.add((status_scheme, RDF.type, SKOS.ConceptScheme))
    graph.add(
        (status_scheme, DCTERMS.title, Literal("Assertion origins; not truth values"))
    )
    assertions = {a.relationship_id: a for a in extra.assertions}
    types = {r.id: r for r in artifact.relation_types}
    formalized = 0
    for edge in artifact.relationships:
        assertion = assertions[edge.id]
        resource = statements[edge.id]
        relation = types[edge.relation]
        predicate = {"subclass_of": RDFS.subClassOf, "instance_of": RDF.type}.get(
            relation.label, relation_iris[edge.relation]
        )
        graph.add((resource, RDF.type, app.Claim))
        graph.add((resource, RDF.type, prov.Entity))
        graph.add((resource, RDF.type, RDF.Statement))
        graph.add((resource, RDF.subject, concepts[edge.source]))
        graph.add((resource, RDF.predicate, predicate))
        graph.add((resource, RDF.object, concepts[edge.target]))
        graph.add((resource, RDFS.label, Literal(edge.description)))
        graph.add((resource, meta.jsonId, Literal(edge.id)))
        graph.add(
            (
                resource,
                meta.logic,
                Literal(json.dumps(asdict(edge.logic), sort_keys=True)),
            )
        )
        status = URIRef(str(app) + "status/" + assertion.origin)
        graph.add((status, RDF.type, SKOS.Concept))
        graph.add((status, SKOS.prefLabel, Literal(assertion.origin)))
        graph.add((status, SKOS.inScheme, status_scheme))
        graph.add((resource, app.epistemicStatus, status))
        for activity_id in assertion.activity_ids:
            graph.add((resource, prov.wasGeneratedBy, activities[activity_id]))
        generated = max(
            a.ended_at for a in extra.activities if a.id in assertion.activity_ids
        )
        graph.add(
            (resource, prov.generatedAtTime, Literal(generated, datatype=XSD.dateTime))
        )
        derived(
            resource,
            assertion.passage_ids,
            edge.id,
            assertion.confidence,
            assertion.confidence_basis,
        )
        triples = (
            formalize_relationship(
                edge,
                relation,
                concepts[edge.source],
                concepts[edge.target],
                relation_iris[edge.relation],
            )
            if assertion.origin == "explicit"
            else None
        )
        if triples is not None:
            formalized += 1
            for triple in triples:
                graph.add(triple)
            if triples[0][2] == OWL.NegativePropertyAssertion:
                axiom = triples[0][0]
            else:
                axiom = node("assertion", edge.id)
                graph.add((axiom, RDF.type, OWL.Axiom))
                s, p, o = triples[-1]
                graph.add((axiom, OWL.annotatedSource, s))
                graph.add((axiom, OWL.annotatedProperty, p))
                graph.add((axiom, OWL.annotatedTarget, o))
            graph.add((axiom, prov.wasDerivedFrom, resource))

    theme_scheme = node("scheme", "themes")
    graph.add((theme_scheme, RDF.type, SKOS.ConceptScheme))
    graph.add((theme_scheme, DCTERMS.title, Literal("Source-grounded book themes")))
    for theme in extra.themes:
        resource = node("theme", theme.id)
        graph.add((resource, RDF.type, SKOS.Concept))
        graph.add((resource, SKOS.prefLabel, Literal(theme.label)))
        graph.add((resource, SKOS.definition, Literal(theme.definition)))
        graph.add((resource, SKOS.inScheme, theme_scheme))
        graph.add((book_node, DCTERMS.subject, resource))
        if theme.concept_id is not None:
            graph.add((resource, RDFS.seeAlso, concepts[theme.concept_id]))
        if theme.shared_iri is not None:
            graph.add((resource, SKOS.exactMatch, URIRef(theme.shared_iri)))
        for passage_id in theme.passage_ids:
            graph.add((passages[passage_id], DCTERMS.subject, resource))
        derived(resource, theme.passage_ids, theme.id)
    for temporal_reference in extra.temporal_references:
        resource = node("time", temporal_reference.id)
        subject = concepts.get(
            temporal_reference.item_id, statements.get(temporal_reference.item_id)
        )
        assert subject is not None
        graph.add((subject, time.hasTime, resource))
        graph.add((resource, RDFS.label, Literal(temporal_reference.expression)))
        graph.add(
            (resource, meta.temporalPrecision, Literal(temporal_reference.precision))
        )
        if temporal_reference.precision != "unknown":
            graph.add(
                (
                    resource,
                    RDF.type,
                    time.Interval
                    if temporal_reference.precision == "interval"
                    else time.Instant,
                )
            )
            for bound, bound_value in (
                ("start", temporal_reference.start),
                ("end", temporal_reference.end),
            ):
                if bound_value is None:
                    continue
                instant = (
                    node("time-bound", temporal_reference.id + "-" + bound)
                    if temporal_reference.precision == "interval"
                    else resource
                )
                if temporal_reference.precision == "interval":
                    graph.add(
                        (
                            resource,
                            time.hasBeginning if bound == "start" else time.hasEnd,
                            instant,
                        )
                    )
                    graph.add((instant, RDF.type, time.Instant))
                datatype = validate_date(bound_value)
                if datatype == "gYear":
                    date_description = node(
                        "date-description", temporal_reference.id + "-" + bound
                    )
                    graph.add((instant, time.inDateTime, date_description))
                    graph.add((date_description, RDF.type, time.DateTimeDescription))
                    graph.add((date_description, time.unitType, time.unitYear))
                    graph.add(
                        (
                            date_description,
                            time.year,
                            Literal(bound_value, datatype=XSD.gYear),
                        )
                    )
                else:
                    graph.add(
                        (
                            instant,
                            time.inXSDDate
                            if datatype == "date"
                            else time.inXSDDateTime,
                            Literal(bound_value, datatype=XSD[datatype]),
                        )
                    )
        derived(resource, temporal_reference.passage_ids, temporal_reference.id)
    for index, link in enumerate(extra.claim_links):
        graph.add(
            (statements[link.source_id], app[link.relation], statements[link.target_id])
        )
        resource = node("claim-link", str(index))
        graph.add((resource, RDF.type, RDF.Statement))
        graph.add((resource, RDF.subject, statements[link.source_id]))
        graph.add((resource, RDF.predicate, app[link.relation]))
        graph.add((resource, RDF.object, statements[link.target_id]))
        derived(resource, link.passage_ids, "claim-link-" + str(index))
    del catalog
    return graph, formalized


def validate_standard_graph(graph: Graph, application_iri: str) -> str:
    import pyshacl
    from rdflib import Graph

    data = (files("alex") / "ontologies" / "book" / "shapes-v001.ttl").read_text()
    shapes = Graph().parse(
        data=data.replace(
            "urn:alex:ontology:book:", application_namespace(application_iri)
        ),
        format="turtle",
    )
    api: Any = pyshacl
    conforms, _, report = api.validate(
        graph,
        shacl_graph=shapes,
        inference="none",
        do_owl_imports=False,
        advanced=False,
        js=False,
    )
    if not conforms:
        raise ValueError("Standard ontology failed SHACL validation:\n" + str(report))
    return str(report)


def ontology_report(
    artifact: OntologyArtifact,
    graph: Graph,
    validation: str,
    application_file: Path | None = None,
    instance_file: Path | None = None,
) -> str:
    extra = artifact.enrichment
    if extra is None:
        raise ValueError("The A-H report requires enrichment.")

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    app_graph = application_graph(extra.profile.application_iri, graph)
    app = application_namespace(extra.profile.application_iri)
    sections = [
        "# Book ontology report",
        "",
        "## A. Scope and assumptions",
        "",
        extra.scope.purpose,
        "",
        *[f"- {x}" for x in extra.scope.boundaries],
        *[f"- {x}" for x in extra.scope.assumptions],
        "",
        "## B. Competency questions",
        "",
        *[f"- {q}" for q in extra.scope.competency_questions],
        "",
        "## C. Application ontology",
        "",
        "| URI | Label | Definition | Parent | Domain | Range | Use |",
        "|---|---|---|---|---|---|---|",
    ]
    from rdflib import Namespace
    from rdflib.namespace import RDFS

    namespace = Namespace(app)
    for term in sorted(app_graph.subjects(namespace.termPurpose, None), key=str):
        sections.append(
            "| "
            + " | ".join(
                cell(str(value or "-"))
                for value in (
                    term,
                    app_graph.value(term, RDFS.label),
                    app_graph.value(term, RDFS.comment),
                    app_graph.value(term, RDFS.subClassOf),
                    app_graph.value(term, RDFS.domain),
                    app_graph.value(term, RDFS.range),
                    app_graph.value(term, namespace.termPurpose),
                )
            )
            + " |"
        )
    sections.extend(
        [
            "",
            "Existing alex: extensions retain JSON IDs, raw coordinates, "
            "logical qualifiers,",
            "hashes, prompt details, and mapping audit information.",
            "",
            "## D. Controlled vocabularies",
            "",
            "- Shared epistemic-status scheme: explicit / interpretive / "
            "speculative / external / unknown.",
            "- Local, source-grounded theme scheme; accepted shared topic links only.",
            "",
        ]
    )
    sections.extend(f"- **{cell(t.label)}**: {t.definition}" for t in extra.themes)
    for heading, path, data in (
        ("E. Turtle ontology", application_file, app_graph),
        ("F. Turtle instance graph", instance_file, graph),
    ):
        sections.extend(["", "## " + heading, ""])
        if path is not None:
            sections.append(f"[{path.name}]({path.name})")
        else:
            sections.extend(["```turtle", str(data.serialize(format="turtle")), "```"])
    sections.extend(
        [
            "",
            "## G. Evidence table",
            "",
            "| Claim | Source passage | Assertion type | Evidence status | "
            "Confidence |",
            "|---|---|---|---|---|",
        ]
    )
    claims = {edge.id: edge for edge in artifact.relationships}
    for assertion in extra.assertions:
        edge = claims[assertion.relationship_id]
        sections.append(
            "| "
            + " | ".join(
                [
                    cell(edge.id + ": " + edge.description),
                    ", ".join(assertion.passage_ids),
                    assertion.origin + "; " + edge.logic.strength,
                    "Exact raw-source spans",
                    str(assertion.confidence)
                    if assertion.confidence is not None
                    else "Not estimated",
                ]
            )
            + " |"
        )
    accepted = sum(a.status == "accepted" for a in extra.alignments)
    proposed = sum(a.status == "proposed" for a in extra.alignments)
    sections.extend(
        [
            "",
            "## H. Validation",
            "",
            validation.strip(),
            "",
            f"Instance graph triples: {len(graph)}. "
            "Every core relationship has evidence and activity provenance.",
            f"Accepted mappings: {accepted}; proposed mappings: {proposed}.",
            "Syntax, references, source spans, catalog guards, "
            "and SHACL constraints are checked.",
            "These checks do not establish factual truth, semantic entailment, "
            "or complete coverage.",
            "No source-grounded argumentative links were extracted."
            if not extra.claim_links
            else f"Source-grounded argumentative links: {len(extra.claim_links)}.",
            "Interpretation generation is disabled. Unsupported page numbers "
            "and missing dates are omitted.",
            "",
        ]
    )
    return "\n".join(sections)
