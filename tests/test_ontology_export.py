from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from alex.commands.ontology_export import build_ontology_export_command
from alex.lib.ontology import OntologyError
from alex.lib.ontology_export import META_IRI, OntologyExportConfig, export_ontology

BASE = "urn:book:test"
CONCEPT = Namespace(BASE + "#concept/")
RELATION = Namespace(BASE + "#relation/")
META = Namespace(META_IRI)


def payload() -> dict[str, Any]:
    quote = 'A "tree" is a plant.\nAn example is described.'
    evidence = [
        {
            "quote": quote,
            "char_start": 0,
            "char_end": len(quote),
            "line_start": 1,
            "line_end": 2,
        }
    ]
    return {
        "schema_version": 2,
        "created_at": "2026-10-04T00:00:00+00:00",
        "source": {
            "path": "/books/book.md",
            "sha256": hashlib.sha256(quote.encode()).hexdigest(),
            "characters": len(quote),
        },
        "generation": {"model": "test", "prompt": {"version": "v003"}},
        "concepts": [
            {
                "id": key,
                "label": label,
                "kind": kind,
                "definition": "A concept.",
                "aliases": ['Alias with 文 and "quotes"'],
                "evidence": evidence,
            }
            for key, label, kind in [
                ("A", "Tree", "class"),
                ("B", "Plant", "class"),
                ("a", "Alice", "instance"),
                ("b", "Bob", "instance"),
            ]
        ],
        "relation_types": [
            {
                "id": "r",
                "label": "uses",
                "definition": "Uses the target.",
                "domain": ["A", "B"],
                "range": [],
                "evidence": evidence,
            },
            {
                "id": "sub",
                "label": "subclass_of",
                "definition": "A specialization.",
                "domain": [],
                "range": [],
                "evidence": evidence,
            },
            {
                "id": "member",
                "label": "instance_of",
                "definition": "Class membership.",
                "domain": [],
                "range": [],
                "evidence": evidence,
            },
        ],
        "relationships": [
            {
                "id": "edge",
                "source": "A",
                "relation": "r",
                "target": "B",
                "description": "Every A uses some B.",
                "evidence": evidence,
                "logic": {
                    "subject_quantifier": "all",
                    "object_quantifier": "some",
                    "polarity": "positive",
                    "strength": "categorical",
                    "condition": None,
                    "rationale": "Explicit source scope.",
                },
            }
        ],
    }


def write_payload(tmp_path: Path, data: dict[str, Any]) -> Path:
    source = tmp_path / "ontology.json"
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return source


def exported_graph(tmp_path: Path, data: dict[str, Any]) -> Graph:
    source = write_payload(tmp_path, data)
    result = export_ontology(OntologyExportConfig(source, base_iri=BASE))
    return Graph().parse(result.output_path, format="turtle")


def test_universal_subject_and_existential_target_become_a_restriction(
    tmp_path: Path,
) -> None:
    graph = exported_graph(tmp_path, payload())
    expression = graph.value(CONCEPT.A, RDFS.subClassOf)
    assert isinstance(expression, BNode)
    assert (expression, RDF.type, OWL.Restriction) in graph
    assert (expression, OWL.onProperty, RELATION.r) in graph
    assert (expression, OWL.someValuesFrom, CONCEPT.B) in graph
    assert (CONCEPT.A, RDF.type, OWL.NamedIndividual) not in graph
    assert (RELATION.r, RDFS.domain, CONCEPT.A) not in graph
    assert (RELATION.r, RDFS.domain, CONCEPT.B) not in graph
    assert (RELATION.r, META.candidateDomain, CONCEPT.A) in graph
    assert (CONCEPT.A, SKOS.altLabel, Literal('Alias with 文 and "quotes"')) in graph
    assert len(list(graph.objects(predicate=META.quote))) == 1


