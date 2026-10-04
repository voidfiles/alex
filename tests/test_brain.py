import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

from alex.commands.brain import build_brain_command
from alex.commands.collisions import build_collision_command
from alex.lib.brain import (
    BrainIndex,
    BrainIndexConfig,
    KnowledgePage,
    SearchHit,
    _embedding_input_type,
    discover_notes,
    normalize_embedding_model,
    select_diverse_hits,
)
from alex.lib.collisions import CollisionResult, run_collisions
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


def test_discovery_indexes_only_brainstorm_generated_ideas(tmp_path: Path) -> None:
    ideas = tmp_path / "resources" / "ideas"
    ideas.mkdir(parents=True)
    (ideas / "brainstorm.md").write_text(
        "---\nmode: brainstorm\n---\n# Generated idea", encoding="utf-8"
    )
    (ideas / "lsd.md").write_text("---\nmode: lsd\n---\n# Generated", encoding="utf-8")
    (ideas / "legacy.md").write_text("# Unknown generated idea", encoding="utf-8")

    paths = tuple(note.logical_path for note in discover_notes(tmp_path))

    assert paths == (Path("resources/ideas/brainstorm.md"),)


def test_index_records_page_domain_and_unique_resolved_wikilink_inbound_counts(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "source-one.md").write_text(
        "# Source\n\n[[target]] and again [[target]].", encoding="utf-8"
    )
    (vault / "source-two.md").write_text("# Source\n\n[[target]]", encoding="utf-8")
    (vault / "target.md").write_text("# Target\n\nBody", encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))

    index.index(defer_embeddings=True)

    target = index.connection.execute(
        "SELECT domain, inbound_links, last_retrieved_at "
        "FROM notes WHERE path = 'target.md'"
    ).fetchone()
    assert target is not None
    assert tuple(target) == ("root/target", 2, None)


def test_index_uses_the_first_two_path_segments_for_nested_domains(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "projects" / "active" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Note\n\nBody", encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))

    index.index(defer_embeddings=True)

    row = index.connection.execute(
        "SELECT domain FROM notes WHERE path = 'projects/active/note.md'"
    ).fetchone()
    assert row is not None
    assert row["domain"] == "projects/active"


def test_page_search_reuses_one_question_embedding_for_close_and_far_selection(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "close.md").write_text("# Close\n\nFeedback loops", encoding="utf-8")
    (vault / "other").mkdir()
    (vault / "other" / "far.md").write_text(
        "# Far\n\nMeditation practice", encoding="utf-8"
    )
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)
    vectors: dict[int, Sequence[float]] = {
        chunk_id: (1.0, 0.0) for chunk_id in index.stale_chunk_ids()
    }
    index.store_embeddings(vectors)

    class Embedder:
        calls = 0

        def embed(
            self, *, texts: Sequence[str], model: str
        ) -> tuple[tuple[float, ...], ...]:
            del texts, model
            self.calls += 1
            return ((1.0, 0.0),)

    embedder = Embedder()
    question_embedding = index.embed_question("How do loops help?", embedder)
    close = index.search_diverse_pages(
        "How do loops help?",
        embedder=embedder,
        query_embedding=question_embedding,
        limit=1,
    )
    far = index.far_pages(
        close, limit=1, mode="lsd", question_embedding=question_embedding
    )

    assert embedder.calls == 1
    assert tuple(page.path for page in far) == ("other/far.md",)


def test_lsd_far_pages_choose_least_recently_retrieved_eligible_domain(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "close.md").write_text("# Close\n\nFeedback loops", encoding="utf-8")
    (vault / "projects").mkdir()
    (vault / "projects" / "old.md").write_text("# Old\n\nPractice", encoding="utf-8")
    (vault / "topics").mkdir()
    (vault / "topics" / "new.md").write_text("# New\n\nPractice", encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)
    index.connection.execute(
        "UPDATE notes SET last_retrieved_at = 100 WHERE path = 'projects/old.md'"
    )
    index.connection.execute(
        "UPDATE notes SET last_retrieved_at = 200 WHERE path = 'topics/new.md'"
    )
    index.connection.commit()

    close = (KnowledgePage("close.md", "Close", 1, "root/close", 0, None),)
    far = index.far_pages(close, limit=2, mode="lsd")

    assert tuple(page.path for page in far) == ("projects/old.md", "topics/new.md")


def test_far_pages_prioritizes_close_chunk_distance_over_question_distance(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "close.md").write_text("# Close\n\nAnchor", encoding="utf-8")
    (vault / "one").mkdir()
    (vault / "one" / "close-far.md").write_text("# One\n\nBody", encoding="utf-8")
    (vault / "two").mkdir()
    (vault / "two" / "question-far.md").write_text("# Two\n\nBody", encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)
    rows = index.connection.execute(
        "SELECT c.id, n.path FROM chunks c JOIN notes n ON n.id = c.note_id"
    ).fetchall()
    index.store_embeddings(
        {
            int(row["id"]): (1.0, 0.0)
            if row["path"] == "close.md"
            else (-1.0, 0.0)
            if row["path"] == "one/close-far.md"
            else (0.0, -1.0)
            for row in rows
        }
    )
    close = index.search_diverse_pages("anchor", limit=1)

    far = index.far_pages(
        close, limit=1, mode="semantic", question_embedding=(0.0, 1.0)
    )

    assert tuple(page.path for page in far) == ("one/close-far.md",)


