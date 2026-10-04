"""Deterministically export explicitly scoped ontology JSON to OWL/RDF."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal
from urllib.parse import quote

from pydantic import Field, ValidationError

from alex.lib.ontology import (
    OntologyError,
    stable_id,
    validate_relationship_logic,
    validate_subclass_hierarchy,
    write_ontology_text,
)
from alex.lib.ontology_enrichment_models import OntologyEnrichment
from alex.lib.ontology_models import (
    OntologyConcept,
    OntologyRelationship,
    OntologyRelationType,
    OntologyResponseModel,
    SourceEvidence,
    Text,
)

if TYPE_CHECKING:
    from rdflib import BNode, Graph, URIRef
    from rdflib.term import Literal as RdfLiteral

type RdfTriple = tuple[URIRef | BNode, URIRef, URIRef | BNode | RdfLiteral]
META_IRI = "urn:alex:ontology:metadata:"


class ArtifactSource(OntologyResponseModel):
    path: Text
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    characters: Annotated[int, Field(ge=0)]


class OntologyArtifact(OntologyResponseModel):
    schema_version: Literal[2]
    created_at: Text
    source: ArtifactSource
    generation: dict[str, object]
    concepts: list[OntologyConcept]
    relation_types: list[OntologyRelationType]
    relationships: list[OntologyRelationship]
    enrichment: OntologyEnrichment | None = None


@dataclass(frozen=True)
class OntologyExportConfig:
    source: Path
    output_path: Path | None = None
    base_iri: str | None = None
    force: bool = False
    profile: Literal["standard", "legacy"] | None = None
    report_path: Path | None = None
    bundle_dir: Path | None = None


@dataclass(frozen=True)
class OntologyExportOutput:
    output_path: Path
    base_iri: str
    triple_count: int
    formalized_relationships: int
    annotated_relationships: int


def load_ontology_artifact(path: Path) -> OntologyArtifact:
    return parse_ontology_artifact(path.read_text(encoding="utf-8"))


def parse_ontology_artifact(text: str) -> OntologyArtifact:
    try:
        artifact = OntologyArtifact.model_validate_json(text)
    except ValidationError as error:
        detail = error.errors(include_input=False)[0]
        raise OntologyError(
            f"Invalid ontology artifact ({detail['type']}); export requires schema "
            "version 2 with explicit relationship logic. Regenerate older artifacts."
        ) from error
    concepts = {item.id: item for item in artifact.concepts}
    types = {item.id: item for item in artifact.relation_types}
    relationships = {item.id: item for item in artifact.relationships}
    if (
        len(concepts) != len(artifact.concepts)
        or len(types) != len(artifact.relation_types)
        or len(relationships) != len(artifact.relationships)
    ):
        raise OntologyError("Duplicate IDs in the ontology artifact.")
    for item_type in artifact.relation_types:
        for reference in (*item_type.domain, *item_type.range):
            if reference not in concepts or concepts[reference].kind != "class":
                raise OntologyError(
                    "Domain/range references must identify existing classes."
                )
    for edge in artifact.relationships:
        if (
            edge.source not in concepts
            or edge.target not in concepts
            or edge.relation not in types
        ):
            raise OntologyError(f"Unknown reference in relationship {edge.id}.")
        label = types[edge.relation].label
        kinds = (concepts[edge.source].kind, concepts[edge.target].kind)
        if label == "subclass_of" and kinds != ("class", "class"):
            raise OntologyError("subclass_of requires two classes.")
        if label == "instance_of" and kinds != ("instance", "class"):
            raise OntologyError("instance_of requires an instance and a class.")
        validate_relationship_logic(edge, concepts, types)
    items: tuple[OntologyConcept | OntologyRelationType | OntologyRelationship, ...] = (
        *artifact.concepts,
        *artifact.relation_types,
        *artifact.relationships,
    )
    for item in items:
        if not item.id.strip() or not item.evidence:
            raise OntologyError(
                "Every ontology item requires an ID and source evidence."
            )
        for evidence in item.evidence:
            if evidence.match_mode == "whitespace_normalized" and (
                evidence.model_quote is None
                or evidence.model_quote.split() != evidence.quote.split()
            ):
                raise OntologyError(
                    "Evidence alignment must preserve words and punctuation."
                )
            if (
                not evidence.quote.strip()
                or evidence.char_start < 0
                or evidence.char_end > artifact.source.characters
                or evidence.char_end - evidence.char_start != len(evidence.quote)
                or evidence.line_start < 1
                or evidence.line_end < evidence.line_start
            ):
                raise OntologyError("Invalid source evidence coordinates.")
    validate_subclass_hierarchy(concepts, types, relationships)
    if artifact.enrichment is not None:
        from alex.lib.ontology_enrichment import validate_enrichment

        validate_enrichment(artifact)
    from alex.lib.ontology_enrichment import validate_native_concepts

    validate_native_concepts(artifact)
    return artifact


def ontology_base_iri(artifact: OntologyArtifact, override: str | None) -> str:
    base = (
        override
        if override is not None
        else f"urn:alex:ontology:sha256:{artifact.source.sha256}"
    )
    base = base.rstrip("#/")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", base) is None or re.search(
        r'[\s<>"{}|^`\\#]', base
    ):
        raise OntologyError(
            "--base-iri must be an absolute IRI without a fragment or whitespace."
        )
    return base


def formalize_relationship(
    edge: OntologyRelationship,
    relation: OntologyRelationType,
    source: URIRef,
    target: URIRef,
    property_iri: URIRef,
) -> list[RdfTriple] | None:
    from rdflib import BNode
    from rdflib.namespace import OWL, RDF, RDFS

    logic = edge.logic
    if logic.strength != "categorical" or logic.subject_quantifier == "unspecified":
        return None
    if relation.label == "subclass_of":
        # Negated subsumption and disjointness are different claims. The schema
        # does not distinguish them, so retain negative taxonomy as annotations.
        return (
            [(source, RDFS.subClassOf, target)]
            if logic.polarity == "positive"
            else None
        )
    if relation.label == "instance_of":
        if logic.polarity == "positive":
            return [(source, RDF.type, target)]
        complement = BNode(stable_id("complement", edge.id))
        return [
            (complement, RDF.type, OWL.Class),
            (complement, OWL.complementOf, target),
            (source, RDF.type, complement),
        ]
    if logic.object_quantifier == "unspecified":
        return None
    if logic.subject_quantifier == "individual" and logic.object_quantifier == "value":
        if logic.polarity == "positive":
            return [(source, property_iri, target)]
        negative = BNode(stable_id("negative", edge.id))
        return [
            (negative, RDF.type, OWL.NegativePropertyAssertion),
            (negative, OWL.sourceIndividual, source),
            (negative, OWL.assertionProperty, property_iri),
            (negative, OWL.targetIndividual, target),
        ]
    restriction = BNode(stable_id("restriction", edge.id))
    filler = {
        "some": OWL.someValuesFrom,
        "only": OWL.allValuesFrom,
        "value": OWL.hasValue,
    }[logic.object_quantifier]
    triples: list[RdfTriple] = [
        (restriction, RDF.type, OWL.Restriction),
        (restriction, OWL.onProperty, property_iri),
        (restriction, filler, target),
    ]
    expression: URIRef | BNode = restriction
    if logic.polarity == "negative":
        expression = BNode(stable_id("complement", edge.id))
        triples.extend(
            [
                (expression, RDF.type, OWL.Class),
                (expression, OWL.complementOf, restriction),
            ]
        )
    if logic.subject_quantifier == "all":
        triples.append((source, RDFS.subClassOf, expression))
    elif logic.subject_quantifier == "individual":
        triples.append((source, RDF.type, expression))
    else:
        # A source existential needs a witness; it must not become a restriction
        # on every member of the source class. An anonymous individual suffices.
        witness = BNode(stable_id("witness", edge.id))
        triples.extend([(witness, RDF.type, source), (witness, RDF.type, expression)])
    return triples


def build_ontology_rdf(artifact: OntologyArtifact, base_iri: str) -> tuple[Graph, int]:
    from rdflib import Graph, Namespace, URIRef
    from rdflib import Literal as RdfLiteral
    from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

    graph = Graph()
    meta = Namespace(META_IRI)
    concepts_ns = Namespace(base_iri + "#concept/")
    relations_ns = Namespace(base_iri + "#relation/")
    claims_ns = Namespace(base_iri + "#claim/")
    assertions_ns = Namespace(base_iri + "#assertion/")
    evidence_ns = Namespace(base_iri + "#evidence/")
    for prefix, namespace in (
        ("alex", meta),
        ("concept", concepts_ns),
        ("relation", relations_ns),
        ("claim", claims_ns),
        ("assertion", assertions_ns),
        ("evidence", evidence_ns),
    ):
        graph.bind(prefix, namespace)
    for predicate in (
        DCTERMS.source,
        DCTERMS.created,
        SKOS.definition,
        SKOS.altLabel,
        meta.sourceSha256,
        meta.sourceCharacters,
        meta.generation,
        meta.sourceEvidence,
        meta.quote,
        meta.charStart,
        meta.charEnd,
        meta.lineStart,
        meta.lineEnd,
        meta.jsonId,
        meta.logic,
        meta.candidateDomain,
        meta.candidateRange,
        meta.standardPredicate,
        meta.describesProperty,
        meta.modelQuote,
        meta.evidenceMatchMode,
    ):
        graph.add((predicate, RDF.type, OWL.AnnotationProperty))
    ontology = URIRef(base_iri)
    source_path = Path(artifact.source.path)
    source_document = (
        URIRef(source_path.as_uri())
        if source_path.is_absolute()
        else RdfLiteral(artifact.source.path)
    )
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, DCTERMS.source, source_document))
    graph.add(
        (
            ontology,
            DCTERMS.created,
            RdfLiteral(artifact.created_at, datatype=XSD.dateTime),
        )
    )
    graph.add((ontology, meta.sourceSha256, RdfLiteral(artifact.source.sha256)))
    graph.add((ontology, meta.sourceCharacters, RdfLiteral(artifact.source.characters)))
    graph.add(
        (
            ontology,
            meta.generation,
            RdfLiteral(
                json.dumps(artifact.generation, sort_keys=True, ensure_ascii=False)
            ),
        )
    )
    graph.add((ontology, OWL.versionInfo, RdfLiteral("alex ontology JSON schema 2")))

    def attach_evidence(
        subject: URIRef | BNode, records: tuple[SourceEvidence, ...]
    ) -> None:
        for record in records:
            digest = hashlib.sha256(
                json.dumps(asdict(record), sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            node = evidence_ns[digest]
            graph.add((subject, meta.sourceEvidence, node))
            graph.add((node, DCTERMS.source, source_document))
            graph.add((node, meta.evidenceMatchMode, RdfLiteral(record.match_mode)))
            if record.model_quote is not None:
                graph.add((node, meta.modelQuote, RdfLiteral(record.model_quote)))
            for predicate, value in (
                (meta.quote, record.quote),
                (meta.charStart, record.char_start),
                (meta.charEnd, record.char_end),
                (meta.lineStart, record.line_start),
                (meta.lineEnd, record.line_end),
            ):
                graph.add((node, predicate, RdfLiteral(value)))

    concept_iris = {
        item.id: concepts_ns[quote(item.id, safe="")] for item in artifact.concepts
    }
    relation_iris = {
        item.id: relations_ns[quote(item.id, safe="")]
        for item in artifact.relation_types
    }
    types = {item.id: item for item in artifact.relation_types}
    for item in artifact.concepts:
        node = concept_iris[item.id]
        graph.add(
            (node, RDF.type, OWL.Class if item.kind == "class" else OWL.NamedIndividual)
        )
        graph.add((node, RDFS.label, RdfLiteral(item.label)))
        graph.add((node, SKOS.definition, RdfLiteral(item.definition)))
        graph.add((node, meta.jsonId, RdfLiteral(item.id)))
        for alias in item.aliases:
            graph.add((node, SKOS.altLabel, RdfLiteral(alias)))
        attach_evidence(node, item.evidence)
    for item_type in artifact.relation_types:
        node = relation_iris[item_type.id]
        builtin = {"subclass_of": RDFS.subClassOf, "instance_of": RDF.type}.get(
            item_type.label
        )
        graph.add(
            (
                node,
                RDF.type,
                OWL.ObjectProperty if builtin is None else OWL.AnnotationProperty,
            )
        )
        graph.add((node, RDFS.label, RdfLiteral(item_type.label)))
        graph.add((node, SKOS.definition, RdfLiteral(item_type.definition)))
        graph.add((node, meta.jsonId, RdfLiteral(item_type.id)))
        if builtin is not None:
            graph.add((node, meta.standardPredicate, builtin))
        for predicate, references in (
            (meta.candidateDomain, item_type.domain),
            (meta.candidateRange, item_type.range),
        ):
            for reference in references:
                graph.add((node, predicate, concept_iris[reference]))
        claim = claims_ns[quote(item_type.id, safe="")]
        graph.add((claim, RDF.type, OWL.AnnotationProperty))
        graph.add((claim, RDFS.label, RdfLiteral(item_type.label)))
        graph.add((claim, meta.describesProperty, node))
        attach_evidence(node, item_type.evidence)
    formalized = 0
    for edge in artifact.relationships:
        source, target = concept_iris[edge.source], concept_iris[edge.target]
        relation = types[edge.relation]
        triples = formalize_relationship(
            edge, relation, source, target, relation_iris[edge.relation]
        )
        assertion: URIRef | BNode = assertions_ns[quote(edge.id, safe="")]
        if triples is None:
            predicate = claims_ns[quote(edge.relation, safe="")]
            graph.add((source, predicate, target))
            graph.add((assertion, RDF.type, OWL.Axiom))
            graph.add((assertion, OWL.annotatedSource, source))
            graph.add((assertion, OWL.annotatedProperty, predicate))
            graph.add((assertion, OWL.annotatedTarget, target))
        else:
            formalized += 1
            for triple in triples:
                graph.add(triple)
            if triples[0][2] == OWL.NegativePropertyAssertion:
                # Negative assertion annotations belong on the assertion node itself.
                assertion = triples[0][0]
            else:
                logical_source, predicate, logical_target = triples[-1]
                graph.add((assertion, RDF.type, OWL.Axiom))
                graph.add((assertion, OWL.annotatedSource, logical_source))
                graph.add((assertion, OWL.annotatedProperty, predicate))
                graph.add((assertion, OWL.annotatedTarget, logical_target))
        graph.add((assertion, meta.jsonId, RdfLiteral(edge.id)))
        graph.add((assertion, RDFS.comment, RdfLiteral(edge.description)))
        graph.add(
            (
                assertion,
                meta.logic,
                RdfLiteral(
                    json.dumps(asdict(edge.logic), sort_keys=True, ensure_ascii=False)
                ),
            )
        )
        attach_evidence(assertion, edge.evidence)
    return graph, formalized


def export_ontology(config: OntologyExportConfig) -> OntologyExportOutput:
    from rdflib import Graph
    from rdflib.compare import isomorphic

    output_path = config.output_path or config.source.with_suffix(".ttl")
    if output_path.resolve() == config.source.resolve() or (
        output_path.exists() and output_path.samefile(config.source)
    ):
        raise OntologyError("The export cannot replace the source JSON.")
    formats = {".ttl": "turtle", ".owl": "xml", ".rdf": "xml", ".jsonld": "json-ld"}
    serialization = formats.get(output_path.suffix.casefold())
    if serialization is None:
        raise OntologyError(
            "Choose .ttl (Turtle), .owl/.rdf (RDF/XML), or .jsonld (JSON-LD)."
        )
    if output_path.exists() and (output_path.is_dir() or not config.force):
        raise OntologyError(
            f"Output already exists: {output_path}. Use --force to replace it."
        )
    artifact = load_ontology_artifact(config.source)
    base = ontology_base_iri(artifact, config.base_iri)
    standard = config.profile == "standard" or (
        config.profile is None and artifact.enrichment is not None
    )
    if standard:
        from alex.lib.ontology_standard_export import (
            application_graph,
            ontology_report,
            standard_graph,
            validate_standard_graph,
        )

        if artifact.enrichment is None:
            raise OntologyError("The standard profile requires --enrich extraction.")
        instances, formalized = standard_graph(artifact, base)
        application = application_graph(
            artifact.enrichment.profile.application_iri, instances
        )
        graph = instances + application
        validation = validate_standard_graph(
            graph, artifact.enrichment.profile.application_iri
        )
    else:
        if config.report_path is not None or config.bundle_dir is not None:
            raise OntologyError("Reports and bundles require the standard profile.")
        graph, formalized = build_ontology_rdf(artifact, base)
    if serialization == "json-ld":
        from alex.lib.ontology_vocabularies import NAMESPACES

        context = dict(NAMESPACES)
        if artifact.enrichment is not None:
            context["book"] = artifact.enrichment.profile.application_iri
        context["alex"] = META_IRI
        text = str(
            graph.serialize(format="json-ld", context=context, auto_compact=True)
        )
    else:
        text = graph.serialize(format=serialization, encoding="utf-8").decode("utf-8")
    reparsed = Graph().parse(data=text, format=serialization)
    if not isomorphic(graph, reparsed):
        raise OntologyError("The serialized ontology failed its RDF round-trip check.")
    outputs: dict[Path, str] = {output_path: text}
    if standard and (config.report_path is not None or config.bundle_dir is not None):
        bundle = config.bundle_dir
        report = config.report_path or ((bundle / "report.md") if bundle else None)
        assert report is not None
        app_path = (
            (bundle / "application.ttl")
            if bundle
            else report.with_suffix(".application.ttl")
        )
        instances_path = (
            (bundle / "instances.ttl")
            if bundle
            else report.with_suffix(".instances.ttl")
        )
        for path, value in (
            (app_path, str(application.serialize(format="turtle"))),
            (instances_path, str(instances.serialize(format="turtle"))),
            (
                report,
                ontology_report(
                    artifact, instances, validation, app_path, instances_path
                ),
            ),
        ):
            if path in outputs:
                raise OntologyError(
                    "Export, report, and bundle paths must be distinct."
                )
            outputs[path] = value
        if bundle is not None:
            import hashlib

            manifest = {
                "schema_version": 1,
                "source_sha256": artifact.source.sha256,
                "files": {
                    str(p.resolve()): hashlib.sha256(value.encode()).hexdigest()
                    for p, value in outputs.items()
                },
            }
            outputs[bundle / "manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    resolved: set[Path] = set()
    for path in outputs:
        target = path.resolve()
        if target == config.source.resolve() or target in resolved:
            raise OntologyError(
                "Output files must be distinct and cannot replace the source JSON."
            )
        resolved.add(target)
        if path.exists() and (path.is_dir() or not config.force):
            raise OntologyError(
                f"Output already exists: {path}. Use --force to replace it."
            )
    for path, value in outputs.items():
        write_ontology_text(path, value, force=config.force)
    return OntologyExportOutput(
        output_path,
        base,
        len(graph),
        formalized,
        len(artifact.relationships) - formalized,
    )
