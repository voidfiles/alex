from collections.abc import Sequence
from pathlib import Path

from click.testing import CliRunner

from alex.commands.brain import build_brain_command
from alex.lib.brain import (
    BrainIndex,
    BrainIndexConfig,
    SearchHit,
    _embedding_input_type,
    discover_notes,
    normalize_embedding_model,
    select_diverse_hits,
)
from alex.lib.collisions import run_collisions
from alex.lib.llm import LlmError


def test_discovery_prefers_asset_chunks_and_excludes_generated_ideas(
    tmp_path: Path,
) -> None:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "plain.md").write_text("# Plain\n\nBody", encoding="utf-8")
    asset = tmp_path / "assets" / "book"
    (asset / "chunks").mkdir(parents=True)
    (asset / "chunks" / "one.md").write_text("# One\n\nChunk", encoding="utf-8")
    (asset / "summary.md").write_text("# Summary", encoding="utf-8")
    (asset / "book.md").write_text("# Extract", encoding="utf-8")
    (tmp_path / "resources" / "ideas").mkdir(parents=True)
    (tmp_path / "resources" / "ideas" / "generated.md").write_text(
        "# Idea", encoding="utf-8"
    )

    paths = tuple(
        note.source_path.relative_to(tmp_path) for note in discover_notes(tmp_path)
    )

    assert paths == (Path("assets/book/chunks/one.md"), Path("notes/plain.md"))


def test_discovery_keeps_root_notes_when_the_vault_has_a_chunks_directory(
    tmp_path: Path,
) -> None:
    root_note = tmp_path / "root-note.md"
    root_note.write_text("# Root note\n\nImportant context.", encoding="utf-8")
    (tmp_path / "chunks").mkdir()
    (tmp_path / "chunks" / "001_root-summary.md").write_text(
        "# Root chunk\n\nCondensed context.", encoding="utf-8"
    )
    asset = tmp_path / "assets" / "book"
    (asset / "chunks").mkdir(parents=True)
    (asset / "chunks" / "one.md").write_text("# One\n\nChunk", encoding="utf-8")

    paths = tuple(
        note.source_path.relative_to(tmp_path) for note in discover_notes(tmp_path)
    )

    assert paths == (
        Path("assets/book/chunks/one.md"),
        Path("chunks/001_root-summary.md"),
        Path("root-note.md"),
    )


def test_index_commits_lexical_chunks_before_embeddings(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(
        "# Systems\n\nFeedback loops stabilize systems.", encoding="utf-8"
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))

    result = index.index(defer_embeddings=True)

    assert result.indexed_files == 1
    assert result.stale_chunks == 1
    hits = index.search_lexical("feedback loops")
    assert len(hits) == 1
    assert hits[0].title == "Systems"
    assert hits[0].line_start == 1