def test_hydrate_page_caps_source_marks_retrieval_at_most_once_per_five_minutes(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# Note\n\n" + "x" * 5_000, encoding="utf-8")
    index = BrainIndex(BrainIndexConfig(vault=vault, cache_root=tmp_path / "cache"))
    index.index(defer_embeddings=True)
    page = index.search_diverse_pages("note", limit=1)[0]

    hydrated = index.hydrate_page(page)
    first_mark = index.connection.execute(
        "SELECT last_retrieved_at FROM notes WHERE path = 'note.md'"
    ).fetchone()[0]
    index.hydrate_page(hydrated)
    second_mark = index.connection.execute(
        "SELECT last_retrieved_at FROM notes WHERE path = 'note.md'"
    ).fetchone()[0]

    assert len(hydrated.text) == 4_000
    assert hydrated.text == "# Note\n\n" + "x" * 3_992
    assert first_mark == second_mark


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
            if '"index"' in prompt:
                return (
                    '[{"index": 0, "originality": 5, "defensibility": 4, '
                    '"thesis_density": 5, "concrete_grounding": 4, '
                    '"cognitive_load": 4, "obviousness": 3, '
                    '"both_sources_material": true, "substantive_inversion": true, '
                    '"notes": "specific"}]'
                )
            return (
                '[{"idea": "Use attention resets before uncertainty reviews.", '
                '"original_axiom": "Reports create clarity.", '
                '"inverted_axiom": "More pausing beats more reporting."}]'
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
    assert max(completer.max_tokens_seen) >= 700


def test_collision_run_batches_judging_when_one_response_would_be_truncated() -> None:
    """A judge response must preserve every candidate when the full list is too big."""

    close = tuple(
        SearchHit(f"close-{index}.md", "Close", "Close text", 1, 1, 0.0)
        for index in range(3)
    )
    far = tuple(
        SearchHit(f"far-{index}.md", "Far", "Far text", 1, 1, 0.0) for index in range(4)
    )

    class Index:
        def search_diverse_hybrid(
            self, query: str, *, embedder: object | None, limit: int
        ) -> tuple[SearchHit, ...]:
            del query, embedder, limit
            return close

        def far_notes(
            self, selected: Sequence[SearchHit], *, limit: int
        ) -> tuple[SearchHit, ...]:
            del selected, limit
            return far

    class Completer:
        def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
            del model, max_tokens
            if '"index"' not in prompt:
                return '[{"idea": "A grounded idea."}]'
            payload = json.loads(prompt.rsplit("\n", 1)[1])
            if len(payload) > 100:
                return "{"
            return json.dumps(
                [
                    {
                        "index": item["index"],
                        "originality": 5,
                        "defensibility": 5,
                        "thesis_density": 5,
                        "concrete_grounding": 5,
                        "cognitive_load": 5,
                        "obviousness": 1,
                        "both_sources_material": True,
                        "notes": "specific",
                    }
                    for item in payload
                ]
            )

    result = run_collisions(
        index=Index(),  # type: ignore[arg-type]
        question="How do teams create clarity?",
        mode="brainstorm",
        limit=4,
        completer=Completer(),
        model="test",
        judge_model="judge",
    )

    assert len(result.candidates) == 12
    assert {(item.score, item.novelty) for item in result.candidates} == {(5.0, 5.0)}


def test_collision_run_rejects_a_malformed_judge_response() -> None:
    close = SearchHit("close.md", "Close", "Close text", 1, 1, 0.0)
    far = SearchHit("far.md", "Far", "Far text", 1, 1, 0.0)

    class Index:
        def search_diverse_hybrid(
            self, query: str, *, embedder: object | None, limit: int
        ) -> tuple[SearchHit, ...]:
            del query, embedder, limit
            return (close,)

        def far_notes(
            self, selected: Sequence[SearchHit], *, limit: int
        ) -> tuple[SearchHit, ...]:
            del selected, limit
            return (far,)

    class Completer:
        def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
            del model, max_tokens
            if '"index"' in prompt:
                return "{"
            return (
                '[{"idea": "A grounded idea.", "original_axiom": "A", '
                '"inverted_axiom": "Not A"}]'
            )

    with pytest.raises(ValueError, match="Judge returned invalid JSON"):
        run_collisions(
            index=Index(),  # type: ignore[arg-type]
            question="How do teams create clarity?",
            mode="lsd",
            limit=1,
            completer=Completer(),
            model="test",
            judge_model="judge",
        )


def test_collision_command_reports_a_judge_error_without_json_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    def fail_judging(**_: object) -> object:
        raise ValueError("Judge returned invalid JSON.")

    monkeypatch.setattr("alex.commands.collisions.run_collisions", fail_judging)

    result = CliRunner().invoke(
        build_collision_command("lsd", cache_root=tmp_path / "cache"),
        ["How do teams create clarity?", "--vault", str(vault), "--json"],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Searching the vault and generating collision ideas...\n"
        "Error: Judge returned invalid JSON.\n"
    )


def test_collision_command_reports_progress_to_stderr_for_json_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    def return_no_candidates(**_: object) -> CollisionResult:
        return CollisionResult((), (), ())

    monkeypatch.setattr("alex.commands.collisions.run_collisions", return_no_candidates)

    result = CliRunner().invoke(
        build_collision_command("lsd", cache_root=tmp_path / "cache"),
        ["How do teams create clarity?", "--vault", str(vault), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["candidates"] == []
    assert result.stderr == "Searching the vault and generating collision ideas...\n"


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
