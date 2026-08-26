import json
from dataclasses import dataclass, field

import pytest

from alex.lib.claim_graph import (
    EmbeddingIndex,
    GraphPrompts,
    GraphSettings,
    GraphSource,
    build_claim_graph,
    build_embedding_index,
    claim_evidence_items,
    claim_score,
    concept_score,
    document_graph_source,
    key_passage_score,
    merge_chunk_graphs,
    render_selected_subgraph,
    select_claim_subgraph,
    source_graph_items,
)
from alex.lib.summary_eval import EvalJudgeError, EvalSettings
from helpers import BagOfWordsEmbedder

# Threshold tuned for the bag-of-words fake embedder: the two graph-method claims
# in DOC share most of their tokens (cosine ~0.68), the baseline claim shares
# almost none. 0.5 links the first pair without linking the baseline.
TEST_SIMILARITY_THRESHOLD = 0.5

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
                    ],
                    "concepts": [
                        {
                            "concept": "Graph methods",
                            "definition": (
                                "Methods that preserve claim and evidence "
                                "relationships."
                            ),
                            "evidence": (
                                "Graph methods preserve claim and evidence "
                                "relationships."
                            ),
                        }
                    ],
                    "key_passages": [
                        {
                            "passage": (
                                "Graph methods preserve claim and evidence "
                                "relationships."
                            ),
                            "why_it_matters": (
                                "It states the graph method's core value."
                            ),
                        }
                    ],
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
                    ],
                    "concepts": [
                        {
                            "concept": "Simple baselines",
                            "definition": "Cheaper methods for linear documents.",
                            "evidence": (
                                "Simple baselines remain cheaper for linear documents."
                            ),
                        }
                    ],
                    "key_passages": [
                        {
                            "passage": (
                                "Simple baselines remain cheaper for linear documents."
                            ),
                            "why_it_matters": "It qualifies when baselines are useful.",
                        }
                    ],
                }
            )
        raise AssertionError(f"Unexpected prompt: {prompt[:120]!r}")


def test_claim_evidence_items_validates_shape() -> None:
    payload = {"claims": [{"claim": "Claim A.", "evidence": "Evidence A."}]}

    assert claim_evidence_items(payload)[0].claim == "Claim A."
    assert source_graph_items(payload).concepts == ()
    assert source_graph_items(payload).key_passages == ()

    with pytest.raises(EvalJudgeError, match="'claims' list"):
        claim_evidence_items({"items": []})
    with pytest.raises(EvalJudgeError, match="non-empty string"):
        claim_evidence_items({"claims": [{"claim": "", "evidence": "Evidence."}]})


def test_source_graph_items_parses_concepts_and_key_passages() -> None:
    payload = {
        "claims": [{"claim": "Claim A.", "evidence": "Evidence A."}],
        "concepts": [
            {
                "concept": "Concept A",
                "definition": "A useful idea.",
                "evidence": "The source defines Concept A.",
            }
        ],
        "key_passages": [
            {
                "passage": "A useful source sentence.",
                "why_it_matters": "It anchors the concept.",
            }
        ],
    }

    items = source_graph_items(payload)

    assert items.concepts[0].concept == "Concept A"
    assert items.key_passages[0].passage == "A useful source sentence."

    with pytest.raises(EvalJudgeError, match="concept"):
        source_graph_items({"claims": [], "concepts": [{"concept": ""}]})
    with pytest.raises(EvalJudgeError, match="Key passage"):
        source_graph_items({"claims": [], "key_passages": [{"passage": ""}]})


def test_build_claim_graph_creates_claim_and_support_edges() -> None:
    graph = build_claim_graph(
        source=document_graph_source(doc_name="note.md", doc_text=DOC),
        prompts=GraphPrompts.load(),
        completer=ClaimCompleter(),
        embedder=BagOfWordsEmbedder(),
        eval_settings=EvalSettings(
            judge_model="judge/test",
            fact_extractor_model="extractor/test",
        ),
        settings=GraphSettings(similarity_threshold=TEST_SIMILARITY_THRESHOLD),
    )

    assert {node.type for node in graph.nodes} == {
        "claim",
        "concept",
        "document",
        "evidence",
        "key_passage",
        "section",
    }
    assert sum(node.type == "claim" for node in graph.nodes) == 3
    assert sum(node.type == "concept" for node in graph.nodes) == 2
    assert sum(node.type == "key_passage" for node in graph.nodes) == 2
    scored_sections = [
        node
        for node in graph.nodes
        if node.type == "section" and node.label != "Document Preamble"
    ]
    assert scored_sections
    assert all(node.score > 0 for node in scored_sections)
    assert any(edge.type == "supports" for edge in graph.edges)
    assert any(edge.type == "defines" for edge in graph.edges)
    assert any(edge.type == "highlights" for edge in graph.edges)
    assert any(edge.type == "similar_to" for edge in graph.edges)


