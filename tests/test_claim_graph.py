import json
from dataclasses import dataclass, field

import pytest

from alex.lib.claim_graph import (
    GraphPrompts,
    GraphSettings,
    GraphSource,
    build_claim_graph,
    claim_evidence_items,
    document_graph_source,
    merge_chunk_graphs,
    render_selected_subgraph,
    select_claim_subgraph,
)
from alex.lib.summary_eval import EvalJudgeError, EvalSettings

DOC = (
    "# Research Note\n"
    "\n"
    "## Graphs\n"
    "\n"
    "Graph methods preserve claim and evidence relationships.\n"
    "\n"
    "## Baselines\n"
    "\n"
    "Simple baselines remain cheaper for linear documents.\n"
)


@dataclass
class ClaimCompleter:
    calls: list[str] = field(default_factory=list)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append(prompt)
        if 'section title="Document Preamble"' in prompt:
            return json.dumps({"claims": []})
        if "Graph methods preserve claim and evidence relationships." in prompt:
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": (
                                "Graph methods preserve claim and evidence "
                                "relationships."
                            ),
                            "evidence": (
                                "Graph methods preserve claim and evidence "
                                "relationships."
                            ),
                        },
                        {
                            "claim": "Graph methods preserve source evidence.",
                            "evidence": "Graph methods preserve claim relationships.",
                        },
                    ]
                }
            )
        if "Simple baselines remain cheaper for linear documents." in prompt:
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": (
                                "Simple baselines remain cheaper for linear documents."
                            ),
                            "evidence": (
                                "Simple baselines remain cheaper for linear documents."
                            ),
                        }
                    ]
                }
            )
        raise AssertionError(f"Unexpected prompt: {prompt[:120]!r}")


def test_claim_evidence_items_validates_shape() -> None:
    payload = {"claims": [{"claim": "Claim A.", "evidence": "Evidence A."}]}

    assert claim_evidence_items(payload)[0].claim == "Claim A."

    with pytest.raises(EvalJudgeError, match="'claims' list"):
        claim_evidence_items({"items": []})
    with pytest.raises(EvalJudgeError, match="non-empty string"):
        claim_evidence_items({"claims": [{"claim": "", "evidence": "Evidence."}]})


def test_build_claim_graph_creates_claim_and_support_edges() -> None:
    graph = build_claim_graph(
        source=document_graph_source(doc_name="note.md", doc_text=DOC),
        prompts=GraphPrompts.load(),
        completer=ClaimCompleter(),
        eval_settings=EvalSettings(
            judge_model="judge/test",
            fact_extractor_model="extractor/test",
        ),
    )

    assert {node.type for node in graph.nodes} == {
        "claim",
        "document",
        "evidence",
        "section",
    }
    assert sum(node.type == "claim" for node in graph.nodes) == 3
    assert any(edge.type == "supports" for edge in graph.edges)
    assert any(edge.type == "similar_to" for edge in graph.edges)


def test_build_claim_graph_supports_chunk_source() -> None:
    graph = build_claim_graph(
        source=GraphSource(
            id="chunk:note:1",
            type="chunk",
            label="001_note.md",
            text=DOC,
            source_path="chunks/001_note.md",
            chunk_index=1,
            chunk_filename="001_note.md",
        ),
        prompts=GraphPrompts.load(),
        completer=ClaimCompleter(),
        eval_settings=EvalSettings(
            judge_model="judge/test",
            fact_extractor_model="extractor/test",
        ),
    )

    root = graph.nodes[0]
    assert root.id == "chunk:note:1"
    assert root.type == "chunk"
    assert root.label == "001_note.md"
    assert root.source == "chunks/001_note.md"
    assert root.metadata["chunk_index"] == "1"
    assert root.metadata["chunk_filename"] == "001_note.md"
    assert any(node.id.startswith("section:note:1:") for node in graph.nodes)
    assert any(node.id.startswith("evidence:note:1:") for node in graph.nodes)
    assert any(node.id.startswith("claim:note:1:") for node in graph.nodes)
    assert any(edge.type == "supports" for edge in graph.edges)


def test_merge_chunk_graphs_creates_document_graph_with_chunk_edges() -> None:
    prompts = GraphPrompts.load()
    eval_settings = EvalSettings(
        judge_model="judge/test",
        fact_extractor_model="extractor/test",
    )
    first = build_claim_graph(
        source=GraphSource(
            id="chunk:note:1",
            type="chunk",
            label="001_note.md",
            text=DOC,
            source_path="chunks/001_note.md",
            chunk_index=1,
            chunk_filename="001_note.md",
        ),
        prompts=prompts,
        completer=ClaimCompleter(),
        eval_settings=eval_settings,
    )
    second = build_claim_graph(
        source=GraphSource(
            id="chunk:note:2",
            type="chunk",
            label="002_note.md",
            text=DOC,
            source_path="chunks/002_note.md",
            chunk_index=2,
            chunk_filename="002_note.md",
        ),
        prompts=prompts,
        completer=ClaimCompleter(),
        eval_settings=eval_settings,
    )

    merged = merge_chunk_graphs(
        doc_name="note.md",
        source_path="note.md",
        chunk_graphs=(first, second),
    )

    assert merged.nodes[0].id == "doc:note-md"
    assert merged.nodes[0].type == "document"
    assert sum(node.type == "chunk" for node in merged.nodes) == 2
    assert any(
        edge.source == "doc:note-md"
        and edge.target == "chunk:note:1"
        and edge.type == "contains"
        for edge in merged.edges
    )
    assert any(edge.type == "similar_to" for edge in merged.edges)


def test_select_claim_subgraph_keeps_section_coverage() -> None:
    graph = build_claim_graph(
        source=document_graph_source(doc_name="note.md", doc_text=DOC),
        prompts=GraphPrompts.load(),
        completer=ClaimCompleter(),
        eval_settings=EvalSettings(
            judge_model="judge/test",
            fact_extractor_model="extractor/test",
        ),
    )

    selected = select_claim_subgraph(graph, settings=GraphSettings(max_claims=2))
    selected_claim_sections = {
        node.metadata["section"] for node in selected.nodes if node.type == "claim"
    }

    assert selected_claim_sections == {
        "Research Note > Graphs",
        "Research Note > Baselines",
    }

    rendered = render_selected_subgraph(selected)
    assert "# Selected Claim/Evidence Subgraph" in rendered
    assert "Supported by:" in rendered
    assert "Graph methods preserve claim and evidence relationships." in rendered
