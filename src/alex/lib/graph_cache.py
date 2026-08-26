"""Disk cache for chunk claim graphs and the merged document graph.

Off by default; enable by pointing ALEX_GRAPH_CACHE_DIR at a directory. The
cache key covers everything that feeds graph CONSTRUCTION: the chunk texts
(and filenames), the document name, the source_claim_extraction prompt
version, the extraction model and its max-token budget, the claims-per-section
cap, and the embedding model plus similarity threshold that produce scores and
similar_to edges.

The selection caps (graph_max_claims, chunk_graph_max_claims) are deliberately
NOT in the key: they only feed select_claim_subgraph, which is deterministic
and re-derived from the cached full graphs on every load, so changing a cap
still takes effect on a cache hit.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from alex.lib.claim_graph import ClaimGraph, graph_from_dict, graph_to_dict

GRAPH_CACHE_FORMAT = 1


@dataclass(frozen=True)
class CachedChunkGraph:
    chunk_filename: str
    graph: ClaimGraph


@dataclass(frozen=True)
class CachedDocumentGraphs:
    document_graph: ClaimGraph
    chunk_graphs: tuple[CachedChunkGraph, ...]


def graph_cache_key(
    *,
    doc_name: str,
    chunks: Sequence[tuple[str, str]],
    extraction_prompt_version: str,
    extraction_model: str,
    source_claims_per_section: int,
    extractor_max_tokens: int,
    embedding_model: str,
    similarity_threshold: float,
) -> str:
    payload = json.dumps(
        {
            "format": GRAPH_CACHE_FORMAT,
            "doc_name": doc_name,
            "chunks": [[name, text] for name, text in chunks],
            "extraction_prompt_version": extraction_prompt_version,
            "extraction_model": extraction_model,
            "source_claims_per_section": source_claims_per_section,
            "extractor_max_tokens": extractor_max_tokens,
            "embedding_model": embedding_model,
            "similarity_threshold": similarity_threshold,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def graph_cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def load_graph_cache(*, cache_dir: Path, key: str) -> CachedDocumentGraphs | None:
    """Return cached graphs, or None when absent or corrupt (rebuild)."""
    path = graph_cache_path(cache_dir, key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cached = CachedDocumentGraphs(
            document_graph=graph_from_dict(payload["document_graph"]),
            chunk_graphs=tuple(
                CachedChunkGraph(
                    chunk_filename=str(entry["chunk_filename"]),
                    graph=graph_from_dict(entry["graph"]),
                )
                for entry in payload["chunk_graphs"]
            ),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    print(f"graph cache hit: {path}", file=sys.stderr)
    return cached


def store_graph_cache(
    *,
    cache_dir: Path,
    key: str,
    graphs: CachedDocumentGraphs,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = graph_cache_path(cache_dir, key)
    payload = {
        "format": GRAPH_CACHE_FORMAT,
        "document_graph": graph_to_dict(graphs.document_graph),
        "chunk_graphs": [
            {
                "chunk_filename": entry.chunk_filename,
                "graph": graph_to_dict(entry.graph),
            }
            for entry in graphs.chunk_graphs
        ],
    }
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)
    print(f"graph cache wrote: {path}", file=sys.stderr)
    return path
