# ruff: noqa: E501
"""Disposable SQLite retrieval index for an Obsidian vault.

Markdown remains authoritative.  This module only caches enough structured
text, links, and optional vectors to make retrieval fast and resumable.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import struct
import time
from collections.abc import Iterator, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from alex.lib.llm import Embedder, LiteLlmEmbedder, LlmError

SCHEMA_VERSION = 1
CHUNKING_VERSION = 1
DISCOVERY_VERSION = 2
MAX_NORMAL_BYTES = 500_000
MAX_FILE_BYTES = 5_000_000
EXCLUDED_DIRS = frozenset(
    {"trash", "backup tests", "research-corpus", "attachments", "cache"}
)
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class BrainError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrainIndexConfig:
    vault: Path
    cache_root: Path
    embedding_model: str = "ollama/nomic-embed-text"

    @property
    def resolved_vault(self) -> Path:
        return self.vault.expanduser().resolve()

    @property
    def database_path(self) -> Path:
        digest = hashlib.sha256(str(self.resolved_vault).encode()).hexdigest()[:24]
        return self.cache_root / "brain" / f"{digest}.sqlite3"


@dataclass(frozen=True)
class DiscoveredNote:
    source_path: Path
    logical_path: Path
    size_bytes: int


@dataclass(frozen=True)
class SearchHit:
    path: str
    title: str
    text: str
    line_start: int
    line_end: int
    score: float


@dataclass(frozen=True)
class IndexResult:
    indexed_files: int
    skipped_files: int
    stale_chunks: int
    large_files: int


def discover_notes(vault: Path) -> Iterator[DiscoveredNote]:
    """Yield one Markdown representation for each logical vault artifact."""
    root = vault.expanduser().resolve()
    candidates: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        parts = relative.parts
        lowered = tuple(part.casefold() for part in parts)
        if any(part.startswith(".") for part in parts) or any(
            part in EXCLUDED_DIRS for part in lowered[:-1]
        ):
            continue
        if lowered[:2] == ("resources", "ideas"):
            continue
        asset = _asset_root(root, path)
        if asset is not None:
            representation = _asset_representation(asset)
            if representation is None:
                continue
            if path.parent.name == "chunks":
                if representation.parent.name != "chunks":
                    continue
            elif path != representation:
                continue
        candidates.append(path)
    for path in candidates:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        yield DiscoveredNote(path, path.relative_to(root), size)


def _asset_root(vault: Path, path: Path) -> Path | None:
    """Return the canonical asset folder containing ``path``, if any."""
    relative = path.relative_to(vault)
    if len(relative.parts) < 2 or relative.parts[0].casefold() != "assets":
        return None
    asset = vault / relative.parts[0] / relative.parts[1]
    return asset if asset.is_dir() else None


def _asset_representation(asset: Path) -> Path | None:
    chunks = sorted((asset / "chunks").glob("*.md"))
    if chunks:
        # Individual chunks are independent retrieval notes, but their asset
        # parent is marked selected only once discovery reaches the first one.
        return chunks[0]
    summary = asset / "summary.md"
    if summary.is_file():
        return summary
    extracts = sorted(
        path
        for path in asset.glob("*.md")
        if path.name not in {"headers.md", "chunk_summary.md"}
    )
    return extracts[0] if extracts else None


def recursive_chunks(text: str, *, title: str) -> tuple[tuple[str, int, int, str], ...]:
    """Split pathological Markdown without dropping text or provenance."""
    lines = text.splitlines()
    headings: list[str] = []
    units: list[tuple[str, int, int, str]] = []
    start = 1
    current: list[str] = []
    context = title
    for number, line in enumerate(lines, 1):
        match = HEADING.match(line)
        if match and current:
            units.append(("\n".join(current), start, number - 1, context))
            current = []
            start = number
        if match:
            level = len(match.group(1))
            headings = [*headings[: level - 1], match.group(2)]
            context = " > ".join([title, *headings])
        current.append(line)
    if current:
        units.append(("\n".join(current), start, len(lines), context))

    chunks: list[tuple[str, int, int, str]] = []
    for body, line_start, line_end, hierarchy in units:
        words = body.split()
        if len(words) <= 300 and len(body) <= 6000:
            chunks.append((body, line_start, line_end, hierarchy))
            continue
        # Words preserve every byte-ish unit when prose has no normal breaks.
        for offset in range(0, len(words), 250):
            window = words[offset : offset + 300]
            chunk = " ".join(window)
            chunks.append((chunk[:6000], line_start, line_end, hierarchy))
    return tuple(chunks)


class BrainIndex:
    def __init__(self, config: BrainIndexConfig) -> None:
        self.config = config
        config.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(config.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        self.connection.enable_load_extension(True)
        try:
            import sqlite_vec  # type: ignore[import-untyped]

            sqlite_vec.load(self.connection)
        except (ImportError, sqlite3.Error) as error:
            raise BrainError(f"sqlite-vec could not be loaded: {error}") from error
        finally:
            self.connection.enable_load_extension(False)
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS brain_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, source_hash TEXT NOT NULL,
                title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'indexed', updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, body TEXT NOT NULL, embedded_text TEXT NOT NULL,
                text_hash TEXT NOT NULL, hierarchy TEXT NOT NULL, line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL, embedding_signature TEXT, embedding BLOB, embedded_at REAL,
                UNIQUE(note_id, ordinal)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(body, title, path);
            CREATE TABLE IF NOT EXISTS links (
                source_note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                target TEXT NOT NULL
            );
            """
        )
        version = self.connection.execute(
            "SELECT value FROM brain_meta WHERE key = 'schema_version'"
        ).fetchone()
        if version is None:
            self.connection.executemany(
                "INSERT INTO brain_meta(key, value) VALUES (?, ?)",
                (
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("chunking_version", str(CHUNKING_VERSION)),
                    ("discovery_version", str(DISCOVERY_VERSION)),
                ),
            )
        elif version["value"] != str(SCHEMA_VERSION):
            raise BrainError("Brain schema changed. Re-run with --rebuild.")
        self.connection.commit()

    def index(self, *, defer_embeddings: bool = False) -> IndexResult:
        del defer_embeddings  # The command chooses when to call embed_stale.
        seen: set[str] = set()
        indexed = skipped = large = 0
        force_reingest = self._meta("discovery_version") != str(DISCOVERY_VERSION)
        for note in discover_notes(self.config.resolved_vault):
            path = str(note.logical_path)
            seen.add(path)
            if note.size_bytes > MAX_FILE_BYTES:
                self._record_skipped(path, "file_too_large")
                skipped += 1
                continue
            if note.size_bytes > MAX_NORMAL_BYTES:
                large += 1
            try:
                content = note.source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                self._record_skipped(path, "unreadable")
                skipped += 1
                continue
            if self._ingest_note(path, content, force=force_reingest):
                indexed += 1
        with self.connection:
            if seen:
                marks = ",".join("?" for _ in seen)
                self.connection.execute(
                    f"DELETE FROM notes WHERE path NOT IN ({marks})", tuple(seen)
                )
            else:
                self.connection.execute("DELETE FROM notes")
            self.connection.execute(
                "INSERT OR REPLACE INTO brain_meta(key, value) VALUES ('last_scan_at', ?)",
                (str(time.time()),),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO brain_meta(key, value) VALUES ('discovery_version', ?)",
                (str(DISCOVERY_VERSION),),
            )
        return IndexResult(indexed, skipped, self.stale_chunks(), large)

    def _record_skipped(self, path: str, status: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO notes(path, source_hash, title, status, updated_at) VALUES (?, '', ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
                (path, Path(path).stem, status, time.time()),
            )

    def _ingest_note(self, path: str, content: str, *, force: bool = False) -> bool:
        source_hash = hashlib.sha256(content.encode()).hexdigest()
        old = self.connection.execute(
            "SELECT id, source_hash FROM notes WHERE path = ?", (path,)
        ).fetchone()
        if old is not None and old["source_hash"] == source_hash and not force:
            return False
        title = _title(content, Path(path).stem)
        with self.connection:
            if old is None:
                cursor = self.connection.execute(
                    "INSERT INTO notes(path, source_hash, title, updated_at) VALUES (?, ?, ?, ?)",
                    (path, source_hash, title, time.time()),
                )
                if cursor.lastrowid is None:
                    raise BrainError("SQLite did not return a note identifier.")
                note_id = cursor.lastrowid
            else:
                note_id = int(old["id"])
                old_chunk_ids = self.connection.execute(
                    "SELECT id FROM chunks WHERE note_id = ?", (note_id,)
                ).fetchall()
                with suppress(sqlite3.OperationalError):
                    self.connection.executemany(
                        "DELETE FROM vec_chunks WHERE rowid = ?",
                        ((row["id"],) for row in old_chunk_ids),
                    )
                self.connection.executemany(
                    "DELETE FROM chunks_fts WHERE rowid = ?",
                    ((row["id"],) for row in old_chunk_ids),
                )
                self.connection.execute(
                    "DELETE FROM chunks WHERE note_id = ?", (note_id,)
                )
                self.connection.execute(
                    "DELETE FROM links WHERE source_note_id = ?", (note_id,)
                )
                self.connection.execute(
                    "UPDATE notes SET source_hash=?, title=?, status='indexed', updated_at=? WHERE id=?",
                    (source_hash, title, time.time(), note_id),
                )
            for ordinal, (body, start, end, hierarchy) in enumerate(
                recursive_chunks(content, title=title)
            ):
                embedded = _document_text(self.config.embedding_model, hierarchy, body)
                cursor = self.connection.execute(
                    "INSERT INTO chunks(note_id, ordinal, body, embedded_text, text_hash, hierarchy, line_start, line_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        note_id,
                        ordinal,
                        body,
                        embedded,
                        hashlib.sha256(embedded.encode()).hexdigest(),
                        hierarchy,
                        start,
                        end,
                    ),
                )
                if cursor.lastrowid is None:
                    raise BrainError("SQLite did not return a chunk identifier.")
                chunk_id = cursor.lastrowid
                self.connection.execute(
                    "INSERT INTO chunks_fts(rowid, body, title, path) VALUES (?, ?, ?, ?)",
                    (chunk_id, body, title, path),
                )
            self.connection.executemany(
                "INSERT INTO links(source_note_id, target) VALUES (?, ?)",
                (
                    (note_id, match.group(1).strip())
                    for match in WIKILINK.finditer(content)
                ),
            )
        return True

    def stale_chunk_ids(self) -> tuple[int, ...]:
        rows = self.connection.execute(
            "SELECT id FROM chunks WHERE embedding IS NULL ORDER BY id"
        ).fetchall()
        return tuple(int(row["id"]) for row in rows)

    def stale_chunks(self) -> int:
        return len(self.stale_chunk_ids())

    def fresh_vector_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM chunks WHERE embedding IS NOT NULL"
            ).fetchone()[0]
        )

    def store_embeddings(self, embeddings: dict[int, Sequence[float]]) -> None:
        import sqlite_vec

        if not embeddings:
            return
        dimensions = {len(vector) for vector in embeddings.values()}
        if len(dimensions) != 1 or 0 in dimensions:
            raise BrainError("Embedding dimensions must be non-zero and consistent.")
        dimensions_value = dimensions.pop()
        signature = (
            f"{self.config.embedding_model}:{dimensions_value}:document-query:"
            f"v{CHUNKING_VERSION}"
        )
        stored_dimensions = self._meta("vector_dimensions")
        if stored_dimensions is None:
            with self.connection:
                self.connection.execute(
                    f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{dimensions_value}])"
                )
                self.connection.execute(
                    "INSERT INTO brain_meta(key, value) VALUES ('vector_dimensions', ?)",
                    (str(dimensions_value),),
                )
        elif stored_dimensions != str(dimensions_value):
            raise BrainError("Embedding dimensions changed. Re-run with --rebuild.")
        with self.connection:
            for chunk_id, vector in embeddings.items():
                blob = sqlite_vec.serialize_float32(list(vector))
                self.connection.execute(
                    "INSERT OR REPLACE INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                    (chunk_id, blob),
                )
                self.connection.execute(
                    "UPDATE chunks SET embedding=?, embedding_signature=?, embedded_at=? "
                    "WHERE id=? AND embedding IS NULL",
                    (blob, signature, time.time(), chunk_id),
                )

    def embed_stale(self, embedder: Embedder) -> tuple[int, int, str | None]:
        """Backfill stale rows, committing each successful adaptive batch."""
        completed = failed = 0
        first_error: str | None = None
        batch_size = (
            16 if self.config.embedding_model == "ollama/nomic-embed-text" else 64
        )
        while True:
            rows = self.connection.execute(
                "SELECT id, embedded_text FROM chunks WHERE embedding IS NULL ORDER BY id LIMIT 2000"
            ).fetchall()
            if not rows:
                break
            failed_in_scan = False
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                completed_now, failed_now, error = self._embed_batch(embedder, batch)
                completed += completed_now
                failed += failed_now
                failed_in_scan = failed_in_scan or failed_now > 0
                if first_error is None:
                    first_error = error
            # Failed rows remain stale. Stop rather than retrying them forever,
            # but keep scanning while every batch succeeds.
            if failed_in_scan:
                break
        return completed, failed, first_error

    def _embed_batch(
        self, embedder: Embedder, rows: Sequence[sqlite3.Row]
    ) -> tuple[int, int, str | None]:
        if not rows:
            return 0, 0, None
        try:
            vectors = _embed_for_role(
                embedder,
                tuple(str(row["embedded_text"]) for row in rows),
                self.config.embedding_model,
                "document",
            )
            if len(vectors) != len(rows):
                raise BrainError("Embedding provider returned the wrong vector count.")
            self.store_embeddings(
                {
                    int(row["id"]): vector
                    for row, vector in zip(rows, vectors, strict=True)
                }
            )
            return len(rows), 0, None
        except LlmError as error:
            return 0, len(rows), str(error)
        except Exception as error:
            if len(rows) == 1:
                return 0, 1, str(error)
            midpoint = len(rows) // 2
            left = self._embed_batch(embedder, rows[:midpoint])
            right = self._embed_batch(embedder, rows[midpoint:])
            return left[0] + right[0], left[1] + right[1], left[2] or right[2]

    def status(self) -> dict[str, object]:
        rows = self.connection.execute(
            "SELECT status, count(*) AS count FROM notes GROUP BY status"
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        return {
            "database": str(self.config.database_path),
            "schema_version": SCHEMA_VERSION,
            "chunking_version": CHUNKING_VERSION,
            "discovery_version": self._meta("discovery_version"),
            "embedding_model": self.config.embedding_model,
            "indexed_files": counts.get("indexed", 0),
            "skipped_files": sum(
                value for key, value in counts.items() if key != "indexed"
            ),
            "fresh_vectors": self.fresh_vector_count(),
            "stale_vectors": self.stale_chunks(),
            "last_successful_scan": self._meta("last_scan_at"),
        }

    def _meta(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM brain_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else None

    def search_lexical(
        self, query: str, *, limit: int = 20, scope: str | None = None
    ) -> tuple[SearchHit, ...]:
        fts_query = _fts_query(query)
        if not fts_query:
            return ()
        rows = self.connection.execute(
            f"""SELECT n.path, n.title, c.body, c.line_start, c.line_end, bm25(chunks_fts) AS score
               FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN notes n ON n.id = c.note_id
               WHERE chunks_fts MATCH ? AND {_scope_sql(scope)} ORDER BY score LIMIT ?""",
            (fts_query, limit),
        ).fetchall()
        return tuple(
            SearchHit(
                row["path"],
                row["title"],
                row["body"],
                row["line_start"],
                row["line_end"],
                float(row["score"]),
            )
            for row in rows
        )

    def search_vector(
        self,
        query: str,
        *,
        embedder: Embedder,
        limit: int = 20,
        scope: str | None = None,
    ) -> tuple[SearchHit, ...]:
        try:
            import sqlite_vec

            vector = _embed_for_role(
                embedder, (query,), self.config.embedding_model, "query"
            )[0]
            blob = sqlite_vec.serialize_float32(list(vector))
            rows = self.connection.execute(
                f"""SELECT n.path, n.title, c.body, c.line_start, c.line_end, v.distance
                   FROM vec_chunks v JOIN chunks c ON c.id=v.rowid JOIN notes n ON n.id=c.note_id
                   WHERE v.embedding MATCH ? AND {_scope_sql(scope)}
                   ORDER BY v.distance LIMIT ?""",
                (blob, limit),
            ).fetchall()
        except (IndexError, ImportError, sqlite3.Error, RuntimeError):
            return ()
        return tuple(
            SearchHit(
                row["path"],
                row["title"],
                row["body"],
                row["line_start"],
                row["line_end"],
                float(row["distance"]),
            )
            for row in rows
        )

    def search_hybrid(
        self,
        query: str,
        *,
        embedder: Embedder | None = None,
        limit: int = 20,
        scope: str | None = None,
    ) -> tuple[SearchHit, ...]:
        lexical = self.search_lexical(query, limit=limit * 2, scope=scope)
        vector = (
            self.search_vector(query, embedder=embedder, limit=limit * 2, scope=scope)
            if embedder
            else ()
        )
        fused: dict[str, tuple[SearchHit, float]] = {}
        for channel in (lexical, vector):
            for rank, hit in enumerate(channel, 1):
                key = hit.path
                current = fused.get(key)
                score = 1.0 / (60 + rank)
                fused[key] = (hit, score + (current[1] if current else 0.0))
        ranked = sorted(fused.values(), key=lambda item: (-item[1], item[0].path))
        return tuple(
            SearchHit(
                hit.path, hit.title, hit.text, hit.line_start, hit.line_end, score
            )
            for hit, score in ranked[:limit]
        )

    def search_diverse_hybrid(
        self, query: str, *, embedder: Embedder | None = None, limit: int = 20
    ) -> tuple[SearchHit, ...]:
        global_hits = self.search_hybrid(query, embedder=embedder, limit=limit * 20)
        scoped_hits = tuple(
            hit
            for scope in ("root", "assets", "nested")
            for hit in self.search_hybrid(
                query, embedder=embedder, limit=1, scope=scope
            )
        )
        return select_diverse_hits((*global_hits, *scoped_hits), limit=limit)

    def far_notes(
        self, close: Sequence[SearchHit], *, limit: int
    ) -> tuple[SearchHit, ...]:
        close_domains = {_domain_key(hit.path) for hit in close}
        close_vectors = self._note_vectors(hit.path for hit in close)
        vector_candidates = self._far_vector_candidates(close_domains)
        if close_vectors and vector_candidates:
            ranked = sorted(
                vector_candidates,
                key=lambda item: (
                    -_mean_cosine_distance(item[1], close_vectors),
                    item[0].path,
                ),
            )
            return tuple(hit for hit, _ in ranked[:limit])
        rows = self.connection.execute(
            """SELECT n.path, n.title, c.body, c.line_start, c.line_end
               FROM chunks c JOIN notes n ON n.id = c.note_id
               WHERE n.status = 'indexed' ORDER BY n.updated_at ASC, c.id ASC"""
        ).fetchall()
        selected: list[SearchHit] = []
        seen: set[str] = set()
        for row in rows:
            path = str(row["path"])
            if _domain_key(path) in close_domains or path in seen:
                continue
            selected.append(
                SearchHit(
                    path,
                    row["title"],
                    row["body"],
                    row["line_start"],
                    row["line_end"],
                    0.0,
                )
            )
            seen.add(path)
            if len(selected) >= limit:
                break
        return tuple(selected)

    def _note_vectors(self, paths: Iterator[str]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for path in paths:
            row = self.connection.execute(
                """SELECT c.embedding FROM chunks c JOIN notes n ON n.id = c.note_id
                   WHERE n.path = ? AND c.embedding IS NOT NULL ORDER BY c.id LIMIT 1""",
                (path,),
            ).fetchone()
            if row is not None:
                vectors.append(_deserialize_vector(bytes(row["embedding"])))
        return tuple(vectors)

    def _far_vector_candidates(
        self, close_domains: set[str]
    ) -> tuple[tuple[SearchHit, tuple[float, ...]], ...]:
        rows = self.connection.execute(
            """SELECT n.path, n.title, c.body, c.line_start, c.line_end, c.embedding
               FROM chunks c JOIN notes n ON n.id = c.note_id
               WHERE n.status = 'indexed' AND c.embedding IS NOT NULL
               ORDER BY n.path, c.id LIMIT 4096"""
        ).fetchall()
        selected: list[tuple[SearchHit, tuple[float, ...]]] = []
        domains: set[str] = set()
        for row in rows:
            path = str(row["path"])
            domain = _domain_key(path)
            if domain in close_domains or domain in domains:
                continue
            selected.append(
                (
                    SearchHit(
                        path,
                        row["title"],
                        row["body"],
                        row["line_start"],
                        row["line_end"],
                        0.0,
                    ),
                    _deserialize_vector(bytes(row["embedding"])),
                )
            )
            domains.add(domain)
        return tuple(selected)


def _title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        match = HEADING.match(line)
        if match:
            return match.group(2)
    return fallback


def _fts_query(query: str) -> str:
    """Turn arbitrary human text into an FTS5 expression, never SQL syntax."""
    terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    return " OR ".join(f'"{term}"' for term in terms)


def _domain_key(path: str) -> str:
    parts = Path(path).parts
    return "/".join(parts[:2]) if len(parts) >= 2 else f"root/{Path(path).stem}"


def _source_scope(path: str) -> str:
    if "/" not in path:
        return "root"
    return "assets" if path.startswith("assets/") else "nested"


def _scope_sql(scope: str | None) -> str:
    if scope is None:
        return "1"
    if scope == "root":
        return "n.path NOT LIKE '%/%'"
    if scope == "assets":
        return "n.path LIKE 'assets/%'"
    if scope == "nested":
        return "n.path LIKE '%/%' AND n.path NOT LIKE 'assets/%'"
    raise ValueError(f"Unknown vault scope: {scope}")


def select_diverse_hits(
    hits: Sequence[SearchHit], *, limit: int
) -> tuple[SearchHit, ...]:
    """Preserve relevance while reserving space for each represented scope."""
    selected: list[SearchHit] = []
    scopes: set[str] = set()
    seen_paths: set[str] = set()
    for hit in hits:
        scope = _source_scope(hit.path)
        if scope in scopes or hit.path in seen_paths:
            continue
        selected.append(hit)
        scopes.add(scope)
        seen_paths.add(hit.path)
        if len(selected) == limit:
            return tuple(selected)
    for hit in hits:
        if hit.path in seen_paths:
            continue
        selected.append(hit)
        seen_paths.add(hit.path)
        if len(selected) == limit:
            break
    return tuple(selected)


def _deserialize_vector(blob: bytes) -> tuple[float, ...]:
    if len(blob) % 4:
        raise BrainError("Stored embedding has an invalid byte length.")
    return tuple(value[0] for value in struct.iter_unpack("<f", blob))


def _mean_cosine_distance(
    candidate: Sequence[float], close_vectors: Sequence[Sequence[float]]
) -> float:
    candidate_norm = math.sqrt(sum(value * value for value in candidate))
    if not candidate_norm:
        return 0.0
    distances: list[float] = []
    for close in close_vectors:
        if len(close) != len(candidate):
            continue
        close_norm = math.sqrt(sum(value * value for value in close))
        if close_norm:
            similarity = sum(
                left * right for left, right in zip(candidate, close, strict=True)
            ) / (candidate_norm * close_norm)
            distances.append(1.0 - similarity)
    return sum(distances) / len(distances) if distances else 0.0


def _embedding_input_type(model: str, role: str) -> str | None:
    if model == "openrouter/voyageai/voyage-4":
        return role
    return None


def normalize_embedding_model(model: str) -> str:
    """Map user-friendly provider/model names to LiteLLM model identifiers."""
    return "openrouter/voyageai/voyage-4" if model == "voyageai/voyage-4" else model


def _embed_for_role(
    embedder: Embedder, texts: tuple[str, ...], model: str, role: str
) -> tuple[tuple[float, ...], ...]:
    if isinstance(embedder, LiteLlmEmbedder):
        return embedder.embed(
            texts=texts, model=model, input_type=_embedding_input_type(model, role)
        )
    return embedder.embed(texts=texts, model=model)


def _document_text(model: str, hierarchy: str, body: str) -> str:
    prefix = "" if model == "openrouter/voyageai/voyage-4" else "search_document: "
    return f"{prefix}{hierarchy}\n\n{body}"