def test_only_restricts_targets_without_asserting_their_existence(
    tmp_path: Path,
) -> None:
    data = payload()
    data["relationships"][0]["logic"]["object_quantifier"] = "only"
    graph = exported_graph(tmp_path, data)
    restriction = graph.value(CONCEPT.A, RDFS.subClassOf)
    assert (restriction, OWL.allValuesFrom, CONCEPT.B) in graph
    assert not list(graph.triples((None, OWL.someValuesFrom, None)))


def test_existential_subject_uses_a_witness_and_does_not_strengthen_the_class(
    tmp_path: Path,
) -> None:
    data = payload()
    data["relationships"][0]["logic"]["subject_quantifier"] = "some"
    graph = exported_graph(tmp_path, data)
    assert not list(graph.objects(CONCEPT.A, RDFS.subClassOf))
    witness = next(graph.subjects(RDF.type, CONCEPT.A))
    assert isinstance(witness, BNode)
    restrictions = [
        target for target in graph.objects(witness, RDF.type) if target != CONCEPT.A
    ]
    assert len(restrictions) == 1
    assert (restrictions[0], OWL.someValuesFrom, CONCEPT.B) in graph


@pytest.mark.parametrize("negative", [False, True])
def test_named_individual_property_assertions(tmp_path: Path, negative: bool) -> None:
    data = payload()
    edge = data["relationships"][0]
    edge.update(source="a", target="b")
    edge["logic"].update(
        subject_quantifier="individual",
        object_quantifier="value",
        polarity="negative" if negative else "positive",
    )
    graph = exported_graph(tmp_path, data)
    if negative:
        statement = next(graph.subjects(RDF.type, OWL.NegativePropertyAssertion))
        assert (statement, OWL.sourceIndividual, CONCEPT.a) in graph
        assert (statement, OWL.assertionProperty, RELATION.r) in graph
        assert (statement, OWL.targetIndividual, CONCEPT.b) in graph
        assert list(graph.objects(statement, META.sourceEvidence))
        assert (CONCEPT.a, RELATION.r, CONCEPT.b) not in graph
    else:
        assert (CONCEPT.a, RELATION.r, CONCEPT.b) in graph


def test_negative_restriction_negates_the_filler_inside_subject_scope(
    tmp_path: Path,
) -> None:
    data = payload()
    data["relationships"][0]["logic"]["polarity"] = "negative"
    graph = exported_graph(tmp_path, data)
    complement = graph.value(CONCEPT.A, RDFS.subClassOf)
    restriction = graph.value(complement, OWL.complementOf)
    assert (restriction, OWL.someValuesFrom, CONCEPT.B) in graph


@pytest.mark.parametrize("subject_quantifier", ["all", "some"])
def test_named_value_is_scoped_to_universal_or_existential_subjects(
    tmp_path: Path,
    subject_quantifier: str,
) -> None:
    data = payload()
    edge = data["relationships"][0]
    edge["target"] = "b"
    edge["logic"].update(
        subject_quantifier=subject_quantifier, object_quantifier="value"
    )
    graph = exported_graph(tmp_path, data)
    restriction = next(graph.subjects(OWL.hasValue, CONCEPT.b))
    if subject_quantifier == "all":
        assert (CONCEPT.A, RDFS.subClassOf, restriction) in graph
    else:
        assert (CONCEPT.A, RDFS.subClassOf, restriction) not in graph
        witness = next(graph.subjects(RDF.type, CONCEPT.A))
        assert (witness, RDF.type, restriction) in graph


def test_individual_can_have_an_existential_class_restriction(tmp_path: Path) -> None:
    data = payload()
    edge = data["relationships"][0]
    edge["source"] = "a"
    edge["logic"]["subject_quantifier"] = "individual"
    graph = exported_graph(tmp_path, data)
    restriction = next(graph.subjects(OWL.someValuesFrom, CONCEPT.B))
    assert (CONCEPT.a, RDF.type, restriction) in graph


