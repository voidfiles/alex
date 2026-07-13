import json
from collections.abc import Sequence
from pathlib import Path

from alex.lib.triage.clustering import (
    build_cluster_map,
    cluster_paths,
    embed_notes,
    embedding_text,
    label_clusters,
    load_embedding_cache,
    slice_batches,
)
from alex.lib.triage.models import Batch, Cluster, Inventory, NoteEvidence
from helpers import BagOfWordsEmbedder


class RecordingEmbedder:
    """Wraps the bag-of-words fake and records every batch it embeds."""

    def __init__(self) -> None:
        self.inner = BagOfWordsEmbedder()
        self.batches: list[list[str]] = []

    def embed(
        self, *, texts: Sequence[str], model: str
    ) -> tuple[tuple[float, ...], ...]:
        self.batches.append(list(texts))
        return self.inner.embed(texts=texts, model=model)


def make_note(
    path: str, title: str, *, snippet: str = "", mtime: float = 1.0
) -> NoteEvidence:
    return NoteEvidence(
        path=path, title=title, population="root", snippet=snippet, mtime=mtime
    )


def test_embedding_text_joins_title_tags_and_snippet() -> None:
    note = NoteEvidence(
        path="note.md",
        title="Rust ownership",
        population="root",
        tags=["rust", "memory"],
        snippet="the borrow checker enforces ownership",
    )

    text = embedding_text(note)

    assert "Rust ownership" in text
    assert "rust memory" in text
    assert "the borrow checker enforces ownership" in text
    assert embedding_text(make_note("bare.md", "Just a title")) == "Just a title"