def test_source_claims_per_section_sets_extraction_cap() -> None:
    completer = ClaimCompleter()
    build_claim_graph(
        source=document_graph_source(doc_name="note.md", doc_text=DOC),
        prompts=GraphPrompts.load(),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
        eval_settings=EvalSettings(
            judge_model="judge/test",
            fact_extractor_model="extractor/test",
        ),
        settings=GraphSettings(
            similarity_threshold=TEST_SIMILARITY_THRESHOLD,
            source_claims_per_section=5,
        ),
    )

    extraction_prompts = [
        prompt for prompt in completer.calls if "source-grounded items" in prompt
    ]
    assert extraction_prompts
    assert all(
        "Extract up to 5 items per category" in prompt for prompt in extraction_prompts
    )


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
        embedder=BagOfWordsEmbedder(),
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
    assert any(node.id.startswith("concept:note:1:") for node in graph.nodes)
    assert any(node.id.startswith("key_passage:note:1:") for node in graph.nodes)
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
        embedder=BagOfWordsEmbedder(),
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
        embedder=BagOfWordsEmbedder(),
        eval_settings=eval_settings,
    )

    merged = merge_chunk_graphs(
        doc_name="note.md",
        source_path="note.md",
        chunk_graphs=(first, second),
        embedder=BagOfWordsEmbedder(),
        settings=GraphSettings(similarity_threshold=TEST_SIMILARITY_THRESHOLD),
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
        embedder=BagOfWordsEmbedder(),
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
    assert any(node.type == "concept" for node in selected.nodes)
    assert any(node.type == "key_passage" for node in selected.nodes)

    rendered = render_selected_subgraph(selected)
    assert "# Selected Summary Graph" in rendered
    assert "Supported by:" in rendered
    assert "## Concepts" in rendered
    assert "## Key Passages" in rendered
    assert "Graph methods preserve claim and evidence relationships." in rendered


def test_select_claim_subgraph_respects_concept_and_passage_limits() -> None:
    graph = build_claim_graph(
        source=document_graph_source(doc_name="note.md", doc_text=DOC),
        prompts=GraphPrompts.load(),
        completer=ClaimCompleter(),
        embedder=BagOfWordsEmbedder(),
        eval_settings=EvalSettings(
            judge_model="judge/test",
            fact_extractor_model="extractor/test",
        ),
    )

    selected = select_claim_subgraph(
        graph,
        settings=GraphSettings(max_claims=2, max_concepts=1, max_key_passages=1),
    )

    assert sum(node.type == "claim" for node in selected.nodes) == 2
    assert sum(node.type == "concept" for node in selected.nodes) == 1
    assert sum(node.type == "key_passage" for node in selected.nodes) == 1


def test_embedding_index_similarity_matches_cosine() -> None:
    index = build_embedding_index(
        ["alpha beta gamma", "delta epsilon"],
        embedder=BagOfWordsEmbedder(),
        model="test/model",
    )

    assert index.similarity("alpha beta gamma", "alpha beta gamma") == pytest.approx(
        1.0
    )
    assert index.similarity("alpha beta gamma", "delta epsilon") == pytest.approx(0.0)
    # A text that was never embedded scores 0.0 instead of raising.
    assert index.similarity("alpha beta gamma", "never embedded") == 0.0


def test_build_embedding_index_dedupes_and_drops_blank() -> None:
    index = build_embedding_index(
        ["alpha", "alpha", "   "],
        embedder=BagOfWordsEmbedder(),
        model="test/model",
    )

    assert set(index.vectors) == {"alpha"}


def test_build_embedding_index_handles_no_texts() -> None:
    index = build_embedding_index([], embedder=BagOfWordsEmbedder(), model="test/model")

    assert index == EmbeddingIndex(vectors={})


def test_claim_score_rewards_grounded_claims() -> None:
    claim = "Graph methods preserve claim and evidence relationships."
    grounded = "Graph methods preserve claim and evidence relationships."
    weak = "Unrelated trivia regarding weather patterns."
    index = build_embedding_index(
        [claim, grounded, weak],
        embedder=BagOfWordsEmbedder(),
        model="test/model",
    )

    assert claim_score(claim, grounded, index=index) > claim_score(
        claim, weak, index=index
    )


def test_concept_and_key_passage_scores_reward_grounding() -> None:
    concept = "Graph methods"
    definition = "Graph methods preserve claim and evidence relationships."
    evidence = "Graph methods preserve claim and evidence relationships."
    weak = "Unrelated trivia regarding weather patterns."
    index = build_embedding_index(
        [concept, definition, evidence, weak],
        embedder=BagOfWordsEmbedder(),
        model="test/model",
    )

    assert concept_score(concept, definition, evidence, index=index) > concept_score(
        concept, weak, weak, index=index
    )
    assert key_passage_score(evidence, definition, index=index) > key_passage_score(
        weak, definition, index=index
    )