@pytest.mark.parametrize(
    "strength", ["typical", "possible", "conditional", "unspecified"]
)
def test_qualified_or_unresolved_claims_preserve_logic_as_annotations(
    tmp_path: Path, strength: str
) -> None:
    data = payload()
    logic = data["relationships"][0]["logic"]
    if strength == "unspecified":
        logic["subject_quantifier"] = "unspecified"
    else:
        logic["strength"] = strength
        if strength == "conditional":
            logic["condition"] = "Under a specified task constraint."
    graph = exported_graph(tmp_path, data)
    assert not list(graph.subjects(RDF.type, OWL.Restriction))
    claim = URIRef(BASE + "#claim/r")
    assert (CONCEPT.A, claim, CONCEPT.B) in graph
    assertion = next(graph.subjects(OWL.annotatedProperty, claim))
    assert json.loads(str(graph.value(assertion, META.logic))) == logic
    assert list(graph.objects(assertion, META.sourceEvidence))


def test_taxonomy_and_membership_map_to_standard_predicates(tmp_path: Path) -> None:
    data = payload()
    edge = data["relationships"][0]
    edge["relation"] = "sub"
    edge["logic"]["object_quantifier"] = "unspecified"
    membership = {
        **edge,
        "id": "membership",
        "source": "a",
        "target": "A",
        "relation": "member",
        "logic": {**edge["logic"], "subject_quantifier": "individual"},
    }
    data["relationships"].append(membership)
    graph = exported_graph(tmp_path, data)
    assert (CONCEPT.A, RDFS.subClassOf, CONCEPT.B) in graph
    assert (CONCEPT.a, RDF.type, CONCEPT.A) in graph
    assert (CONCEPT.A, RDF.type, OWL.Class) in graph
    assert (CONCEPT.a, RDF.type, OWL.NamedIndividual) in graph


def test_turtle_and_rdfxml_represent_the_same_graph(tmp_path: Path) -> None:
    source = write_payload(tmp_path, payload())
    ttl = export_ontology(OntologyExportConfig(source, base_iri=BASE))
    rdfxml = export_ontology(
        OntologyExportConfig(source, tmp_path / "ontology.owl", BASE)
    )
    assert isomorphic(
        Graph().parse(ttl.output_path, format="turtle"),
        Graph().parse(rdfxml.output_path, format="xml"),
    )
    assert ttl.formalized_relationships == rdfxml.formalized_relationships == 1


@pytest.mark.parametrize(
    "failure",
    [
        "legacy",
        "reference",
        "duplicate",
        "logic",
        "evidence",
        "iri",
        "source_output",
        "exists",
    ],
)
def test_invalid_export_is_rejected_and_keeps_existing_files(
    tmp_path: Path, failure: str
) -> None:
    data = payload()
    if failure == "legacy":
        data["schema_version"] = 1
    elif failure == "reference":
        data["relationships"][0]["target"] = "missing"
    elif failure == "duplicate":
        data["concepts"].append(data["concepts"][0])
    elif failure == "logic":
        data["relationships"][0]["logic"]["subject_quantifier"] = "individual"
    elif failure == "evidence":
        data["concepts"][0]["evidence"][0]["char_start"] = -1
    source = write_payload(tmp_path, data)
    original = source.read_bytes()
    output = tmp_path / "ontology.ttl"
    output.write_text("existing export")
    config = OntologyExportConfig(
        source,
        source if failure == "source_output" else output,
        "not an IRI" if failure == "iri" else BASE,
        force=failure != "exists",
    )
    with pytest.raises(OntologyError):
        export_ontology(config)
    assert output.read_text() == "existing export"
    assert source.read_bytes() == original


def test_cli_exports_without_a_model_call(tmp_path: Path) -> None:
    source = write_payload(tmp_path, payload())
    result = CliRunner().invoke(
        build_ontology_export_command(), [str(source), "--base-iri", BASE]
    )
    assert result.exit_code == 0, result.output
    assert "formalized relationships: 1" in result.output
    assert source.with_suffix(".ttl").is_file()