def test_load_embedding_cache_takes_last_row_per_path_and_skips_garbage(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "embeddings.jsonl"
    rows = [
        json.dumps({"path": "a.md", "mtime": 1.0, "vector": [1.0, 0.0]}),
        "not json at all",
        json.dumps({"path": "a.md", "mtime": 2.0, "vector": [0.0, 1.0]}),
        json.dumps({"missing": "keys"}),
    ]
    cache.write_text("\n".join(rows) + "\n", encoding="utf-8")

    assert load_embedding_cache(cache) == {"a.md": (0.0, 1.0)}


def test_load_embedding_cache_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert load_embedding_cache(tmp_path / "absent.jsonl") == {}


def test_embed_notes_reuses_cached_vectors_and_embeds_only_mtime_misses(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "embeddings.jsonl"
    cache.write_text(
        json.dumps({"path": "hit.md", "mtime": 10.0, "vector": [1.0, 0.0]})
        + "\n"
        + json.dumps({"path": "stale.md", "mtime": 5.0, "vector": [0.5, 0.5]})
        + "\n",
        encoding="utf-8",
    )
    inventory = Inventory(
        generated="2026-07-12T00:00:00",
        notes=[
            make_note("hit.md", "Hit", mtime=10.0),
            make_note("stale.md", "Stale", mtime=6.0),
            make_note("new.md", "New", mtime=1.0),
        ],
    )
    embedder = RecordingEmbedder()

    vectors = embed_notes(inventory, embedder, "test-model", cache)

    assert set(vectors) == {"hit.md", "stale.md", "new.md"}
    assert vectors["hit.md"] == (1.0, 0.0)
    assert embedder.batches == [
        [embedding_text(inventory.notes[1]), embedding_text(inventory.notes[2])]
    ]
    reloaded = load_embedding_cache(cache)
    assert reloaded["stale.md"] == vectors["stale.md"]
    assert reloaded["new.md"] == vectors["new.md"]


def test_embed_notes_makes_no_embed_call_when_cache_is_fully_warm(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "embeddings.jsonl"
    cache.write_text(
        json.dumps({"path": "only.md", "mtime": 4.0, "vector": [0.25, 0.75]}) + "\n",
        encoding="utf-8",
    )
    inventory = Inventory(
        generated="g", notes=[make_note("only.md", "Only", mtime=4.0)]
    )
    embedder = RecordingEmbedder()

    vectors = embed_notes(inventory, embedder, "test-model", cache)

    assert vectors == {"only.md": (0.25, 0.75)}
    assert embedder.batches == []


class ScriptedLabelCompleter:
    """Returns a canned label when its marker string appears in the prompt."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        for marker, label in self.responses.items():
            if marker in prompt:
                return label
        return "unmatched"


def test_cluster_paths_is_deterministic_and_orders_by_size_then_first_path() -> None:
    vectors: dict[str, tuple[float, ...]] = {
        "z-solo.md": (0.0, 1.0, 0.0),
        "b-pair.md": (1.0, 0.0, 0.0),
        "a-pair.md": (1.0, 0.0, 0.0),
        "c-solo.md": (0.0, 0.0, 1.0),
    }
    expected = [["a-pair.md", "b-pair.md"], ["c-solo.md"], ["z-solo.md"]]

    assert cluster_paths(vectors, threshold=0.5) == expected
    reversed_insertion = dict(reversed(list(vectors.items())))
    assert cluster_paths(reversed_insertion, threshold=0.5) == expected


def test_label_clusters_labels_multi_note_clusters_and_misc_singletons() -> None:
    inventory = Inventory(
        generated="g",
        notes=[
            make_note("a.md", "Rust ownership"),
            make_note("b.md", "Rust borrowing"),
            make_note("c.md", "Lone note"),
        ],
    )
    completer = ScriptedLabelCompleter({"Rust ownership": "rust memory"})

    clusters = label_clusters(
        [["a.md", "b.md"], ["c.md"]], inventory, completer, "model"
    )

    assert clusters == [
        Cluster(cluster_id=1, label="rust memory", note_paths=["a.md", "b.md"]),
        Cluster(cluster_id=2, label="misc", note_paths=["c.md"]),
    ]
    assert len(completer.prompts) == 1
    assert "Rust ownership" in completer.prompts[0]
    assert "Rust borrowing" in completer.prompts[0]
    assert "Lone note" not in completer.prompts[0]


def test_label_clusters_caps_prompt_at_fifteen_titles() -> None:
    notes = [make_note(f"note-{i:02d}.md", f"Title {i:02d}") for i in range(20)]
    inventory = Inventory(generated="g", notes=notes)
    completer = ScriptedLabelCompleter({})

    label_clusters([[note.path for note in notes]], inventory, completer, "model")

    assert len(completer.prompts) == 1
    assert "Title 14" in completer.prompts[0]
    assert "Title 15" not in completer.prompts[0]


def test_slice_batches_pools_misc_clusters_after_topic_clusters() -> None:
    clusters = [
        Cluster(cluster_id=1, label="misc", note_paths=["m1.md"]),
        Cluster(cluster_id=2, label="rust", note_paths=["r1.md", "r2.md"]),
        Cluster(cluster_id=3, label="misc", note_paths=["m2.md"]),
        Cluster(cluster_id=4, label="bread", note_paths=["b1.md"]),
    ]

    batches = slice_batches(clusters, batch_size=3)

    assert batches == [
        Batch(batch_id=1, note_paths=["r1.md", "r2.md", "b1.md"], label="rust"),
        Batch(batch_id=2, note_paths=["m1.md", "m2.md"], label="misc"),
    ]


def test_slice_batches_spans_oversized_cluster_across_consecutive_batches() -> None:
    big = Cluster(
        cluster_id=1,
        label="giant",
        note_paths=[f"n{i}.md" for i in range(1, 10)],
    )
    tail = Cluster(cluster_id=2, label="misc", note_paths=["z.md"])

    batches = slice_batches([big, tail], batch_size=4)

    assert [batch.note_paths for batch in batches] == [
        ["n1.md", "n2.md", "n3.md", "n4.md"],
        ["n5.md", "n6.md", "n7.md", "n8.md"],
        ["n9.md", "z.md"],
    ]
    assert [batch.batch_id for batch in batches] == [1, 2, 3]
    assert [batch.label for batch in batches] == ["giant", "giant", "giant"]


def test_build_cluster_map_embeds_clusters_labels_and_batches(tmp_path: Path) -> None:
    rust = "rust memory ownership borrow checker rules"
    bread = "sourdough starter flour water ferment schedule"
    inventory = Inventory(
        generated="2026-07-12T00:00:00",
        notes=[
            make_note("note-a.md", "Rust ownership", snippet=rust),
            make_note("note-b.md", "Rust borrowing", snippet=rust),
            make_note("note-c.md", "Bread starter", snippet=bread),
            make_note("note-d.md", "Bread proofing", snippet=bread),
            make_note("note-e.md", "Quantum entanglement"),
        ],
    )
    completer = ScriptedLabelCompleter(
        {"Rust ownership": "rust", "Bread starter": "baking"}
    )
    cache_path = tmp_path / "embeddings.jsonl"

    cluster_map = build_cluster_map(
        inventory,
        BagOfWordsEmbedder(),
        completer,
        embed_model="embed-model",
        label_model="label-model",
        threshold=0.45,
        batch_size=4,
        cache_path=cache_path,
        generated="2026-07-12T00:00:00",
    )

    assert cluster_map.generated == "2026-07-12T00:00:00"
    assert cluster_map.clusters == [
        Cluster(cluster_id=1, label="rust", note_paths=["note-a.md", "note-b.md"]),
        Cluster(cluster_id=2, label="baking", note_paths=["note-c.md", "note-d.md"]),
        Cluster(cluster_id=3, label="misc", note_paths=["note-e.md"]),
    ]
    assert cluster_map.batches == [
        Batch(
            batch_id=1,
            note_paths=["note-a.md", "note-b.md", "note-c.md", "note-d.md"],
            label="rust",
        ),
        Batch(batch_id=2, note_paths=["note-e.md"], label="misc"),
    ]
    assert len(load_embedding_cache(cache_path)) == 5