def test_index_reingests_unchanged_notes_after_a_discovery_rule_change(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Note\n\nBody", encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)
    index.connection.execute(
        "INSERT OR REPLACE INTO brain_meta(key, value) "
        "VALUES ('discovery_version', '1')"
    )
    index.connection.commit()

    result = index.index(defer_embeddings=True)

    assert result.indexed_files == 1


def test_changed_note_never_keeps_an_obsolete_embedding(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "note.md"
    note.write_text("# First\n\nOld text.", encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)
    chunk_id = index.stale_chunk_ids()[0]
    index.store_embeddings({chunk_id: (0.1, 0.2)})

    note.write_text("# Second\n\nNew text.", encoding="utf-8")
    index.index(defer_embeddings=True)

    assert index.fresh_vector_count() == 0
    assert index.stale_chunks() == 1


def test_embed_stale_returns_the_provider_error_after_a_failed_batch(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(
        "# First\n\nBody\n\n# Second\n\nBody", encoding="utf-8"
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)

    class FailingEmbedder:
        calls = 0

        def embed(
            self, *, texts: Sequence[str], model: str
        ) -> tuple[tuple[float, ...], ...]:
            self.calls += 1
            raise LlmError("provider unavailable")

    embedder = FailingEmbedder()

    assert index.embed_stale(embedder) == (0, 2, "provider unavailable")
    assert embedder.calls == 1


def test_embed_stale_continues_after_successful_batches_beyond_the_scan_window(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(
        "\n\n".join(f"# Note {number}\n\nBody" for number in range(2_001)),
        encoding="utf-8",
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)

    class ConstantEmbedder:
        calls = 0

        def embed(
            self, *, texts: Sequence[str], model: str
        ) -> tuple[tuple[float, ...], ...]:
            self.calls += 1
            return tuple((0.1, 0.2) for _ in texts)

    embedder = ConstantEmbedder()

    assert index.embed_stale(embedder) == (2_001, 0, None)
    assert index.stale_chunks() == 0
    assert embedder.calls == 126


def test_brain_index_and_status_are_available_without_an_embedding_provider(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Note\n\nLexical retrieval.", encoding="utf-8")
    command = build_brain_command(cache_root=tmp_path / "cache")
    runner = CliRunner()

    indexed = runner.invoke(command, ["index", str(vault), "--defer-embeddings"])
    status = runner.invoke(command, ["status", str(vault), "--json"])

    assert indexed.exit_code == 0, indexed.output
    assert "Indexed: 1 changed" in indexed.output
    assert status.exit_code == 0, status.output
    assert '"stale_vectors": 1' in status.output


def test_lexical_search_accepts_a_normal_question_with_punctuation(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(
        "# Leadership\n\nTeam performance improves during uncertainty.",
        encoding="utf-8",
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)

    hits = index.search_lexical("How does leadership improve team performance?")

    assert hits[0].title == "Leadership"


def test_voyage_model_name_normalizes_to_the_openrouter_provider() -> None:
    assert (
        normalize_embedding_model("voyageai/voyage-4") == "openrouter/voyageai/voyage-4"
    )


def test_voyage_openrouter_embeddings_use_voyage_input_types() -> None:
    assert (
        _embedding_input_type("openrouter/voyageai/voyage-4", "document") == "document"
    )
    assert _embedding_input_type("openrouter/voyageai/voyage-4", "query") == "query"


def test_select_diverse_hits_includes_root_asset_and_nested_scopes() -> None:
    hits = (
        SearchHit("projects/near.md", "Near", "", 1, 1, 0.9),
        SearchHit("root.md", "Root", "", 1, 1, 0.8),
        SearchHit("assets/book/chunks/one.md", "Asset", "", 1, 1, 0.7),
        SearchHit("projects/other.md", "Other", "", 1, 1, 0.6),
    )

    selected = select_diverse_hits(hits, limit=3)

    assert tuple(hit.path for hit in selected) == (
        "projects/near.md",
        "root.md",
        "assets/book/chunks/one.md",
    )


def test_diverse_hybrid_search_reserves_sources_for_each_vault_scope(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "root.md").write_text("# Root\n\nTeam clarity", encoding="utf-8")
    asset = vault / "assets" / "book" / "chunks"
    asset.mkdir(parents=True)
    (asset / "one.md").write_text("# Asset\n\nTeam clarity", encoding="utf-8")
    (vault / "projects").mkdir()
    (vault / "projects" / "nested.md").write_text(
        "# Nested\n\nTeam clarity", encoding="utf-8"
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)

    hits = index.search_diverse_hybrid("team clarity", limit=3)

    assert {hit.path for hit in hits} == {
        "root.md",
        "assets/book/chunks/one.md",
        "projects/nested.md",
    }


def test_far_notes_prefers_the_most_embedding_distant_eligible_source(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "root.md").write_text("# Root\n\nClose", encoding="utf-8")
    (vault / "projects").mkdir()
    (vault / "projects" / "far.md").write_text("# Far\n\nDistant", encoding="utf-8")
    asset = vault / "assets" / "book" / "chunks"
    asset.mkdir(parents=True)
    (asset / "one.md").write_text("# Asset\n\nNear", encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)
    rows = index.connection.execute(
        "SELECT c.id, n.path FROM chunks c JOIN notes n ON n.id = c.note_id"
    ).fetchall()
    vectors: dict[int, Sequence[float]] = {
        int(row["id"]): (1.0, 0.0)
        if row["path"] == "root.md"
        else (0.0, 1.0)
        if row["path"] == "projects/far.md"
        else (0.9, 0.1)
        for row in rows
    }
    index.store_embeddings(vectors)

    far = index.far_notes((SearchHit("root.md", "Root", "Close", 1, 1, 0.0),), limit=1)

    assert tuple(hit.path for hit in far) == ("projects/far.md",)


def test_collision_run_generates_and_judges_grounded_ideas(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "close.md").write_text("# Close\n\nTeams need clarity.", encoding="utf-8")
    (vault / "far").mkdir()
    (vault / "far" / "other.md").write_text(
        "# Far\n\nMeditation trains attention.", encoding="utf-8"
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)

    class Completer:
        def __init__(self) -> None:
            self.max_tokens_seen: list[int] = []

        def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
            self.max_tokens_seen.append(max_tokens)
            if "Score these ideas" in prompt:
                return (
                    '[{"index": 0, "score": 4.5, "novelty": 4.5, "notes": "specific"}]'
                )
            return (
                '[{"idea": "Use attention resets before uncertainty reviews.", '
                '"inversion": "More pausing beats more reporting."}]'
            )

    completer = Completer()
    result = run_collisions(
        index=index,
        question="How do teams create clarity?",
        mode="lsd",
        limit=1,
        completer=completer,
        model="test",
        judge_model="judge",
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].score == 4.5
    assert max(completer.max_tokens_seen) >= 1_600


def test_collision_run_continues_when_one_generation_pair_fails(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "close.md").write_text("# Close\n\nTeams need clarity.", encoding="utf-8")
    (vault / "far").mkdir()
    (vault / "far" / "other.md").write_text(
        "# Far\n\nAttention helps.", encoding="utf-8"
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)

    class Completer:
        calls = 0

        def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
            self.calls += 1
            if "Score these ideas" in prompt:
                return '[{"index": 0, "score": 4.5, "notes": "specific"}]'
            if self.calls == 1:
                raise RuntimeError("temporary provider failure")
            return '[{"idea": "Attention reset", "inversion": "Pause first."}]'

    result = run_collisions(
        index=index,
        question="How do teams create clarity?",
        mode="lsd",
        limit=1,
        completer=Completer(),
        model="test",
        judge_model="judge",
    )

    assert result.candidates == ()


def test_collision_run_rejects_an_idea_with_low_novelty(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "close.md").write_text("# Close\n\nTeams need clarity.", encoding="utf-8")
    (vault / "far").mkdir()
    (vault / "far" / "other.md").write_text(
        "# Far\n\nMeditation trains attention.", encoding="utf-8"
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)

    class Completer:
        def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
            if "Score these ideas" in prompt:
                return '[{"index": 0, "score": 5, "novelty": 2, "notes": "obvious"}]'
            return '[{"idea": "Attention reset", "inversion": "Pause first."}]'

    result = run_collisions(
        index=index,
        question="How do teams create clarity?",
        mode="lsd",
        limit=1,
        completer=Completer(),
        model="test",
        judge_model="judge",
    )

    assert result.candidates == ()
