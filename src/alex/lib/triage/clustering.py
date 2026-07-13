"""Embed, cluster, label, and batch the triage inventory."""

from __future__ import annotations

import json
from pathlib import Path

from alex.lib.llm import Completer, Embedder
from alex.lib.prompt_templates import load_prompt
from alex.lib.triage.models import Batch, Cluster, ClusterMap, Inventory, NoteEvidence
from alex.lib.vectors import cosine_similarity, mean_vector

_MAX_LABEL_TITLES = 15
_LABEL_MAX_TOKENS = 50
_MISC_LABEL = "misc"


def embedding_text(note: NoteEvidence) -> str:
    parts = [note.title, " ".join(note.tags), note.snippet]
    return "\n".join(part for part in parts if part)


def load_embedding_cache(path: Path) -> dict[str, tuple[float, ...]]:
    return {note: vector for note, (_, vector) in _cache_rows(path).items()}


def _cache_rows(path: Path) -> dict[str, tuple[float, tuple[float, ...]]]:
    if not path.exists():
        return {}
    rows: dict[str, tuple[float, tuple[float, ...]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            note_path = row["path"]
            mtime = float(row["mtime"])
            vector = tuple(float(value) for value in row["vector"])
        except (KeyError, TypeError, ValueError):
            continue
        if isinstance(note_path, str):
            rows[note_path] = (mtime, vector)
    return rows


def embed_notes(
    inventory: Inventory,
    embedder: Embedder,
    model: str,
    cache_path: Path,
) -> dict[str, tuple[float, ...]]:
    cached = _cache_rows(cache_path)
    vectors: dict[str, tuple[float, ...]] = {}
    misses: list[NoteEvidence] = []
    for note in inventory.notes:
        row = cached.get(note.path)
        if row is not None and row[0] == note.mtime:
            vectors[note.path] = row[1]
        else:
            misses.append(note)
    if not misses:
        return vectors
    fresh = embedder.embed(texts=[embedding_text(note) for note in misses], model=model)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a", encoding="utf-8") as handle:
        for note, vector in zip(misses, fresh, strict=True):
            vectors[note.path] = vector
            row_out = {"path": note.path, "mtime": note.mtime, "vector": list(vector)}
            handle.write(json.dumps(row_out) + "\n")
    return vectors


def cluster_paths(
    vectors: dict[str, tuple[float, ...]], threshold: float
) -> list[list[str]]:
    clusters: list[list[str]] = []
    members: list[list[tuple[float, ...]]] = []
    centroids: list[tuple[float, ...]] = []
    for path in sorted(vectors):
        vector = vectors[path]
        placed = False
        for index, centroid in enumerate(centroids):
            if cosine_similarity(vector, centroid) >= threshold:
                clusters[index].append(path)
                members[index].append(vector)
                centroids[index] = mean_vector(members[index])
                placed = True
                break
        if not placed:
            clusters.append([path])
            members.append([vector])
            centroids.append(vector)
    clusters.sort(key=lambda cluster: (-len(cluster), cluster[0]))
    return clusters


def label_clusters(
    clusters: list[list[str]],
    inventory: Inventory,
    completer: Completer,
    model: str,
) -> list[Cluster]:
    titles = {note.path: note.title for note in inventory.notes}
    template = load_prompt("triage_cluster_label")
    labeled: list[Cluster] = []
    for index, paths in enumerate(clusters):
        if len(paths) == 1:
            label = _MISC_LABEL
        else:
            listed = "\n".join(
                titles.get(path, path) for path in paths[:_MAX_LABEL_TITLES]
            )
            raw = completer.complete(
                prompt=template.render(titles=listed),
                model=model,
                max_tokens=_LABEL_MAX_TOKENS,
            )
            lines = raw.strip().splitlines()
            label = lines[0].strip() if lines else _MISC_LABEL
        labeled.append(
            Cluster(cluster_id=index + 1, label=label, note_paths=list(paths))
        )
    return labeled


def slice_batches(clusters: list[Cluster], batch_size: int) -> list[Batch]:
    ordered: list[tuple[str, str]] = []
    for cluster in clusters:
        if cluster.label != _MISC_LABEL:
            ordered.extend((path, cluster.label) for path in cluster.note_paths)
    for cluster in clusters:
        if cluster.label == _MISC_LABEL:
            ordered.extend((path, _MISC_LABEL) for path in cluster.note_paths)
    batches: list[Batch] = []
    for start in range(0, len(ordered), batch_size):
        chunk = ordered[start : start + batch_size]
        batches.append(
            Batch(
                batch_id=start // batch_size + 1,
                note_paths=[path for path, _ in chunk],
                label=_batch_label(chunk),
            )
        )
    return batches


def _batch_label(chunk: list[tuple[str, str]]) -> str:
    """Label of the non-misc cluster contributing the most notes; else misc.

    Ties break by first appearance in the batch (dict preserves insertion
    order and max returns the first maximum).
    """
    counts: dict[str, int] = {}
    for _, label in chunk:
        if label != _MISC_LABEL:
            counts[label] = counts.get(label, 0) + 1
    if not counts:
        return _MISC_LABEL
    return max(counts, key=lambda label: counts[label])


def build_cluster_map(
    inventory: Inventory,
    embedder: Embedder,
    completer: Completer,
    *,
    embed_model: str,
    label_model: str,
    threshold: float,
    batch_size: int,
    cache_path: Path,
    generated: str,
) -> ClusterMap:
    vectors = embed_notes(inventory, embedder, embed_model, cache_path)
    clusters = cluster_paths(vectors, threshold)
    labeled = label_clusters(clusters, inventory, completer, label_model)
    batches = slice_batches(labeled, batch_size)
    return ClusterMap(generated=generated, clusters=labeled, batches=batches)
