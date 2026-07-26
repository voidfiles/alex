"""Claim/evidence graph construction for graph-guided summary evals."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Literal

from alex.lib.llm import (
    Completer,
    Embedder,
    resolve_claim_similarity_threshold,
    resolve_embedding_model,
    resolve_source_claims_per_section,
)
from alex.lib.prompt_templates import PromptTemplate, load_prompt
from alex.lib.summary_eval import (
    EvalJudgeError,
    EvalSettings,
    FactSection,
    fact_sections,
    parse_json_payload,
)
from alex.lib.vectors import cosine_similarity

SOURCE_CLAIM_PROMPT_NAME = "source_claim_extraction"
GRAPH_SUMMARY_PROMPT_NAME = "graph_guided_summary"
DEFAULT_MAX_GRAPH_CLAIMS = 24


@dataclass(frozen=True)
class ClaimEvidenceItem:
    claim: str
    evidence: str


@dataclass(frozen=True)
class ConceptItem:
    concept: str
    definition: str
    evidence: str


@dataclass(frozen=True)
class KeyPassageItem:
    passage: str
    why_it_matters: str


@dataclass(frozen=True)
class SourceGraphItems:
    claims: tuple[ClaimEvidenceItem, ...] = ()
    concepts: tuple[ConceptItem, ...] = ()
    key_passages: tuple[KeyPassageItem, ...] = ()


@dataclass(frozen=True)
class GraphSource:
    id: str
    type: Literal["document", "chunk"]
    label: str
    text: str
    source_path: str
    chunk_index: int | None = None
    chunk_filename: str | None = None


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: str
    label: str
    source: str
    text: str = ""
    section_index: int | None = None
    score: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    type: str
    weight: float = 1.0
    evidence: str = ""


@dataclass(frozen=True)
class ClaimGraph:
    doc_name: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def node_map(self) -> dict[str, GraphNode]:
        return {node.id: node for node in self.nodes}


@dataclass(frozen=True)
class GraphPrompts:
    source_claim_extraction: PromptTemplate
    graph_guided_summary: PromptTemplate

    @classmethod
    def load(
        cls,
        overrides: Mapping[str, str] | None = None,
        *,
        root: Traversable | None = None,
    ) -> GraphPrompts:
        versions = dict(overrides or {})
        return cls(
            source_claim_extraction=load_prompt(
                SOURCE_CLAIM_PROMPT_NAME,
                version=versions.get(SOURCE_CLAIM_PROMPT_NAME),
                root=root,
            ),
            graph_guided_summary=load_prompt(
                GRAPH_SUMMARY_PROMPT_NAME,
                version=versions.get(GRAPH_SUMMARY_PROMPT_NAME),
                root=root,
            ),
        )


@dataclass(frozen=True)
class GraphSettings:
    max_claims: int = DEFAULT_MAX_GRAPH_CLAIMS
    max_concepts: int | None = None
    max_key_passages: int | None = None
    similarity_threshold: float = field(
        default_factory=resolve_claim_similarity_threshold
    )
    embedding_model: str = field(default_factory=resolve_embedding_model)
    source_claims_per_section: int = field(
        default_factory=resolve_source_claims_per_section
    )


@dataclass(frozen=True)
class EmbeddingIndex:
    """Cosine similarity over a fixed set of pre-embedded texts.

    Embed every text once up front, then answer claim/claim and claim/evidence
    similarity by lookup. Texts not in the index score 0.0 (they were empty or
    never embedded), which keeps callers free of None-handling.
    """

    vectors: dict[str, tuple[float, ...]]

    def similarity(self, left: str, right: str) -> float:
        a = self.vectors.get(left)
        b = self.vectors.get(right)
        if a is None or b is None:
            return 0.0
        return cosine_similarity(a, b)


def build_embedding_index(
    texts: Sequence[str],
    *,
    embedder: Embedder,
    model: str,
) -> EmbeddingIndex:
    unique = tuple(dict.fromkeys(text for text in texts if text.strip()))
    vectors = embedder.embed(texts=unique, model=model) if unique else ()
    return EmbeddingIndex(vectors=dict(zip(unique, vectors, strict=True)))


def build_claim_graph(
    *,
    source: GraphSource,
    prompts: GraphPrompts,
    completer: Completer,
    embedder: Embedder,
    eval_settings: EvalSettings,
    settings: GraphSettings | None = None,
) -> ClaimGraph:
    graph_settings = settings or GraphSettings()
    source_key = graph_source_key(source)
    source_metadata = graph_source_metadata(source)
    sections = fact_sections(source.text)

    # Extract every section's summary items first so all related texts can be
    # embedded in one batched call before any scoring happens.
    extracted: list[tuple[int, FactSection, SourceGraphItems]] = []
    for section_index, section in enumerate(sections, 1):
        items = extract_source_claims(
            section=section,
            template=prompts.source_claim_extraction,
            completer=completer,
            settings=eval_settings,
            max_claims=graph_settings.source_claims_per_section,
        )
        extracted.append((section_index, section, items))

    graph_item_texts = [
        text for _, _, items in extracted for text in source_graph_item_texts(items)
    ]
    index = build_embedding_index(
        graph_item_texts,
        embedder=embedder,
        model=graph_settings.embedding_model,
    )

    nodes: list[GraphNode] = [
        GraphNode(
            id=source.id,
            type=source.type,
            label=source.label,
            source=source.source_path,
            text="",
            metadata=source_metadata,
        )
    ]
    edges: list[GraphEdge] = []
    claim_counts: Counter[str] = Counter()
    concept_counts: Counter[str] = Counter()

    for section_index, section, items in extracted:
        section_id = f"section:{source_key}:{section_index}"
        section_node = GraphNode(
            id=section_id,
            type="section",
            label=section.title,
            source=source.source_path,
            text=trim_text(section.text),
            section_index=section_index,
            metadata=source_metadata,
        )
        nodes.append(section_node)
        edges.append(GraphEdge(source=source.id, target=section_id, type="contains"))

        section_scores: list[float] = []

        for claim_index, item in enumerate(items.claims, 1):
            normalized = slugify(item.claim, limit=72)
            claim_counts[normalized] += 1
            suffix = claim_counts[normalized]
            claim_id = f"claim:{source_key}:{normalized}:{suffix}"
            evidence_id = f"evidence:{source_key}:{section_index}:{claim_index}"
            score = claim_score(item.claim, item.evidence, index=index)
            section_scores.append(score)
            metadata = {**source_metadata, "section": section.title}
            nodes.append(
                GraphNode(
                    id=evidence_id,
                    type="evidence",
                    label=f"{section.title} evidence {claim_index}",
                    source=source.source_path,
                    text=item.evidence,
                    section_index=section_index,
                    score=score,
                    metadata=metadata,
                )
            )
            nodes.append(
                GraphNode(
                    id=claim_id,
                    type="claim",
                    label=trim_text(item.claim, limit=120),
                    source=source.source_path,
                    text=item.claim,
                    section_index=section_index,
                    score=score,
                    metadata={**metadata, "evidence_id": evidence_id},
                )
            )
            edges.append(
                GraphEdge(source=section_id, target=evidence_id, type="contains")
            )
            edges.append(
                GraphEdge(
                    source=evidence_id,
                    target=claim_id,
                    type="supports",
                    evidence=item.evidence,
                )
            )

        for concept_item in items.concepts:
            normalized = slugify(concept_item.concept, limit=72)
            concept_counts[normalized] += 1
            suffix = concept_counts[normalized]
            concept_id = f"concept:{source_key}:{normalized}:{suffix}"
            score = concept_score(
                concept_item.concept,
                concept_item.definition,
                concept_item.evidence,
                index=index,
            )
            section_scores.append(score)
            metadata = {
                **source_metadata,
                "section": section.title,
                "evidence": concept_item.evidence,
            }
            nodes.append(
                GraphNode(
                    id=concept_id,
                    type="concept",
                    label=trim_text(concept_item.concept, limit=120),
                    source=source.source_path,
                    text=concept_item.definition,
                    section_index=section_index,
                    score=score,
                    metadata=metadata,
                )
            )
            edges.append(
                GraphEdge(source=section_id, target=concept_id, type="defines")
            )

        for passage_index, passage_item in enumerate(items.key_passages, 1):
            passage_id = f"key_passage:{source_key}:{section_index}:{passage_index}"
            score = key_passage_score(
                passage_item.passage,
                passage_item.why_it_matters,
                index=index,
            )
            section_scores.append(score)
            metadata = {
                **source_metadata,
                "section": section.title,
                "why_it_matters": passage_item.why_it_matters,
            }
            nodes.append(
                GraphNode(
                    id=passage_id,
                    type="key_passage",
                    label=f"{section.title} key passage {passage_index}",
                    source=source.source_path,
                    text=passage_item.passage,
                    section_index=section_index,
                    score=score,
                    metadata=metadata,
                )
            )
            edges.append(
                GraphEdge(source=section_id, target=passage_id, type="highlights")
            )

        if section_scores:
            nodes[nodes.index(section_node)] = GraphNode(
                id=section_node.id,
                type=section_node.type,
                label=section_node.label,
                source=section_node.source,
                text=section_node.text,
                section_index=section_node.section_index,
                score=max(section_scores),
                metadata=section_node.metadata,
            )

    edges.extend(
        similar_claim_edges(
            nodes, index=index, threshold=graph_settings.similarity_threshold
        )
    )
    return ClaimGraph(doc_name=source.label, nodes=tuple(nodes), edges=tuple(edges))


def document_graph_source(*, doc_name: str, doc_text: str) -> GraphSource:
    return GraphSource(
        id=f"doc:{slugify(doc_name)}",
        type="document",
        label=doc_name,
        text=doc_text,
        source_path=doc_name,
    )


def chunk_graph_source(
    *,
    doc_name: str,
    chunk_index: int,
    chunk_path: Path,
    chunk_text: str,
) -> GraphSource:
    return GraphSource(
        id=f"chunk:{slugify(doc_name)}:{chunk_index}",
        type="chunk",
        label=chunk_path.name,
        text=chunk_text,
        source_path=f"chunks/{chunk_path.name}",
        chunk_index=chunk_index,
        chunk_filename=chunk_path.name,
    )


def graph_source_key(source: GraphSource) -> str:
    if source.type == "chunk" and source.chunk_index is not None:
        return source.id.removeprefix("chunk:")
    if source.type == "document":
        return source.id.removeprefix("doc:")
    return slugify(source.label)


def graph_source_metadata(source: GraphSource) -> dict[str, str]:
    metadata = {"source_path": source.source_path}
    if source.chunk_index is not None:
        metadata["chunk_index"] = str(source.chunk_index)
    if source.chunk_filename is not None:
        metadata["chunk_filename"] = source.chunk_filename
    return metadata


def merge_chunk_graphs(
    *,
    doc_name: str,
    source_path: str,
    chunk_graphs: Sequence[ClaimGraph],
    embedder: Embedder,
    settings: GraphSettings | None = None,
) -> ClaimGraph:
    graph_settings = settings or GraphSettings()
    document_id = f"doc:{slugify(doc_name)}"
    nodes: list[GraphNode] = [
        GraphNode(
            id=document_id,
            type="document",
            label=doc_name,
            source=source_path,
            metadata={"source_path": source_path},
        )
    ]
    edges: list[GraphEdge] = []
    seen_node_ids = {document_id}

    for graph in chunk_graphs:
        chunk_nodes = [node for node in graph.nodes if node.type == "chunk"]
        if len(chunk_nodes) != 1:
            raise ValueError(f"Expected exactly one chunk root in {graph.doc_name}.")
        chunk_node = chunk_nodes[0]
        edges.append(
            GraphEdge(source=document_id, target=chunk_node.id, type="contains")
        )
        for node in graph.nodes:
            if node.id in seen_node_ids:
                raise ValueError(f"Duplicate graph node id while merging: {node.id}")
            seen_node_ids.add(node.id)
            nodes.append(node)
        edges.extend(edge for edge in graph.edges if edge.type != "similar_to")

    index = build_embedding_index(
        [node.text for node in nodes if node.type == "claim"],
        embedder=embedder,
        model=graph_settings.embedding_model,
    )
    edges.extend(
        similar_claim_edges(
            nodes, index=index, threshold=graph_settings.similarity_threshold
        )
    )
    return ClaimGraph(doc_name=doc_name, nodes=tuple(nodes), edges=tuple(edges))


def extract_source_claims(
    *,
    section: FactSection,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
    max_claims: int,
) -> SourceGraphItems:
    payload = parse_json_payload(
        completer.complete(
            prompt=template.render(
                section_title=section.title,
                section_text=section.text,
                max_claims=str(max_claims),
            ),
            model=settings.fact_extractor_model,
            max_tokens=settings.extractor_max_tokens,
        ),
        step="Source claim extraction",
    )
    return source_graph_items(payload)


def claim_evidence_items(payload: Any) -> tuple[ClaimEvidenceItem, ...]:
    return source_graph_items(payload).claims


def source_graph_items(payload: Any) -> SourceGraphItems:
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        raise EvalJudgeError("Expected a JSON object with a 'claims' list.")
    claims: list[ClaimEvidenceItem] = []
    for item in payload["claims"]:
        if not isinstance(item, dict):
            raise EvalJudgeError("Each source claim must be a JSON object.")
        claim = item.get("claim")
        evidence = item.get("evidence")
        if not isinstance(claim, str) or not claim.strip():
            raise EvalJudgeError(
                "Source claim field 'claim' must be a non-empty string."
            )
        if not isinstance(evidence, str) or not evidence.strip():
            raise EvalJudgeError(
                "Source claim field 'evidence' must be a non-empty string."
            )
        claims.append(ClaimEvidenceItem(claim=claim.strip(), evidence=evidence.strip()))

    concepts: list[ConceptItem] = []
    for item in payload.get("concepts", []):
        if not isinstance(item, dict):
            raise EvalJudgeError("Each source concept must be a JSON object.")
        concept = item.get("concept")
        definition = item.get("definition")
        evidence = item.get("evidence")
        if not isinstance(concept, str) or not concept.strip():
            raise EvalJudgeError(
                "Source concept field 'concept' must be a non-empty string."
            )
        if not isinstance(definition, str) or not definition.strip():
            raise EvalJudgeError(
                "Source concept field 'definition' must be a non-empty string."
            )
        if not isinstance(evidence, str) or not evidence.strip():
            raise EvalJudgeError(
                "Source concept field 'evidence' must be a non-empty string."
            )
        concepts.append(
            ConceptItem(
                concept=concept.strip(),
                definition=definition.strip(),
                evidence=evidence.strip(),
            )
        )

    key_passages: list[KeyPassageItem] = []
    for item in payload.get("key_passages", []):
        if not isinstance(item, dict):
            raise EvalJudgeError("Each key passage must be a JSON object.")
        passage = item.get("passage")
        why_it_matters = item.get("why_it_matters")
        if not isinstance(passage, str) or not passage.strip():
            raise EvalJudgeError(
                "Key passage field 'passage' must be a non-empty string."
            )
        if not isinstance(why_it_matters, str) or not why_it_matters.strip():
            raise EvalJudgeError(
                "Key passage field 'why_it_matters' must be a non-empty string."
            )
        key_passages.append(
            KeyPassageItem(
                passage=passage.strip(),
                why_it_matters=why_it_matters.strip(),
            )
        )

    return SourceGraphItems(
        claims=tuple(claims),
        concepts=tuple(concepts),
        key_passages=tuple(key_passages),
    )


def source_graph_item_texts(items: SourceGraphItems) -> tuple[str, ...]:
    return (
        *(text for item in items.claims for text in (item.claim, item.evidence)),
        *(
            text
            for item in items.concepts
            for text in (item.concept, item.definition, item.evidence)
        ),
        *(
            text
            for item in items.key_passages
            for text in (item.passage, item.why_it_matters)
        ),
    )


def select_claim_subgraph(
    graph: ClaimGraph,
    *,
    settings: GraphSettings,
) -> ClaimGraph:
    return select_summary_subgraph(graph, settings=settings)


def select_summary_subgraph(
    graph: ClaimGraph,
    *,
    settings: GraphSettings,
) -> ClaimGraph:
    if settings.max_claims <= 0:
        raise ValueError("max_claims must be positive.")

    nodes_by_id = graph.node_map()
    incoming: dict[str, list[GraphEdge]] = defaultdict(list)
    outgoing: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in graph.edges:
        incoming[edge.target].append(edge)
        outgoing[edge.source].append(edge)

    selected_item_ids = [
        *select_ranked_items_by_type(
            graph.nodes,
            node_type="claim",
            limit=settings.max_claims,
        ),
        *select_ranked_items_by_type(
            graph.nodes,
            node_type="concept",
            limit=resolved_graph_item_limit(settings.max_concepts, settings.max_claims),
        ),
        *select_ranked_items_by_type(
            graph.nodes,
            node_type="key_passage",
            limit=resolved_graph_item_limit(
                settings.max_key_passages,
                settings.max_claims,
            ),
        ),
    ]

    selected_ids = set(selected_item_ids)

    def add_ancestors(node_id: str) -> None:
        for edge in incoming[node_id]:
            if edge.source in selected_ids:
                continue
            selected_ids.add(edge.source)
            add_ancestors(edge.source)

    for item_id in selected_item_ids:
        add_ancestors(item_id)
        for edge in outgoing[item_id]:
            selected_ids.add(edge.target)

    selected_nodes = tuple(
        sorted(
            (node for node_id, node in nodes_by_id.items() if node_id in selected_ids),
            key=lambda node: (node.type, node.section_index or 0, -node.score, node.id),
        )
    )
    selected_edges = tuple(
        edge
        for edge in graph.edges
        if edge.source in selected_ids and edge.target in selected_ids
    )
    return ClaimGraph(
        doc_name=graph.doc_name,
        nodes=selected_nodes,
        edges=selected_edges,
    )


def resolved_graph_item_limit(configured: int | None, max_claims: int) -> int:
    if configured is not None:
        if configured < 0:
            raise ValueError("graph item limits must be non-negative.")
        return configured
    return max(1, max_claims // 2)


def select_ranked_items_by_type(
    nodes: Sequence[GraphNode],
    *,
    node_type: str,
    limit: int,
) -> list[str]:
    if limit <= 0:
        return []

    items = [node for node in nodes if node.type == node_type]
    by_section: dict[int, list[GraphNode]] = defaultdict(list)
    for item in items:
        if item.section_index is not None:
            by_section[item.section_index].append(item)

    selected_ids: list[str] = []
    for section_index in sorted(by_section):
        ranked = sorted(
            by_section[section_index],
            key=lambda node: (-node.score, node.id),
        )
        if ranked and len(selected_ids) < limit:
            selected_ids.append(ranked[0].id)

    remaining = sorted(items, key=lambda node: (-node.score, node.id))
    for item in remaining:
        if len(selected_ids) >= limit:
            break
        if item.id not in selected_ids:
            selected_ids.append(item.id)
    return selected_ids


def render_selected_subgraph(graph: ClaimGraph) -> str:
    incoming: dict[str, list[GraphEdge]] = defaultdict(list)
    nodes_by_id = graph.node_map()
    for edge in graph.edges:
        incoming[edge.target].append(edge)

    lines = [
        "# Selected Summary Graph",
        "",
        f"Document: `{graph.doc_name}`",
        "",
        "## Claims",
        "",
    ]
    for claim in [node for node in graph.nodes if node.type == "claim"]:
        support_edges = [edge for edge in incoming[claim.id] if edge.type == "supports"]
        evidence_ids = [edge.source for edge in support_edges]
        section_label = claim.metadata.get("section", "Unknown section")
        lines.extend(
            [
                f"### {claim.id}",
                "",
                f"- Score: {claim.score:.4f}",
                f"- Section: {section_label}",
                f"- Claim: {claim.text}",
                f"- Supported by: {', '.join(f'`{item}`' for item in evidence_ids)}",
                "",
            ]
        )

    lines.extend(["## Concepts", ""])
    for concept in [node for node in graph.nodes if node.type == "concept"]:
        section_label = concept.metadata.get("section", "Unknown section")
        evidence = concept.metadata.get("evidence", "")
        lines.extend(
            [
                f"### {concept.id}",
                "",
                f"- Score: {concept.score:.4f}",
                f"- Section: {section_label}",
                f"- Concept: {concept.label}",
                f"- Definition: {concept.text}",
                f"- Source evidence: {evidence}",
                "",
            ]
        )

    lines.extend(["## Key Passages", ""])
    for passage in [node for node in graph.nodes if node.type == "key_passage"]:
        section_label = passage.metadata.get("section", "Unknown section")
        rationale = passage.metadata.get("why_it_matters", "")
        lines.extend(
            [
                f"### {passage.id}",
                "",
                f"- Score: {passage.score:.4f}",
                f"- Section: {section_label}",
                f"- Why it matters: {rationale}",
                "",
                passage.text,
                "",
            ]
        )

    lines.extend(["## Evidence", ""])
    for evidence_node in [node for node in graph.nodes if node.type == "evidence"]:
        section_label = evidence_node.metadata.get("section", "Unknown section")
        lines.extend(
            [
                f"### {evidence_node.id}",
                "",
                f"- Section: {section_label}",
                f"- Supports: {supported_claims(evidence_node.id, graph.edges)}",
                "",
                evidence_node.text,
                "",
            ]
        )

    lines.extend(["## Sections", ""])
    for section_node in [node for node in graph.nodes if node.type == "section"]:
        selected_child_count = sum(
            1
            for edge in graph.edges
            if edge.source == section_node.id
            and nodes_by_id[edge.target].type in {"evidence", "concept", "key_passage"}
        )
        lines.extend(
            [
                f"- `{section_node.id}` {section_node.label} "
                f"(score {section_node.score:.4f}; "
                f"{selected_child_count} selected summary nodes)",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def graph_summary_prompt(
    *,
    doc_name: str,
    selected_subgraph_markdown: str,
    template: PromptTemplate,
) -> str:
    return template.render(
        document_name=doc_name,
        selected_subgraph=selected_subgraph_markdown,
    )


def graph_to_dict(graph: ClaimGraph) -> dict[str, Any]:
    return {
        "doc_name": graph.doc_name,
        "nodes": [asdict(node) for node in graph.nodes],
        "edges": [asdict(edge) for edge in graph.edges],
    }


def graph_from_dict(payload: Mapping[str, Any]) -> ClaimGraph:
    """Rebuild a ClaimGraph from graph_to_dict output. Raises on bad shapes."""
    nodes = tuple(
        GraphNode(
            id=str(node["id"]),
            type=str(node["type"]),
            label=str(node["label"]),
            source=str(node["source"]),
            text=str(node.get("text", "")),
            section_index=(
                int(node["section_index"])
                if node.get("section_index") is not None
                else None
            ),
            score=float(node.get("score", 0.0)),
            metadata={
                str(key): str(value)
                for key, value in dict(node.get("metadata") or {}).items()
            },
        )
        for node in payload["nodes"]
    )
    edges = tuple(
        GraphEdge(
            source=str(edge["source"]),
            target=str(edge["target"]),
            type=str(edge["type"]),
            weight=float(edge.get("weight", 1.0)),
            evidence=str(edge.get("evidence", "")),
        )
        for edge in payload["edges"]
    )
    return ClaimGraph(doc_name=str(payload["doc_name"]), nodes=nodes, edges=edges)


def write_graph_json(path: Path, graph: ClaimGraph) -> None:
    path.write_text(json.dumps(graph_to_dict(graph), indent=2) + "\n", encoding="utf-8")


def supported_claims(evidence_id: str, edges: Sequence[GraphEdge]) -> str:
    claim_ids = [edge.target for edge in edges if edge.source == evidence_id]
    return ", ".join(f"`{claim_id}`" for claim_id in claim_ids) or "none"


def similar_claim_edges(
    nodes: Sequence[GraphNode],
    *,
    index: EmbeddingIndex,
    threshold: float,
) -> tuple[GraphEdge, ...]:
    claim_nodes = [node for node in nodes if node.type == "claim"]
    edges: list[GraphEdge] = []
    for position, left in enumerate(claim_nodes):
        for right in claim_nodes[position + 1 :]:
            score = index.similarity(left.text, right.text)
            if score >= threshold:
                edges.append(
                    GraphEdge(
                        source=left.id,
                        target=right.id,
                        type="similar_to",
                        weight=round(score, 3),
                    )
                )
    return tuple(edges)


def claim_score(claim: str, evidence: str, *, index: EmbeddingIndex) -> float:
    claim_terms = terms(claim)
    evidence_terms = terms(evidence)
    grounding = index.similarity(claim, evidence)
    specificity = min(1.0, len(claim_terms) / 18)
    evidence_density = min(1.0, len(evidence_terms) / 28)
    return round(grounding + specificity + evidence_density, 4)


def concept_score(
    concept: str,
    definition: str,
    evidence: str,
    *,
    index: EmbeddingIndex,
) -> float:
    definition_terms = terms(definition)
    evidence_terms = terms(evidence)
    grounding = max(
        index.similarity(concept, definition),
        index.similarity(definition, evidence),
    )
    specificity = min(1.0, len(definition_terms) / 18)
    evidence_density = min(1.0, len(evidence_terms) / 28)
    return round(grounding + specificity + evidence_density, 4)


def key_passage_score(
    passage: str,
    why_it_matters: str,
    *,
    index: EmbeddingIndex,
) -> float:
    passage_terms = terms(passage)
    rationale_terms = terms(why_it_matters)
    grounding = index.similarity(passage, why_it_matters)
    specificity = min(1.0, len(rationale_terms) / 18)
    quote_density = min(1.0, len(passage_terms) / 42)
    return round(grounding + specificity + quote_density, 4)


def terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "against",
        "because",
        "before",
        "between",
        "could",
        "from",
        "have",
        "into",
        "more",
        "most",
        "that",
        "their",
        "there",
        "these",
        "this",
        "through",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
    }
    words = re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
    return {word for word in words if word not in stopwords}


def slugify(value: str, *, limit: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:limit].strip("-") or "item"


def trim_text(text: str, *, limit: int = 600) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."
