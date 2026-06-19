"""Claim/evidence graph construction for graph-guided summary evals."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from alex.lib.llm import Completer
from alex.lib.prompt_templates import PromptTemplate, load_prompt
from alex.lib.summary_eval import (
    EvalJudgeError,
    EvalSettings,
    FactSection,
    fact_sections,
    parse_json_payload,
)

SOURCE_CLAIM_PROMPT_NAME = "source_claim_extraction"
GRAPH_SUMMARY_PROMPT_NAME = "graph_guided_summary"
DEFAULT_MAX_GRAPH_CLAIMS = 24


@dataclass(frozen=True)
class ClaimEvidenceItem:
    claim: str
    evidence: str


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
    def load(cls) -> GraphPrompts:
        return cls(
            source_claim_extraction=load_prompt(SOURCE_CLAIM_PROMPT_NAME),
            graph_guided_summary=load_prompt(GRAPH_SUMMARY_PROMPT_NAME),
        )


@dataclass(frozen=True)
class GraphSettings:
    max_claims: int = DEFAULT_MAX_GRAPH_CLAIMS
    similarity_threshold: float = 0.28


def build_claim_graph(
    *,
    source: GraphSource,
    prompts: GraphPrompts,
    completer: Completer,
    eval_settings: EvalSettings,
    settings: GraphSettings | None = None,
) -> ClaimGraph:
    graph_settings = settings or GraphSettings()
    source_key = graph_source_key(source)
    source_metadata = graph_source_metadata(source)
    sections = fact_sections(source.text)
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

    for section_index, section in enumerate(sections, 1):
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

        for claim_index, item in enumerate(
            extract_source_claims(
                section=section,
                template=prompts.source_claim_extraction,
                completer=completer,
                settings=eval_settings,
            ),
            1,
        ):
            normalized = slugify(item.claim, limit=72)
            claim_counts[normalized] += 1
            suffix = claim_counts[normalized]
            claim_id = f"claim:{source_key}:{normalized}:{suffix}"
            evidence_id = f"evidence:{source_key}:{section_index}:{claim_index}"
            score = claim_score(item.claim, item.evidence)
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

    edges.extend(
        similar_claim_edges(nodes, threshold=graph_settings.similarity_threshold)
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

    edges.extend(
        similar_claim_edges(nodes, threshold=graph_settings.similarity_threshold)
    )
    return ClaimGraph(doc_name=doc_name, nodes=tuple(nodes), edges=tuple(edges))


def extract_source_claims(
    *,
    section: FactSection,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
) -> tuple[ClaimEvidenceItem, ...]:
    payload = parse_json_payload(
        completer.complete(
            prompt=template.render(
                section_title=section.title,
                section_text=section.text,
            ),
            model=settings.fact_extractor_model,
            max_tokens=settings.extractor_max_tokens,
        ),
        step="Source claim extraction",
    )
    return claim_evidence_items(payload)


def claim_evidence_items(payload: Any) -> tuple[ClaimEvidenceItem, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        raise EvalJudgeError("Expected a JSON object with a 'claims' list.")
    items: list[ClaimEvidenceItem] = []
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
        items.append(ClaimEvidenceItem(claim=claim.strip(), evidence=evidence.strip()))
    return tuple(items)


def select_claim_subgraph(
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

    claims = [node for node in graph.nodes if node.type == "claim"]
    by_section: dict[int, list[GraphNode]] = defaultdict(list)
    for claim in claims:
        if claim.section_index is not None:
            by_section[claim.section_index].append(claim)

    selected_claim_ids: list[str] = []
    for section_index in sorted(by_section):
        ranked = sorted(
            by_section[section_index],
            key=lambda node: (-node.score, node.id),
        )
        if ranked and len(selected_claim_ids) < settings.max_claims:
            selected_claim_ids.append(ranked[0].id)

    remaining = sorted(claims, key=lambda node: (-node.score, node.id))
    for claim in remaining:
        if len(selected_claim_ids) >= settings.max_claims:
            break
        if claim.id not in selected_claim_ids:
            selected_claim_ids.append(claim.id)

    selected_ids = set(selected_claim_ids)

    def add_ancestors(node_id: str) -> None:
        for edge in incoming[node_id]:
            if edge.source in selected_ids:
                continue
            selected_ids.add(edge.source)
            add_ancestors(edge.source)

    for claim_id in selected_claim_ids:
        add_ancestors(claim_id)
        for edge in outgoing[claim_id]:
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


def render_selected_subgraph(graph: ClaimGraph) -> str:
    incoming: dict[str, list[GraphEdge]] = defaultdict(list)
    nodes_by_id = graph.node_map()
    for edge in graph.edges:
        incoming[edge.target].append(edge)

    lines = [
        "# Selected Claim/Evidence Subgraph",
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

    lines.extend(["## Evidence", ""])
    for evidence in [node for node in graph.nodes if node.type == "evidence"]:
        section_label = evidence.metadata.get("section", "Unknown section")
        lines.extend(
            [
                f"### {evidence.id}",
                "",
                f"- Section: {section_label}",
                f"- Supports: {supported_claims(evidence.id, graph.edges)}",
                "",
                evidence.text,
                "",
            ]
        )

    lines.extend(["## Sections", ""])
    for section_node in [node for node in graph.nodes if node.type == "section"]:
        claim_count = sum(
            1
            for edge in graph.edges
            if edge.source == section_node.id
            and nodes_by_id[edge.target].type == "evidence"
        )
        lines.extend(
            [
                f"- `{section_node.id}` {section_node.label} "
                f"({claim_count} selected evidence nodes)",
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


def write_graph_json(path: Path, graph: ClaimGraph) -> None:
    path.write_text(json.dumps(graph_to_dict(graph), indent=2) + "\n", encoding="utf-8")


def supported_claims(evidence_id: str, edges: Sequence[GraphEdge]) -> str:
    claim_ids = [edge.target for edge in edges if edge.source == evidence_id]
    return ", ".join(f"`{claim_id}`" for claim_id in claim_ids) or "none"


def similar_claim_edges(
    nodes: Sequence[GraphNode],
    *,
    threshold: float = 0.28,
) -> tuple[GraphEdge, ...]:
    claim_nodes = [node for node in nodes if node.type == "claim"]
    edges: list[GraphEdge] = []
    for index, left in enumerate(claim_nodes):
        for right in claim_nodes[index + 1 :]:
            score = similarity(left.text, right.text)
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


def claim_score(claim: str, evidence: str) -> float:
    claim_terms = terms(claim)
    evidence_terms = terms(evidence)
    overlap = len(claim_terms & evidence_terms)
    specificity = min(1.0, len(claim_terms) / 18)
    evidence_density = min(1.0, len(evidence_terms) / 28)
    score = overlap / max(math.sqrt(len(claim_terms) + 1), 1)
    return round(score + specificity + evidence_density, 4)


def similarity(left: str, right: str) -> float:
    left_terms = terms(left)
    right_terms = terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / math.sqrt(len(left_terms) * len(right_terms))


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
