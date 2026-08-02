# Vault Triage Tool Implementation Plan

> **Historical status — do not execute wholesale.** This historical snapshot
> is not an instruction file to execute wholesale. Tasks 1–9 were
> implemented at commits `722c86d` through `47457c9` and are the only content
> integrated by this milestone. Tasks 10–18 remain unimplemented. The old
> Anthropic pins and agent/co-author directives are superseded by current
> repository conventions. Continuation must be split into separately reviewed
> milestones; do not run the remaining 11,000-line plan end-to-end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `alex triage`, a batch-review pipeline plus Textual TUI that drains the Obsidian vault's ~3,000-note backlog into PARA with LLM-proposed filing decisions, human-corrected atomic notes, and a corrections ledger distilled into a versioned rubric so proposals improve over time.

**Architecture:** A `triage` command group in the existing `alex` Click CLI. State lives in the vault (`.claude/triage/` machine caches, `projects/vault-triage/` ledger + rubric, decisions as a `triage:` frontmatter block on each note). Pipeline: inventory -> embed/cluster into topic batches -> per-note LLM proposals generated one batch ahead -> TUI review -> frontmatter annotation -> separate dry-run-by-default apply step that moves notes with wiki-link rewriting.

**Tech Stack:** Python 3.12, Click, pydantic v2, PyYAML, LiteLLM (existing `Completer`/`Embedder` protocols in `src/alex/lib/llm.py`), Textual (TUI), pytest + pytest-asyncio (Textual Pilot), uv, mypy strict, ruff.

**Spec:** `docs/superpowers/specs/2026-07-12-vault-triage-design.md` (read it before starting).

## Global Constraints

- Python >=3.12, mypy strict, ruff line length 88, rules E,F,I,UP,B,SIM,RUF. `just check` must pass after every task (lint includes `ruff format --check`; run `just fmt` to fix).
- New runtime deps allowed: `pyyaml>=6.0` (Task 1), `textual>=1.0` (Task 15). New dev deps: `types-pyyaml>=6.0` (Task 1), `pytest-asyncio>=0.24` (Task 15). Nothing else.
- Tests: flat `tests/` dir, `tmp_path` only (no conftest/fixtures), full type hints including `-> None`, behavioral snake_case names, `from helpers import BagOfWordsEmbedder` for embeddings, typed inline fakes for `Completer`.
- All state-file writes are atomic (temp file + `Path.replace`), via `alex.lib.triage.storage.atomic_write_text`.
- YAML via `yaml.safe_load` / `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)`.
- Vault notes: only frontmatter is ever modified, bodies stay byte-identical; nothing is deleted; nothing under dot-directories is touched.
- Vault root resolution everywhere: `--vault-root` flag > `OBSIDIAN_ROOT` env > error (deliberate spec deviation: reuse the repo's existing env var, no hardcoded fallback path).
- Model roles (deliberate spec pin): proposals/atomic `anthropic/claude-sonnet-4-6`, cluster labels `anthropic/claude-haiku-4-5`, distill `anthropic/claude-opus-4-8`, all env-overridable via `ALEX_TRIAGE_*`.
- Commits: `feat(triage): ...` / `test(triage): ...`, message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Tasks run in order 1-18; each task ends with lint+typecheck+tests green and a commit.

---
### Task 1: Triage State Models, Storage, and Path Layout

**Files:**
- Modify: `pyproject.toml` (dependencies list at lines 7-13, dev group at lines 18-23)
- Create: `src/alex/lib/triage/__init__.py`
- Create: `src/alex/lib/triage/models.py`
- Create: `src/alex/lib/triage/storage.py`
- Create: `src/alex/lib/triage/paths.py`
- Test: `tests/test_triage_models.py` (covers models, storage, and paths; the contract's test enumeration defines no separate storage/paths test files)

**Interfaces:**
- Consumes: nothing (foundation task; shapes fixed by the contract).
- Produces:
  - `alex.lib.triage.models`: type aliases `Population`, `ProposalDecision`, `FilingDecision`, `Confidence`, `LedgerEventKind`; models `NoteEvidence`, `Inventory`, `Cluster`, `Batch`, `ClusterMap`, `NewAreaProposal`, `Proposal`, `BatchProposals`, `TriageBlock`, `LedgerEvent`, `Rubric`, `CatalogEntry`, `Catalog`, `AtomicDraft`, `PlannedMove`, `ApplyPlan`, `MoveResult`, `ApplyReport`, `PendingDecision`, `SessionState`, `PendingAreas`
  - `alex.lib.triage.storage`: `atomic_write_text(path: Path, text: str) -> None`, `read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None`, `write_yaml_model(path: Path, model: BaseModel) -> None`
  - `alex.lib.triage.paths`: `TriagePaths(vault_root: Path)` frozen dataclass with properties `state_dir`, `inventory_path`, `cluster_map_path`, `catalog_path`, `embeddings_cache_path`, `proposals_dir`, `session_path`, `pending_areas_path`, `project_dir`, `ledger_path`, `rubric_path`, `processing_log_path`, `lock_path`, and method `proposals_path(batch_id: int, rubric_version: int) -> Path`

- [ ] **Step 1: Add the pyyaml runtime dep and types-pyyaml dev dep**

  In `pyproject.toml`, change the `[project]` dependencies list (lines 7-13):

  ```toml
  dependencies = [
      "click>=8.4.0",
      "litellm>=1.80.0",
      "marker-pdf>=1.10.2",
      "pydantic>=2.13.4",
      "pymupdf4llm>=1.27.2.3",
      "pyyaml>=6.0",
  ]
  ```

  and the dev group (lines 18-23):

  ```toml
  [dependency-groups]
  dev = [
      "mypy>=2.1.0",
      "pytest>=9.0.1",
      "ruff>=0.15.16",
      "types-pyyaml>=6.0",
  ]
  ```

  Then install:

  ```bash
  cd /home/alex/code/alex && uv sync
  ```

  Expect uv to resolve and install `pyyaml` (already in the lockfile as a transitive dep, now direct) and `types-pyyaml`, updating `uv.lock`.

- [ ] **Step 2: Write the failing model tests**

  Create `tests/test_triage_models.py`:

  ```python
  """Tests for triage models, storage helpers, and filesystem layout."""

  from alex.lib.triage.models import Proposal, TriageBlock


  def test_triage_block_defaults_to_no_decision() -> None:
      block = TriageBlock()
      assert block.decision is None
      assert block.target == ""
      assert block.promising is False
      assert block.status is None
      assert block.decided == ""
      assert block.applied == ""


  def test_proposal_serializes_to_plain_json_types() -> None:
      proposal = Proposal(
          note_path="Some Note.md",
          decision="area",
          target="learning-science",
          confidence="high",
          why="Clearly about spaced repetition.",
      )

      dumped = proposal.model_dump(mode="json")

      assert dumped["decision"] == "area"
      assert dumped["new_area"] is None
      assert dumped["alternatives"] == []
      assert dumped["needs_manual"] is False
  ```

- [ ] **Step 3: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_models.py -v
  ```

  Expect a collection error: `ModuleNotFoundError: No module named 'alex.lib.triage'`.

- [ ] **Step 4: Write the package init and models.py**

  Create `src/alex/lib/triage/__init__.py`:

  ```python
  """Vault triage pipeline: state models, storage, and processing stages."""
  ```

  Create `src/alex/lib/triage/models.py` (the contract's model block with three additions: `Batch.label` for the dominant-cluster label Task 6 assigns and Task 9 renders, `SessionState.corrections`/`SessionState.extra_events` so Task 15 can persist in-batch corrections and reject/repropose ledger events across a crash, and `PendingAreas` at the end, which the contract's apply section assigns to this task):

  ```python
  """Pydantic models for the vault triage pipeline state."""

  from __future__ import annotations

  from typing import Any, Literal

  from pydantic import BaseModel, Field

  Population = Literal["root", "clippings", "meetings", "weekly"]
  ProposalDecision = Literal["area", "resource", "archive", "trash", "skip"]
  FilingDecision = Literal["area", "resource", "archive", "trash"]
  Confidence = Literal["high", "medium", "low"]
  LedgerEventKind = Literal[
      "approve", "reject", "edit", "repropose", "atomic_approve", "atomic_revise"
  ]


  class NoteEvidence(BaseModel):
      path: str  # vault-relative posix path
      title: str
      population: Population
      tags: list[str] = Field(default_factory=list)
      wikilinks: list[str] = Field(default_factory=list)
      snippet: str = ""
      has_highlights: bool = False
      mtime: float = 0.0
      word_count: int = 0


  class Inventory(BaseModel):
      generated: str  # ISO timestamp
      notes: list[NoteEvidence] = Field(default_factory=list)


  class Cluster(BaseModel):
      cluster_id: int
      label: str = ""
      note_paths: list[str] = Field(default_factory=list)


  class Batch(BaseModel):
      batch_id: int
      label: str = ""  # label of the dominant cluster; "misc" for pooled singletons
      note_paths: list[str] = Field(default_factory=list)


  class ClusterMap(BaseModel):
      generated: str
      clusters: list[Cluster] = Field(default_factory=list)
      batches: list[Batch] = Field(default_factory=list)


  class NewAreaProposal(BaseModel):
      slug: str
      name: str
      description: str


  class Proposal(BaseModel):
      note_path: str
      decision: ProposalDecision
      target: str = ""  # area slug | resource topic | archives subfolder
      confidence: Confidence = "low"
      why: str = ""
      alternatives: list[str] = Field(default_factory=list)
      new_area: NewAreaProposal | None = None
      needs_manual: bool = False


  class BatchProposals(BaseModel):
      batch_id: int
      rubric_version: int
      proposals: list[Proposal] = Field(default_factory=list)


  class TriageBlock(BaseModel):
      decision: FilingDecision | None = None
      target: str = ""
      promising: bool = False
      status: Literal["decided", "applied"] | None = None
      decided: str = ""  # YYYY-MM-DD
      applied: str = ""


  class LedgerEvent(BaseModel):
      ts: str
      note: str
      batch: int
      rubric_version: int
      event: LedgerEventKind
      proposal: dict[str, Any] = Field(default_factory=dict)
      correction: dict[str, Any] | None = None
      reason: str = ""


  class Rubric(BaseModel):
      version: int
      text: str  # full markdown body below the frontmatter


  class CatalogEntry(BaseModel):
      slug: str
      name: str
      description: str = ""
      evidence: list[str] = Field(default_factory=list)


  class Catalog(BaseModel):
      areas: list[CatalogEntry] = Field(default_factory=list)
      resource_topics: list[str] = Field(default_factory=list)
      source_mtimes: dict[str, float] = Field(default_factory=dict)


  class AtomicDraft(BaseModel):
      title: str
      body: str
      tags: list[str] = Field(default_factory=list)
      related: list[str] = Field(default_factory=list)  # existing note paths, no [[]]
      source_path: str


  class PlannedMove(BaseModel):
      note_path: str
      destination: str  # vault-relative posix
      decision: FilingDecision
      target: str


  class ApplyPlan(BaseModel):
      moves: list[PlannedMove] = Field(default_factory=list)
      new_areas: list[NewAreaProposal] = Field(default_factory=list)
      skipped: list[str] = Field(default_factory=list)  # human-readable reasons


  class MoveResult(BaseModel):
      note_path: str
      destination: str
      status: Literal["moved", "collision_renamed", "failed", "dry_run"]
      links_rewritten: int = 0
      error: str = ""


  class ApplyReport(BaseModel):
      results: list[MoveResult] = Field(default_factory=list)
      areas_created: list[str] = Field(default_factory=list)


  class PendingDecision(BaseModel):
      proposal: Proposal
      action: LedgerEventKind
      promising: bool = False
      reason: str = ""


  class SessionState(BaseModel):
      batch_id: int
      pending: dict[str, PendingDecision] = Field(default_factory=dict)
      corrections: list[str] = Field(default_factory=list)
      extra_events: list[LedgerEvent] = Field(default_factory=list)


  class PendingAreas(BaseModel):
      areas: list[NewAreaProposal] = Field(default_factory=list)
  ```

- [ ] **Step 5: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_models.py -v
  ```

  Expect `2 passed`.

- [ ] **Step 6: Write the failing storage and paths tests**

  In `tests/test_triage_models.py`, replace the header (docstring plus the single import line) with:

  ```python
  """Tests for triage models, storage helpers, and filesystem layout."""

  import hashlib
  from pathlib import Path

  import yaml

  from alex.lib.triage.models import (
      Inventory,
      NewAreaProposal,
      NoteEvidence,
      PendingAreas,
      Proposal,
      TriageBlock,
  )
  from alex.lib.triage.paths import TriagePaths
  from alex.lib.triage.storage import (
      atomic_write_text,
      read_yaml_model,
      write_yaml_model,
  )
  ```

  Then append these tests at the end of the file:

  ```python
  def test_atomic_write_text_creates_parents_and_leaves_no_temp_file(
      tmp_path: Path,
  ) -> None:
      target = tmp_path / "state" / "deep" / "inventory.yaml"

      atomic_write_text(target, "generated: now\n")

      assert target.read_text(encoding="utf-8") == "generated: now\n"
      assert list(target.parent.iterdir()) == [target]


  def test_atomic_write_text_replaces_existing_content(tmp_path: Path) -> None:
      target = tmp_path / "file.yaml"
      atomic_write_text(target, "first")

      atomic_write_text(target, "second")

      assert target.read_text(encoding="utf-8") == "second"


  def test_read_yaml_model_returns_none_for_missing_file(tmp_path: Path) -> None:
      assert read_yaml_model(tmp_path / "absent.yaml", Inventory) is None


  def test_read_yaml_model_returns_none_for_corrupt_yaml(tmp_path: Path) -> None:
      path = tmp_path / "broken.yaml"
      path.write_text("{unclosed: [", encoding="utf-8")

      assert read_yaml_model(path, Inventory) is None


  def test_read_yaml_model_returns_none_for_wrong_shape(tmp_path: Path) -> None:
      path = tmp_path / "wrong.yaml"
      path.write_text("notes: not-a-list\n", encoding="utf-8")

      assert read_yaml_model(path, Inventory) is None


  def test_yaml_model_roundtrip_preserves_note_evidence(tmp_path: Path) -> None:
      inventory = Inventory(
          generated="2026-07-12T09:00:00",
          notes=[
              NoteEvidence(
                  path="Ideas about spaced repetition.md",
                  title="Ideas about spaced repetition",
                  population="root",
                  tags=["learning"],
                  wikilinks=["areas/learning-science/index"],
                  snippet="Spaced repetition works because recall effort is the point.",
                  has_highlights=True,
                  mtime=123.5,
                  word_count=87,
              )
          ],
      )
      path = tmp_path / "inventory.yaml"

      write_yaml_model(path, inventory)

      assert read_yaml_model(path, Inventory) == inventory


  def test_write_yaml_model_keeps_field_order_and_unicode(tmp_path: Path) -> None:
      pending = PendingAreas(
          areas=[
              NewAreaProposal(
                  slug="cafe-notes",
                  name="Café Notes",
                  description="Notes about café culture",
              )
          ]
      )
      path = tmp_path / "pending-areas.yaml"

      write_yaml_model(path, pending)

      raw = path.read_text(encoding="utf-8")
      assert "Café" in raw
      data = yaml.safe_load(raw)
      assert list(data["areas"][0]) == ["slug", "name", "description"]


  def test_triage_paths_derive_from_vault_root(tmp_path: Path) -> None:
      paths = TriagePaths(vault_root=tmp_path)

      assert paths.state_dir == tmp_path / ".claude" / "triage"
      assert paths.inventory_path == paths.state_dir / "inventory.yaml"
      assert paths.cluster_map_path == paths.state_dir / "cluster-map.yaml"
      assert paths.catalog_path == paths.state_dir / "catalog.yaml"
      assert paths.embeddings_cache_path == paths.state_dir / "embeddings.jsonl"
      assert paths.proposals_dir == paths.state_dir / "proposals"
      assert paths.session_path == paths.state_dir / "session.yaml"
      assert paths.pending_areas_path == paths.state_dir / "pending-areas.yaml"
      assert paths.project_dir == tmp_path / "projects" / "vault-triage"
      assert paths.ledger_path == paths.project_dir / "ledger.jsonl"
      assert paths.rubric_path == paths.project_dir / "rubric.md"
      assert paths.processing_log_path == tmp_path / "_meta" / "processing-log.md"


  def test_triage_lock_path_lives_in_user_cache_keyed_by_vault_root(
      tmp_path: Path,
  ) -> None:
      paths = TriagePaths(vault_root=tmp_path)
      digest = hashlib.sha256(str(tmp_path.resolve()).encode()).hexdigest()[:12]

      assert paths.lock_path == (
          Path.home() / ".cache" / "alex" / f"triage-{digest}.lock"
      )


  def test_triage_lock_path_differs_per_vault(tmp_path: Path) -> None:
      lock_a = TriagePaths(vault_root=tmp_path / "vault-a").lock_path
      lock_b = TriagePaths(vault_root=tmp_path / "vault-b").lock_path

      assert lock_a != lock_b


  def test_proposals_path_encodes_batch_and_rubric_version(tmp_path: Path) -> None:
      paths = TriagePaths(vault_root=tmp_path)

      assert paths.proposals_path(3, 2) == (
          paths.proposals_dir / "batch-003.rubric-v02.yaml"
      )
  ```

- [ ] **Step 7: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_models.py -v
  ```

  Expect a collection error: `ModuleNotFoundError: No module named 'alex.lib.triage.paths'`.

- [ ] **Step 8: Write storage.py and paths.py**

  Create `src/alex/lib/triage/storage.py`:

  ```python
  """Atomic writes and YAML persistence for triage state files."""

  from __future__ import annotations

  from pathlib import Path

  import yaml
  from pydantic import BaseModel, ValidationError


  def atomic_write_text(path: Path, text: str) -> None:
      path.parent.mkdir(parents=True, exist_ok=True)
      temp_path = path.with_suffix(path.suffix + ".tmp")
      temp_path.write_text(text, encoding="utf-8")
      temp_path.replace(path)


  def read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None:
      try:
          raw = path.read_text(encoding="utf-8")
      except FileNotFoundError:
          return None
      try:
          return model_type.model_validate(yaml.safe_load(raw))
      except (yaml.YAMLError, ValidationError):
          # Corrupt or stale cache files are rebuilt, never fatal.
          return None


  def write_yaml_model(path: Path, model: BaseModel) -> None:
      dumped = yaml.safe_dump(
          model.model_dump(mode="json"), sort_keys=False, allow_unicode=True
      )
      atomic_write_text(path, dumped)
  ```

  Create `src/alex/lib/triage/paths.py` (the contract's layout with two amendments: `lock_path` is keyed by a sha256 digest of the resolved vault root so two vaults never contend on one lock, and the `pending_areas_path` property from the contract's apply section is placed after `session_path`):

  ```python
  """Filesystem layout for triage state inside and outside the vault."""

  from __future__ import annotations

  import hashlib
  from dataclasses import dataclass
  from pathlib import Path


  @dataclass(frozen=True)
  class TriagePaths:
      vault_root: Path

      @property
      def state_dir(self) -> Path:
          return self.vault_root / ".claude" / "triage"

      @property
      def inventory_path(self) -> Path:
          return self.state_dir / "inventory.yaml"

      @property
      def cluster_map_path(self) -> Path:
          return self.state_dir / "cluster-map.yaml"

      @property
      def catalog_path(self) -> Path:
          return self.state_dir / "catalog.yaml"

      @property
      def embeddings_cache_path(self) -> Path:
          return self.state_dir / "embeddings.jsonl"

      @property
      def proposals_dir(self) -> Path:
          return self.state_dir / "proposals"

      @property
      def session_path(self) -> Path:
          return self.state_dir / "session.yaml"

      @property
      def pending_areas_path(self) -> Path:
          return self.state_dir / "pending-areas.yaml"

      @property
      def project_dir(self) -> Path:
          return self.vault_root / "projects" / "vault-triage"

      @property
      def ledger_path(self) -> Path:
          return self.project_dir / "ledger.jsonl"

      @property
      def rubric_path(self) -> Path:
          return self.project_dir / "rubric.md"

      @property
      def processing_log_path(self) -> Path:
          return self.vault_root / "_meta" / "processing-log.md"

      @property
      def lock_path(self) -> Path:
          key = str(self.vault_root.resolve()).encode()
          digest = hashlib.sha256(key).hexdigest()[:12]
          return Path.home() / ".cache" / "alex" / f"triage-{digest}.lock"

      def proposals_path(self, batch_id: int, rubric_version: int) -> Path:
          return self.proposals_dir / (
              f"batch-{batch_id:03d}.rubric-v{rubric_version:02d}.yaml"
          )
  ```

- [ ] **Step 9: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_models.py -v
  ```

  Expect `13 passed`.

- [ ] **Step 10: Run lint and typecheck**

  ```bash
  cd /home/alex/code/alex && just lint && uv run mypy
  ```

  Expect both clean (`just lint` also runs `ruff format --check`; the code above is already format-clean).

- [ ] **Step 11: Commit**

  ```bash
  cd /home/alex/code/alex && git add pyproject.toml uv.lock src/alex/lib/triage/__init__.py src/alex/lib/triage/models.py src/alex/lib/triage/storage.py src/alex/lib/triage/paths.py tests/test_triage_models.py && git commit -m "$(cat <<'EOF'
  feat(triage): add state models, yaml storage, and path layout

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 2: Byte-Preserving Frontmatter Editing

**Files:**
- Create: `src/alex/lib/triage/frontmatter.py`
- Test: `tests/test_triage_frontmatter.py`

**Interfaces:**
- Consumes: `from alex.lib.triage.models import TriageBlock` (Task 1).
- Produces (`alex.lib.triage.frontmatter`):
  - `split_frontmatter(text: str) -> tuple[str | None, str]`
  - `assemble_frontmatter(yaml_text: str, body: str) -> str`
  - `read_frontmatter(text: str) -> dict[str, Any]`
  - `replace_top_level_key(text: str, key: str, yaml_block: str | None) -> str`
  - `read_triage_block(text: str) -> TriageBlock | None`
  - `write_triage_block(text: str, block: TriageBlock) -> str`
  - `set_frontmatter_list(text: str, key: str, values: list[str]) -> str`

- [ ] **Step 1: Write the failing split/assemble/replace tests**

  Create `tests/test_triage_frontmatter.py`:

  ```python
  """Tests for surgical frontmatter editing used by the triage pipeline."""

  from alex.lib.triage.frontmatter import (
      assemble_frontmatter,
      read_frontmatter,
      replace_top_level_key,
      split_frontmatter,
  )

  NOTE = (
      "---\n"
      "type: article\n"
      "created: 2026-01-05\n"
      "# reviewed by hand, do not touch\n"
      "tags:\n"
      "  - learning\n"
      "  - spaced-repetition\n"
      "workflow:\n"
      "  highlighted: true\n"
      "---\n"
      "\n"
      "Body with **bold** and ==highlight== marks.\n"
  )


  def test_split_frontmatter_returns_yaml_and_body() -> None:
      yaml_text, body = split_frontmatter("---\ntype: note\n---\nBody\n")

      assert yaml_text == "type: note"
      assert body == "Body\n"


  def test_split_frontmatter_handles_missing_block() -> None:
      assert split_frontmatter("Just text\n") == (None, "Just text\n")


  def test_split_frontmatter_handles_fence_at_end_of_file() -> None:
      yaml_text, body = split_frontmatter("---\ntype: note\n---")

      assert yaml_text == "type: note"
      assert body == ""


  def test_split_frontmatter_ignores_unclosed_fence() -> None:
      text = "---\ntype: note\nno closing fence\n"

      assert split_frontmatter(text) == (None, text)


  def test_assemble_frontmatter_round_trips_split() -> None:
      yaml_text, body = split_frontmatter(NOTE)

      assert yaml_text is not None
      assert assemble_frontmatter(yaml_text, body) == NOTE


  def test_read_frontmatter_parses_nested_keys() -> None:
      frontmatter = read_frontmatter(NOTE)

      assert frontmatter["type"] == "article"
      assert frontmatter["workflow"] == {"highlighted": True}
      assert frontmatter["tags"] == ["learning", "spaced-repetition"]


  def test_read_frontmatter_returns_empty_dict_for_invalid_yaml() -> None:
      assert read_frontmatter("---\n{unclosed: [\n---\nBody\n") == {}


  def test_read_frontmatter_returns_empty_dict_for_non_mapping() -> None:
      assert read_frontmatter("---\n- just\n- a list\n---\nBody\n") == {}


  def test_replace_top_level_key_appends_block_keeping_other_lines_byte_identical() -> (
      None
  ):
      result = replace_top_level_key(NOTE, "triage", "triage:\n  decision: area")

      original_yaml, original_body = split_frontmatter(NOTE)
      new_yaml, new_body = split_frontmatter(result)
      assert new_body == original_body
      assert new_yaml is not None
      assert new_yaml == f"{original_yaml}\ntriage:\n  decision: area"
      assert "# reviewed by hand, do not touch" in result


  def test_replace_top_level_key_removes_old_entry_with_nested_lines() -> None:
      text = (
          "---\n"
          "title: T\n"
          "triage:\n"
          "  decision: area\n"
          "  target: old-target\n"
          "status: keep-me\n"
          "---\n"
          "Body\n"
      )

      result = replace_top_level_key(text, "triage", "triage:\n  decision: trash")

      assert "old-target" not in result
      assert "status: keep-me" in result
      assert result.index("status: keep-me") < result.index("triage:")


  def test_replace_top_level_key_with_none_deletes_entry() -> None:
      text = "---\ntitle: T\ntriage:\n  decision: area\n---\nBody\n"

      result = replace_top_level_key(text, "triage", None)

      assert result == "---\ntitle: T\n---\nBody\n"


  def test_replace_top_level_key_removes_column_zero_list_items() -> None:
      text = "---\ntags:\n- one\n- two\ntitle: T\n---\nBody\n"

      result = replace_top_level_key(text, "tags", None)

      assert result == "---\ntitle: T\n---\nBody\n"


  def test_replace_top_level_key_leaves_similarly_prefixed_keys_alone() -> None:
      text = "---\ntriage-notes: keep\n---\nBody\n"

      result = replace_top_level_key(text, "triage", "triage:\n  promising: true")

      assert "triage-notes: keep" in result


  def test_replace_top_level_key_creates_frontmatter_when_missing() -> None:
      result = replace_top_level_key(
          "Plain body\n", "triage", "triage:\n  promising: true"
      )

      assert result == "---\ntriage:\n  promising: true\n---\nPlain body\n"


  def test_replace_top_level_key_delete_without_frontmatter_is_a_noop() -> None:
      assert replace_top_level_key("Plain body\n", "triage", None) == "Plain body\n"
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_frontmatter.py -v
  ```

  Expect a collection error: `ModuleNotFoundError: No module named 'alex.lib.triage.frontmatter'`.

- [ ] **Step 3: Implement the core frontmatter surgery**

  Create `src/alex/lib/triage/frontmatter.py`:

  ```python
  """Surgical YAML frontmatter editing that preserves every untouched byte.

  Vault notes carry state from several pipelines (workflow blocks, tags,
  comments, hand-written keys). Editing the triage block must never reformat
  or reorder anything else, so edits are line-based splices instead of a
  parse/re-dump roundtrip.
  """

  from __future__ import annotations

  from typing import Any

  import yaml


  def split_frontmatter(text: str) -> tuple[str | None, str]:
      """Return (frontmatter yaml without fences, body after the closing fence)."""
      if not text.startswith("---\n"):
          return None, text
      close = text.find("\n---\n", 3)
      if close >= 0:
          return text[4:close], text[close + 5 :]
      if text.endswith("\n---"):
          return text[4:-4], ""
      return None, text


  def assemble_frontmatter(yaml_text: str, body: str) -> str:
      stripped = yaml_text.rstrip("\n")
      return f"---\n{stripped}\n---\n{body}"


  def read_frontmatter(text: str) -> dict[str, Any]:
      yaml_text, _ = split_frontmatter(text)
      if yaml_text is None:
          return {}
      try:
          data = yaml.safe_load(yaml_text)
      except yaml.YAMLError:
          return {}
      return data if isinstance(data, dict) else {}


  def replace_top_level_key(text: str, key: str, yaml_block: str | None) -> str:
      """Remove the top-level `key:` entry, then append yaml_block at the end.

      yaml_block is the full entry starting with f"{key}:", 2-space indented,
      no trailing newline; None deletes the key. Every other line survives
      byte-identical, comments included. Creates a frontmatter block when the
      file has none.
      """
      yaml_text, body = split_frontmatter(text)
      if yaml_text is None:
          if yaml_block is None:
              return text
          return assemble_frontmatter(yaml_block, text)
      kept: list[str] = []
      in_entry = False
      for line in yaml_text.split("\n"):
          if in_entry and _is_entry_continuation(line):
              continue
          in_entry = False
          if line.startswith(f"{key}:"):
              in_entry = True
              continue
          kept.append(line)
      if yaml_block is not None:
          kept.append(yaml_block)
      return assemble_frontmatter("\n".join(kept), body)


  def _is_entry_continuation(line: str) -> bool:
      return bool(line) and (line[0] in " \t" or line.startswith("- "))
  ```

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_frontmatter.py -v
  ```

  Expect `15 passed`.

- [ ] **Step 5: Write the failing triage-block and list tests**

  In `tests/test_triage_frontmatter.py`, replace the import block:

  ```python
  from alex.lib.triage.frontmatter import (
      assemble_frontmatter,
      read_frontmatter,
      replace_top_level_key,
      split_frontmatter,
  )
  ```

  with:

  ```python
  from alex.lib.triage.frontmatter import (
      assemble_frontmatter,
      read_frontmatter,
      read_triage_block,
      replace_top_level_key,
      set_frontmatter_list,
      split_frontmatter,
      write_triage_block,
  )
  from alex.lib.triage.models import TriageBlock
  ```

  Then append these tests at the end of the file:

  ```python
  def test_write_triage_block_then_read_round_trips() -> None:
      block = TriageBlock(
          decision="area",
          target="learning-science",
          status="decided",
          decided="2026-07-12",
      )

      result = write_triage_block(NOTE, block)

      assert read_triage_block(result) == block
      assert "Body with **bold** and ==highlight== marks." in result


  def test_write_triage_block_keeps_body_and_other_keys_byte_identical() -> None:
      original_yaml, original_body = split_frontmatter(NOTE)

      result = write_triage_block(NOTE, TriageBlock(decision="area", target="x"))

      new_yaml, new_body = split_frontmatter(result)
      assert new_body == original_body
      assert original_yaml is not None
      assert new_yaml is not None
      assert new_yaml.startswith(original_yaml)


  def test_write_triage_block_emits_only_non_default_fields() -> None:
      result = write_triage_block(
          "---\ntitle: T\n---\nBody\n", TriageBlock(promising=True)
      )

      yaml_text, _ = split_frontmatter(result)
      assert yaml_text == "title: T\ntriage:\n  promising: true"


  def test_write_triage_block_replaces_previous_block() -> None:
      first = write_triage_block(NOTE, TriageBlock(promising=True))

      second = write_triage_block(
          first, TriageBlock(decision="trash", status="decided", decided="2026-07-12")
      )

      expected = TriageBlock(decision="trash", status="decided", decided="2026-07-12")
      assert read_triage_block(second) == expected
      assert second.count("triage:") == 1
      assert "promising" not in second


  def test_write_triage_block_creates_frontmatter_on_bare_note() -> None:
      result = write_triage_block("Just a body\n", TriageBlock(promising=True))

      assert result == "---\ntriage:\n  promising: true\n---\nJust a body\n"


  def test_write_triage_block_with_all_defaults_deletes_the_key() -> None:
      with_block = write_triage_block(NOTE, TriageBlock(promising=True))

      result = write_triage_block(with_block, TriageBlock())

      assert result == NOTE
      assert read_triage_block(result) is None


  def test_read_triage_block_returns_none_without_triage_key() -> None:
      assert read_triage_block(NOTE) is None


  def test_read_triage_block_treats_null_triage_value_as_defaults() -> None:
      text = "---\ntitle: T\ntriage:\n---\nBody\n"

      assert read_triage_block(text) == TriageBlock()


  def test_read_triage_block_accepts_hand_edited_unquoted_dates() -> None:
      text = (
          "---\n"
          "triage:\n"
          "  decision: archive\n"
          "  status: applied\n"
          "  decided: 2026-07-01\n"
          "  applied: 2026-07-12\n"
          "---\n"
          "Body\n"
      )

      block = read_triage_block(text)

      assert block is not None
      assert block.decided == "2026-07-01"
      assert block.applied == "2026-07-12"


  def test_set_frontmatter_list_renders_quoted_wikilinks() -> None:
      values = [
          "[[resources/permanent-notes/Spacing beats cramming]]",
          "[[resources/permanent-notes/Testing is learning]]",
      ]

      result = set_frontmatter_list(NOTE, "permanent_notes", values)

      assert read_frontmatter(result)["permanent_notes"] == values
      yaml_text, _ = split_frontmatter(result)
      assert yaml_text is not None
      assert '  - "[[resources/permanent-notes/Spacing beats cramming]]"' in yaml_text


  def test_set_frontmatter_list_with_empty_values_writes_empty_list() -> None:
      result = set_frontmatter_list(NOTE, "permanent_notes", [])

      assert read_frontmatter(result)["permanent_notes"] == []
  ```

- [ ] **Step 6: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_frontmatter.py -v
  ```

  Expect a collection error: `ImportError: cannot import name 'read_triage_block' from 'alex.lib.triage.frontmatter'`.

- [ ] **Step 7: Implement the triage block and list writers**

  In `src/alex/lib/triage/frontmatter.py`, replace the import section:

  ```python
  from __future__ import annotations

  from typing import Any

  import yaml
  ```

  with:

  ```python
  from __future__ import annotations

  import json
  from datetime import date
  from typing import Any

  import yaml

  from alex.lib.triage.models import TriageBlock
  ```

  Then append at the end of the file:

  ```python
  def read_triage_block(text: str) -> TriageBlock | None:
      frontmatter = read_frontmatter(text)
      if "triage" not in frontmatter:
          return None
      raw = frontmatter["triage"]
      if raw is None:
          # A bare `triage:` line (hand edit, or a stray data-free block)
          # parses as YAML null; treat it as an all-default block.
          return TriageBlock()
      if isinstance(raw, dict):
          # yaml parses bare dates like `decided: 2026-07-12` into date
          # objects; the model stores plain strings.
          raw = {
              key: value.isoformat() if isinstance(value, date) else value
              for key, value in raw.items()
          }
      return TriageBlock.model_validate(raw)


  def write_triage_block(text: str, block: TriageBlock) -> str:
      lines = ["triage:"]
      if block.decision is not None:
          lines.append(f"  decision: {block.decision}")
      if block.target:
          lines.append(f"  target: {block.target}")
      if block.promising:
          lines.append("  promising: true")
      if block.status is not None:
          lines.append(f"  status: {block.status}")
      if block.decided:
          lines.append(f"  decided: {block.decided}")
      if block.applied:
          lines.append(f"  applied: {block.applied}")
      if len(lines) == 1:
          # An all-default block would serialize as a bare `triage:` key
          # (YAML null); delete the key instead of writing a data-free block.
          return replace_top_level_key(text, "triage", None)
      return replace_top_level_key(text, "triage", "\n".join(lines))


  def set_frontmatter_list(text: str, key: str, values: list[str]) -> str:
      if not values:
          return replace_top_level_key(text, key, f"{key}: []")
      lines = [f"{key}:"]
      lines.extend(f"  - {json.dumps(value)}" for value in values)
      return replace_top_level_key(text, key, "\n".join(lines))
  ```

  Note: `read_triage_block` deliberately coerces YAML date objects to ISO strings before validation. `write_triage_block` renders dates unquoted (matching the spec's frontmatter example), YAML parses those back as `datetime.date`, and the model stores `str`; without the coercion the tool would choke on its own output. The all-default path matters too: writing an all-default block deletes the `triage:` key entirely (a bare `triage:` key parses as YAML null and would otherwise poison every later read), and `read_triage_block` maps a null value to `TriageBlock()` so hand-emptied blocks stay harmless. Genuinely corrupt blocks still raise `ValidationError` loudly, per the contract.

- [ ] **Step 8: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_frontmatter.py -v
  ```

  Expect `26 passed`.

- [ ] **Step 9: Run lint and typecheck**

  ```bash
  cd /home/alex/code/alex && just lint && uv run mypy
  ```

  Expect both clean.

- [ ] **Step 10: Commit**

  ```bash
  cd /home/alex/code/alex && git add src/alex/lib/triage/frontmatter.py tests/test_triage_frontmatter.py && git commit -m "$(cat <<'EOF'
  feat(triage): add byte-preserving frontmatter editing

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3: Triage Model Roles in the LLM Layer

Finding (checked against the repo): the existing role resolvers live in `src/alex/lib/llm.py`, constants at lines 21-59 and resolver functions at lines 62-126 (`resolve_fast_summary_model` through `resolve_summary_max_workers`, immediately before `class LlmError` at line 129). `tests/test_llm.py` EXISTS (579 lines, 27 collected tests), so per the contract the resolver tests go into `tests/test_llm.py`, and `tests/test_triage_llm_roles.py` is NOT created.

**Files:**
- Modify: `src/alex/lib/llm.py` (insert after `resolve_summary_max_workers`, which ends at line 126, before `class LlmError` at line 129)
- Test: Modify `tests/test_llm.py` (import block at lines 13-45; new tests appended at end of file, currently line 579)

**Interfaces:**
- Consumes: nothing new (follows the existing resolver pattern in `llm.py`).
- Produces (`alex.lib.llm`): constants `DEFAULT_TRIAGE_LABEL_MODEL`, `DEFAULT_TRIAGE_PROPOSAL_MODEL`, `DEFAULT_TRIAGE_ATOMIC_MODEL`, `DEFAULT_TRIAGE_DISTILL_MODEL`, `DEFAULT_TRIAGE_CLUSTER_THRESHOLD`, `DEFAULT_TRIAGE_BATCH_SIZE`, `TRIAGE_LABEL_MODEL_ENV`, `TRIAGE_PROPOSAL_MODEL_ENV`, `TRIAGE_ATOMIC_MODEL_ENV`, `TRIAGE_DISTILL_MODEL_ENV`, `TRIAGE_CLUSTER_THRESHOLD_ENV`, `TRIAGE_BATCH_SIZE_ENV`; functions `resolve_triage_label_model() -> str`, `resolve_triage_proposal_model() -> str`, `resolve_triage_atomic_model() -> str`, `resolve_triage_distill_model() -> str`, `resolve_triage_cluster_threshold() -> float`, `resolve_triage_batch_size() -> int`

- [ ] **Step 1: Write the failing resolver tests**

  In `tests/test_llm.py`, replace the `from alex.lib.llm import (...)` block (lines 13-45) with (the twelve `*TRIAGE*` constants and six `resolve_triage_*` functions are the additions; ordering follows ruff isort's order-by-type convention already used in this block):

  ```python
  from alex.lib.llm import (
      CHUNK_GRAPH_MAX_CLAIMS_ENV,
      DEFAULT_CHUNK_GRAPH_MAX_CLAIMS,
      DEFAULT_EMBEDDING_MODEL,
      DEFAULT_FAST_SUMMARY_MODEL,
      DEFAULT_FINAL_SUMMARY_MODEL,
      DEFAULT_GRAPH_MAX_CLAIMS,
      DEFAULT_SOURCE_CLAIMS_PER_SECTION,
      DEFAULT_TRANSCRIPTION_MODEL,
      DEFAULT_TRIAGE_ATOMIC_MODEL,
      DEFAULT_TRIAGE_BATCH_SIZE,
      DEFAULT_TRIAGE_CLUSTER_THRESHOLD,
      DEFAULT_TRIAGE_DISTILL_MODEL,
      DEFAULT_TRIAGE_LABEL_MODEL,
      DEFAULT_TRIAGE_PROPOSAL_MODEL,
      EMBEDDING_MODEL_ENV,
      FAST_SUMMARY_MODEL_ENV,
      FINAL_SUMMARY_MODEL_ENV,
      GRAPH_MAX_CLAIMS_ENV,
      SOURCE_CLAIMS_PER_SECTION_ENV,
      SUMMARY_MAX_WORKERS_ENV,
      TRANSCRIPTION_MODEL_ENV,
      TRIAGE_ATOMIC_MODEL_ENV,
      TRIAGE_BATCH_SIZE_ENV,
      TRIAGE_CLUSTER_THRESHOLD_ENV,
      TRIAGE_DISTILL_MODEL_ENV,
      TRIAGE_LABEL_MODEL_ENV,
      TRIAGE_PROPOSAL_MODEL_ENV,
      AudioTranscript,
      LiteLlmCompleter,
      LiteLlmEmbedder,
      LiteLlmTranscriber,
      LlmError,
      TranscriptSegment,
      complete_all,
      ordered_parallel_map,
      resolve_chunk_graph_max_claims,
      resolve_embedding_model,
      resolve_fast_summary_model,
      resolve_final_summary_model,
      resolve_graph_max_claims,
      resolve_source_claims_per_section,
      resolve_summary_max_workers,
      resolve_transcription_model,
      resolve_triage_atomic_model,
      resolve_triage_batch_size,
      resolve_triage_cluster_threshold,
      resolve_triage_distill_model,
      resolve_triage_label_model,
      resolve_triage_proposal_model,
  )
  ```

  Then append at the end of `tests/test_llm.py`:

  ```python
  def test_triage_models_default_per_role(monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.delenv(TRIAGE_LABEL_MODEL_ENV, raising=False)
      monkeypatch.delenv(TRIAGE_PROPOSAL_MODEL_ENV, raising=False)
      monkeypatch.delenv(TRIAGE_ATOMIC_MODEL_ENV, raising=False)
      monkeypatch.delenv(TRIAGE_DISTILL_MODEL_ENV, raising=False)

      assert resolve_triage_label_model() == DEFAULT_TRIAGE_LABEL_MODEL
      assert resolve_triage_proposal_model() == DEFAULT_TRIAGE_PROPOSAL_MODEL
      assert resolve_triage_atomic_model() == DEFAULT_TRIAGE_ATOMIC_MODEL
      assert resolve_triage_distill_model() == DEFAULT_TRIAGE_DISTILL_MODEL
      assert resolve_triage_label_model() == "anthropic/claude-haiku-4-5"
      assert resolve_triage_proposal_model() == "anthropic/claude-sonnet-4-6"
      assert resolve_triage_distill_model() == "anthropic/claude-opus-4-8"


  def test_triage_models_can_be_swapped_via_environment(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      monkeypatch.setenv(TRIAGE_LABEL_MODEL_ENV, "gemini/gemini-2.5-flash")
      monkeypatch.setenv(TRIAGE_PROPOSAL_MODEL_ENV, "openai/gpt-5")
      monkeypatch.setenv(TRIAGE_ATOMIC_MODEL_ENV, "openai/gpt-5-mini")
      monkeypatch.setenv(TRIAGE_DISTILL_MODEL_ENV, "anthropic/claude-opus-4-8")

      assert resolve_triage_label_model() == "gemini/gemini-2.5-flash"
      assert resolve_triage_proposal_model() == "openai/gpt-5"
      assert resolve_triage_atomic_model() == "openai/gpt-5-mini"
      assert resolve_triage_distill_model() == "anthropic/claude-opus-4-8"


  def test_triage_clustering_knobs_default_and_override(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      monkeypatch.delenv(TRIAGE_CLUSTER_THRESHOLD_ENV, raising=False)
      monkeypatch.delenv(TRIAGE_BATCH_SIZE_ENV, raising=False)
      assert DEFAULT_TRIAGE_CLUSTER_THRESHOLD == 0.45
      assert DEFAULT_TRIAGE_BATCH_SIZE == 40
      assert resolve_triage_cluster_threshold() == DEFAULT_TRIAGE_CLUSTER_THRESHOLD
      assert resolve_triage_batch_size() == DEFAULT_TRIAGE_BATCH_SIZE

      monkeypatch.setenv(TRIAGE_CLUSTER_THRESHOLD_ENV, "0.6")
      monkeypatch.setenv(TRIAGE_BATCH_SIZE_ENV, "25")
      assert resolve_triage_cluster_threshold() == 0.6
      assert resolve_triage_batch_size() == 25
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_llm.py -v
  ```

  Expect a collection error: `ImportError: cannot import name 'DEFAULT_TRIAGE_ATOMIC_MODEL' from 'alex.lib.llm'`.

- [ ] **Step 3: Add the triage roles to llm.py**

  In `src/alex/lib/llm.py`, find this function (lines 119-126, the last resolver before `class LlmError`):

  ```python
  def resolve_summary_max_workers() -> int:
      raw = os.getenv(SUMMARY_MAX_WORKERS_ENV)
      if raw is None:
          return 4
      value = int(raw)
      if value <= 0:
          raise ValueError(f"{SUMMARY_MAX_WORKERS_ENV} must be positive.")
      return value
  ```

  and insert directly after it (two blank lines above and below, keeping the contract block contiguous and verbatim):

  ```python
  DEFAULT_TRIAGE_LABEL_MODEL = "anthropic/claude-haiku-4-5"
  DEFAULT_TRIAGE_PROPOSAL_MODEL = "anthropic/claude-sonnet-4-6"
  DEFAULT_TRIAGE_ATOMIC_MODEL = "anthropic/claude-sonnet-4-6"
  DEFAULT_TRIAGE_DISTILL_MODEL = "anthropic/claude-opus-4-8"
  DEFAULT_TRIAGE_CLUSTER_THRESHOLD = 0.45
  DEFAULT_TRIAGE_BATCH_SIZE = 40
  TRIAGE_LABEL_MODEL_ENV = "ALEX_TRIAGE_LABEL_MODEL"
  TRIAGE_PROPOSAL_MODEL_ENV = "ALEX_TRIAGE_PROPOSAL_MODEL"
  TRIAGE_ATOMIC_MODEL_ENV = "ALEX_TRIAGE_ATOMIC_MODEL"
  TRIAGE_DISTILL_MODEL_ENV = "ALEX_TRIAGE_DISTILL_MODEL"
  TRIAGE_CLUSTER_THRESHOLD_ENV = "ALEX_TRIAGE_CLUSTER_THRESHOLD"
  TRIAGE_BATCH_SIZE_ENV = "ALEX_TRIAGE_BATCH_SIZE"


  def resolve_triage_label_model() -> str:
      return os.getenv(TRIAGE_LABEL_MODEL_ENV) or DEFAULT_TRIAGE_LABEL_MODEL


  def resolve_triage_proposal_model() -> str:
      return os.getenv(TRIAGE_PROPOSAL_MODEL_ENV) or DEFAULT_TRIAGE_PROPOSAL_MODEL


  def resolve_triage_atomic_model() -> str:
      return os.getenv(TRIAGE_ATOMIC_MODEL_ENV) or DEFAULT_TRIAGE_ATOMIC_MODEL


  def resolve_triage_distill_model() -> str:
      return os.getenv(TRIAGE_DISTILL_MODEL_ENV) or DEFAULT_TRIAGE_DISTILL_MODEL


  def resolve_triage_cluster_threshold() -> float:
      raw = os.getenv(TRIAGE_CLUSTER_THRESHOLD_ENV)
      return float(raw) if raw else DEFAULT_TRIAGE_CLUSTER_THRESHOLD


  def resolve_triage_batch_size() -> int:
      raw = os.getenv(TRIAGE_BATCH_SIZE_ENV)
      return int(raw) if raw else DEFAULT_TRIAGE_BATCH_SIZE
  ```

  The next line after the inserted block must remain `class LlmError(RuntimeError):` (with the standard two blank lines above it).

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_llm.py -v
  ```

  Expect `30 passed` (27 pre-existing plus the 3 new tests).

- [ ] **Step 5: Run lint and typecheck**

  ```bash
  cd /home/alex/code/alex && just lint && uv run mypy
  ```

  Expect both clean.

- [ ] **Step 6: Commit**

  ```bash
  cd /home/alex/code/alex && git add src/alex/lib/llm.py tests/test_llm.py && git commit -m "$(cat <<'EOF'
  feat(triage): add triage model roles and knobs to the llm layer

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```
### Task 4: Area catalog (catalog.py)

**Files:**
- Create: `src/alex/lib/triage/catalog.py`
- Test: `tests/test_triage_catalog.py`

**Interfaces:**
- Consumes (Task 1, `alex.lib.triage.models`): `Catalog(areas: list[CatalogEntry], resource_topics: list[str], source_mtimes: dict[str, float])`, `CatalogEntry(slug: str, name: str, description: str = "", evidence: list[str] = ...)`.
- Consumes (Task 1, `alex.lib.triage.paths`): `TriagePaths(vault_root: Path)` with `.catalog_path` and `.vault_root`.
- Consumes (Task 1, `alex.lib.triage.storage`): `read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None` (None on missing or corrupt), `write_yaml_model(path: Path, model: BaseModel) -> None`.
- Consumes (Task 2, `alex.lib.triage.frontmatter`): `read_frontmatter(text: str) -> dict[str, Any]`, `split_frontmatter(text: str) -> tuple[str | None, str]`.
- Produces (used by Tasks 9, 15, 17):
  - `build_catalog(vault_root: Path) -> Catalog`
  - `load_or_build_catalog(paths: TriagePaths) -> Catalog`
  - `catalog_prompt_text(catalog: Catalog) -> str`

Resolved ambiguity: "any recorded mtime differs" is implemented as full-map equality between the cached `source_mtimes` and a freshly computed map. That also catches a newly created area index (a key that was never recorded) and a deleted one, not just touched files.

- [ ] **Step 1: Write the failing tests for build_catalog and catalog_prompt_text** - create `tests/test_triage_catalog.py`:

```python
"""Catalog derivation from areas/*/index.md and resources/ topic folders."""

from pathlib import Path

from alex.lib.triage.catalog import build_catalog, catalog_prompt_text
from alex.lib.triage.models import Catalog, CatalogEntry


def write_area_index(
    vault: Path,
    slug: str,
    *,
    description: str,
    name: str | None = None,
    evidence: list[str] | None = None,
) -> Path:
    index = vault / "areas" / slug / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: area",
        "created: 2026-06-05",
        f"description: {description}",
        "---",
        "",
    ]
    if name is not None:
        lines.extend([f"# {name}", ""])
    if evidence is not None:
        lines.extend(["## Discovery Evidence", ""])
        lines.extend(f"- {bullet}" for bullet in evidence)
        lines.extend(["", "## Notes", "", "- [[A filed note]]"])
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index


def test_build_catalog_reads_slug_name_description_and_evidence(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(
        vault,
        "organizational-design",
        description="How teams coordinate work across boundaries",
        name="Organizational Design",
        evidence=[
            "[[Meeting with platform team]] raised ownership boundaries",
            "14 root notes reference team topology tradeoffs",
        ],
    )
    write_area_index(vault, "learning-science", description="How people learn")

    catalog = build_catalog(vault)

    assert [entry.slug for entry in catalog.areas] == [
        "learning-science",
        "organizational-design",
    ]
    org = catalog.areas[1]
    assert org.name == "Organizational Design"
    assert org.description == "How teams coordinate work across boundaries"
    assert org.evidence == [
        "[[Meeting with platform team]] raised ownership boundaries",
        "14 root notes reference team topology tradeoffs",
    ]
    fallback = catalog.areas[0]
    assert fallback.name == "learning-science"
    assert fallback.evidence == []


def test_build_catalog_lists_resource_dirs_and_skips_files_and_dotdirs(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / "resources" / "permanent-notes").mkdir(parents=True)
    (vault / "resources" / "learning-science").mkdir()
    (vault / "resources" / ".obsidian-cache").mkdir()
    (vault / "resources" / "index.md").write_text("# Resources\n", encoding="utf-8")

    catalog = build_catalog(vault)

    assert catalog.resource_topics == ["learning-science", "permanent-notes"]
    assert catalog.areas == []


def test_build_catalog_records_source_mtimes_for_cache_invalidation(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    index = write_area_index(vault, "writing", description="Craft of writing")
    (vault / "resources" / "books").mkdir(parents=True)

    catalog = build_catalog(vault)

    assert catalog.source_mtimes == {
        "areas/writing/index.md": index.stat().st_mtime,
        "resources": (vault / "resources").stat().st_mtime,
    }


def test_build_catalog_handles_a_vault_without_areas_or_resources(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    assert build_catalog(vault) == Catalog()


def test_catalog_prompt_text_lists_areas_then_resource_topics() -> None:
    catalog = Catalog(
        areas=[
            CatalogEntry(
                slug="writing",
                name="Writing",
                description="Craft of writing",
            )
        ],
        resource_topics=["books", "permanent-notes"],
    )

    assert catalog_prompt_text(catalog) == (
        "## Areas\n"
        "- writing: Craft of writing\n"
        "\n"
        "## Resource topics\n"
        "- books\n"
        "- permanent-notes"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_catalog.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.catalog'`.

- [ ] **Step 3: Write the implementation** - create `src/alex/lib/triage/catalog.py`:

```python
"""Live area and resource catalog derived from the vault's PARA folders."""

from __future__ import annotations

from pathlib import Path

from alex.lib.triage.frontmatter import read_frontmatter, split_frontmatter
from alex.lib.triage.models import Catalog, CatalogEntry

DISCOVERY_EVIDENCE_HEADING = "## Discovery Evidence"


def build_catalog(vault_root: Path) -> Catalog:
    areas = [
        _catalog_entry(index_path)
        for index_path in sorted((vault_root / "areas").glob("*/index.md"))
    ]
    resources_dir = vault_root / "resources"
    resource_topics: list[str] = []
    if resources_dir.is_dir():
        resource_topics = sorted(
            child.name
            for child in resources_dir.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )
    return Catalog(
        areas=areas,
        resource_topics=resource_topics,
        source_mtimes=_source_mtimes(vault_root),
    )


def catalog_prompt_text(catalog: Catalog) -> str:
    lines = ["## Areas"]
    lines.extend(f"- {entry.slug}: {entry.description}" for entry in catalog.areas)
    lines.extend(["", "## Resource topics"])
    lines.extend(f"- {topic}" for topic in catalog.resource_topics)
    return "\n".join(lines)


def _catalog_entry(index_path: Path) -> CatalogEntry:
    text = index_path.read_text(encoding="utf-8")
    slug = index_path.parent.name
    description = read_frontmatter(text).get("description")
    return CatalogEntry(
        slug=slug,
        name=_first_heading(text) or slug,
        description=str(description) if description else "",
        evidence=_discovery_evidence(text),
    )


def _source_mtimes(vault_root: Path) -> dict[str, float]:
    mtimes = {
        index_path.relative_to(vault_root).as_posix(): index_path.stat().st_mtime
        for index_path in sorted((vault_root / "areas").glob("*/index.md"))
    }
    resources_dir = vault_root / "resources"
    if resources_dir.is_dir():
        mtimes["resources"] = resources_dir.stat().st_mtime
    return mtimes


def _first_heading(text: str) -> str:
    _, body = split_frontmatter(text)
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _discovery_evidence(text: str) -> list[str]:
    _, body = split_frontmatter(text)
    bullets: list[str] = []
    in_section = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line == DISCOVERY_EVIDENCE_HEADING:
            in_section = True
        elif in_section and line.startswith("## "):
            break
        elif in_section and line.startswith("- "):
            bullets.append(line[2:].strip())
    return bullets
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_catalog.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Write the failing tests for the mtime-invalidated cache** - in `tests/test_triage_catalog.py`, replace the import block at the top with:

```python
import os
from pathlib import Path

from alex.lib.triage.catalog import (
    build_catalog,
    catalog_prompt_text,
    load_or_build_catalog,
)
from alex.lib.triage.models import Catalog, CatalogEntry
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.storage import read_yaml_model, write_yaml_model
```

and append at the end of the file:

```python
def test_load_or_build_catalog_builds_and_writes_cache_when_missing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)

    catalog = load_or_build_catalog(paths)

    assert [entry.slug for entry in catalog.areas] == ["writing"]
    assert read_yaml_model(paths.catalog_path, Catalog) == catalog


def test_load_or_build_catalog_returns_cache_when_sources_are_unchanged(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)
    load_or_build_catalog(paths)

    cached = read_yaml_model(paths.catalog_path, Catalog)
    assert cached is not None
    cached.areas[0].description = "sentinel only present in the cache"
    write_yaml_model(paths.catalog_path, cached)

    catalog = load_or_build_catalog(paths)

    assert catalog.areas[0].description == "sentinel only present in the cache"


def test_load_or_build_catalog_rebuilds_when_an_index_mtime_changes(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    index = write_area_index(vault, "writing", description="Old description")
    paths = TriagePaths(vault_root=vault)
    load_or_build_catalog(paths)

    write_area_index(vault, "writing", description="New description")
    bumped = index.stat().st_mtime + 10
    os.utime(index, (bumped, bumped))

    catalog = load_or_build_catalog(paths)

    assert catalog.areas[0].description == "New description"
    refreshed = read_yaml_model(paths.catalog_path, Catalog)
    assert refreshed is not None
    assert refreshed.areas[0].description == "New description"


def test_load_or_build_catalog_rebuilds_when_a_new_area_appears(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)
    load_or_build_catalog(paths)

    write_area_index(vault, "learning-science", description="How people learn")

    catalog = load_or_build_catalog(paths)

    assert [entry.slug for entry in catalog.areas] == ["learning-science", "writing"]


def test_load_or_build_catalog_rebuilds_when_cache_is_corrupt(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_area_index(vault, "writing", description="Craft of writing")
    paths = TriagePaths(vault_root=vault)
    paths.catalog_path.parent.mkdir(parents=True)
    paths.catalog_path.write_text("{broken yaml: [", encoding="utf-8")

    catalog = load_or_build_catalog(paths)

    assert [entry.slug for entry in catalog.areas] == ["writing"]
```

- [ ] **Step 6: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_catalog.py -v
```

Expected: collection error, `ImportError: cannot import name 'load_or_build_catalog' from 'alex.lib.triage.catalog'`.

- [ ] **Step 7: Write the implementation** - in `src/alex/lib/triage/catalog.py`, replace the two `alex.lib.triage` imports with:

```python
from alex.lib.triage.frontmatter import read_frontmatter, split_frontmatter
from alex.lib.triage.models import Catalog, CatalogEntry
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.storage import read_yaml_model, write_yaml_model
```

and insert this function immediately after `build_catalog`:

```python
def load_or_build_catalog(paths: TriagePaths) -> Catalog:
    cached = read_yaml_model(paths.catalog_path, Catalog)
    current = _source_mtimes(paths.vault_root)
    if cached is not None and cached.source_mtimes == current:
        return cached
    catalog = build_catalog(paths.vault_root)
    write_yaml_model(paths.catalog_path, catalog)
    return catalog
```

- [ ] **Step 8: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_catalog.py -v
```

Expected: 10 passed.

- [ ] **Step 9: Run just lint and mypy, expecting clean**

```bash
just lint
uv run mypy
```

Expected: ruff check and format check pass with no findings; mypy prints `Success: no issues found`.

- [ ] **Step 10: Commit**

```bash
git add src/alex/lib/triage/catalog.py tests/test_triage_catalog.py
git commit -m "feat(triage): build area catalog with mtime-invalidated cache

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 5: Inventory scan (inventory.py)

**Files:**
- Create: `src/alex/lib/triage/inventory.py`
- Test: `tests/test_triage_inventory.py`

**Interfaces:**
- Consumes (Task 1, `alex.lib.triage.models`): `Inventory(generated: str, notes: list[NoteEvidence])`, `NoteEvidence(path, title, population, tags, wikilinks, snippet, has_highlights, mtime, word_count)`, `Population = Literal["root", "clippings", "meetings", "weekly"]`.
- Consumes (Task 2, `alex.lib.triage.frontmatter`): `read_frontmatter(text: str) -> dict[str, Any]`, `split_frontmatter(text: str) -> tuple[str | None, str]`.
- Produces (used by Tasks 6, 9, 12, 13, 17):
  - `POPULATION_DIRS: dict[Population, str]`
  - `MOVABLE_POPULATIONS: frozenset[Population]`
  - `discover_population_files(vault_root: Path) -> list[tuple[Population, Path]]`
  - `is_eligible(fm: dict[str, Any]) -> bool`
  - `extract_evidence(vault_root: Path, md_path: Path, population: Population) -> NoteEvidence`
  - `build_inventory(vault_root: Path, previous: Inventory | None) -> Inventory`

Resolved ambiguities: `NoteEvidence.title` is the frontmatter `title` when it is a non-empty string, else the filename stem. `Inventory.generated` is stamped internally with `datetime.now(UTC).isoformat()` because the contract signature takes no timestamp. A scalar `tags: foo` string becomes `["foo"]`. When mtime is unchanged, the prior evidence is reused without re-reading the file at all: the prior entry proves the note was eligible, and any frontmatter change (including a written triage block) bumps mtime. Eligibility rule for `workflow:` frontmatter: a dict containing ANY truthy value marks the note ineligible (mid-flight or terminal in the old pipeline, triage must not touch it); an all-false or empty workflow dict stays eligible.

- [ ] **Step 1: Write the failing tests for discovery and eligibility** - create `tests/test_triage_inventory.py`:

```python
"""Discovery, eligibility, and evidence extraction over a fixture vault."""

from pathlib import Path

from alex.lib.triage.inventory import (
    MOVABLE_POPULATIONS,
    discover_population_files,
    is_eligible,
)


def write_note(
    path: Path, *, frontmatter: str = "", body: str = "A note body."
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{frontmatter}\n---\n\n{body}\n" if frontmatter else f"{body}\n"
    path.write_text(text, encoding="utf-8")
    return path


def test_discover_scans_root_nonrecursively_and_population_dirs_recursively(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    write_note(vault / "Loose idea.md")
    write_note(vault / "areas" / "writing" / "index.md")
    write_note(vault / "Clippings" / "2026" / "Saved article.md")
    write_note(vault / "Meetings" / "Platform sync.md")
    write_note(vault / "Weekly" / "2026-W27.md")
    write_note(vault / ".hidden draft.md")
    (vault / "Symlinked.md").symlink_to(vault / "Loose idea.md")

    discovered = discover_population_files(vault)

    assert discovered == [
        ("root", vault / "Loose idea.md"),
        ("clippings", vault / "Clippings" / "2026" / "Saved article.md"),
        ("meetings", vault / "Meetings" / "Platform sync.md"),
        ("weekly", vault / "Weekly" / "2026-W27.md"),
    ]


def test_movable_populations_are_root_and_clippings() -> None:
    assert MOVABLE_POPULATIONS == frozenset({"root", "clippings"})


def test_is_eligible_skips_processed_notes() -> None:
    assert is_eligible({"processed": True}) is False
    assert is_eligible({"processed": False}) is True
    assert is_eligible({}) is True


def test_is_eligible_skips_notes_with_a_triage_decision() -> None:
    assert is_eligible({"triage": {"decision": "area", "target": "writing"}}) is False
    assert is_eligible({"triage": {"promising": True}}) is True


def test_is_eligible_skips_notes_with_any_workflow_state() -> None:
    assert is_eligible({"workflow": {"extracted": True}}) is False
    assert is_eligible({"workflow": {"extracted": "2026-07-01"}}) is False
    assert is_eligible({"workflow": {"highlighted": True}}) is False
    assert is_eligible({"workflow": {"processed": True}}) is False
    assert is_eligible({"workflow": {"highlighted": False, "extracted": False}}) is True
    assert is_eligible({"workflow": {}}) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_inventory.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.inventory'`.

- [ ] **Step 3: Write the implementation** - create `src/alex/lib/triage/inventory.py`:

```python
"""Note discovery, eligibility, and evidence extraction for the triage sweep."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alex.lib.triage.models import Population

POPULATION_DIRS: dict[Population, str] = {
    "clippings": "Clippings",
    "meetings": "Meetings",
    "weekly": "Weekly",
}
MOVABLE_POPULATIONS: frozenset[Population] = frozenset({"root", "clippings"})


def discover_population_files(vault_root: Path) -> list[tuple[Population, Path]]:
    files: list[tuple[Population, Path]] = []
    for path in sorted(vault_root.glob("*.md")):
        if _is_note(path, vault_root):
            files.append(("root", path))
    for population, dir_name in POPULATION_DIRS.items():
        for path in sorted((vault_root / dir_name).rglob("*.md")):
            if _is_note(path, vault_root):
                files.append((population, path))
    return files


def is_eligible(fm: dict[str, Any]) -> bool:
    if fm.get("processed") is True:
        return False
    triage = fm.get("triage")
    if isinstance(triage, dict) and triage.get("decision"):
        return False
    workflow = fm.get("workflow")
    if isinstance(workflow, dict) and any(workflow.values()):
        return False
    return True


def _is_note(path: Path, vault_root: Path) -> bool:
    if path.is_symlink():
        return False
    parts = path.relative_to(vault_root).parts
    return all(not part.startswith(".") for part in parts)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_inventory.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Write the failing tests for evidence extraction** - in `tests/test_triage_inventory.py`, replace the `alex.lib.triage.inventory` import with:

```python
from alex.lib.triage.inventory import (
    MOVABLE_POPULATIONS,
    discover_population_files,
    extract_evidence,
    is_eligible,
)
```

and append at the end of the file:

```python
def test_extract_evidence_builds_snippet_links_tags_and_counts(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    body = (
        "The ==key insight== is that **narrow areas** beat bundles.\n\n"
        "See [[areas/organizational-design/index|org design]] and "
        "[[Learning By Writing#Draft first]].\n"
    )
    note = write_note(
        vault / "Loose idea.md",
        frontmatter="title: Narrow areas beat bundles\ntags:\n  - pkm\n  - areas",
        body=body,
    )

    evidence = extract_evidence(vault, note, "root")

    assert evidence.path == "Loose idea.md"
    assert evidence.title == "Narrow areas beat bundles"
    assert evidence.population == "root"
    assert evidence.tags == ["pkm", "areas"]
    assert evidence.wikilinks == [
        "areas/organizational-design/index",
        "Learning By Writing",
    ]
    assert evidence.has_highlights is True
    assert evidence.mtime == note.stat().st_mtime
    assert evidence.word_count == len(body.split())
    assert evidence.snippet.startswith("The ==key insight==")
    assert "title:" not in evidence.snippet


def test_extract_evidence_caps_snippet_at_200_words_and_links_at_20(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    words = " ".join(f"word{i}" for i in range(250))
    links = " ".join(f"[[note-{i:02d}]]" for i in range(25))
    note = write_note(vault / "Big note.md", body=f"{words}\n\n{links}\n")

    evidence = extract_evidence(vault, note, "root")

    assert len(evidence.snippet.split()) == 200
    assert evidence.snippet.split()[-1] == "word199"
    assert len(evidence.wikilinks) == 20
    assert evidence.wikilinks[0] == "note-00"
    assert evidence.wikilinks[-1] == "note-19"
    assert evidence.title == "Big note"
    assert evidence.has_highlights is False
    assert evidence.tags == []


def test_extract_evidence_accepts_a_scalar_tags_value(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = write_note(
        vault / "Clippings" / "Tagged clip.md",
        frontmatter="tags: clipping",
        body="Saved article body.",
    )

    evidence = extract_evidence(vault, note, "clippings")

    assert evidence.tags == ["clipping"]
    assert evidence.population == "clippings"
    assert evidence.path == "Clippings/Tagged clip.md"
```

- [ ] **Step 6: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_inventory.py -v
```

Expected: collection error, `ImportError: cannot import name 'extract_evidence' from 'alex.lib.triage.inventory'`.

- [ ] **Step 7: Write the implementation** - in `src/alex/lib/triage/inventory.py`, replace the import section with:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from alex.lib.triage.frontmatter import read_frontmatter, split_frontmatter
from alex.lib.triage.models import NoteEvidence, Population
```

add these constants directly below `MOVABLE_POPULATIONS`:

```python
SNIPPET_WORDS = 200
MAX_WIKILINKS = 20
WIKILINK_TARGET_PATTERN = re.compile(r"\[\[([^\]|#]+)")
```

insert this function after `is_eligible`:

```python
def extract_evidence(
    vault_root: Path, md_path: Path, population: Population
) -> NoteEvidence:
    text = md_path.read_text(encoding="utf-8")
    frontmatter = read_frontmatter(text)
    _, body = split_frontmatter(text)
    words = body.split()
    title = frontmatter.get("title")
    return NoteEvidence(
        path=md_path.relative_to(vault_root).as_posix(),
        title=title if isinstance(title, str) and title else md_path.stem,
        population=population,
        tags=_string_list(frontmatter.get("tags")),
        wikilinks=WIKILINK_TARGET_PATTERN.findall(body)[:MAX_WIKILINKS],
        snippet=" ".join(words[:SNIPPET_WORDS]),
        has_highlights="==" in body or "**" in body,
        mtime=md_path.stat().st_mtime,
        word_count=len(words),
    )
```

and append this helper after `_is_note` at the end of the file:

```python
def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []
```

- [ ] **Step 8: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_inventory.py -v
```

Expected: 8 passed.

- [ ] **Step 9: Write the failing tests for build_inventory** - in `tests/test_triage_inventory.py`, replace the import block at the top with:

```python
import os
from pathlib import Path

from alex.lib.triage.inventory import (
    MOVABLE_POPULATIONS,
    build_inventory,
    discover_population_files,
    extract_evidence,
    is_eligible,
)
```

and append at the end of the file:

```python
def test_build_inventory_includes_only_eligible_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_note(vault / "Fresh capture.md", body="An unprocessed thought.")
    write_note(
        vault / "Old import.md",
        frontmatter="processed: true",
        body="Already ran through the pipeline.",
    )
    write_note(
        vault / "Clippings" / "Mid-flight clip.md",
        frontmatter="workflow:\n  highlighted: true\n  extracted: true",
        body="Extraction suggestions pending.",
    )
    write_note(
        vault / "Already filed.md",
        frontmatter="triage:\n  decision: area\n  target: writing\n  status: decided",
        body="Decided last week.",
    )
    write_note(vault / "Meetings" / "Platform sync.md", body="Notes from the sync.")

    inventory = build_inventory(vault, None)

    assert [note.path for note in inventory.notes] == [
        "Fresh capture.md",
        "Meetings/Platform sync.md",
    ]
    assert inventory.notes[0].population == "root"
    assert inventory.notes[1].population == "meetings"
    assert inventory.generated != ""


def test_build_inventory_reuses_prior_evidence_when_mtime_is_unchanged(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    note = write_note(vault / "Stable note.md", body="Original body text.")
    original_ns = note.stat().st_mtime_ns
    first = build_inventory(vault, None)
    assert first.notes[0].snippet == "Original body text."

    note.write_text("Rewritten body that must not be re-read.\n", encoding="utf-8")
    os.utime(note, ns=(original_ns, original_ns))

    second = build_inventory(vault, first)

    assert [note.path for note in second.notes] == ["Stable note.md"]
    assert second.notes[0].snippet == "Original body text."


def test_build_inventory_refreshes_evidence_when_mtime_changes(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    note = write_note(vault / "Edited note.md", body="First version.")
    first = build_inventory(vault, None)

    note.write_text("Second version with new thinking.\n", encoding="utf-8")
    bumped = note.stat().st_mtime + 10
    os.utime(note, (bumped, bumped))

    second = build_inventory(vault, first)

    assert second.notes[0].snippet == "Second version with new thinking."
    assert second.notes[0].mtime != first.notes[0].mtime


def test_build_inventory_drops_newly_decided_and_vanished_notes(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    decided = write_note(vault / "Now decided.md", body="Decided body.")
    write_note(vault / "Now gone.md", body="Gone body.")
    first = build_inventory(vault, None)
    assert len(first.notes) == 2

    write_note(
        vault / "Now decided.md",
        frontmatter=(
            "triage:\n  decision: trash\n  status: decided\n  decided: 2026-07-12"
        ),
        body="Decided body.",
    )
    bumped = decided.stat().st_mtime + 10
    os.utime(decided, (bumped, bumped))
    (vault / "Now gone.md").unlink()

    second = build_inventory(vault, first)

    assert second.notes == []
```

- [ ] **Step 10: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_inventory.py -v
```

Expected: collection error, `ImportError: cannot import name 'build_inventory' from 'alex.lib.triage.inventory'`.

- [ ] **Step 11: Write the implementation** - in `src/alex/lib/triage/inventory.py`, replace the import section with:

```python
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alex.lib.triage.frontmatter import read_frontmatter, split_frontmatter
from alex.lib.triage.models import Inventory, NoteEvidence, Population
```

and insert this function after `extract_evidence`:

```python
def build_inventory(vault_root: Path, previous: Inventory | None) -> Inventory:
    prior = {note.path: note for note in previous.notes} if previous else {}
    notes: list[NoteEvidence] = []
    for population, md_path in discover_population_files(vault_root):
        rel_path = md_path.relative_to(vault_root).as_posix()
        cached = prior.get(rel_path)
        if cached is not None and cached.mtime == md_path.stat().st_mtime:
            notes.append(cached)
            continue
        frontmatter = read_frontmatter(md_path.read_text(encoding="utf-8"))
        if not is_eligible(frontmatter):
            continue
        notes.append(extract_evidence(vault_root, md_path, population))
    return Inventory(generated=datetime.now(UTC).isoformat(), notes=notes)
```

- [ ] **Step 12: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_inventory.py -v
```

Expected: 12 passed.

- [ ] **Step 13: Run just lint and mypy, expecting clean**

```bash
just lint
uv run mypy
```

Expected: ruff check and format check pass with no findings; mypy prints `Success: no issues found`.

- [ ] **Step 14: Commit**

```bash
git add src/alex/lib/triage/inventory.py tests/test_triage_inventory.py
git commit -m "feat(triage): add inventory scan with eligibility and evidence reuse

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
### Task 6: Clustering, cluster labeling, and batch slicing

**Files:**
- Create: `src/alex/lib/triage/clustering.py`
- Create: `src/alex/prompts/triage_cluster_label/v001.md`
- Create: `src/alex/prompts/triage_cluster_label/active.txt`
- Test: `tests/test_triage_clustering.py`

**Interfaces:**
- Consumes (Task 1 `alex.lib.triage.models`): `NoteEvidence`, `Inventory`, `Cluster`, `Batch`, `ClusterMap`.
- Consumes (existing repo): `Completer` and `Embedder` protocols from `alex.lib.llm`; `cosine_similarity(a, b) -> float` and `mean_vector(vectors) -> tuple[float, ...]` from `alex.lib.vectors`; `load_prompt(name, *, version=None, root=None) -> PromptTemplate` from `alex.lib.prompt_templates`.
- Produces (Task 17 `cluster` subcommand and the e2e test rely on these exact signatures):
  - `embedding_text(note: NoteEvidence) -> str`
  - `load_embedding_cache(path: Path) -> dict[str, tuple[float, ...]]`
  - `embed_notes(inventory: Inventory, embedder: Embedder, model: str, cache_path: Path) -> dict[str, tuple[float, ...]]`
  - `cluster_paths(vectors: dict[str, tuple[float, ...]], threshold: float) -> list[list[str]]`
  - `label_clusters(clusters: list[list[str]], inventory: Inventory, completer: Completer, model: str) -> list[Cluster]`
  - `slice_batches(clusters: list[Cluster], batch_size: int) -> list[Batch]` (populates `Batch.label`; rule in the decisions paragraph below, consumed by Task 9's `generate_batch_proposals`)
  - `build_cluster_map(inventory: Inventory, embedder: Embedder, completer: Completer, *, embed_model: str, label_model: str, threshold: float, batch_size: int, cache_path: Path, generated: str) -> ClusterMap`
  - Prompt name `triage_cluster_label` (placeholder `{{titles}}`), loadable via `load_prompt("triage_cluster_label")`.

Decisions encoded here (intentional, do not second-guess): `cluster_id` and `batch_id` are 1-based to match the `batch-001` proposals filename convention; `slice_batches` is a stream chunker (non-misc clusters in given order, then all misc clusters pooled, concatenated and cut into `batch_size` slices, so an oversized cluster naturally spans consecutive batches); each `Batch.label` is the label of the non-misc cluster contributing the most notes to that batch (ties break by first appearance in the batch), and "misc" when the batch holds only pooled singletons; the embeddings cache is append-only jsonl where the last row per path wins.

- [ ] **Step 1: Write the failing tests for embedding text and the mtime-keyed cache**

Create `tests/test_triage_clustering.py`:

```python
import json
from collections.abc import Sequence
from pathlib import Path

from alex.lib.triage.clustering import (
    embed_notes,
    embedding_text,
    load_embedding_cache,
)
from alex.lib.triage.models import Inventory, NoteEvidence
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
```

- [ ] **Step 2: Run the tests to verify they fail**

From `/home/alex/code/alex`:

```
uv run pytest tests/test_triage_clustering.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.clustering'`. No tests run.

- [ ] **Step 3: Implement embedding text, cache read, and embed_notes**

Create `src/alex/lib/triage/clustering.py`:

```python
"""Embed, cluster, label, and batch the triage inventory."""

from __future__ import annotations

import json
from pathlib import Path

from alex.lib.llm import Embedder
from alex.lib.triage.models import Inventory, NoteEvidence


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
    fresh = embedder.embed(
        texts=[embedding_text(note) for note in misses], model=model
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a", encoding="utf-8") as handle:
        for note, vector in zip(misses, fresh, strict=True):
            vectors[note.path] = vector
            row_out = {"path": note.path, "mtime": note.mtime, "vector": list(vector)}
            handle.write(json.dumps(row_out) + "\n")
    return vectors
```

- [ ] **Step 4: Run the tests to verify they pass**

```
uv run pytest tests/test_triage_clustering.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Write the failing tests for cluster order, misc labeling, and batch slicing**

In `tests/test_triage_clustering.py`, replace the two `from alex.lib.triage...` import statements at the top with:

```python
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
```

Then append at the end of the file:

```python
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
    vectors = {
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
```

- [ ] **Step 6: Run the tests to verify the new ones fail**

```
uv run pytest tests/test_triage_clustering.py -v
```

Expected: collection error, `ImportError: cannot import name 'cluster_paths' from 'alex.lib.triage.clustering'`. No tests run.

- [ ] **Step 7: Create the cluster-label prompt files**

Create `src/alex/prompts/triage_cluster_label/v001.md` with exactly this content:

```
You are labeling one cluster of Obsidian notes for a vault triage tool. The notes below were grouped together because their content is similar. Your label becomes the batch heading a human sees while reviewing filing decisions.

Note titles, one per line:

{{titles}}

Reply with a single short topic label for this cluster on one line: two to four lowercase words, letters and spaces only, no punctuation, no quotes, no explanation. Name the shared subject matter, not the note format.
```

Create `src/alex/prompts/triage_cluster_label/active.txt` containing exactly `v001` plus a trailing newline:

```
v001
```

- [ ] **Step 8: Implement clustering, labeling, and slicing**

Overwrite `src/alex/lib/triage/clustering.py` with the complete final file:

```python
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
    fresh = embedder.embed(
        texts=[embedding_text(note) for note in misses], model=model
    )
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
```

- [ ] **Step 9: Run the tests to verify they pass**

```
uv run pytest tests/test_triage_clustering.py -v
```

Expected: 11 passed.

- [ ] **Step 10: Run lint and typecheck, expecting clean**

```
cd /home/alex/code/alex && just lint && uv run mypy
```

Expected: ruff check clean, `ruff format --check` clean, mypy `Success: no issues found`. If `ruff format --check` flags a file, run `just fmt` and re-run Step 9.

- [ ] **Step 11: Commit**

```bash
cd /home/alex/code/alex
git add src/alex/lib/triage/clustering.py src/alex/prompts/triage_cluster_label/v001.md src/alex/prompts/triage_cluster_label/active.txt tests/test_triage_clustering.py
git commit -m "$(cat <<'EOF'
feat(triage): add topic clustering, labeling, and batch slicing

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

### Task 7: Corrections ledger

**Files:**
- Create: `src/alex/lib/triage/ledger.py`
- Test: `tests/test_triage_ledger.py`

**Interfaces:**
- Consumes (Task 1 `alex.lib.triage.models`): `LedgerEvent`, `LedgerEventKind`.
- Produces (Tasks 10, 15, 16, 17 rely on these exact signatures):
  - `append_event(ledger_path: Path, event: LedgerEvent) -> None`
  - `read_events(ledger_path: Path, *, since_version: int | None = None) -> list[LedgerEvent]`

The ledger is append-only jsonl, deliberately NOT written via atomic temp-rename (append semantics). `read_events` returns `[]` for a missing file, silently skips malformed lines (a synced file can tear), and `since_version` keeps events with `rubric_version >= since_version`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage_ledger.py`:

```python
import json
from pathlib import Path

from alex.lib.triage.ledger import append_event, read_events
from alex.lib.triage.models import LedgerEvent, LedgerEventKind


def make_event(
    *,
    note: str = "note.md",
    rubric_version: int = 1,
    event: LedgerEventKind = "approve",
) -> LedgerEvent:
    return LedgerEvent(
        ts="2026-07-12T10:00:00",
        note=note,
        batch=3,
        rubric_version=rubric_version,
        event=event,
        proposal={"decision": "area", "target": "learning-science"},
        correction=None,
        reason="",
    )


def test_append_event_creates_parent_dirs_and_round_trips(tmp_path: Path) -> None:
    ledger = tmp_path / "projects" / "vault-triage" / "ledger.jsonl"
    first = make_event(note="a.md")
    second = make_event(note="b.md", event="reject")

    append_event(ledger, first)
    append_event(ledger, second)

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["note"] == "a.md"
    assert read_events(ledger) == [first, second]


def test_read_events_returns_empty_list_when_ledger_missing(tmp_path: Path) -> None:
    assert read_events(tmp_path / "absent.jsonl") == []


def test_read_events_skips_malformed_lines(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    good = make_event(note="keep.md")
    lines = [
        good.model_dump_json(),
        "{ this is not json",
        json.dumps({"ts": "2026-07-12", "note": "half.md"}),
        json.dumps(["a", "list", "not", "an", "object"]),
        "",
    ]
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert read_events(ledger) == [good]


def test_read_events_since_version_keeps_only_matching_rubric_versions(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    for version in (1, 2, 3):
        append_event(ledger, make_event(note=f"v{version}.md", rubric_version=version))

    since_two = read_events(ledger, since_version=2)

    assert [event.note for event in since_two] == ["v2.md", "v3.md"]
    assert [event.note for event in read_events(ledger)] == [
        "v1.md",
        "v2.md",
        "v3.md",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

From `/home/alex/code/alex`:

```
uv run pytest tests/test_triage_ledger.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.ledger'`. No tests run.

- [ ] **Step 3: Write the implementation**

Create `src/alex/lib/triage/ledger.py`:

```python
"""Append-only corrections ledger stored as jsonl inside the vault."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from alex.lib.triage.models import LedgerEvent


def append_event(ledger_path: Path, event: LedgerEvent) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.model_dump(mode="json")) + "\n")


def read_events(
    ledger_path: Path, *, since_version: int | None = None
) -> list[LedgerEvent]:
    if not ledger_path.exists():
        return []
    events: list[LedgerEvent] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = LedgerEvent.model_validate_json(line)
        except ValidationError:
            continue
        if since_version is not None and event.rubric_version < since_version:
            continue
        events.append(event)
    return events
```

- [ ] **Step 4: Run the tests to verify they pass**

```
uv run pytest tests/test_triage_ledger.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run lint and typecheck, expecting clean**

```
cd /home/alex/code/alex && just lint && uv run mypy
```

Expected: ruff check clean, `ruff format --check` clean, mypy `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
cd /home/alex/code/alex
git add src/alex/lib/triage/ledger.py tests/test_triage_ledger.py
git commit -m "$(cat <<'EOF'
feat(triage): add append-only corrections ledger

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

### Task 8: Versioned rubric

**Files:**
- Create: `src/alex/lib/triage/rubric.py`
- Test: `tests/test_triage_rubric.py`

**Interfaces:**
- Consumes (Task 1): `Rubric` from `alex.lib.triage.models`; `atomic_write_text(path: Path, text: str) -> None` from `alex.lib.triage.storage`.
- Consumes (Task 2 `alex.lib.triage.frontmatter`): `split_frontmatter(text: str) -> tuple[str | None, str]`, `read_frontmatter(text: str) -> dict[str, Any]`, `assemble_frontmatter(yaml_text: str, body: str) -> str`.
- Produces (Tasks 9, 10, 15, 17 rely on these exact names):
  - `DEFAULT_RUBRIC_TEXT: str`
  - `load_rubric(path: Path) -> Rubric` (missing file seeds `Rubric(version=1, text=DEFAULT_RUBRIC_TEXT)` and writes it)
  - `save_rubric(path: Path, rubric: Rubric) -> None` (atomic)

The rubric file is markdown with `version: N` frontmatter. Hand edits are legitimate, so `load_rubric` is forgiving: a file without frontmatter or without an int `version` loads as version 1 with the whole content as the body.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage_rubric.py`:

```python
from pathlib import Path

from alex.lib.triage.models import Rubric
from alex.lib.triage.rubric import DEFAULT_RUBRIC_TEXT, load_rubric, save_rubric


def test_load_rubric_seeds_and_writes_default_when_file_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projects" / "vault-triage" / "rubric.md"

    rubric = load_rubric(path)

    assert rubric == Rubric(version=1, text=DEFAULT_RUBRIC_TEXT)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\nversion: 1\n---\n")
    assert "## Triage rules" in content
    assert "## Atomic note rules" in content
    assert load_rubric(path) == rubric


def test_load_rubric_parses_version_from_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "rubric.md"
    body = "## Triage rules\n\n1. Hand-edited rule.\n"
    path.write_text(f"---\nversion: 7\n---\n{body}", encoding="utf-8")

    rubric = load_rubric(path)

    assert rubric.version == 7
    assert rubric.text == body


def test_load_rubric_defaults_version_when_frontmatter_is_absent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rubric.md"
    path.write_text("## Triage rules\n\n1. No frontmatter here.\n", encoding="utf-8")

    rubric = load_rubric(path)

    assert rubric.version == 1
    assert rubric.text == "## Triage rules\n\n1. No frontmatter here.\n"


def test_save_rubric_writes_atomically_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "rubric.md"
    rubric = Rubric(version=3, text="## Triage rules\n\n1. Updated.\n")

    save_rubric(path, rubric)

    assert path.read_text(encoding="utf-8") == (
        "---\nversion: 3\n---\n## Triage rules\n\n1. Updated.\n"
    )
    assert not list(tmp_path.glob("*.tmp"))
    assert load_rubric(path) == rubric
```

- [ ] **Step 2: Run the tests to verify they fail**

From `/home/alex/code/alex`:

```
uv run pytest tests/test_triage_rubric.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.rubric'`. No tests run.

- [ ] **Step 3: Write the implementation**

Create `src/alex/lib/triage/rubric.py`:

```python
"""Versioned, hand-editable triage rubric stored as markdown in the vault."""

from __future__ import annotations

from pathlib import Path

from alex.lib.triage.frontmatter import (
    assemble_frontmatter,
    read_frontmatter,
    split_frontmatter,
)
from alex.lib.triage.models import Rubric
from alex.lib.triage.storage import atomic_write_text

DEFAULT_RUBRIC_TEXT = """\
## Triage rules

1. Prefer archive over force-fit. A note that matches no catalog area with
   confidence goes to archives, not into the nearest-sounding area.
2. Meetings and 1:1 notes are weak area evidence. Associate one with an area
   only when the topic is unmistakable; never justify a new area with them.
3. Prefer narrow durable domains over bundles. Two crisp areas beat one blob.
4. Work deliverables with a deadline are project material, not areas. Skip
   them for manual project filing instead of forcing an area.
5. A note about doing the job supports a work area, not a general life area.
6. Propose a new area only when several notes point at the same durable
   domain and nothing in the catalog fits.
7. Clippings that were read once and never linked go to archives/clippings,
   not resources.
8. Trash only what is empty, duplicated, or content-free. When in doubt,
   archive.

## Atomic note rules

1. One claim per note; the title states the claim.
2. The body stands alone: 2-4 short paragraphs in Alex's plain first-person
   register, own words, no long quotes.
3. Related links may only point to permanent notes that already exist.
4. Draft only from notes Alex flagged promising; volume is not the goal.
"""


def load_rubric(path: Path) -> Rubric:
    if not path.exists():
        rubric = Rubric(version=1, text=DEFAULT_RUBRIC_TEXT)
        save_rubric(path, rubric)
        return rubric
    raw = path.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw)
    version_value = read_frontmatter(raw).get("version")
    version = version_value if isinstance(version_value, int) else 1
    return Rubric(version=version, text=body)


def save_rubric(path: Path, rubric: Rubric) -> None:
    content = assemble_frontmatter(f"version: {rubric.version}", rubric.text)
    atomic_write_text(path, content)
```

- [ ] **Step 4: Run the tests to verify they pass**

```
uv run pytest tests/test_triage_rubric.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run lint and typecheck, expecting clean**

```
cd /home/alex/code/alex && just lint && uv run mypy
```

Expected: ruff check clean, `ruff format --check` clean, mypy `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
cd /home/alex/code/alex
git add src/alex/lib/triage/rubric.py tests/test_triage_rubric.py
git commit -m "$(cat <<'EOF'
feat(triage): add versioned rubric with seeded defaults

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```
### Task 9: Triage Proposals (proposals.py + triage_proposal prompt)

**Files:**
- Create: `src/alex/prompts/triage_proposal/v001.md`
- Create: `src/alex/prompts/triage_proposal/active.txt`
- Create: `src/alex/lib/triage/proposals.py`
- Test: `tests/test_triage_proposals.py`

**Interfaces:**

Consumes (all from earlier tasks or the existing repo):
- `alex.lib.triage.models` (Task 1): `Batch`, `BatchProposals`, `Catalog`, `CatalogEntry`, `Inventory`, `NoteEvidence`, `Proposal`, `Rubric`
- `alex.lib.triage.paths` (Task 1): `TriagePaths`, `TriagePaths.proposals_path(batch_id: int, rubric_version: int) -> Path`
- `alex.lib.triage.storage` (Task 1): `read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None`, `write_yaml_model(path: Path, model: BaseModel) -> None`
- `alex.lib.triage.catalog` (Task 4): `catalog_prompt_text(catalog: Catalog) -> str`
- `alex.lib.triage.inventory` (Task 5): `MOVABLE_POPULATIONS: frozenset[Population]`
- `alex.lib.llm` (existing): `Completer` protocol (`complete(*, prompt: str, model: str, max_tokens: int) -> str`), `ordered_parallel_map[T, U](items: Sequence[T], func: Callable[[T], U], *, max_workers: int) -> tuple[U, ...]`
- `alex.lib.prompt_templates` (existing): `load_prompt(name, *, version=None, root=None) -> PromptTemplate`

Produces (later tasks rely on these exact signatures):
```python
class ProposalParseError(ValueError): ...
def extract_json_object(raw: str) -> dict[str, Any]
def proposal_prompt(note: NoteEvidence, *, catalog_text: str, rubric_text: str,
                    cluster_label: str, corrections: Sequence[str]) -> str
def parse_proposal(raw: str, note_path: str) -> Proposal
def generate_batch_proposals(batch: Batch, inventory: Inventory, *,
        catalog: Catalog, rubric: Rubric, completer: Completer, model: str,
        corrections: Sequence[str] = (), max_workers: int = 4) -> BatchProposals
def load_batch_proposals(paths: TriagePaths, batch_id: int, rubric_version: int) -> BatchProposals | None
def write_batch_proposals(paths: TriagePaths, proposals: BatchProposals) -> None
```
Plus prompt `triage_proposal` v001 (active), placeholders exactly `{{rubric}}`, `{{catalog}}`, `{{cluster_label}}`, `{{corrections}}`, `{{evidence}}`.

Notes on contract resolutions: `Batch` carries a `label` field (Task 1) that `slice_batches` populates (Task 6); `generate_batch_proposals` renders `{{cluster_label}}` from `batch.label`, falling back to `"(none)"` when the label is empty. The TUI's per-note re-propose does not call `proposal_prompt` directly; it constructs a single-note `Batch` that preserves the parent batch's label and goes through `generate_batch_proposals`. Batch note paths missing from the inventory are dropped without a proposal (there is no evidence to prompt with; the TUI ejects vanished notes at batch open). `parse_proposal` truncates `alternatives` to the first two (the `Proposal` model stays unconstrained). For annotate-only populations (any `NoteEvidence.population` not in `MOVABLE_POPULATIONS`), `generate_batch_proposals` coerces any decision other than area/skip to skip with `why` prefixed `"annotate-only: "`.

- [ ] **Step 1: Write the failing prompt test**

  Create `tests/test_triage_proposals.py`:

  ```python
  """Tests for triage proposal generation, parsing, and caching."""

  from alex.lib.prompt_templates import load_prompt


  def test_triage_proposal_prompt_has_exact_placeholder_set() -> None:
      template = load_prompt("triage_proposal")
      assert template.version == "v001"
      assert template.placeholders() == frozenset(
          {"rubric", "catalog", "cluster_label", "corrections", "evidence"}
      )
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_proposals.py -v
  ```

  Expected: 1 failed with `PromptTemplateError: Unknown prompt: triage_proposal`.

- [ ] **Step 3: Create the prompt files**

  Create `src/alex/prompts/triage_proposal/v001.md` with exactly this content:

  ```markdown
  You are the filing assistant for a personal Obsidian vault organized with
  PARA (Projects, Areas, Resources, Archives). You triage exactly one note:
  decide where it belongs, or say that you cannot.

  The vault owner reviews every decision by hand. Your job is a confident,
  well-reasoned first pass, not a final verdict. Be decisive when the
  evidence is clear and honest when it is not.

  ## Rubric

  These rules were distilled from the owner's past corrections. When they
  conflict with your instincts, the rubric wins.

  {{rubric}}

  ## Catalog

  The complete list of valid destinations. Area slugs and resource topics
  that are not in this catalog do not exist.

  {{catalog}}

  ## Cluster label

  This note was grouped with similar notes under the topic label:
  {{cluster_label}}

  ## Corrections from this batch

  The owner made these corrections while reviewing the current batch. Apply
  them to this note when they are relevant.

  {{corrections}}

  ## Note evidence

  {{evidence}}

  ## Decisions

  Pick exactly one:

  - "area": the note belongs to a stable knowledge domain. "target" must be
    an area slug from the catalog.
  - "resource": the note is reference material for a topic. "target" must be
    a resource topic from the catalog.
  - "archive": the note is finished business or record-keeping material.
    "target" is a short kebab-case subfolder name; use "notes" when nothing
    more specific fits.
  - "trash": the note has no plausible future value (empty, duplicate,
    accidental capture, boilerplate).
  - "skip": you cannot make a useful call; a human must decide.

  ## Rules

  1. Never use an area slug or resource topic that is not in the catalog.
  2. New areas are rare. Only when nothing in the catalog fits AND the
     evidence points at a durable knowledge domain (not a one-off event or a
     work deliverable), set "decision" to "area", set "target" to a new
     kebab-case slug, and fill "new_area" with that slug, a human-readable
     name, and a one-sentence description. In every other case "new_area"
     must be null.
  3. Notes from the meetings or weekly populations are never moved. For them
     the only valid decisions are "area" (recording which area the note
     relates to) or "skip".
  4. When nothing fits confidently, prefer "archive" over force-fitting a
     marginal area.
  5. "confidence" reflects the evidence: "high" only when the note obviously
     belongs at the target, "low" when you are guessing.
  6. "alternatives" lists up to two other plausible targets (slug or topic
     strings), best first. Leave it empty when there are none.
  7. "why" is one or two plain sentences naming the evidence you used.

  ## Response format

  Respond with ONLY a JSON object, no prose before or after, no code fences:

  {"decision": "area|resource|archive|trash|skip",
   "target": "catalog slug, resource topic, or archive subfolder; empty for trash and skip",
   "confidence": "high|medium|low",
   "why": "one or two sentences",
   "alternatives": ["up to two alternative targets"],
   "new_area": {"slug": "kebab-case-slug", "name": "Human Name", "description": "one sentence"}}

  Set "new_area" to null unless rule 2 applies.
  ```

  Create `src/alex/prompts/triage_proposal/active.txt` containing exactly `v001` plus a trailing newline:

  ```text
  v001
  ```

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_proposals.py -v
  ```

  Expected: 1 passed.

- [ ] **Step 5: Write the failing parsing and prompt-render tests**

  Replace `tests/test_triage_proposals.py` in full with:

  ````python
  """Tests for triage proposal generation, parsing, and caching."""

  import json

  import pytest

  from alex.lib.prompt_templates import load_prompt
  from alex.lib.triage.models import NoteEvidence
  from alex.lib.triage.proposals import (
      ProposalParseError,
      extract_json_object,
      parse_proposal,
      proposal_prompt,
  )


  def valid_reply(target: str = "learning-science") -> str:
      return json.dumps(
          {
              "decision": "area",
              "target": target,
              "confidence": "high",
              "why": "The note is about spaced repetition.",
              "alternatives": [],
              "new_area": None,
          }
      )


  def make_note(path: str, title: str) -> NoteEvidence:
      return NoteEvidence(
          path=path,
          title=title,
          population="root",
          tags=["learning"],
          snippet="Spaced repetition beats cramming.",
      )


  def test_triage_proposal_prompt_has_exact_placeholder_set() -> None:
      template = load_prompt("triage_proposal")
      assert template.version == "v001"
      assert template.placeholders() == frozenset(
          {"rubric", "catalog", "cluster_label", "corrections", "evidence"}
      )


  def test_extract_json_object_parses_bare_object() -> None:
      assert extract_json_object('{"decision": "trash"}') == {"decision": "trash"}


  def test_extract_json_object_strips_code_fences_and_prose() -> None:
      raw = 'Sure!\n```json\n{"decision": "trash", "target": ""}\n```\n'
      assert extract_json_object(raw) == {"decision": "trash", "target": ""}


  def test_extract_json_object_raises_on_reply_without_object() -> None:
      with pytest.raises(ProposalParseError):
          extract_json_object("I cannot decide where this note belongs.")


  def test_extract_json_object_raises_on_json_array() -> None:
      with pytest.raises(ProposalParseError):
          extract_json_object('["not", "an", "object"]')


  def test_parse_proposal_injects_note_path_and_validates() -> None:
      proposal = parse_proposal(valid_reply(), "Note A.md")
      assert proposal.note_path == "Note A.md"
      assert proposal.decision == "area"
      assert proposal.target == "learning-science"
      assert proposal.confidence == "high"
      assert proposal.new_area is None
      assert proposal.needs_manual is False


  def test_parse_proposal_wraps_schema_violation_in_parse_error() -> None:
      raw = json.dumps({"decision": "banana", "target": ""})
      with pytest.raises(ProposalParseError):
          parse_proposal(raw, "Note A.md")


  def test_parse_proposal_truncates_alternatives_to_first_two() -> None:
      raw = json.dumps(
          {
              "decision": "area",
              "target": "learning-science",
              "confidence": "medium",
              "why": "Learning content.",
              "alternatives": ["writing", "memory", "habits", "focus"],
              "new_area": None,
          }
      )
      proposal = parse_proposal(raw, "Note A.md")
      assert proposal.alternatives == ["writing", "memory"]


  def test_proposal_prompt_renders_rubric_catalog_and_evidence() -> None:
      prompt = proposal_prompt(
          make_note("Note A.md", "Spaced repetition"),
          catalog_text="- learning-science: How people learn",
          rubric_text="1. Prefer narrow areas.",
          cluster_label="memory",
          corrections=["stop filing meetings as areas"],
      )
      assert "1. Prefer narrow areas." in prompt
      assert "- learning-science: How people learn" in prompt
      assert "memory" in prompt
      assert "- stop filing meetings as areas" in prompt
      assert "Title: Spaced repetition" in prompt
      assert "Spaced repetition beats cramming." in prompt


  def test_proposal_prompt_marks_empty_label_and_corrections_as_none() -> None:
      prompt = proposal_prompt(
          make_note("Note A.md", "Spaced repetition"),
          catalog_text="- learning-science: How people learn",
          rubric_text="1. Prefer narrow areas.",
          cluster_label="",
          corrections=(),
      )
      assert prompt.count("(none)") >= 2
  ````

- [ ] **Step 6: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_proposals.py -v
  ```

  Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.proposals'`.

- [ ] **Step 7: Write the parsing implementation**

  Create `src/alex/lib/triage/proposals.py`:

  ````python
  """Per-note triage proposals: prompt rendering, JSON parsing, batching."""

  from __future__ import annotations

  import json
  from collections.abc import Sequence
  from typing import Any

  from pydantic import ValidationError

  from alex.lib.prompt_templates import load_prompt
  from alex.lib.triage.models import NoteEvidence, Proposal

  _PROMPT_NAME = "triage_proposal"


  class ProposalParseError(ValueError):
      pass


  def extract_json_object(raw: str) -> dict[str, Any]:
      text = raw.strip()
      if text.startswith("```"):
          text = text.removeprefix("```json").removeprefix("```").strip()
          text = text.removesuffix("```").strip()
      start = text.find("{")
      end = text.rfind("}")
      if start == -1 or end <= start:
          raise ProposalParseError(f"no JSON object in reply: {raw[:120]!r}")
      try:
          data = json.loads(text[start : end + 1])
      except json.JSONDecodeError as error:
          raise ProposalParseError(f"invalid JSON: {error}") from error
      if not isinstance(data, dict):
          raise ProposalParseError("JSON reply is not an object")
      return data


  def parse_proposal(raw: str, note_path: str) -> Proposal:
      data = extract_json_object(raw)
      data["note_path"] = note_path
      alternatives = data.get("alternatives")
      if isinstance(alternatives, list):
          data["alternatives"] = alternatives[:2]
      try:
          return Proposal.model_validate(data)
      except ValidationError as error:
          raise ProposalParseError(f"proposal failed validation: {error}") from error


  def proposal_prompt(
      note: NoteEvidence,
      *,
      catalog_text: str,
      rubric_text: str,
      cluster_label: str,
      corrections: Sequence[str],
  ) -> str:
      return load_prompt(_PROMPT_NAME).render(
          rubric=rubric_text,
          catalog=catalog_text,
          cluster_label=cluster_label or "(none)",
          corrections=_corrections_text(corrections),
          evidence=_evidence_text(note),
      )


  def _corrections_text(corrections: Sequence[str]) -> str:
      if not corrections:
          return "(none)"
      return "\n".join(f"- {correction}" for correction in corrections)


  def _evidence_text(note: NoteEvidence) -> str:
      tags = ", ".join(note.tags) if note.tags else "(none)"
      wikilinks = ", ".join(note.wikilinks) if note.wikilinks else "(none)"
      return (
          f"Path: {note.path}\n"
          f"Title: {note.title}\n"
          f"Population: {note.population}\n"
          f"Tags: {tags}\n"
          f"Wikilinks: {wikilinks}\n"
          f"Word count: {note.word_count}\n"
          f"Has highlights: {note.has_highlights}\n"
          f"Snippet:\n{note.snippet}"
      )
  ````

- [ ] **Step 8: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_proposals.py -v
  ```

  Expected: 10 passed.

- [ ] **Step 9: Write the failing generation and cache tests**

  Replace `tests/test_triage_proposals.py` in full with:

  ````python
  """Tests for triage proposal generation, parsing, and caching."""

  import json
  from pathlib import Path

  import pytest

  from alex.lib.prompt_templates import load_prompt
  from alex.lib.triage.models import (
      Batch,
      BatchProposals,
      Catalog,
      CatalogEntry,
      Inventory,
      NoteEvidence,
      Population,
      Proposal,
      Rubric,
  )
  from alex.lib.triage.paths import TriagePaths
  from alex.lib.triage.proposals import (
      ProposalParseError,
      extract_json_object,
      generate_batch_proposals,
      load_batch_proposals,
      parse_proposal,
      proposal_prompt,
      write_batch_proposals,
  )


  class QueueCompleter:
      """Pops scripted replies in call order; records every prompt."""

      def __init__(self, responses: list[str]) -> None:
          self.responses = responses
          self.prompts: list[str] = []

      def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
          self.prompts.append(prompt)
          return self.responses.pop(0)


  def valid_reply(target: str = "learning-science") -> str:
      return json.dumps(
          {
              "decision": "area",
              "target": target,
              "confidence": "high",
              "why": "The note is about spaced repetition.",
              "alternatives": [],
              "new_area": None,
          }
      )


  def trash_reply() -> str:
      return json.dumps(
          {
              "decision": "trash",
              "target": "",
              "confidence": "medium",
              "why": "Empty accidental capture.",
              "alternatives": [],
              "new_area": None,
          }
      )


  def make_note(
      path: str, title: str, population: Population = "root"
  ) -> NoteEvidence:
      return NoteEvidence(
          path=path,
          title=title,
          population=population,
          tags=["learning"],
          snippet="Spaced repetition beats cramming.",
      )


  def make_inventory(notes: list[NoteEvidence]) -> Inventory:
      return Inventory(generated="2026-07-12T00:00:00", notes=notes)


  def make_catalog() -> Catalog:
      return Catalog(
          areas=[
              CatalogEntry(
                  slug="learning-science",
                  name="Learning Science",
                  description="How people learn and retain knowledge",
              )
          ],
          resource_topics=["permanent-notes"],
      )


  def make_rubric() -> Rubric:
      return Rubric(version=3, text="## Triage rules\n1. Prefer narrow areas.")


  def test_triage_proposal_prompt_has_exact_placeholder_set() -> None:
      template = load_prompt("triage_proposal")
      assert template.version == "v001"
      assert template.placeholders() == frozenset(
          {"rubric", "catalog", "cluster_label", "corrections", "evidence"}
      )


  def test_extract_json_object_parses_bare_object() -> None:
      assert extract_json_object('{"decision": "trash"}') == {"decision": "trash"}


  def test_extract_json_object_strips_code_fences_and_prose() -> None:
      raw = 'Sure!\n```json\n{"decision": "trash", "target": ""}\n```\n'
      assert extract_json_object(raw) == {"decision": "trash", "target": ""}


  def test_extract_json_object_raises_on_reply_without_object() -> None:
      with pytest.raises(ProposalParseError):
          extract_json_object("I cannot decide where this note belongs.")


  def test_extract_json_object_raises_on_json_array() -> None:
      with pytest.raises(ProposalParseError):
          extract_json_object('["not", "an", "object"]')


  def test_parse_proposal_injects_note_path_and_validates() -> None:
      proposal = parse_proposal(valid_reply(), "Note A.md")
      assert proposal.note_path == "Note A.md"
      assert proposal.decision == "area"
      assert proposal.target == "learning-science"
      assert proposal.confidence == "high"
      assert proposal.new_area is None
      assert proposal.needs_manual is False


  def test_parse_proposal_wraps_schema_violation_in_parse_error() -> None:
      raw = json.dumps({"decision": "banana", "target": ""})
      with pytest.raises(ProposalParseError):
          parse_proposal(raw, "Note A.md")


  def test_parse_proposal_truncates_alternatives_to_first_two() -> None:
      raw = json.dumps(
          {
              "decision": "area",
              "target": "learning-science",
              "confidence": "medium",
              "why": "Learning content.",
              "alternatives": ["writing", "memory", "habits", "focus"],
              "new_area": None,
          }
      )
      proposal = parse_proposal(raw, "Note A.md")
      assert proposal.alternatives == ["writing", "memory"]


  def test_proposal_prompt_renders_rubric_catalog_and_evidence() -> None:
      prompt = proposal_prompt(
          make_note("Note A.md", "Spaced repetition"),
          catalog_text="- learning-science: How people learn",
          rubric_text="1. Prefer narrow areas.",
          cluster_label="memory",
          corrections=["stop filing meetings as areas"],
      )
      assert "1. Prefer narrow areas." in prompt
      assert "- learning-science: How people learn" in prompt
      assert "memory" in prompt
      assert "- stop filing meetings as areas" in prompt
      assert "Title: Spaced repetition" in prompt
      assert "Spaced repetition beats cramming." in prompt


  def test_proposal_prompt_marks_empty_label_and_corrections_as_none() -> None:
      prompt = proposal_prompt(
          make_note("Note A.md", "Spaced repetition"),
          catalog_text="- learning-science: How people learn",
          rubric_text="1. Prefer narrow areas.",
          cluster_label="",
          corrections=(),
      )
      assert prompt.count("(none)") >= 2


  def test_generate_batch_proposals_parses_valid_reply_per_note() -> None:
      completer = QueueCompleter([valid_reply()])
      result = generate_batch_proposals(
          Batch(batch_id=1, note_paths=["Note A.md"]),
          make_inventory([make_note("Note A.md", "Spaced repetition")]),
          catalog=make_catalog(),
          rubric=make_rubric(),
          completer=completer,
          model="fake/model",
          max_workers=1,
      )
      assert result.batch_id == 1
      assert result.rubric_version == 3
      assert [p.note_path for p in result.proposals] == ["Note A.md"]
      assert result.proposals[0].decision == "area"
      assert result.proposals[0].target == "learning-science"
      assert "learning-science" in completer.prompts[0]


  def test_generate_batch_proposals_repairs_after_one_invalid_reply() -> None:
      completer = QueueCompleter(["hmm, this looks like learning", valid_reply()])
      result = generate_batch_proposals(
          Batch(batch_id=1, note_paths=["Note A.md"]),
          make_inventory([make_note("Note A.md", "Spaced repetition")]),
          catalog=make_catalog(),
          rubric=make_rubric(),
          completer=completer,
          model="fake/model",
          max_workers=1,
      )
      proposal = result.proposals[0]
      assert proposal.decision == "area"
      assert proposal.needs_manual is False
      assert len(completer.prompts) == 2
      assert completer.prompts[1].startswith(completer.prompts[0])
      assert "Your previous reply was not valid JSON" in completer.prompts[1]
      assert completer.prompts[1].endswith("Reply with ONLY the JSON object.")


  def test_generate_batch_proposals_marks_needs_manual_after_two_failures() -> None:
      completer = QueueCompleter(["no json here", "still no json"])
      result = generate_batch_proposals(
          Batch(batch_id=1, note_paths=["Note A.md"]),
          make_inventory([make_note("Note A.md", "Spaced repetition")]),
          catalog=make_catalog(),
          rubric=make_rubric(),
          completer=completer,
          model="fake/model",
          max_workers=1,
      )
      proposal = result.proposals[0]
      assert proposal.decision == "skip"
      assert proposal.confidence == "low"
      assert proposal.needs_manual is True
      assert proposal.why.startswith("needs manual: ")
      assert len(completer.prompts) == 2


  def test_generate_batch_proposals_keeps_batch_order_with_one_worker() -> None:
      completer = QueueCompleter([valid_reply(), trash_reply()])
      result = generate_batch_proposals(
          Batch(batch_id=2, note_paths=["A.md", "B.md"]),
          make_inventory([make_note("A.md", "Alpha"), make_note("B.md", "Beta")]),
          catalog=make_catalog(),
          rubric=make_rubric(),
          completer=completer,
          model="fake/model",
          max_workers=1,
      )
      assert [p.note_path for p in result.proposals] == ["A.md", "B.md"]
      assert result.proposals[0].decision == "area"
      assert result.proposals[1].decision == "trash"
      assert "Title: Alpha" in completer.prompts[0]
      assert "Title: Beta" in completer.prompts[1]


  def test_generate_batch_proposals_skips_paths_missing_from_inventory() -> None:
      completer = QueueCompleter([valid_reply()])
      result = generate_batch_proposals(
          Batch(batch_id=3, note_paths=["ghost.md", "A.md"]),
          make_inventory([make_note("A.md", "Alpha")]),
          catalog=make_catalog(),
          rubric=make_rubric(),
          completer=completer,
          model="fake/model",
          max_workers=1,
      )
      assert [p.note_path for p in result.proposals] == ["A.md"]


  def test_generate_batch_proposals_renders_batch_label_in_prompt() -> None:
      completer = QueueCompleter([valid_reply()])
      generate_batch_proposals(
          Batch(batch_id=4, label="memory-techniques", note_paths=["Note A.md"]),
          make_inventory([make_note("Note A.md", "Spaced repetition")]),
          catalog=make_catalog(),
          rubric=make_rubric(),
          completer=completer,
          model="fake/model",
          max_workers=1,
      )
      before_corrections = completer.prompts[0].split("## Corrections")[0]
      assert "memory-techniques" in before_corrections
      assert "(none)" not in before_corrections


  def test_generate_batch_proposals_coerces_annotate_only_trash_to_skip() -> None:
      completer = QueueCompleter([trash_reply(), valid_reply()])
      result = generate_batch_proposals(
          Batch(batch_id=5, note_paths=["Meetings/Standup.md", "Meetings/1-1.md"]),
          make_inventory(
              [
                  make_note("Meetings/Standup.md", "Standup", "meetings"),
                  make_note("Meetings/1-1.md", "One on one", "meetings"),
              ]
          ),
          catalog=make_catalog(),
          rubric=make_rubric(),
          completer=completer,
          model="fake/model",
          max_workers=1,
      )
      coerced, kept = result.proposals
      assert coerced.decision == "skip"
      assert coerced.target == ""
      assert coerced.why == "annotate-only: Empty accidental capture."
      assert coerced.alternatives == []
      assert kept.decision == "area"
      assert kept.target == "learning-science"


  def test_batch_proposals_cache_roundtrip(tmp_path: Path) -> None:
      paths = TriagePaths(vault_root=tmp_path)
      proposals = BatchProposals(
          batch_id=7,
          rubric_version=2,
          proposals=[
              Proposal(
                  note_path="Note A.md",
                  decision="area",
                  target="learning-science",
                  confidence="medium",
                  why="Looks like learning content.",
              )
          ],
      )
      write_batch_proposals(paths, proposals)
      cache_file = paths.proposals_path(7, 2)
      assert cache_file.is_file()
      assert cache_file.name == "batch-007.rubric-v02.yaml"
      assert load_batch_proposals(paths, 7, 2) == proposals


  def test_load_batch_proposals_returns_none_when_cache_missing(tmp_path: Path) -> None:
      paths = TriagePaths(vault_root=tmp_path)
      assert load_batch_proposals(paths, 1, 1) is None
  ````

- [ ] **Step 10: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_proposals.py -v
  ```

  Expected: collection error, `ImportError: cannot import name 'generate_batch_proposals' from 'alex.lib.triage.proposals'`.

- [ ] **Step 11: Write the full implementation**

  Replace `src/alex/lib/triage/proposals.py` in full with:

  ````python
  """Per-note triage proposals: prompt rendering, JSON parsing, batching."""

  from __future__ import annotations

  import json
  from collections.abc import Sequence
  from typing import Any

  from pydantic import ValidationError

  from alex.lib.llm import Completer, ordered_parallel_map
  from alex.lib.prompt_templates import load_prompt
  from alex.lib.triage.catalog import catalog_prompt_text
  from alex.lib.triage.inventory import MOVABLE_POPULATIONS
  from alex.lib.triage.models import (
      Batch,
      BatchProposals,
      Catalog,
      Inventory,
      NoteEvidence,
      Proposal,
      Rubric,
  )
  from alex.lib.triage.paths import TriagePaths
  from alex.lib.triage.storage import read_yaml_model, write_yaml_model

  _PROMPT_NAME = "triage_proposal"
  _PROPOSAL_MAX_TOKENS = 1024


  class ProposalParseError(ValueError):
      pass


  def extract_json_object(raw: str) -> dict[str, Any]:
      text = raw.strip()
      if text.startswith("```"):
          text = text.removeprefix("```json").removeprefix("```").strip()
          text = text.removesuffix("```").strip()
      start = text.find("{")
      end = text.rfind("}")
      if start == -1 or end <= start:
          raise ProposalParseError(f"no JSON object in reply: {raw[:120]!r}")
      try:
          data = json.loads(text[start : end + 1])
      except json.JSONDecodeError as error:
          raise ProposalParseError(f"invalid JSON: {error}") from error
      if not isinstance(data, dict):
          raise ProposalParseError("JSON reply is not an object")
      return data


  def parse_proposal(raw: str, note_path: str) -> Proposal:
      data = extract_json_object(raw)
      data["note_path"] = note_path
      alternatives = data.get("alternatives")
      if isinstance(alternatives, list):
          data["alternatives"] = alternatives[:2]
      try:
          return Proposal.model_validate(data)
      except ValidationError as error:
          raise ProposalParseError(f"proposal failed validation: {error}") from error


  def proposal_prompt(
      note: NoteEvidence,
      *,
      catalog_text: str,
      rubric_text: str,
      cluster_label: str,
      corrections: Sequence[str],
  ) -> str:
      return load_prompt(_PROMPT_NAME).render(
          rubric=rubric_text,
          catalog=catalog_text,
          cluster_label=cluster_label or "(none)",
          corrections=_corrections_text(corrections),
          evidence=_evidence_text(note),
      )


  def generate_batch_proposals(
      batch: Batch,
      inventory: Inventory,
      *,
      catalog: Catalog,
      rubric: Rubric,
      completer: Completer,
      model: str,
      corrections: Sequence[str] = (),
      max_workers: int = 4,
  ) -> BatchProposals:
      catalog_text = catalog_prompt_text(catalog)
      by_path = {note.path: note for note in inventory.notes}
      # Vanished notes are ejected at batch open; without evidence there is
      # nothing to prompt with, so unknown paths are dropped here too.
      notes = [by_path[path] for path in batch.note_paths if path in by_path]

      def propose(note: NoteEvidence) -> Proposal:
          prompt = proposal_prompt(
              note,
              catalog_text=catalog_text,
              rubric_text=rubric.text,
              cluster_label=batch.label,
              corrections=corrections,
          )
          raw = completer.complete(
              prompt=prompt, model=model, max_tokens=_PROPOSAL_MAX_TOKENS
          )
          try:
              return _coerce_annotate_only(parse_proposal(raw, note.path), note)
          except ProposalParseError as error:
              repair_prompt = (
                  f"{prompt}\n\nYour previous reply was not valid JSON: {error}."
                  " Reply with ONLY the JSON object."
              )
          repaired = completer.complete(
              prompt=repair_prompt, model=model, max_tokens=_PROPOSAL_MAX_TOKENS
          )
          try:
              return _coerce_annotate_only(
                  parse_proposal(repaired, note.path), note
              )
          except ProposalParseError as second_error:
              return Proposal(
                  note_path=note.path,
                  decision="skip",
                  confidence="low",
                  why=f"needs manual: {second_error}",
                  needs_manual=True,
              )

      generated = ordered_parallel_map(notes, propose, max_workers=max_workers)
      return BatchProposals(
          batch_id=batch.batch_id,
          rubric_version=rubric.version,
          proposals=list(generated),
      )


  def load_batch_proposals(
      paths: TriagePaths, batch_id: int, rubric_version: int
  ) -> BatchProposals | None:
      return read_yaml_model(
          paths.proposals_path(batch_id, rubric_version), BatchProposals
      )


  def write_batch_proposals(paths: TriagePaths, proposals: BatchProposals) -> None:
      write_yaml_model(
          paths.proposals_path(proposals.batch_id, proposals.rubric_version), proposals
      )


  def _coerce_annotate_only(proposal: Proposal, note: NoteEvidence) -> Proposal:
      """Annotate-only populations may only be area-linked or skipped."""
      if note.population in MOVABLE_POPULATIONS:
          return proposal
      if proposal.decision in ("area", "skip"):
          return proposal
      return proposal.model_copy(
          update={
              "decision": "skip",
              "target": "",
              "alternatives": [],
              "new_area": None,
              "why": f"annotate-only: {proposal.why}",
          }
      )


  def _corrections_text(corrections: Sequence[str]) -> str:
      if not corrections:
          return "(none)"
      return "\n".join(f"- {correction}" for correction in corrections)


  def _evidence_text(note: NoteEvidence) -> str:
      tags = ", ".join(note.tags) if note.tags else "(none)"
      wikilinks = ", ".join(note.wikilinks) if note.wikilinks else "(none)"
      return (
          f"Path: {note.path}\n"
          f"Title: {note.title}\n"
          f"Population: {note.population}\n"
          f"Tags: {tags}\n"
          f"Wikilinks: {wikilinks}\n"
          f"Word count: {note.word_count}\n"
          f"Has highlights: {note.has_highlights}\n"
          f"Snippet:\n{note.snippet}"
      )
  ````

- [ ] **Step 12: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_proposals.py -v
  ```

  Expected: 19 passed.

- [ ] **Step 13: Run lint and typecheck**

  ```bash
  cd /home/alex/code/alex && just lint && uv run mypy
  ```

  Expected: ruff check and ruff format --check clean, mypy reports no issues.

- [ ] **Step 14: Commit**

  ```bash
  cd /home/alex/code/alex
  git add src/alex/prompts/triage_proposal/v001.md src/alex/prompts/triage_proposal/active.txt src/alex/lib/triage/proposals.py tests/test_triage_proposals.py
  git commit -m "feat(triage): proposal prompt, parsing, and batch generation

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
  ```

### Task 10: Rubric Distillation (distill.py + triage_rubric_distill prompt)

**Files:**
- Create: `src/alex/prompts/triage_rubric_distill/v001.md`
- Create: `src/alex/prompts/triage_rubric_distill/active.txt`
- Create: `src/alex/lib/triage/distill.py`
- Test: `tests/test_triage_distill.py`

**Interfaces:**

Consumes:
- `alex.lib.triage.models` (Task 1): `LedgerEvent`, `LedgerEventKind`, `Rubric`
- `alex.lib.llm` (existing): `Completer` protocol, `LlmError`
- `alex.lib.prompt_templates` (existing): `load_prompt`

Produces (later tasks rely on these exact signatures):
```python
def distill_rubric(rubric: Rubric, events: Sequence[LedgerEvent],
                   completer: Completer, model: str) -> Rubric
def format_events_for_distill(events: Sequence[LedgerEvent]) -> str
```
Plus prompt `triage_rubric_distill` v001 (active), placeholders exactly `{{rubric}}`, `{{events}}`.

Pinned event-line format (tests depend on it): non-approve events render as `- <event> <note>; proposed <decision>:<target>; corrected to <decision>:<target>; reason: <reason>` with absent parts omitted; approvals aggregate into trailing `- approved <N>x: <decision>:<target>` lines (target omitted when empty), sorted by (decision, target).

- [ ] **Step 1: Write the failing prompt test**

  Create `tests/test_triage_distill.py`:

  ```python
  """Tests for rubric distillation from ledger events."""

  from alex.lib.prompt_templates import load_prompt


  def test_triage_rubric_distill_prompt_has_exact_placeholder_set() -> None:
      template = load_prompt("triage_rubric_distill")
      assert template.version == "v001"
      assert template.placeholders() == frozenset({"rubric", "events"})
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_distill.py -v
  ```

  Expected: 1 failed with `PromptTemplateError: Unknown prompt: triage_rubric_distill`.

- [ ] **Step 3: Create the prompt files**

  Create `src/alex/prompts/triage_rubric_distill/v001.md` with exactly this content:

  ```markdown
  You maintain the filing rubric for a personal Obsidian vault triage
  pipeline. The rubric is injected into every filing and atomic-note prompt,
  so every rule must earn its tokens. Rewrite it to fold in what the owner's
  latest review events teach.

  ## Current rubric

  {{rubric}}

  ## Review events since the last distillation

  One line per event. Approvals are aggregated into counts and confirm what
  already works. Rejections, edits, and re-proposals carry the owner's
  corrections and are the strongest signal.

  {{events}}

  ## Your task

  Produce the next version of the rubric. This is a compression job, not an
  append job.

  1. Keep exactly two sections, in this order: "## Triage rules" and
     "## Atomic note rules".
  2. Number the rules within each section. Each rule is one line: the rule,
     then a terse rationale.
  3. At most 40 rules total across both sections. Merge overlapping rules,
     generalize repeated corrections into one rule, and drop rules the
     events show to be wrong. Never restate the same idea twice.
  4. Keep rules the events do not contradict, including hand-written ones;
     the owner edits this file directly and those edits are legitimate.
  5. Prefer specific, checkable rules ("meetings are weak area evidence")
     over vague advice ("file thoughtfully").
  6. The whole rubric must stay under roughly 2000 tokens.

  Respond with ONLY the complete replacement rubric markdown body: the two
  sections and their numbered rules. No frontmatter, no code fences, no
  commentary.
  ```

  Create `src/alex/prompts/triage_rubric_distill/active.txt` containing exactly `v001` plus a trailing newline:

  ```text
  v001
  ```

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_distill.py -v
  ```

  Expected: 1 passed.

- [ ] **Step 5: Write the failing distillation tests**

  Replace `tests/test_triage_distill.py` in full with:

  ```python
  """Tests for rubric distillation from ledger events."""

  from alex.lib.llm import LlmError
  from alex.lib.prompt_templates import load_prompt
  from alex.lib.triage.distill import distill_rubric, format_events_for_distill
  from alex.lib.triage.models import LedgerEvent, LedgerEventKind, Rubric


  class ScriptedCompleter:
      """Returns one canned reply for every call; records prompts."""

      def __init__(self, response: str) -> None:
          self.response = response
          self.prompts: list[str] = []

      def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
          self.prompts.append(prompt)
          return self.response


  class FailingCompleter:
      def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
          raise LlmError("model unavailable")


  NEW_RUBRIC = (
      "## Triage rules\n"
      "1. Meetings are weak area evidence; prefer skip. Attendance is not\n"
      "   engagement.\n\n"
      "## Atomic note rules\n"
      "1. One claim per note. Split notes that argue two things."
  )


  def make_event(
      *,
      event: LedgerEventKind,
      note: str,
      proposal: dict[str, str] | None = None,
      correction: dict[str, str] | None = None,
      reason: str = "",
  ) -> LedgerEvent:
      return LedgerEvent(
          ts="2026-07-12T10:00:00",
          note=note,
          batch=1,
          rubric_version=3,
          event=event,
          proposal=proposal or {},
          correction=correction,
          reason=reason,
      )


  def test_triage_rubric_distill_prompt_has_exact_placeholder_set() -> None:
      template = load_prompt("triage_rubric_distill")
      assert template.version == "v001"
      assert template.placeholders() == frozenset({"rubric", "events"})


  def test_distill_rubric_bumps_version_and_replaces_text() -> None:
      rubric = Rubric(version=3, text="## Triage rules\n1. Old rule.")
      completer = ScriptedCompleter(NEW_RUBRIC + "\n")
      events = [make_event(event="reject", note="A.md", reason="not an area")]

      result = distill_rubric(rubric, events, completer, "fake/model")

      assert result.version == 4
      assert result.text == NEW_RUBRIC


  def test_distill_rubric_prompt_contains_rubric_and_events() -> None:
      rubric = Rubric(version=1, text="## Triage rules\n1. Old rule.")
      completer = ScriptedCompleter(NEW_RUBRIC)
      events = [
          make_event(
              event="reject",
              note="A.md",
              proposal={"decision": "area", "target": "writing"},
              reason="not writing",
          )
      ]

      distill_rubric(rubric, events, completer, "fake/model")

      assert len(completer.prompts) == 1
      assert "1. Old rule." in completer.prompts[0]
      assert "reject A.md" in completer.prompts[0]
      assert "proposed area:writing" in completer.prompts[0]
      assert "reason: not writing" in completer.prompts[0]


  def test_distill_rubric_returns_input_rubric_when_llm_fails() -> None:
      rubric = Rubric(version=3, text="## Triage rules\n1. Keep me.")
      events = [make_event(event="reject", note="A.md")]

      result = distill_rubric(rubric, events, FailingCompleter(), "fake/model")

      assert result == rubric


  def test_distill_rubric_returns_input_rubric_on_blank_output() -> None:
      rubric = Rubric(version=3, text="## Triage rules\n1. Keep me.")
      events = [make_event(event="reject", note="A.md")]

      result = distill_rubric(rubric, events, ScriptedCompleter("  \n"), "fake/model")

      assert result == rubric


  def test_format_events_aggregates_approvals_into_counts() -> None:
      events = [
          make_event(
              event="approve",
              note="A.md",
              proposal={"decision": "area", "target": "learning-science"},
          ),
          make_event(
              event="approve",
              note="B.md",
              proposal={"decision": "area", "target": "learning-science"},
          ),
          make_event(
              event="approve",
              note="C.md",
              proposal={"decision": "trash", "target": ""},
          ),
      ]

      text = format_events_for_distill(events)

      assert "- approved 2x: area:learning-science" in text
      assert "- approved 1x: trash" in text
      assert "A.md" not in text


  def test_format_events_renders_correction_and_reason() -> None:
      event = make_event(
          event="edit",
          note="Standup notes.md",
          proposal={"decision": "area", "target": "writing"},
          correction={"decision": "archive", "target": "notes"},
          reason="standups are records, not knowledge",
      )

      assert format_events_for_distill([event]) == (
          "- edit Standup notes.md; proposed area:writing; "
          "corrected to archive:notes; reason: standups are records, not knowledge"
      )
  ```

- [ ] **Step 6: Run test to verify it fails**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_distill.py -v
  ```

  Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.distill'`.

- [ ] **Step 7: Write the implementation**

  Create `src/alex/lib/triage/distill.py`:

  ```python
  """Distill corrections-ledger events into the next rubric version."""

  from __future__ import annotations

  from collections import Counter
  from collections.abc import Sequence
  from typing import Any

  from alex.lib.llm import Completer, LlmError
  from alex.lib.prompt_templates import load_prompt
  from alex.lib.triage.models import LedgerEvent, Rubric

  _PROMPT_NAME = "triage_rubric_distill"
  _DISTILL_MAX_TOKENS = 2048


  def distill_rubric(
      rubric: Rubric,
      events: Sequence[LedgerEvent],
      completer: Completer,
      model: str,
  ) -> Rubric:
      prompt = load_prompt(_PROMPT_NAME).render(
          rubric=rubric.text,
          events=format_events_for_distill(events) or "(no events)",
      )
      try:
          raw = completer.complete(
              prompt=prompt, model=model, max_tokens=_DISTILL_MAX_TOKENS
          )
      except LlmError:
          return rubric
      text = raw.strip()
      if not text:
          return rubric
      return Rubric(version=rubric.version + 1, text=text)


  def format_events_for_distill(events: Sequence[LedgerEvent]) -> str:
      approvals: Counter[tuple[str, str]] = Counter()
      lines: list[str] = []
      for event in events:
          if event.event == "approve":
              approvals[_decision_key(event.proposal)] += 1
              continue
          parts = [f"{event.event} {event.note}"]
          if event.proposal:
              parts.append(f"proposed {_decision_label(event.proposal)}")
          if event.correction:
              parts.append(f"corrected to {_decision_label(event.correction)}")
          if event.reason:
              parts.append(f"reason: {event.reason}")
          lines.append("- " + "; ".join(parts))
      for (decision, target), count in sorted(approvals.items()):
          label = f"{decision}:{target}" if target else decision
          lines.append(f"- approved {count}x: {label}")
      return "\n".join(lines)


  def _decision_key(data: dict[str, Any]) -> tuple[str, str]:
      return str(data.get("decision", "?")), str(data.get("target", ""))


  def _decision_label(data: dict[str, Any]) -> str:
      decision, target = _decision_key(data)
      return f"{decision}:{target}" if target else decision
  ```

- [ ] **Step 8: Run test to verify it passes**

  ```bash
  cd /home/alex/code/alex && uv run pytest tests/test_triage_distill.py -v
  ```

  Expected: 7 passed.

- [ ] **Step 9: Run lint and typecheck**

  ```bash
  cd /home/alex/code/alex && just lint && uv run mypy
  ```

  Expected: ruff check and ruff format --check clean, mypy reports no issues.

- [ ] **Step 10: Commit**

  ```bash
  cd /home/alex/code/alex
  git add src/alex/prompts/triage_rubric_distill/v001.md src/alex/prompts/triage_rubric_distill/active.txt src/alex/lib/triage/distill.py tests/test_triage_distill.py
  git commit -m "feat(triage): rubric distillation from ledger events

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
  ```
### Task 11: Vault link rewriting (`src/alex/lib/vault_links.py`)

Corrected port of the move-file skill script. Obsidian resolves bare-name links (`[[Note]]`, `[[Note#H]]`, `[[Note.md]]`) vault-wide by filename, so those survive a move and are left untouched; only path-style targets (containing `/`) break and get rewritten. The old script silently broke heading and block anchors; this port preserves them. The backlink scan never edits the append-only zones: top-level `archives/`, `archive/`, and `trash/` are excluded alongside dot-directories. Deliberate spec deviation: relative wiki links are not resolved (the original skill script never resolved them either; this vault links vault-relative or bare-name). All commands run from the repo root `/home/alex/code/alex`.

**Files:**
- Create: `src/alex/lib/vault_links.py`
- Test: `tests/test_vault_links.py`

**Interfaces:**
- Consumes: `atomic_write_text(path: Path, text: str) -> None` from `alex.lib.triage.storage` (Task 1).
- Produces:
  - `WIKI_LINK_PATTERN: re.Pattern[str]`
  - `rewrite_links_for_move(content: str, old_rel: str, new_rel: str) -> tuple[str, int]`
  - `move_note(vault_root: Path, source: Path, destination: Path, *, dry_run: bool) -> tuple[Path, list[tuple[Path, int]]]`

  Consumed by Task 12 (`apply.execute_apply_plan`) and the Task 18 e2e.

- [ ] **Step 1: Write the failing tests for the link-rewrite matrix**

Create `tests/test_vault_links.py`:

```python
"""Tests for anchor-safe wiki-link rewriting and note moves."""

from alex.lib.vault_links import rewrite_links_for_move

OLD_REL = "path/to/note.md"
NEW_REL = "areas/topic/note.md"


def test_rewrites_plain_path_link_without_extension() -> None:
    rewritten, count = rewrite_links_for_move(
        "See [[path/to/note]] for details.", OLD_REL, NEW_REL
    )
    assert rewritten == "See [[areas/topic/note]] for details."
    assert count == 1


def test_rewrites_path_link_keeping_md_extension() -> None:
    rewritten, count = rewrite_links_for_move(
        "See [[path/to/note.md]].", OLD_REL, NEW_REL
    )
    assert rewritten == "See [[areas/topic/note.md]]."
    assert count == 1


def test_rewrites_aliased_path_link_preserving_alias() -> None:
    rewritten, count = rewrite_links_for_move(
        "See [[path/to/note|the good note]].", OLD_REL, NEW_REL
    )
    assert rewritten == "See [[areas/topic/note|the good note]]."
    assert count == 1


def test_rewrites_embedded_link_preserving_heading_anchor() -> None:
    rewritten, count = rewrite_links_for_move(
        "![[path/to/note#Key Ideas]]", OLD_REL, NEW_REL
    )
    assert rewritten == "![[areas/topic/note#Key Ideas]]"
    assert count == 1


def test_rewrites_block_anchor_path_link() -> None:
    rewritten, count = rewrite_links_for_move(
        "Quote: [[path/to/note#^block123]].", OLD_REL, NEW_REL
    )
    assert rewritten == "Quote: [[areas/topic/note#^block123]]."
    assert count == 1


def test_rewrites_link_with_anchor_and_alias_together() -> None:
    rewritten, count = rewrite_links_for_move(
        "[[path/to/note#Heading|see this]]", OLD_REL, NEW_REL
    )
    assert rewritten == "[[areas/topic/note#Heading|see this]]"
    assert count == 1


def test_leaves_bare_name_links_untouched() -> None:
    content = "See [[note]] and [[note|alias]] and ![[note#Heading]]."
    rewritten, count = rewrite_links_for_move(content, OLD_REL, NEW_REL)
    assert rewritten == content
    assert count == 0


def test_leaves_links_to_other_paths_untouched() -> None:
    content = "See [[path/to/other]] and [[other/path/to/note]]."
    rewritten, count = rewrite_links_for_move(content, OLD_REL, NEW_REL)
    assert rewritten == content
    assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_vault_links.py -v
```

Expected failure: collection error, `ModuleNotFoundError: No module named 'alex.lib.vault_links'`.

- [ ] **Step 3: Write the implementation (rewrite_links_for_move)**

Create `src/alex/lib/vault_links.py`:

```python
"""Move vault notes while rewriting path-style wiki links.

Corrected port of the move-file skill script. Obsidian resolves bare-name
links ([[Note]], [[Note#Heading]], [[Note.md]]) vault-wide by filename, so
they survive a move untouched; only path-style targets (containing "/")
break and are rewritten. Unlike the old script, heading and block anchors
are preserved instead of silently broken.
"""

from __future__ import annotations

import re

WIKI_LINK_PATTERN = re.compile(r"(!?)\[\[([^\]|#]+)(#[^\]|]*)?(\|[^\]]*)?\]\]")


def _normalize_target(target: str) -> str:
    normalized = target.replace("\\", "/").strip()
    if not normalized.endswith(".md"):
        normalized += ".md"
    return normalized


def rewrite_links_for_move(
    content: str, old_rel: str, new_rel: str
) -> tuple[str, int]:
    """Rewrite path-style wiki links pointing at old_rel to point at new_rel.

    Both paths are vault-relative posix paths including the .md extension.
    Anchors, aliases, embed prefixes, and the writer's extension style are
    preserved. Returns the rewritten content and the number of links changed.
    """
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        target = match.group(2)
        if "/" not in target or _normalize_target(target) != old_rel:
            return match.group(0)
        anchor = match.group(3) or ""
        alias = match.group(4) or ""
        keeps_extension = target.strip().endswith(".md")
        new_target = new_rel if keeps_extension else new_rel.removesuffix(".md")
        count += 1
        return f"{match.group(1)}[[{new_target}{anchor}{alias}]]"

    return WIKI_LINK_PATTERN.sub(replace, content), count
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_vault_links.py -v
```

Expected: `8 passed`.

- [ ] **Step 5: Write the failing tests for move_note**

In `tests/test_vault_links.py`, replace the import line with:

```python
from pathlib import Path

import pytest

from alex.lib.vault_links import move_note, rewrite_links_for_move
```

Append at the end of the file:

```python
def build_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "path" / "to").mkdir(parents=True)
    (vault / "path" / "to" / "note.md").write_text(
        "# Note\n\nSelf link: [[path/to/note]].\n", encoding="utf-8"
    )
    (vault / "linker.md").write_text(
        "Points at [[path/to/note#Heading|alias]].\n", encoding="utf-8"
    )
    (vault / "unrelated.md").write_text(
        "Points at [[path/to/other]] and bare [[note]].\n", encoding="utf-8"
    )
    return vault


def test_move_note_rewrites_backlinks_and_moves_file(tmp_path: Path) -> None:
    vault = build_vault(tmp_path)
    source = vault / "path" / "to" / "note.md"
    destination = vault / "areas" / "topic" / "note.md"

    final, rewrites = move_note(vault, source, destination, dry_run=False)

    assert final == destination
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == (
        "# Note\n\nSelf link: [[areas/topic/note]].\n"
    )
    assert (vault / "linker.md").read_text(encoding="utf-8") == (
        "Points at [[areas/topic/note#Heading|alias]].\n"
    )
    assert {(path.name, count) for path, count in rewrites} == {
        ("note.md", 1),
        ("linker.md", 1),
    }


def test_move_note_leaves_unrelated_file_untouched(tmp_path: Path) -> None:
    vault = build_vault(tmp_path)
    before = (vault / "unrelated.md").read_text(encoding="utf-8")

    move_note(
        vault,
        vault / "path" / "to" / "note.md",
        vault / "areas" / "topic" / "note.md",
        dry_run=False,
    )

    assert (vault / "unrelated.md").read_text(encoding="utf-8") == before


def test_move_note_renames_on_collision_and_links_follow(tmp_path: Path) -> None:
    vault = build_vault(tmp_path)
    destination = vault / "areas" / "topic" / "note.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("occupied\n", encoding="utf-8")

    final, _ = move_note(
        vault, vault / "path" / "to" / "note.md", destination, dry_run=False
    )

    assert final == vault / "areas" / "topic" / "note (2).md"
    assert final.exists()
    assert destination.read_text(encoding="utf-8") == "occupied\n"
    assert (vault / "linker.md").read_text(encoding="utf-8") == (
        "Points at [[areas/topic/note (2)#Heading|alias]].\n"
    )


def test_move_note_dry_run_reports_rewrites_without_touching_disk(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    source = vault / "path" / "to" / "note.md"
    destination = vault / "areas" / "topic" / "note.md"
    linker_before = (vault / "linker.md").read_text(encoding="utf-8")

    final, rewrites = move_note(vault, source, destination, dry_run=True)

    assert final == destination
    assert source.exists()
    assert not destination.exists()
    assert (vault / "linker.md").read_text(encoding="utf-8") == linker_before
    assert sum(count for _, count in rewrites) == 2


def test_move_note_skips_files_in_dot_directories(tmp_path: Path) -> None:
    vault = build_vault(tmp_path)
    hidden = vault / ".obsidian" / "cache.md"
    hidden.parent.mkdir()
    hidden.write_text("cached [[path/to/note]]\n", encoding="utf-8")

    _, rewrites = move_note(
        vault,
        vault / "path" / "to" / "note.md",
        vault / "areas" / "topic" / "note.md",
        dry_run=False,
    )

    assert hidden.read_text(encoding="utf-8") == "cached [[path/to/note]]\n"
    assert all(path != hidden for path, _ in rewrites)


def test_move_note_skips_files_in_append_only_directories(tmp_path: Path) -> None:
    vault = build_vault(tmp_path)
    stale_files: list[Path] = []
    for zone in ("archives", "archive", "trash"):
        stale = vault / zone / "old.md"
        stale.parent.mkdir()
        stale.write_text("kept [[path/to/note]]\n", encoding="utf-8")
        stale_files.append(stale)

    _, rewrites = move_note(
        vault,
        vault / "path" / "to" / "note.md",
        vault / "areas" / "topic" / "note.md",
        dry_run=False,
    )

    rewritten_paths = {path for path, _ in rewrites}
    for stale in stale_files:
        assert stale.read_text(encoding="utf-8") == "kept [[path/to/note]]\n"
        assert stale not in rewritten_paths


def test_move_note_raises_for_missing_source(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(FileNotFoundError):
        move_note(vault, vault / "gone.md", vault / "trash" / "gone.md", dry_run=False)
```

- [ ] **Step 6: Run test to verify it fails**

```bash
uv run pytest tests/test_vault_links.py -v
```

Expected failure: collection error, `ImportError: cannot import name 'move_note' from 'alex.lib.vault_links'`.

- [ ] **Step 7: Write the implementation (move_note)**

In `src/alex/lib/vault_links.py`, replace the import section (everything between the module docstring and `WIKI_LINK_PATTERN`) with:

```python
from __future__ import annotations

import re
import shutil
from pathlib import Path

from alex.lib.triage.storage import atomic_write_text
```

Append at the end of the file:

```python
_EXCLUDED_TOP_DIRS = frozenset({"archives", "archive", "trash"})


def _markdown_files(vault_root: Path) -> list[Path]:
    """Vault .md files eligible for backlink rewriting, sorted for determinism.

    Skips dot-directories and the append-only zones (top-level archives/,
    archive/, and trash/), which are never edited.
    """
    files: list[Path] = []
    for md_file in sorted(vault_root.rglob("*.md")):
        directories = md_file.relative_to(vault_root).parts[:-1]
        if any(part.startswith(".") for part in directories):
            continue
        if directories and directories[0] in _EXCLUDED_TOP_DIRS:
            continue
        files.append(md_file)
    return files


def _next_free_path(destination: Path) -> Path:
    if not destination.exists():
        return destination
    counter = 2
    while True:
        candidate = destination.with_name(
            f"{destination.stem} ({counter}){destination.suffix}"
        )
        if not candidate.exists():
            return candidate
        counter += 1


def move_note(
    vault_root: Path, source: Path, destination: Path, *, dry_run: bool
) -> tuple[Path, list[tuple[Path, int]]]:
    """Move a note, rewriting path-style backlinks across the vault.

    Returns the final destination (after any collision rename) and one
    (file, links_rewritten) pair per file that references the note. With
    dry_run nothing is written; the return value describes what a real run
    would do. Backlink files are rewritten before the note itself moves.
    """
    if not source.is_file():
        raise FileNotFoundError(f"Source note does not exist: {source}")
    final_destination = _next_free_path(destination)
    old_rel = source.relative_to(vault_root).as_posix()
    new_rel = final_destination.relative_to(vault_root).as_posix()
    rewrites: list[tuple[Path, int]] = []
    for md_file in _markdown_files(vault_root):
        content = md_file.read_text(encoding="utf-8")
        rewritten, count = rewrite_links_for_move(content, old_rel, new_rel)
        if count == 0:
            continue
        rewrites.append((md_file, count))
        if not dry_run:
            atomic_write_text(md_file, rewritten)
    if not dry_run:
        final_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(final_destination))
    return final_destination, rewrites
```

- [ ] **Step 8: Run test to verify it passes**

```bash
uv run pytest tests/test_vault_links.py -v
```

Expected: `15 passed`.

- [ ] **Step 9: Lint and typecheck**

```bash
just lint
uv run mypy
```

Expected: both clean (no ruff findings, no format diffs, no mypy errors).

- [ ] **Step 10: Commit**

```bash
cd /home/alex/code/alex && git add src/alex/lib/vault_links.py tests/test_vault_links.py && git commit -m "feat(triage): port move-file link rewriting as vault_links with anchor support

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 12: Apply planner and executor (`src/alex/lib/triage/apply.py`)

Plans and executes the physical moves for notes whose `triage:` block says `status: decided`. Every destination is validated before its move (kebab-case slug, existing area index or approved-this-run area, existing resource topic); a failed validation becomes a `MoveResult(status="failed")` report line and the run continues, so a free-typed or stale target can never silently create an index-less area folder. Depends on Tasks 1 (models, storage, paths), 2 (frontmatter), 5 (inventory), and 11 (vault_links). All commands run from the repo root `/home/alex/code/alex`.

**Files:**
- Create: `src/alex/lib/triage/apply.py`
- Test: `tests/test_triage_apply.py`

**Interfaces:**
- Consumes:
  - Task 1 models: `ApplyPlan`, `ApplyReport`, `MoveResult`, `NewAreaProposal`, `PendingAreas`, `PlannedMove`, `TriageBlock`, `FilingDecision`, `Population` from `alex.lib.triage.models`
  - `TriagePaths` (`pending_areas_path`, `processing_log_path`) from `alex.lib.triage.paths`
  - `atomic_write_text(path: Path, text: str) -> None`, `read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None` from `alex.lib.triage.storage`
  - `read_triage_block(text: str) -> TriageBlock | None`, `write_triage_block(text: str, block: TriageBlock) -> str` from `alex.lib.triage.frontmatter` (Task 2)
  - `MOVABLE_POPULATIONS: frozenset[Population]`, `discover_population_files(vault_root: Path) -> list[tuple[Population, Path]]` from `alex.lib.triage.inventory` (Task 5)
  - `move_note(vault_root: Path, source: Path, destination: Path, *, dry_run: bool) -> tuple[Path, list[tuple[Path, int]]]` from `alex.lib.vault_links` (Task 11)
- Produces (consumed by Task 17 `alex triage apply` and Task 18 e2e):
  - `destination_for(decision: FilingDecision, target: str, note_path: str, population: Population) -> str | None`
  - `build_apply_plan(vault_root: Path) -> ApplyPlan`
  - `execute_apply_plan(plan: ApplyPlan, vault_root: Path, *, write: bool) -> ApplyReport`
  - `render_area_index(area: NewAreaProposal, created: str) -> str`
  - `format_apply_plan(plan: ApplyPlan) -> str`

- [ ] **Step 1: Write the failing tests for destination_for**

Create `tests/test_triage_apply.py`:

```python
"""Tests for the triage apply planner and executor."""

from alex.lib.triage.apply import destination_for
from alex.lib.triage.models import FilingDecision


def test_destination_for_routes_each_filing_decision() -> None:
    cases: dict[FilingDecision, str] = {
        "area": "areas/pkm/N.md",
        "resource": "resources/pkm/N.md",
        "archive": "archives/pkm/N.md",
        "trash": "trash/N.md",
    }
    for decision, expected in cases.items():
        assert destination_for(decision, "pkm", "N.md", "root") == expected


def test_destination_for_defaults_archive_target_to_notes() -> None:
    assert destination_for("archive", "", "N.md", "root") == "archives/notes/N.md"


def test_destination_for_forces_clipping_archives_into_archives_clippings() -> None:
    result = destination_for("archive", "essays", "Clippings/Post.md", "clippings")
    assert result == "archives/clippings/Post.md"


def test_destination_for_returns_none_for_annotate_only_populations() -> None:
    assert destination_for("area", "pkm", "Meetings/Standup.md", "meetings") is None
    assert destination_for("area", "pkm", "Weekly/2026-W28.md", "weekly") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected failure: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.apply'`.

- [ ] **Step 3: Write the implementation (module skeleton + destination_for)**

Create `src/alex/lib/triage/apply.py`. The import block is the complete final one for this module; later steps only append functions.

```python
"""Plan and execute the physical moves for decided triage notes."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml

from alex.lib.triage.frontmatter import read_triage_block, write_triage_block
from alex.lib.triage.inventory import MOVABLE_POPULATIONS, discover_population_files
from alex.lib.triage.models import (
    ApplyPlan,
    ApplyReport,
    FilingDecision,
    MoveResult,
    NewAreaProposal,
    PendingAreas,
    PlannedMove,
    Population,
)
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.storage import atomic_write_text, read_yaml_model
from alex.lib.vault_links import move_note


def destination_for(
    decision: FilingDecision, target: str, note_path: str, population: Population
) -> str | None:
    """Return the vault-relative destination for a decided note.

    None means the population is annotate-only and nothing moves.
    """
    if population not in MOVABLE_POPULATIONS:
        return None
    name = PurePosixPath(note_path).name
    if decision == "area":
        return f"areas/{target}/{name}"
    if decision == "resource":
        return f"resources/{target}/{name}"
    if decision == "archive":
        if population == "clippings":
            return f"archives/clippings/{name}"
        return f"archives/{target or 'notes'}/{name}"
    return f"trash/{name}"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Write the failing tests for build_apply_plan**

In `tests/test_triage_apply.py`, replace the import section with:

```python
from pathlib import Path

from alex.lib.triage.apply import build_apply_plan, destination_for
from alex.lib.triage.frontmatter import write_triage_block
from alex.lib.triage.models import FilingDecision, TriageBlock
```

Add these helpers directly below the imports (before the first test):

```python
def make_note(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def decided_note(decision: FilingDecision, target: str) -> str:
    block = TriageBlock(
        decision=decision, target=target, status="decided", decided="2026-07-10"
    )
    return write_triage_block("---\ntype: note\n---\nBody text.\n", block)
```

Append at the end of the file:

```python
def test_build_apply_plan_collects_decided_notes_and_skips_the_rest(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Filed note.md", decided_note("area", "learning-science"))
    make_note(vault / "Reference dump.md", decided_note("resource", "pkm"))
    make_note(vault / "Old stuff.md", decided_note("archive", ""))
    make_note(vault / "Junk.md", decided_note("trash", ""))
    make_note(vault / "Untriaged.md", "---\ntype: note\n---\nBody.\n")
    applied_block = TriageBlock(
        decision="area",
        target="pkm",
        status="applied",
        decided="2026-07-01",
        applied="2026-07-05",
    )
    make_note(
        vault / "Already applied.md",
        write_triage_block("---\ntype: note\n---\nBody.\n", applied_block),
    )
    make_note(vault / "Clippings" / "Saved article.md", decided_note("archive", ""))

    plan = build_apply_plan(vault)

    destinations = {move.note_path: move.destination for move in plan.moves}
    assert destinations == {
        "Filed note.md": "areas/learning-science/Filed note.md",
        "Reference dump.md": "resources/pkm/Reference dump.md",
        "Old stuff.md": "archives/notes/Old stuff.md",
        "Junk.md": "trash/Junk.md",
        "Clippings/Saved article.md": "archives/clippings/Saved article.md",
    }
    assert plan.skipped == []
    assert plan.new_areas == []


def test_build_apply_plan_reports_decided_meeting_notes_as_skipped(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Meetings" / "Standup.md", decided_note("area", "team-culture"))

    plan = build_apply_plan(vault)

    assert plan.moves == []
    assert plan.skipped == [
        "Meetings/Standup.md: annotate-only population, nothing to move"
    ]


def test_build_apply_plan_lists_pending_areas_whose_folder_is_missing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / "areas" / "existing-area").mkdir(parents=True)
    pending = vault / ".claude" / "triage" / "pending-areas.yaml"
    pending.parent.mkdir(parents=True)
    pending.write_text(
        "areas:\n"
        "- slug: existing-area\n"
        "  name: Existing Area\n"
        "  description: Already on disk.\n"
        "- slug: spaced-repetition\n"
        "  name: Spaced Repetition\n"
        "  description: Retention through scheduled recall.\n",
        encoding="utf-8",
    )

    plan = build_apply_plan(vault)

    assert [area.slug for area in plan.new_areas] == ["spaced-repetition"]
```

- [ ] **Step 6: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected failure: collection error, `ImportError: cannot import name 'build_apply_plan' from 'alex.lib.triage.apply'`.

- [ ] **Step 7: Write the implementation (build_apply_plan)**

Append to `src/alex/lib/triage/apply.py`:

```python
def build_apply_plan(vault_root: Path) -> ApplyPlan:
    """Collect decided-but-unapplied notes and pending new areas."""
    paths = TriagePaths(vault_root=vault_root)
    plan = ApplyPlan()
    for population, md_path in discover_population_files(vault_root):
        block = read_triage_block(md_path.read_text(encoding="utf-8"))
        if block is None or block.status != "decided" or block.decision is None:
            continue
        note_path = md_path.relative_to(vault_root).as_posix()
        destination = destination_for(
            block.decision, block.target, note_path, population
        )
        if destination is None:
            plan.skipped.append(
                f"{note_path}: annotate-only population, nothing to move"
            )
            continue
        plan.moves.append(
            PlannedMove(
                note_path=note_path,
                destination=destination,
                decision=block.decision,
                target=block.target,
            )
        )
    plan.moves.sort(key=lambda move: move.note_path)
    pending = read_yaml_model(paths.pending_areas_path, PendingAreas)
    if pending is not None:
        for area in pending.areas:
            if not (vault_root / "areas" / area.slug).is_dir():
                plan.new_areas.append(area)
    return plan
```

- [ ] **Step 8: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected: `7 passed`.

- [ ] **Step 9: Write the failing tests for render_area_index and execute_apply_plan**

In `tests/test_triage_apply.py`, replace the import section with:

```python
from datetime import date
from pathlib import Path

from alex.lib.triage.apply import (
    build_apply_plan,
    destination_for,
    execute_apply_plan,
    render_area_index,
)
from alex.lib.triage.frontmatter import read_triage_block, write_triage_block
from alex.lib.triage.models import (
    ApplyPlan,
    FilingDecision,
    NewAreaProposal,
    PlannedMove,
    TriageBlock,
)
```

Append at the end of the file:

```python
def test_render_area_index_has_frontmatter_title_and_evidence() -> None:
    area = NewAreaProposal(
        slug="spaced-repetition",
        name="Spaced Repetition",
        description="Retention through scheduled recall.",
    )

    text = render_area_index(area, "2026-07-12")

    assert text == (
        "---\n"
        "type: area\n"
        "created: 2026-07-12\n"
        "description: Retention through scheduled recall.\n"
        "---\n"
        "\n"
        "# Spaced Repetition\n"
        "\n"
        "Retention through scheduled recall.\n"
        "\n"
        "## Discovery Evidence\n"
        "\n"
        "- Proposed during vault triage on 2026-07-12.\n"
    )


def test_execute_apply_plan_write_moves_flips_status_and_logs(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Clippings" / "Great article.md", decided_note("archive", ""))
    make_note(
        vault / "Linker.md",
        "---\ntype: note\n---\nSee [[Clippings/Great article]].\n",
    )
    plan = build_apply_plan(vault)

    report = execute_apply_plan(plan, vault, write=True)

    assert [result.status for result in report.results] == ["moved"]
    assert report.results[0].destination == "archives/clippings/Great article.md"
    assert report.results[0].links_rewritten == 1
    assert not (vault / "Clippings" / "Great article.md").exists()
    moved = vault / "archives" / "clippings" / "Great article.md"
    block = read_triage_block(moved.read_text(encoding="utf-8"))
    assert block is not None
    assert block.status == "applied"
    assert block.applied == date.today().isoformat()
    linker_text = (vault / "Linker.md").read_text(encoding="utf-8")
    assert "See [[archives/clippings/Great article]]." in linker_text
    log = (vault / "_meta" / "processing-log.md").read_text(encoding="utf-8")
    assert log == (
        f"- {date.today().isoformat()} triage: moved Clippings/Great article.md"
        " -> archives/clippings/Great article.md (1 links updated)\n"
    )


def test_execute_apply_plan_creates_pending_areas_before_moving(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Recall note.md", decided_note("area", "spaced-repetition"))
    area = NewAreaProposal(
        slug="spaced-repetition",
        name="Spaced Repetition",
        description="Retention through scheduled recall.",
    )
    plan = ApplyPlan(
        moves=[
            PlannedMove(
                note_path="Recall note.md",
                destination="areas/spaced-repetition/Recall note.md",
                decision="area",
                target="spaced-repetition",
            )
        ],
        new_areas=[area],
    )

    report = execute_apply_plan(plan, vault, write=True)

    assert report.areas_created == ["spaced-repetition"]
    assert [result.status for result in report.results] == ["moved"]
    index_path = vault / "areas" / "spaced-repetition" / "index.md"
    expected_index = render_area_index(area, date.today().isoformat())
    assert index_path.read_text(encoding="utf-8") == expected_index
    assert (vault / "areas" / "spaced-repetition" / "Recall note.md").exists()


def test_execute_apply_plan_records_failures_and_continues(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Real note.md", decided_note("trash", ""))
    plan = ApplyPlan(
        moves=[
            PlannedMove(
                note_path="Ghost.md",
                destination="trash/Ghost.md",
                decision="trash",
                target="",
            ),
            PlannedMove(
                note_path="Real note.md",
                destination="trash/Real note.md",
                decision="trash",
                target="",
            ),
        ]
    )

    report = execute_apply_plan(plan, vault, write=True)

    assert [result.status for result in report.results] == ["failed", "moved"]
    assert "Ghost.md" in report.results[0].error
    assert (vault / "trash" / "Real note.md").exists()


def test_execute_apply_plan_fails_move_to_nonexistent_area(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Note.md", decided_note("area", "ghost-area"))
    plan = build_apply_plan(vault)

    report = execute_apply_plan(plan, vault, write=True)

    assert [result.status for result in report.results] == ["failed"]
    assert "areas/ghost-area/" in report.results[0].error
    assert (vault / "Note.md").exists()
    assert not (vault / "areas").exists()


def test_execute_apply_plan_fails_move_with_malformed_slug(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Note.md", decided_note("area", "Bad Slug!"))
    plan = build_apply_plan(vault)

    report = execute_apply_plan(plan, vault, write=True)

    assert [result.status for result in report.results] == ["failed"]
    assert "invalid area slug" in report.results[0].error
    assert (vault / "Note.md").exists()
    assert not (vault / "areas").exists()


def test_execute_apply_plan_fails_move_to_nonexistent_resource_topic(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Note.md", decided_note("resource", "ghost-topic"))
    plan = build_apply_plan(vault)

    report = execute_apply_plan(plan, vault, write=True)

    assert [result.status for result in report.results] == ["failed"]
    assert "resources/ghost-topic/" in report.results[0].error
    assert (vault / "Note.md").exists()
    assert not (vault / "resources").exists()


def test_execute_apply_plan_allows_archive_default_subfolder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Old note.md", decided_note("archive", ""))
    plan = build_apply_plan(vault)

    report = execute_apply_plan(plan, vault, write=True)

    assert [result.status for result in report.results] == ["moved"]
    assert (vault / "archives" / "notes" / "Old note.md").exists()


def test_execute_apply_plan_dry_run_reports_without_touching_disk(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    make_note(vault / "Clippings" / "Great article.md", decided_note("archive", ""))
    make_note(
        vault / "Linker.md",
        "---\ntype: note\n---\nSee [[Clippings/Great article]].\n",
    )
    pending = vault / ".claude" / "triage" / "pending-areas.yaml"
    pending.parent.mkdir(parents=True)
    pending.write_text(
        "areas:\n- slug: new-area\n  name: New Area\n  description: Fresh.\n",
        encoding="utf-8",
    )
    linker_before = (vault / "Linker.md").read_text(encoding="utf-8")
    plan = build_apply_plan(vault)

    report = execute_apply_plan(plan, vault, write=False)

    assert [result.status for result in report.results] == ["dry_run"]
    assert report.results[0].destination == "archives/clippings/Great article.md"
    assert report.results[0].links_rewritten == 1
    assert report.areas_created == []
    assert (vault / "Clippings" / "Great article.md").exists()
    assert not (vault / "archives").exists()
    assert not (vault / "areas").exists()
    assert not (vault / "_meta").exists()
    assert (vault / "Linker.md").read_text(encoding="utf-8") == linker_before
```

- [ ] **Step 10: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected failure: collection error, `ImportError: cannot import name 'execute_apply_plan' from 'alex.lib.triage.apply'`.

- [ ] **Step 11: Write the implementation (render_area_index + execute_apply_plan)**

Append to `src/alex/lib/triage/apply.py`:

```python
def render_area_index(area: NewAreaProposal, created: str) -> str:
    """Render the index.md for a newly approved area."""
    description_yaml = yaml.safe_dump(
        {"description": area.description}, sort_keys=False, allow_unicode=True
    ).rstrip("\n")
    return (
        "---\n"
        "type: area\n"
        f"created: {created}\n"
        f"{description_yaml}\n"
        "---\n"
        "\n"
        f"# {area.name}\n"
        "\n"
        f"{area.description}\n"
        "\n"
        "## Discovery Evidence\n"
        "\n"
        f"- Proposed during vault triage on {created}.\n"
    )


_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _validate_destination(
    move: PlannedMove, vault_root: Path, areas_created: list[str]
) -> str | None:
    """Return an error string when the move's destination is invalid.

    Guards the "no new areas created silently" rule: an area target must be
    a real area (index.md on disk) or one approved and created this run.
    """
    if move.decision == "area":
        if _SLUG_PATTERN.fullmatch(move.target) is None:
            return f"invalid area slug: {move.target!r}"
        index_path = vault_root / "areas" / move.target / "index.md"
        if move.target not in areas_created and not index_path.is_file():
            return f"area does not exist: areas/{move.target}/ has no index.md"
        return None
    if move.decision == "resource":
        if _SLUG_PATTERN.fullmatch(move.target) is None:
            return f"invalid resource topic: {move.target!r}"
        if not (vault_root / "resources" / move.target).is_dir():
            return f"resource topic does not exist: resources/{move.target}/"
        return None
    if move.decision == "archive":
        subfolder = move.target or "notes"
        if _SLUG_PATTERN.fullmatch(subfolder) is None:
            return f"invalid archive subfolder: {subfolder!r}"
        return None
    return None


def execute_apply_plan(
    plan: ApplyPlan, vault_root: Path, *, write: bool
) -> ApplyReport:
    """Create approved areas, then move each decided note, never aborting.

    Every destination is validated before its move; an invalid one becomes
    a MoveResult(status="failed") and the run continues. With write=False
    nothing touches disk; every valid move is reported with status "dry_run"
    and the link counts a real run would produce.
    """
    paths = TriagePaths(vault_root=vault_root)
    report = ApplyReport()
    today = date.today().isoformat()
    if write:
        for area in plan.new_areas:
            index_path = vault_root / "areas" / area.slug / "index.md"
            atomic_write_text(index_path, render_area_index(area, today))
            report.areas_created.append(area.slug)
    for move in plan.moves:
        error = _validate_destination(move, vault_root, report.areas_created)
        if error is not None:
            report.results.append(
                MoveResult(
                    note_path=move.note_path,
                    destination=move.destination,
                    status="failed",
                    error=error,
                )
            )
            continue
        report.results.append(
            _apply_move(move, vault_root, paths, today=today, write=write)
        )
    return report


def _apply_move(
    move: PlannedMove,
    vault_root: Path,
    paths: TriagePaths,
    *,
    today: str,
    write: bool,
) -> MoveResult:
    source = vault_root / move.note_path
    destination = vault_root / move.destination
    try:
        final_destination, rewrites = move_note(
            vault_root, source, destination, dry_run=not write
        )
        final_rel = final_destination.relative_to(vault_root).as_posix()
        links = sum(count for _, count in rewrites)
        if not write:
            return MoveResult(
                note_path=move.note_path,
                destination=final_rel,
                status="dry_run",
                links_rewritten=links,
            )
        _flip_status_to_applied(final_destination, today)
        _append_processing_log(
            paths.processing_log_path, today, move.note_path, final_rel, links
        )
        status: Literal["moved", "collision_renamed"] = (
            "moved" if final_rel == move.destination else "collision_renamed"
        )
        return MoveResult(
            note_path=move.note_path,
            destination=final_rel,
            status=status,
            links_rewritten=links,
        )
    except (OSError, RuntimeError, ValueError) as error:
        return MoveResult(
            note_path=move.note_path,
            destination=move.destination,
            status="failed",
            error=str(error),
        )


def _flip_status_to_applied(path: Path, today: str) -> None:
    text = path.read_text(encoding="utf-8")
    block = read_triage_block(text)
    if block is None:
        return
    block.status = "applied"
    block.applied = today
    atomic_write_text(path, write_triage_block(text, block))


def _append_processing_log(
    log_path: Path, today: str, source: str, destination: str, links: int
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"- {today} triage: moved {source} -> {destination} "
            f"({links} links updated)\n"
        )
```

- [ ] **Step 12: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected: `16 passed`.

- [ ] **Step 13: Write the failing tests for format_apply_plan**

In `tests/test_triage_apply.py`, add `format_apply_plan` to the `alex.lib.triage.apply` import so it reads:

```python
from alex.lib.triage.apply import (
    build_apply_plan,
    destination_for,
    execute_apply_plan,
    format_apply_plan,
    render_area_index,
)
```

Append at the end of the file:

```python
def test_format_apply_plan_groups_moves_by_destination_folder() -> None:
    plan = ApplyPlan(
        moves=[
            PlannedMove(
                note_path="A.md",
                destination="areas/pkm/A.md",
                decision="area",
                target="pkm",
            ),
            PlannedMove(
                note_path="B.md",
                destination="areas/pkm/B.md",
                decision="area",
                target="pkm",
            ),
            PlannedMove(
                note_path="C.md",
                destination="trash/C.md",
                decision="trash",
                target="",
            ),
        ],
        new_areas=[
            NewAreaProposal(slug="pkm", name="PKM", description="Notes on notes.")
        ],
        skipped=["Meetings/S.md: annotate-only population, nothing to move"],
    )

    text = format_apply_plan(plan)

    assert text == (
        "New areas to create:\n"
        "  areas/pkm/ (PKM)\n"
        "areas/pkm/ (2 notes):\n"
        "  A.md -> areas/pkm/A.md\n"
        "  B.md -> areas/pkm/B.md\n"
        "trash/ (1 note):\n"
        "  C.md -> trash/C.md\n"
        "Skipped:\n"
        "  Meetings/S.md: annotate-only population, nothing to move"
    )


def test_format_apply_plan_for_empty_plan() -> None:
    assert format_apply_plan(ApplyPlan()) == "Nothing to apply."
```

- [ ] **Step 14: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected failure: collection error, `ImportError: cannot import name 'format_apply_plan' from 'alex.lib.triage.apply'`.

- [ ] **Step 15: Write the implementation (format_apply_plan)**

Append to `src/alex/lib/triage/apply.py`:

```python
def format_apply_plan(plan: ApplyPlan) -> str:
    """Human-readable move plan, grouped by destination folder."""
    lines: list[str] = []
    if plan.new_areas:
        lines.append("New areas to create:")
        for area in plan.new_areas:
            lines.append(f"  areas/{area.slug}/ ({area.name})")
    grouped: dict[str, list[PlannedMove]] = {}
    for move in plan.moves:
        folder = str(PurePosixPath(move.destination).parent)
        grouped.setdefault(folder, []).append(move)
    for folder in sorted(grouped):
        moves = grouped[folder]
        plural = "s" if len(moves) != 1 else ""
        lines.append(f"{folder}/ ({len(moves)} note{plural}):")
        for move in moves:
            lines.append(f"  {move.note_path} -> {move.destination}")
    if plan.skipped:
        lines.append("Skipped:")
        for reason in plan.skipped:
            lines.append(f"  {reason}")
    if not lines:
        return "Nothing to apply."
    return "\n".join(lines)
```

- [ ] **Step 16: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_apply.py -v
```

Expected: `18 passed`.

- [ ] **Step 17: Lint and typecheck**

```bash
just lint
uv run mypy
```

Expected: both clean (no ruff findings, no format diffs, no mypy errors).

- [ ] **Step 18: Commit**

```bash
cd /home/alex/code/alex && git add src/alex/lib/triage/apply.py tests/test_triage_apply.py && git commit -m "feat(triage): add apply planner and executor for decided notes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```


### Task 13: Atomic Note Drafting (atomic.py + triage_atomic_draft prompt)

**Files:**
- Create: `src/alex/lib/triage/atomic.py`
- Create: `src/alex/prompts/triage_atomic_draft/v001.md`
- Create: `src/alex/prompts/triage_atomic_draft/active.txt`
- Test: `tests/test_triage_atomic.py`

**Interfaces:**

Consumes (all exist from earlier tasks):
- `from alex.lib.llm import Completer` — Protocol: `complete(*, prompt: str, model: str, max_tokens: int) -> str` (Task 3 / pre-existing).
- `from alex.lib.prompt_templates import load_prompt` — `load_prompt(name, *, version=None, root=None) -> PromptTemplate`; `PromptTemplate.render(**values: str) -> str` is strict about placeholder sets.
- `from alex.lib.triage.models import AtomicDraft, NoteEvidence, Rubric, TriageBlock` (Task 1).
- `from alex.lib.triage.storage import atomic_write_text` — `atomic_write_text(path: Path, text: str) -> None` (Task 1).
- `from alex.lib.triage.frontmatter import assemble_frontmatter, read_triage_block, set_frontmatter_list, write_triage_block` (Task 2); tests also use `read_frontmatter`.
- `from alex.lib.triage.inventory import discover_population_files` — `discover_population_files(vault_root: Path) -> list[tuple[Population, Path]]` (Task 5).

Produces (consumed by Task 16 AtomicScreen and Task 18 e2e):
```python
class AtomicParseError(ValueError): ...

def atomic_draft_prompt(note_text: str, note: NoteEvidence, *, rubric_text: str,
                        permanent_titles: Sequence[str]) -> str
def parse_atomic_drafts(raw: str, source_path: str) -> list[AtomicDraft]
def draft_atomic_notes(note_text: str, note: NoteEvidence, *, rubric: Rubric,
        permanent_titles: Sequence[str], completer: Completer, model: str,
        feedback: str = "") -> list[AtomicDraft]
def verify_related(drafts: list[AtomicDraft], vault_root: Path) -> list[AtomicDraft]
def render_atomic_note(draft: AtomicDraft, created: str) -> str
def write_atomic_note(vault_root: Path, draft: AtomicDraft, created: str) -> Path
def atomic_queue(vault_root: Path) -> list[str]
def mark_atomic_done(vault_root: Path, source_rel: str, written: Sequence[Path]) -> None
```
Plus the versioned prompt `triage_atomic_draft` (placeholders `{{rubric}}`, `{{note}}`, `{{evidence}}`, `{{permanent_titles}}`, `{{feedback}}`), active version `v001`.

Design notes locked in by this task (do not deviate):
- The contract's `atomic_draft_prompt` signature has no `feedback` parameter, but the prompt template has a `{{feedback}}` placeholder. Resolution: a private `_render_draft_prompt(..., feedback: str)` renders the template (the placeholder sits at the tail of the template); `atomic_draft_prompt` calls it with `feedback=""`, and `draft_atomic_notes` calls it with the caller's feedback wrapped in a short revise instruction.
- `mark_atomic_done` writes `permanent_notes` entries as vault-relative posix paths without `.md` (`[[resources/permanent-notes/X]]`), matching the contract's `set_frontmatter_list` example.
- `verify_related` resolves a related entry first as a vault-relative path (`<entry>.md` under vault root) and, when the entry has no `/`, also as `resources/permanent-notes/<entry>.md`, because the model picks entries from bare permanent-note titles.
- An empty JSON array is a valid parse result (the prompt tells the model to return `[]` when nothing is worth keeping).
- `render_atomic_note` emits `type: permanent-note`, matching the files already in `resources/permanent-notes/` and the vault CLAUDE.md frontmatter vocabulary.
- `mark_atomic_done` relies on Task 2's `write_triage_block` deleting an all-default triage block: a note whose block held only `promising: true` ends the flow with no `triage` key at all, not a null one.

- [ ] **Step 1: Write the failing tests for prompt rendering, parsing, drafting, and related-link verification**

Create `tests/test_triage_atomic.py`:

```python
"""Tests for triage atomic-note drafting."""

import json
from pathlib import Path

import pytest

from alex.lib.triage.atomic import (
    AtomicParseError,
    atomic_draft_prompt,
    draft_atomic_notes,
    parse_atomic_drafts,
    verify_related,
)
from alex.lib.triage.models import AtomicDraft, NoteEvidence, Rubric

DRAFT_JSON = json.dumps(
    [
        {
            "title": "Spaced repetition beats rereading",
            "body": "Testing yourself on material beats rereading it.",
            "tags": ["learning", "memory"],
            "related": ["Desirable difficulties improve retention"],
        }
    ]
)


class ScriptedCompleter:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def make_note(path: str = "Inbox note.md") -> NoteEvidence:
    return NoteEvidence(
        path=path,
        title="Inbox note",
        population="root",
        tags=["learning"],
        snippet="Spaced repetition beats rereading.",
    )


def make_rubric() -> Rubric:
    return Rubric(version=1, text="- one idea per note, stated as a claim")


def test_atomic_draft_prompt_carries_rubric_note_and_permanent_titles() -> None:
    prompt = atomic_draft_prompt(
        "The full note body.",
        make_note(),
        rubric_text="- prefer narrow claims",
        permanent_titles=["Existing claim"],
    )
    assert "- prefer narrow claims" in prompt
    assert "The full note body." in prompt
    assert "Inbox note" in prompt
    assert "- Existing claim" in prompt
    assert "JSON array" in prompt


def test_parse_atomic_drafts_reads_a_plain_json_array() -> None:
    drafts = parse_atomic_drafts(DRAFT_JSON, "Inbox note.md")
    assert len(drafts) == 1
    assert drafts[0].title == "Spaced repetition beats rereading"
    assert drafts[0].tags == ["learning", "memory"]
    assert drafts[0].related == ["Desirable difficulties improve retention"]
    assert drafts[0].source_path == "Inbox note.md"


def test_parse_atomic_drafts_strips_code_fences() -> None:
    raw = f"```json\n{DRAFT_JSON}\n```"
    drafts = parse_atomic_drafts(raw, "Inbox note.md")
    assert drafts[0].title == "Spaced repetition beats rereading"


def test_parse_atomic_drafts_raises_on_prose_output() -> None:
    with pytest.raises(AtomicParseError):
        parse_atomic_drafts("I could not find any atomic ideas here.", "note.md")


def test_parse_atomic_drafts_rejects_drafts_missing_required_fields() -> None:
    with pytest.raises(AtomicParseError):
        parse_atomic_drafts('[{"title": "Only a title"}]', "note.md")


def test_draft_atomic_notes_repairs_invalid_json_once() -> None:
    completer = ScriptedCompleter(["not json at all", DRAFT_JSON])
    drafts = draft_atomic_notes(
        "Body text.",
        make_note(),
        rubric=make_rubric(),
        permanent_titles=["Desirable difficulties improve retention"],
        completer=completer,
        model="test-model",
    )
    assert len(drafts) == 1
    assert len(completer.prompts) == 2
    assert "was not valid JSON" in completer.prompts[1]


def test_draft_atomic_notes_raises_after_failed_repair() -> None:
    completer = ScriptedCompleter(["nope", "still nope"])
    with pytest.raises(AtomicParseError):
        draft_atomic_notes(
            "Body text.",
            make_note(),
            rubric=make_rubric(),
            permanent_titles=[],
            completer=completer,
            model="test-model",
        )
    assert len(completer.prompts) == 2


def test_draft_atomic_notes_includes_feedback_in_the_prompt() -> None:
    completer = ScriptedCompleter([DRAFT_JSON])
    draft_atomic_notes(
        "Body text.",
        make_note(),
        rubric=make_rubric(),
        permanent_titles=[],
        completer=completer,
        model="test-model",
        feedback="Make the claim sharper.",
    )
    assert "Make the claim sharper." in completer.prompts[0]


def test_verify_related_drops_entries_without_a_vault_file(tmp_path: Path) -> None:
    permanent = tmp_path / "resources" / "permanent-notes"
    permanent.mkdir(parents=True)
    (permanent / "Existing claim.md").write_text("kept\n", encoding="utf-8")
    draft = AtomicDraft(
        title="T",
        body="B",
        related=[
            "Existing claim",
            "resources/permanent-notes/Existing claim",
            "Missing claim",
        ],
        source_path="note.md",
    )
    verified = verify_related([draft], tmp_path)
    assert verified[0].related == [
        "Existing claim",
        "resources/permanent-notes/Existing claim",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

```
uv run pytest tests/test_triage_atomic.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.atomic'` (exit code 2, 0 tests run).

- [ ] **Step 3: Write the prompt template and the drafting half of atomic.py**

Create `src/alex/prompts/triage_atomic_draft/v001.md` (the `{{feedback}}` placeholder must be the last line; single braces in the JSON example are safe because only `{{word}}` is a placeholder):

```markdown
You are drafting atomic permanent notes for Alex's Obsidian vault. An atomic note captures exactly one idea, stated as a claim, in a form that stands on its own years from now.

## Rubric

{{rubric}}

## Source note

{{note}}

## Source evidence

{{evidence}}

## Existing permanent note titles

{{permanent_titles}}

## Conventions

Follow every one of these:

- One idea per draft. If the source holds several distinct ideas, produce one draft per idea, at most 3 drafts. If nothing is worth keeping as a permanent note, return an empty array.
- The title is a concept-oriented claim: a full statement someone could agree or disagree with ("Spaced repetition beats rereading for retention"), never a topic label ("Spaced repetition").
- The body is 2-4 short paragraphs and fully self-contained: a reader who never sees the source note must understand the idea, why it holds, and when it applies.
- Write the body in Alex's register: plain, direct, first person. No academic hedging, no marketing language.
- Distill in your own words. Never quote the source at length.
- tags: 2-5 lowercase kebab-case domain tags.
- related: 0-4 entries chosen ONLY from the existing permanent note titles above, copied exactly as written there. Never invent a related entry.

Reply with ONLY a JSON array, no prose, no code fences:

[
  {
    "title": "Claim stated as a full sentence",
    "body": "Self-contained body in Alex's plain first-person register.",
    "tags": ["tag-one", "tag-two"],
    "related": ["Existing permanent note title"]
  }
]
{{feedback}}
```

Create `src/alex/prompts/triage_atomic_draft/active.txt` (exactly five bytes, `v001` plus newline):

```
v001
```

Create `src/alex/lib/triage/atomic.py`:

```python
"""Atomic permanent-note drafting for the triage promising queue."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from alex.lib.llm import Completer
from alex.lib.prompt_templates import load_prompt
from alex.lib.triage.models import AtomicDraft, NoteEvidence, Rubric

_PROMPT_NAME = "triage_atomic_draft"
_MAX_TOKENS = 4000
_PERMANENT_NOTES_DIR = "resources/permanent-notes"


class AtomicParseError(ValueError):
    pass


def atomic_draft_prompt(
    note_text: str,
    note: NoteEvidence,
    *,
    rubric_text: str,
    permanent_titles: Sequence[str],
) -> str:
    return _render_draft_prompt(
        note_text,
        note,
        rubric_text=rubric_text,
        permanent_titles=permanent_titles,
        feedback="",
    )


def _render_draft_prompt(
    note_text: str,
    note: NoteEvidence,
    *,
    rubric_text: str,
    permanent_titles: Sequence[str],
    feedback: str,
) -> str:
    template = load_prompt(_PROMPT_NAME)
    titles = "\n".join(f"- {title}" for title in permanent_titles) or "(none yet)"
    feedback_block = ""
    if feedback:
        feedback_block = (
            "\nAlex reviewed your previous drafts and asked for changes:\n"
            f"{feedback}\n"
            "Apply the feedback and reply with ONLY the corrected JSON array.\n"
        )
    return template.render(
        rubric=rubric_text,
        note=note_text,
        evidence=_evidence_text(note),
        permanent_titles=titles,
        feedback=feedback_block,
    )


def _evidence_text(note: NoteEvidence) -> str:
    lines = [
        f"Path: {note.path}",
        f"Title: {note.title}",
        f"Population: {note.population}",
    ]
    if note.tags:
        lines.append("Tags: " + ", ".join(note.tags))
    if note.wikilinks:
        lines.append("Wikilinks: " + ", ".join(note.wikilinks))
    return "\n".join(lines)


def parse_atomic_drafts(raw: str, source_path: str) -> list[AtomicDraft]:
    text = _strip_fences(raw)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        raise AtomicParseError("no JSON array in model output")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise AtomicParseError(f"invalid JSON: {error}") from error
    if not isinstance(parsed, list):
        raise AtomicParseError("expected a JSON array of drafts")
    drafts: list[AtomicDraft] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise AtomicParseError("each draft must be a JSON object")
        try:
            drafts.append(
                AtomicDraft.model_validate({**item, "source_path": source_path})
            )
        except ValidationError as error:
            raise AtomicParseError(f"invalid draft: {error}") from error
    return drafts


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    first_newline = text.find("\n")
    if first_newline == -1:
        return text
    text = text[first_newline + 1 :]
    if text.rstrip().endswith("```"):
        text = text.rstrip()[:-3]
    return text.strip()


def draft_atomic_notes(
    note_text: str,
    note: NoteEvidence,
    *,
    rubric: Rubric,
    permanent_titles: Sequence[str],
    completer: Completer,
    model: str,
    feedback: str = "",
) -> list[AtomicDraft]:
    prompt = _render_draft_prompt(
        note_text,
        note,
        rubric_text=rubric.text,
        permanent_titles=permanent_titles,
        feedback=feedback,
    )
    raw = completer.complete(prompt=prompt, model=model, max_tokens=_MAX_TOKENS)
    try:
        return parse_atomic_drafts(raw, note.path)
    except AtomicParseError as error:
        repair_prompt = (
            f"{prompt}\n\nYour previous reply was not valid JSON: {error}. "
            "Reply with ONLY the JSON array."
        )
        raw = completer.complete(
            prompt=repair_prompt, model=model, max_tokens=_MAX_TOKENS
        )
        return parse_atomic_drafts(raw, note.path)


def verify_related(drafts: list[AtomicDraft], vault_root: Path) -> list[AtomicDraft]:
    verified: list[AtomicDraft] = []
    for draft in drafts:
        kept = [entry for entry in draft.related if _related_exists(vault_root, entry)]
        verified.append(draft.model_copy(update={"related": kept}))
    return verified


def _related_exists(vault_root: Path, entry: str) -> bool:
    name = entry.strip().removesuffix(".md")
    if not name:
        return False
    candidates = [vault_root / f"{name}.md"]
    if "/" not in name:
        candidates.append(vault_root / _PERMANENT_NOTES_DIR / f"{name}.md")
    return any(candidate.is_file() for candidate in candidates)
```

- [ ] **Step 4: Run the tests to verify they pass**

```
uv run pytest tests/test_triage_atomic.py -v
```

Expected: `9 passed`.

- [ ] **Step 5: Write the failing tests for rendering, writing, the promising queue, and writeback**

Modify `tests/test_triage_atomic.py`. First replace the two `from alex.lib.triage...` import statements at the top of the file (keeping `import json`, `from pathlib import Path`, `import pytest` as they are) with:

```python
from alex.lib.triage.atomic import (
    AtomicParseError,
    atomic_draft_prompt,
    atomic_queue,
    draft_atomic_notes,
    mark_atomic_done,
    parse_atomic_drafts,
    render_atomic_note,
    verify_related,
    write_atomic_note,
)
from alex.lib.triage.frontmatter import read_frontmatter, read_triage_block
from alex.lib.triage.models import AtomicDraft, NoteEvidence, Rubric
```

Then append at the end of the file (two blank lines after the last existing test, per ruff format):

```python
def write_note(path: Path, frontmatter: str, body: str = "Body.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")


def promising_frontmatter(decided: str) -> str:
    return (
        "triage:\n"
        "  decision: area\n"
        "  target: learning-science\n"
        "  promising: true\n"
        "  status: decided\n"
        f"  decided: '{decided}'\n"
    )


def test_render_atomic_note_matches_the_vault_note_shape() -> None:
    draft = AtomicDraft(
        title="Spaced repetition beats rereading",
        body="Testing yourself on material beats rereading it.",
        tags=["learning", "memory"],
        related=["Desirable difficulties improve retention"],
        source_path="Inbox note.md",
    )
    assert render_atomic_note(draft, "2026-07-12") == (
        "---\n"
        "title: Spaced repetition beats rereading\n"
        "type: permanent-note\n"
        "created: '2026-07-12'\n"
        "source: '[[Inbox note]]'\n"
        "tags:\n"
        "- learning\n"
        "- memory\n"
        "provenance: llm-drafted, human-approved\n"
        "---\n"
        "\n"
        "Testing yourself on material beats rereading it.\n"
        "\n"
        "## Related\n"
        "\n"
        "- [[Desirable difficulties improve retention]]\n"
        "\n"
        "*From: [[Inbox note]]*\n"
    )


def test_write_atomic_note_adds_a_numeric_suffix_on_collision(tmp_path: Path) -> None:
    draft = AtomicDraft(title="Claim", body="B", source_path="note.md")
    first = write_atomic_note(tmp_path, draft, "2026-07-12")
    second = write_atomic_note(tmp_path, draft, "2026-07-12")
    permanent = tmp_path / "resources" / "permanent-notes"
    assert first == permanent / "Claim.md"
    assert second == permanent / "Claim (2).md"
    assert second.read_text(encoding="utf-8") == first.read_text(encoding="utf-8")


def test_atomic_queue_orders_promising_notes_by_decided_date_then_path(
    tmp_path: Path,
) -> None:
    write_note(tmp_path / "b newer.md", promising_frontmatter("2026-07-11"))
    write_note(tmp_path / "a older.md", promising_frontmatter("2026-07-09"))
    write_note(tmp_path / "Meetings" / "sync.md", promising_frontmatter("2026-07-09"))
    write_note(
        tmp_path / "not promising.md",
        "triage:\n  decision: trash\n  status: decided\n  decided: '2026-07-08'\n",
    )
    (tmp_path / "no block.md").write_text("Just text.\n", encoding="utf-8")
    assert atomic_queue(tmp_path) == [
        "Meetings/sync.md",
        "a older.md",
        "b newer.md",
    ]


def test_mark_atomic_done_unflags_promising_and_records_permanent_notes(
    tmp_path: Path,
) -> None:
    note = tmp_path / "Inbox note.md"
    write_note(note, "type: article\n" + promising_frontmatter("2026-07-10"))
    written = [
        tmp_path / "resources" / "permanent-notes" / "Claim one.md",
        tmp_path / "resources" / "permanent-notes" / "Claim two.md",
    ]
    mark_atomic_done(tmp_path, "Inbox note.md", written)
    text = note.read_text(encoding="utf-8")
    block = read_triage_block(text)
    assert block is not None
    assert block.promising is False
    assert block.decision == "area"
    assert block.target == "learning-science"
    assert block.status == "decided"
    assert block.decided == "2026-07-10"
    frontmatter = read_frontmatter(text)
    assert frontmatter["type"] == "article"
    assert frontmatter["permanent_notes"] == [
        "[[resources/permanent-notes/Claim one]]",
        "[[resources/permanent-notes/Claim two]]",
    ]
    assert text.endswith("Body.\n")


def test_mark_atomic_done_skips_permanent_notes_when_nothing_written(
    tmp_path: Path,
) -> None:
    note = tmp_path / "dropped.md"
    write_note(note, promising_frontmatter("2026-07-10"))
    mark_atomic_done(tmp_path, "dropped.md", [])
    text = note.read_text(encoding="utf-8")
    assert "permanent_notes" not in read_frontmatter(text)
    block = read_triage_block(text)
    assert block is not None
    assert block.promising is False
    assert block.decision == "area"


def test_mark_atomic_done_on_promising_only_note_leaves_no_triage_block(
    tmp_path: Path,
) -> None:
    note = tmp_path / "skipped but promising.md"
    write_note(note, "type: article\ntriage:\n  promising: true\n")
    mark_atomic_done(tmp_path, "skipped but promising.md", [])
    text = note.read_text(encoding="utf-8")
    assert read_triage_block(text) is None
    frontmatter = read_frontmatter(text)
    assert "triage" not in frontmatter
    assert frontmatter["type"] == "article"
    assert text.endswith("Body.\n")
```

- [ ] **Step 6: Run the tests to verify the new ones fail**

```
uv run pytest tests/test_triage_atomic.py -v
```

Expected: collection error, `ImportError: cannot import name 'atomic_queue' from 'alex.lib.triage.atomic'`.

- [ ] **Step 7: Implement rendering, writing, the queue, and writeback**

Modify `src/alex/lib/triage/atomic.py`. Replace the import section (everything between the module docstring and `_PROMPT_NAME = ...`, currently lines 3-13) with:

```python
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from alex.lib.llm import Completer
from alex.lib.prompt_templates import load_prompt
from alex.lib.triage.frontmatter import (
    assemble_frontmatter,
    read_triage_block,
    set_frontmatter_list,
    write_triage_block,
)
from alex.lib.triage.inventory import discover_population_files
from alex.lib.triage.models import AtomicDraft, NoteEvidence, Rubric, TriageBlock
from alex.lib.triage.storage import atomic_write_text
```

Then append at the end of the file (two blank lines after `_related_exists`, per ruff format):

```python
def render_atomic_note(draft: AtomicDraft, created: str) -> str:
    source = draft.source_path.removesuffix(".md")
    frontmatter = yaml.safe_dump(
        {
            "title": draft.title,
            "type": "permanent-note",
            "created": created,
            "source": f"[[{source}]]",
            "tags": draft.tags,
            "provenance": "llm-drafted, human-approved",
        },
        sort_keys=False,
        allow_unicode=True,
    )
    sections = [draft.body.strip()]
    if draft.related:
        links = "\n".join(f"- [[{entry}]]" for entry in draft.related)
        sections.append(f"## Related\n\n{links}")
    sections.append(f"*From: [[{source}]]*")
    body = "\n" + "\n\n".join(sections) + "\n"
    return assemble_frontmatter(frontmatter, body)


def write_atomic_note(vault_root: Path, draft: AtomicDraft, created: str) -> Path:
    directory = vault_root / _PERMANENT_NOTES_DIR
    title = draft.title.replace("/", "-").strip()
    destination = directory / f"{title}.md"
    suffix = 2
    while destination.exists():
        destination = directory / f"{title} ({suffix}).md"
        suffix += 1
    atomic_write_text(destination, render_atomic_note(draft, created))
    return destination


def atomic_queue(vault_root: Path) -> list[str]:
    queue: list[tuple[str, str]] = []
    for _population, md_path in discover_population_files(vault_root):
        block = read_triage_block(md_path.read_text(encoding="utf-8"))
        if block is None or not block.promising:
            continue
        rel = md_path.relative_to(vault_root).as_posix()
        queue.append((block.decided, rel))
    queue.sort()
    return [rel for _decided, rel in queue]


def mark_atomic_done(
    vault_root: Path,
    source_rel: str,
    written: Sequence[Path],
) -> None:
    note_path = vault_root / source_rel
    text = note_path.read_text(encoding="utf-8")
    block = read_triage_block(text)
    if block is None:
        block = TriageBlock()
    text = write_triage_block(text, block.model_copy(update={"promising": False}))
    if written:
        links: list[str] = []
        for path in written:
            rel = path.relative_to(vault_root).as_posix().removesuffix(".md")
            links.append(f"[[{rel}]]")
        text = set_frontmatter_list(text, "permanent_notes", links)
    atomic_write_text(note_path, text)
```

- [ ] **Step 8: Run the tests to verify they pass**

```
uv run pytest tests/test_triage_atomic.py -v
```

Expected: `15 passed`.

- [ ] **Step 9: Run lint and typecheck**

```
just lint
uv run mypy
```

Expected: `ruff check` passes, `ruff format --check` reports all files already formatted, mypy reports no issues.

- [ ] **Step 10: Commit**

```bash
cd /home/alex/code/alex
git add src/alex/lib/triage/atomic.py src/alex/prompts/triage_atomic_draft/active.txt src/alex/prompts/triage_atomic_draft/v001.md tests/test_triage_atomic.py
git commit -m "feat(triage): atomic note drafting, promising queue, and writeback

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 14: Session Persistence (session.py)

**Files:**
- Create: `src/alex/lib/triage/session.py`
- Test: `tests/test_triage_session.py`

**Interfaces:**

Consumes (Task 1):
- `from alex.lib.triage.models import SessionState` (`batch_id: int`, `pending: dict[str, PendingDecision]`, `corrections: list[str]`, `extra_events: list[LedgerEvent]`).
- `from alex.lib.triage.storage import read_yaml_model, write_yaml_model` — `read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None` (None on missing file or yaml/validation error), `write_yaml_model(path: Path, model: BaseModel) -> None` (atomic write).

Produces (consumed by Task 15 TriageScreen and Task 17 command wiring):
```python
def load_session(path: Path) -> SessionState | None
def save_session(path: Path, state: SessionState) -> None
def clear_session(path: Path) -> None
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage_session.py`:

```python
"""Tests for triage session persistence."""

from pathlib import Path

from alex.lib.triage.models import (
    LedgerEvent,
    PendingDecision,
    Proposal,
    SessionState,
)
from alex.lib.triage.session import clear_session, load_session, save_session


def make_state() -> SessionState:
    proposal = Proposal(
        note_path="Inbox note.md",
        decision="area",
        target="learning-science",
        confidence="high",
        why="Clear match against the catalog.",
        alternatives=["resource"],
    )
    return SessionState(
        batch_id=3,
        pending={
            "Inbox note.md": PendingDecision(
                proposal=proposal,
                action="approve",
                promising=True,
                reason="",
            )
        },
        corrections=["Meeting notes go to areas, not resources."],
        extra_events=[
            LedgerEvent(
                ts="2026-07-12T09:00:00",
                note="Inbox note.md",
                batch=3,
                rubric_version=2,
                event="repropose",
                reason="chat correction",
            )
        ],
    )


def test_session_roundtrips_through_yaml(tmp_path: Path) -> None:
    path = tmp_path / "session.yaml"
    state = make_state()
    save_session(path, state)
    loaded = load_session(path)
    assert loaded is not None
    assert loaded == state
    assert loaded.corrections == ["Meeting notes go to areas, not resources."]
    assert loaded.extra_events[0].event == "repropose"


def test_load_session_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    assert load_session(tmp_path / "session.yaml") is None


def test_load_session_returns_none_on_unparseable_yaml(tmp_path: Path) -> None:
    path = tmp_path / "session.yaml"
    path.write_text("batch_id: [unclosed\n", encoding="utf-8")
    assert load_session(path) is None


def test_load_session_returns_none_on_wrong_shape(tmp_path: Path) -> None:
    path = tmp_path / "session.yaml"
    path.write_text("pending: {}\n", encoding="utf-8")
    assert load_session(path) is None


def test_clear_session_removes_the_file_and_tolerates_absence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "session.yaml"
    save_session(path, make_state())
    clear_session(path)
    assert not path.exists()
    clear_session(path)
```

- [ ] **Step 2: Run the tests to verify they fail**

```
uv run pytest tests/test_triage_session.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.session'` (exit code 2, 0 tests run).

- [ ] **Step 3: Write the implementation**

Create `src/alex/lib/triage/session.py`:

```python
"""Session persistence for the triage review TUI."""

from __future__ import annotations

from pathlib import Path

from alex.lib.triage.models import SessionState
from alex.lib.triage.storage import read_yaml_model, write_yaml_model


def load_session(path: Path) -> SessionState | None:
    return read_yaml_model(path, SessionState)


def save_session(path: Path, state: SessionState) -> None:
    write_yaml_model(path, state)


def clear_session(path: Path) -> None:
    path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

```
uv run pytest tests/test_triage_session.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Run lint and typecheck**

```
just lint
uv run mypy
```

Expected: `ruff check` passes, `ruff format --check` reports all files already formatted, mypy reports no issues.

- [ ] **Step 6: Commit**

```bash
cd /home/alex/code/alex
git add src/alex/lib/triage/session.py tests/test_triage_session.py
git commit -m "feat(triage): session persistence for the review TUI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
### Task 15: TUI scaffold + triage screen

**Files:**
- Modify: `pyproject.toml` (dependencies list ~line 7, `[dependency-groups]` dev ~line 19, new `[tool.pytest.ini_options]` table at end of file)
- Create: `src/alex/lib/triage/tui/__init__.py`
- Create: `src/alex/lib/triage/tui/services.py`
- Create: `src/alex/lib/triage/tui/widgets.py`
- Create: `src/alex/lib/triage/tui/triage_screen.py`
- Create: `src/alex/lib/triage/tui/app.py`
- Test: `tests/test_triage_tui.py`

All paths relative to repo root `/home/alex/code/alex`.

**Interfaces:**

Consumes (from earlier tasks, exact contract signatures):
- Task 1 models: `Batch` (with the `label: str = ""` field), `BatchProposals`, `Catalog`, `ClusterMap`, `Inventory`, `LedgerEvent`, `NoteEvidence`, `PendingAreas`, `PendingDecision`, `Proposal`, `ProposalDecision`, `Rubric`, `SessionState` (with `corrections: list[str]` and `extra_events: list[LedgerEvent]`), `TriageBlock`
- Task 1 storage: `atomic_write_text(path: Path, text: str) -> None`, `read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None`, `write_yaml_model(path: Path, model: BaseModel) -> None`
- Task 1 paths: `TriagePaths(vault_root: Path)` with `.session_path`, `.ledger_path`, `.rubric_path`, `.lock_path`, `.pending_areas_path`, `.vault_root`
- Task 2 frontmatter: `split_frontmatter(text: str) -> tuple[str | None, str]`, `read_triage_block(text: str) -> TriageBlock | None`, `write_triage_block(text: str, block: TriageBlock) -> str`
- Task 4 catalog: `load_or_build_catalog(paths: TriagePaths) -> Catalog`, `catalog_prompt_text(catalog: Catalog) -> str`
- Task 5 inventory: `MOVABLE_POPULATIONS`, `extract_evidence(vault_root: Path, md_path: Path, population: Population) -> NoteEvidence`
- Task 7 ledger: `append_event(ledger_path: Path, event: LedgerEvent) -> None`, `read_events(ledger_path: Path, *, since_version: int | None = None) -> list[LedgerEvent]`
- Task 8 rubric: `load_rubric(path: Path) -> Rubric`, `save_rubric(path: Path, rubric: Rubric) -> None`
- Task 9 proposals: `generate_batch_proposals(batch, inventory, *, catalog, rubric, completer, model, corrections=(), max_workers=4) -> BatchProposals`, `load_batch_proposals(paths, batch_id, rubric_version) -> BatchProposals | None`, `write_batch_proposals(paths, proposals) -> None`
- Task 10 distill: `distill_rubric(rubric, events, completer, model) -> Rubric`
- Task 14 session: `load_session(path) -> SessionState | None`, `save_session(path, state) -> None`, `clear_session(path) -> None`
- Repo: `alex.lib.llm.Completer` / `Embedder` protocols and `alex.lib.llm.LlmError`, `alex.lib.locking.exclusive_lock` / `LockHeldError`

Produces (Task 16 and Task 17 rely on these):
- `TriageServices` frozen dataclass (contract-verbatim fields)
- `TriageApp(App[None])` with `__init__(self, services: TriageServices, inventory: Inventory, cluster_map: ClusterMap, *, mode: str = "triage") -> None`
- `TriageScreen(Screen[None])` with `__init__(self, services: TriageServices, inventory: Inventory, cluster_map: ClusterMap) -> None`
- Widgets: `NotePanel.show_note(title: str, body: str) -> None`; `ProposalPanel.show_proposal(proposal: Proposal | None, *, promising: bool, pending_action: str) -> None` plus `ProposalPanel.body_text: str`; `TargetPicker(options: Sequence[str])` a `ModalScreen[str | None]`; `ReasonInput(prompt_text: str)` a `ModalScreen[str | None]`; `ChatPane(context: str, send: Callable[[str], str])` a `ModalScreen[str | None]` dismissing with `None` or `"REPROPOSE:<transcript>"`

Design decisions locked here (contract-compatible, no relitigating in later tasks):
- A user skip/trash is stored as `PendingDecision(proposal=<proposal copied with decision overridden>, action="edit")` (or `action="approve"` when the proposal already said so). The contract's "skips write for action=='skip'" is read as `pending.proposal.decision == "skip"` since `LedgerEventKind` has no `"skip"` member.
- Ledger events at confirm log the model's ORIGINAL proposal (kept in `self._proposals`, never mutated by edits) plus a `correction` dict `{"decision", "target"}` when `action == "edit"`. Reject and chat-repropose events are built as full `LedgerEvent` values at interaction time, persisted in `SessionState.extra_events` (alongside `SessionState.corrections`) on every action, restored on resume, and appended to the ledger at confirm (they are per-interaction, not per-note-final). A reject or chat correction regenerates EVERY unreviewed note in the current batch (the corrected note included) in one background worker, with the full corrections list appended to each prompt; regenerated proposals replace the in-memory entries, are merged over the cached batch through `write_batch_proposals` so the on-disk cache reflects them, and a status notice reports how many notes were re-proposed.
- Annotate-only populations (meetings/weekly, i.e. not in `MOVABLE_POPULATIONS`): `t` shows a status-bar notice and records nothing, the TargetPicker offers area targets only, and `_write_decision` stamps them `status="applied"` with both `decided` and `applied` set to today at confirm (there is nothing to move).
- A batch whose generation raises `LlmError` is marked pending in an in-memory set, a status notice is shown, and the screen advances to the next batch that has or can get proposals.
- `_open_batch` stats every note in the batch: vanished files are ejected from the working batch with a status notice; mtime-changed notes get `extract_evidence` re-run and their proposal regenerated in the background.
- After confirm, the distill worker runs in the background; when no next batch exists the screen shows a done message instead of exiting, so the worker always finishes (and tests can `await app.workers.wait_for_complete()`).
- `mode="atomic"` raises `ValueError` until Task 16 wires `AtomicScreen` in.

- [ ] **Step 1: Add textual + pytest-asyncio and pytest asyncio config**

In `pyproject.toml`, the `[project]` dependencies list (which after Task 1 already contains `pyyaml>=6.0`) gains `textual>=1.0`, and the dev group (which already contains `types-pyyaml>=6.0`) gains `pytest-asyncio>=0.24`. The two lists become exactly:

```toml
dependencies = [
    "click>=8.4.0",
    "litellm>=1.80.0",
    "marker-pdf>=1.10.2",
    "pydantic>=2.13.4",
    "pymupdf4llm>=1.27.2.3",
    "pyyaml>=6.0",
    "textual>=1.0",
]
```

```toml
[dependency-groups]
dev = [
    "mypy>=2.1.0",
    "pytest>=9.0.1",
    "pytest-asyncio>=0.24",
    "ruff>=0.15.16",
    "types-pyyaml>=6.0",
]
```

Append this table at the very end of `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Then install:

```bash
cd /home/alex/code/alex && uv sync
```

Expect uv to resolve and install textual and pytest-asyncio without errors.

- [ ] **Step 2: Write the failing tests (core review flows + batch freshness)**

Create `tests/test_triage_tui.py`:

```python
"""Pilot tests for the triage review screen."""

from __future__ import annotations

import json
from pathlib import Path

from textual.widgets import Static

from alex.lib.llm import Completer, LlmError
from alex.lib.triage.models import (
    Batch,
    BatchProposals,
    Cluster,
    ClusterMap,
    Inventory,
    NoteEvidence,
    PendingDecision,
    Proposal,
    SessionState,
)
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.proposals import load_batch_proposals, write_batch_proposals
from alex.lib.triage.session import load_session, save_session
from alex.lib.triage.tui.app import TriageApp
from alex.lib.triage.tui.services import TriageServices
from alex.lib.triage.tui.triage_screen import TriageScreen
from alex.lib.triage.tui.widgets import ProposalPanel
from helpers import BagOfWordsEmbedder

NOTE_ONE = "Python packaging pain.md"
NOTE_TWO = "Team offsite ideas.md"
RUBRIC_REPLY = "## Triage rules\n1. keep going\n\n## Atomic note rules\n1. one idea\n"


class RoutedCompleter:
    """Returns the first canned response whose marker appears in the prompt."""

    def __init__(self, routes: list[tuple[str, str]], default: str) -> None:
        self.routes = routes
        self.default = default
        self.prompts: list[str] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        for marker, response in self.routes:
            if marker in prompt:
                return response
        return self.default


class ExplodingCompleter:
    """Raises LlmError for proposal calls; canned rubric reply otherwise."""

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if model == "test-proposal":
            raise LlmError("proposal backend down")
        return RUBRIC_REPLY


def proposal_json(decision: str, target: str, why: str) -> str:
    return json.dumps(
        {
            "decision": decision,
            "target": target,
            "confidence": "high",
            "why": why,
            "alternatives": [],
            "new_area": None,
        }
    )


def build_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    areas = [("python", "Python practice"), ("leadership", "Leading teams")]
    for slug, description in areas:
        area = vault / "areas" / slug
        area.mkdir(parents=True)
        (area / "index.md").write_text(
            f"---\ntype: area\ndescription: {description}\n---\n# {slug}\n",
            encoding="utf-8",
        )
    (vault / "resources" / "permanent-notes").mkdir(parents=True)
    (vault / NOTE_ONE).write_text(
        "---\ncreated: 2026-07-01\n---\nPackaging python is painful.\n",
        encoding="utf-8",
    )
    (vault / NOTE_TWO).write_text(
        "---\ncreated: 2026-07-02\n---\nIdeas for the team offsite.\n",
        encoding="utf-8",
    )
    return vault


def build_inventory() -> Inventory:
    return Inventory(
        generated="2026-07-12T00:00:00",
        notes=[
            NoteEvidence(
                path=NOTE_ONE,
                title="Python packaging pain",
                population="root",
                snippet="Packaging python is painful.",
            ),
            NoteEvidence(
                path=NOTE_TWO,
                title="Team offsite ideas",
                population="root",
                snippet="Ideas for the team offsite.",
            ),
        ],
    )


def build_cluster_map() -> ClusterMap:
    return ClusterMap(
        generated="2026-07-12T00:00:00",
        clusters=[
            Cluster(cluster_id=1, label="work", note_paths=[NOTE_ONE, NOTE_TWO])
        ],
        batches=[Batch(batch_id=1, note_paths=[NOTE_ONE, NOTE_TWO])],
    )


def make_services(vault: Path, completer: Completer) -> TriageServices:
    return TriageServices(
        paths=TriagePaths(vault_root=vault),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
        proposal_model="test-proposal",
        atomic_model="test-atomic",
        distill_model="test-distill",
        max_workers=1,
        today="2026-07-12",
    )


def seed_proposals(paths: TriagePaths) -> None:
    write_batch_proposals(
        paths,
        BatchProposals(
            batch_id=1,
            rubric_version=1,
            proposals=[
                Proposal(
                    note_path=NOTE_ONE,
                    decision="area",
                    target="python",
                    confidence="high",
                    why="python note",
                ),
                Proposal(
                    note_path=NOTE_TWO,
                    decision="area",
                    target="leadership",
                    confidence="medium",
                    why="team note",
                ),
            ],
        ),
    )


async def test_approve_records_pending_decision_and_saves_session(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.batch_id == 1
    pending = session.pending[NOTE_ONE]
    assert pending.action == "approve"
    assert pending.proposal.decision == "area"
    assert pending.proposal.target == "python"


async def test_skip_and_trash_override_proposal_decisions(tmp_path: Path) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.pending[NOTE_ONE].proposal.decision == "skip"
    assert session.pending[NOTE_ONE].action == "edit"
    assert session.pending[NOTE_TWO].proposal.decision == "trash"
    assert session.pending[NOTE_TWO].proposal.target == ""
    assert session.pending[NOTE_TWO].action == "edit"


async def test_promising_toggle_carries_into_pending_decision(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p", "a")
        await pilot.pause()
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.pending[NOTE_ONE].promising is True
    assert session.pending[NOTE_ONE].action == "approve"


async def test_edit_target_via_picker_free_text_records_edit(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.press(*"resource:python")
        await pilot.press("enter")
        await pilot.pause()
    session = load_session(services.paths.session_path)
    assert session is not None
    pending = session.pending[NOTE_ONE]
    assert pending.action == "edit"
    assert pending.proposal.decision == "resource"
    assert pending.proposal.target == "python"


async def test_undo_restores_note_to_undecided(tmp_path: Path) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        assert "target: python" in screen.query_one(ProposalPanel).body_text
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.pending == {}


async def test_needs_manual_proposal_renders_highlighted_and_defaults_to_skip(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    write_batch_proposals(
        services.paths,
        BatchProposals(
            batch_id=1,
            rubric_version=1,
            proposals=[
                Proposal(
                    note_path=NOTE_ONE,
                    decision="skip",
                    confidence="low",
                    why="needs manual: bad json",
                    needs_manual=True,
                ),
                Proposal(
                    note_path=NOTE_TWO,
                    decision="area",
                    target="leadership",
                    confidence="medium",
                    why="team note",
                ),
            ],
        ),
    )
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        assert "NEEDS MANUAL" in screen.query_one(ProposalPanel).body_text
        await pilot.press("a")
        await pilot.pause()
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.pending[NOTE_ONE].proposal.decision == "skip"
    assert session.pending[NOTE_ONE].action == "approve"


async def test_missing_proposals_generated_and_next_batch_pregenerated(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    note_three = "Rust ownership notes.md"
    (vault / note_three).write_text(
        "---\ncreated: 2026-07-03\n---\nOwnership rules in rust.\n",
        encoding="utf-8",
    )
    completer = RoutedCompleter(
        routes=[], default=proposal_json("area", "python", "auto")
    )
    services = make_services(vault, completer)
    inventory = build_inventory()
    inventory.notes.append(
        NoteEvidence(
            path=note_three,
            title="Rust ownership notes",
            population="root",
            snippet="Ownership rules in rust.",
        )
    )
    cluster_map = ClusterMap(
        generated="2026-07-12T00:00:00",
        clusters=[
            Cluster(cluster_id=1, label="work", note_paths=[NOTE_ONE, NOTE_TWO]),
            Cluster(cluster_id=2, label="rust", note_paths=[note_three]),
        ],
        batches=[
            Batch(batch_id=1, note_paths=[NOTE_ONE, NOTE_TWO]),
            Batch(batch_id=2, note_paths=[note_three]),
        ],
    )
    app = TriageApp(services, inventory, cluster_map)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        assert "decision: area" in screen.query_one(ProposalPanel).body_text
    assert load_batch_proposals(services.paths, 1, 1) is not None
    assert load_batch_proposals(services.paths, 2, 1) is not None


async def test_session_resume_restores_pending_and_moves_to_first_undecided(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    save_session(
        services.paths.session_path,
        SessionState(
            batch_id=1,
            pending={
                NOTE_ONE: PendingDecision(
                    proposal=Proposal(
                        note_path=NOTE_ONE, decision="area", target="python"
                    ),
                    action="approve",
                )
            },
        ),
    )
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        assert "target: leadership" in screen.query_one(ProposalPanel).body_text
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.pending[NOTE_ONE].action == "approve"


async def test_vanished_note_is_ejected_from_batch_with_notice(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    (vault / NOTE_TWO).unlink()
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        status = str(screen.query_one("#status-bar", Static).renderable)
        assert "vanished" in status
        assert NOTE_TWO in status
        await pilot.press("a")
        await pilot.pause()
    session = load_session(services.paths.session_path)
    assert session is not None
    assert list(session.pending) == [NOTE_ONE]


async def test_llm_error_marks_batch_pending_and_advances_to_next(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    note_three = "Rust ownership notes.md"
    (vault / note_three).write_text(
        "---\ncreated: 2026-07-03\n---\nOwnership rules in rust.\n",
        encoding="utf-8",
    )
    services = make_services(vault, ExplodingCompleter())
    inventory = build_inventory()
    inventory.notes.append(
        NoteEvidence(
            path=note_three,
            title="Rust ownership notes",
            population="root",
            snippet="Ownership rules in rust.",
        )
    )
    cluster_map = ClusterMap(
        generated="2026-07-12T00:00:00",
        clusters=[
            Cluster(cluster_id=1, label="rust", note_paths=[note_three]),
            Cluster(cluster_id=2, label="work", note_paths=[NOTE_ONE, NOTE_TWO]),
        ],
        batches=[
            Batch(batch_id=1, note_paths=[note_three]),
            Batch(batch_id=2, note_paths=[NOTE_ONE, NOTE_TWO]),
        ],
    )
    write_batch_proposals(
        services.paths,
        BatchProposals(
            batch_id=2,
            rubric_version=1,
            proposals=[
                Proposal(
                    note_path=NOTE_ONE,
                    decision="area",
                    target="python",
                    confidence="high",
                    why="python note",
                ),
                Proposal(
                    note_path=NOTE_TWO,
                    decision="area",
                    target="leadership",
                    confidence="medium",
                    why="team note",
                ),
            ],
        ),
    )
    app = TriageApp(services, inventory, cluster_map)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        assert "target: python" in screen.query_one(ProposalPanel).body_text
    assert load_batch_proposals(services.paths, 1, 1) is None
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_tui.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.tui'`.
- [ ] **Step 4: Write the implementation: package init + services**

Create `src/alex/lib/triage/tui/__init__.py`:

```python
"""Textual TUI for the vault triage review flows."""
```

Create `src/alex/lib/triage/tui/services.py`:

```python
"""Dependency container handed to the triage TUI by the command layer."""

from __future__ import annotations

from dataclasses import dataclass

from alex.lib.llm import Completer, Embedder
from alex.lib.triage.paths import TriagePaths


@dataclass(frozen=True)
class TriageServices:
    paths: TriagePaths
    completer: Completer
    embedder: Embedder
    proposal_model: str
    atomic_model: str
    distill_model: str
    max_workers: int = 4
    today: str = ""  # YYYY-MM-DD injected by the command layer
```

- [ ] **Step 5: Write the implementation: widgets**

Create `src/alex/lib/triage/tui/widgets.py`:

```python
"""Reusable widgets and modal screens for the triage TUI."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from alex.lib.triage.models import Proposal


class NotePanel(Vertical):
    """Renders one note (or a set of drafts) as markdown."""

    def compose(self) -> ComposeResult:
        yield Markdown("")

    def show_note(self, title: str, body: str) -> None:
        self.query_one(Markdown).update(f"# {title}\n\n{body}")


class ProposalPanel(Static):
    """Shows the current proposal plus its pending review state."""

    body_text: str = ""

    def show_proposal(
        self,
        proposal: Proposal | None,
        *,
        promising: bool,
        pending_action: str,
    ) -> None:
        if proposal is None:
            self.body_text = "Generating proposal..."
        else:
            lines: list[str] = []
            if proposal.needs_manual:
                lines.append("!! NEEDS MANUAL (defaults to skip)")
            lines.append(f"decision: {proposal.decision}")
            if proposal.target:
                lines.append(f"target: {proposal.target}")
            lines.append(f"confidence: {proposal.confidence}")
            if proposal.why:
                lines.append(f"why: {proposal.why}")
            if proposal.alternatives:
                lines.append("alternatives: " + ", ".join(proposal.alternatives))
            if proposal.new_area is not None:
                lines.append(
                    f"new area: {proposal.new_area.slug}"
                    f" ({proposal.new_area.name})"
                )
            if promising:
                lines.append("promising: yes")
            if pending_action:
                lines.append(f"pending: {pending_action}")
            self.body_text = "\n".join(lines)
        self.update(self.body_text)


class TargetPicker(ModalScreen[str | None]):
    """Pick a filing target from the catalog, or type decision:target."""

    DEFAULT_CSS = """
    TargetPicker {
        align: center middle;
    }
    #target-picker {
        width: 60;
        height: 20;
        border: solid $accent;
        background: $surface;
        padding: 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, options: Sequence[str]) -> None:
        super().__init__()
        self._options = list(options)

    def compose(self) -> ComposeResult:
        with Vertical(id="target-picker"):
            yield Label("Edit target: pick an option or type decision:target")
            yield Input(placeholder="filter or decision:target")
            yield OptionList(*self._options)

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        needle = event.value.lower()
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        option_list.add_options(
            Option(text) for text in self._options if needle in text.lower()
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value if value else None)

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        self.dismiss(str(event.option.prompt))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ReasonInput(ModalScreen[str | None]):
    """One-line free-text prompt; empty input dismisses with None."""

    DEFAULT_CSS = """
    ReasonInput {
        align: center middle;
    }
    #reason-input {
        width: 60;
        height: 5;
        border: solid $accent;
        background: $surface;
        padding: 0 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, prompt_text: str) -> None:
        super().__init__()
        self._prompt_text = prompt_text

    def compose(self) -> ComposeResult:
        with Vertical(id="reason-input"):
            yield Label(self._prompt_text)
            yield Input(placeholder="reason")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value if value else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ChatPane(ModalScreen[str | None]):
    """Chat about the current item; ctrl+r ends the chat in a re-propose."""

    DEFAULT_CSS = """
    ChatPane {
        align: center middle;
    }
    #chat-pane {
        width: 80%;
        height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 0 1;
    }
    #chat-transcript {
        height: 1fr;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Close"),
        Binding("ctrl+r", "repropose", "Re-propose"),
    ]

    def __init__(self, context: str, send: Callable[[str], str]) -> None:
        super().__init__()
        self._context = context
        self._send = send
        self.transcript = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-pane"):
            yield Static("", id="chat-transcript")
            yield Input(placeholder="message (ctrl+r re-propose, esc close)")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return
        self.query_one(Input).value = ""
        self.transcript += f"you: {message}\n"
        self.query_one("#chat-transcript", Static).update(self.transcript)
        self._reply(self.transcript)

    @work(thread=True)
    def _reply(self, transcript: str) -> None:
        reply = self._send(f"{self._context}\n\n{transcript}")
        self.app.call_from_thread(self._append_reply, reply)

    def _append_reply(self, reply: str) -> None:
        self.transcript += f"model: {reply}\n"
        self.query_one("#chat-transcript", Static).update(self.transcript)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_repropose(self) -> None:
        self.dismiss(f"REPROPOSE:{self.transcript}" if self.transcript else None)
```

- [ ] **Step 6: Write the implementation: triage screen (core flows)**

Create `src/alex/lib/triage/tui/triage_screen.py`. This version covers batch open (with vanish/mtime freshness checks), proposal generation, pre-generation, and subset regeneration workers (all `LlmError`-resilient; `_regenerate` re-proposes any subset of the current batch and serves both stale notes here and the batch-wide correction flows in Step 11), session save/resume (including corrections and extra events), and the local actions (approve, skip, trash with the annotate-only guard, promising, edit, undo). Reject, chat, batch confirm, and distill land in Step 11.

```python
"""Batch review screen: one note, one proposal, keyboard-first decisions."""

from __future__ import annotations

from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Static

from alex.lib.llm import LlmError
from alex.lib.triage.catalog import load_or_build_catalog
from alex.lib.triage.frontmatter import read_triage_block, split_frontmatter
from alex.lib.triage.inventory import MOVABLE_POPULATIONS, extract_evidence
from alex.lib.triage.models import (
    Batch,
    BatchProposals,
    Catalog,
    ClusterMap,
    Inventory,
    LedgerEvent,
    NoteEvidence,
    PendingDecision,
    Proposal,
    ProposalDecision,
    Rubric,
    SessionState,
)
from alex.lib.triage.proposals import (
    generate_batch_proposals,
    load_batch_proposals,
    write_batch_proposals,
)
from alex.lib.triage.rubric import load_rubric
from alex.lib.triage.session import load_session, save_session
from alex.lib.triage.tui.services import TriageServices
from alex.lib.triage.tui.widgets import NotePanel, ProposalPanel, TargetPicker


class TriageScreen(Screen[None]):
    """Reviews one clustered batch of proposals at a time."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "approve", "Approve"),
        Binding("e", "edit", "Edit target"),
        Binding("p", "promising", "Promising"),
        Binding("t", "trash", "Trash"),
        Binding("s", "skip", "Skip"),
        Binding("u", "undo", "Undo"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(
        self,
        services: TriageServices,
        inventory: Inventory,
        cluster_map: ClusterMap,
    ) -> None:
        super().__init__()
        self._services = services
        self._inventory = inventory
        self._cluster_map = cluster_map
        self._notes: dict[str, NoteEvidence] = {
            note.path: note for note in inventory.notes
        }
        self._catalog: Catalog = load_or_build_catalog(services.paths)
        self._rubric: Rubric = load_rubric(services.paths.rubric_path)
        self._batch: Batch | None = None
        self._proposals: dict[str, Proposal] = {}
        self._pending: dict[str, PendingDecision] = {}
        self._promising: set[str] = set()
        self._corrections: list[str] = []
        self._extra_events: list[LedgerEvent] = []
        self._undo_stack: list[tuple[str, PendingDecision | None]] = []
        self._pregenerated: BatchProposals | None = None
        self._pending_batches: set[int] = set()
        self._index = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="status-bar")
        with Horizontal(id="panels"):
            yield NotePanel(id="note-panel")
            yield ProposalPanel("", id="proposal-panel")
        yield Footer()

    def on_mount(self) -> None:
        session = load_session(self._services.paths.session_path)
        if session is not None and self._find_batch(session.batch_id) is not None:
            self._pending = dict(session.pending)
            self._corrections = list(session.corrections)
            self._extra_events = list(session.extra_events)
            self._open_batch(session.batch_id)
            return
        self._open_batch(self._first_open_batch_id())

    # -- batch plumbing -----------------------------------------------------

    def _find_batch(self, batch_id: int) -> Batch | None:
        for batch in self._cluster_map.batches:
            if batch.batch_id == batch_id:
                return batch
        return None

    def _batch_after(self, batch_id: int) -> Batch | None:
        batches = self._cluster_map.batches
        for index, batch in enumerate(batches):
            if batch.batch_id != batch_id:
                continue
            for candidate in batches[index + 1 :]:
                if candidate.batch_id not in self._pending_batches:
                    return candidate
            return None
        return None

    def _first_open_batch_id(self) -> int | None:
        for batch in self._cluster_map.batches:
            for path in batch.note_paths:
                note_file = self._services.paths.vault_root / path
                if not note_file.exists():
                    continue
                block = read_triage_block(note_file.read_text(encoding="utf-8"))
                if block is None or block.decision is None:
                    return batch.batch_id
        return None

    def _open_batch(self, batch_id: int | None) -> None:
        if batch_id is None:
            self._batch = None
            self._set_status("Nothing left to triage. q to quit.")
            return
        batch = self._find_batch(batch_id)
        if batch is None:
            self._batch = None
            self._set_status(f"Batch {batch_id} not found. q to quit.")
            return
        batch, ejected, stale = self._freshen_batch(batch)
        if not batch.note_paths:
            next_batch = self._batch_after(batch_id)
            self._open_batch(next_batch.batch_id if next_batch is not None else None)
            self._set_status(f"All notes in batch {batch_id} vanished; skipped it.")
            return
        self._batch = batch
        self._index = 0
        self._undo_stack.clear()
        self._promising = {
            path for path, pending in self._pending.items() if pending.promising
        }
        cached = load_batch_proposals(
            self._services.paths, batch.batch_id, self._rubric.version
        )
        if (
            cached is None
            and self._pregenerated is not None
            and self._pregenerated.batch_id == batch.batch_id
        ):
            cached = self._pregenerated
        if cached is None:
            self._proposals = {}
            self._refresh_view()
            self._generate_current_batch()
        else:
            self._proposals = {p.note_path: p for p in cached.proposals}
            self._advance_to_open_note()
            self._refresh_view()
            self._pregenerate_next()
            if stale:
                self._regenerate(
                    stale,
                    notice=f"re-proposed {len(stale)} changed notes",
                )
        if ejected:
            self._set_status("Ejected vanished notes: " + ", ".join(ejected))

    def _freshen_batch(self, batch: Batch) -> tuple[Batch, list[str], list[str]]:
        """Stat every batch note: eject vanished files, refresh stale evidence."""
        kept: list[str] = []
        ejected: list[str] = []
        stale: list[str] = []
        for path in batch.note_paths:
            note_file = self._services.paths.vault_root / path
            if not note_file.exists():
                ejected.append(path)
                continue
            kept.append(path)
            note = self._notes.get(path)
            if (
                note is None
                or not note.mtime
                or note.mtime == note_file.stat().st_mtime
            ):
                continue
            stale.append(path)
            fresh = extract_evidence(
                self._services.paths.vault_root, note_file, note.population
            )
            self._notes[path] = fresh
            for index, entry in enumerate(self._inventory.notes):
                if entry.path == path:
                    self._inventory.notes[index] = fresh
        if ejected:
            batch = batch.model_copy(update={"note_paths": kept})
        return batch, ejected, stale

    # -- proposal workers ---------------------------------------------------

    @work(thread=True)
    def _generate_current_batch(self) -> None:
        batch = self._batch
        if batch is None:
            return
        try:
            generated = generate_batch_proposals(
                batch,
                self._inventory,
                catalog=self._catalog,
                rubric=self._rubric,
                completer=self._services.completer,
                model=self._services.proposal_model,
                corrections=tuple(self._corrections),
                max_workers=self._services.max_workers,
            )
        except LlmError as error:
            self.app.call_from_thread(
                self._on_generation_failed, batch.batch_id, str(error)
            )
            return
        write_batch_proposals(self._services.paths, generated)
        self.app.call_from_thread(self._on_batch_generated, generated)

    def _on_batch_generated(self, generated: BatchProposals) -> None:
        if self._batch is None or generated.batch_id != self._batch.batch_id:
            return
        self._proposals = {p.note_path: p for p in generated.proposals}
        self._advance_to_open_note()
        self._refresh_view()
        self._pregenerate_next()

    def _pregenerate_next(self) -> None:
        batch = self._batch
        if batch is None:
            return
        next_batch = self._batch_after(batch.batch_id)
        if next_batch is None:
            return
        cached = load_batch_proposals(
            self._services.paths, next_batch.batch_id, self._rubric.version
        )
        if cached is not None:
            self._pregenerated = cached
            return
        self._pregenerate(next_batch, self._rubric)

    @work(thread=True)
    def _pregenerate(self, batch: Batch, rubric: Rubric) -> None:
        try:
            generated = generate_batch_proposals(
                batch,
                self._inventory,
                catalog=self._catalog,
                rubric=rubric,
                completer=self._services.completer,
                model=self._services.proposal_model,
                max_workers=self._services.max_workers,
            )
        except LlmError as error:
            self.app.call_from_thread(
                self._on_generation_failed, batch.batch_id, str(error)
            )
            return
        write_batch_proposals(self._services.paths, generated)
        self.app.call_from_thread(self._on_pregenerated, generated)

    def _on_pregenerated(self, generated: BatchProposals) -> None:
        self._pregenerated = generated

    def _on_generation_failed(self, batch_id: int, error: str) -> None:
        """LlmError fallback: park the batch and keep the review moving."""
        self._pending_batches.add(batch_id)
        if self._batch is not None and self._batch.batch_id == batch_id:
            next_batch = self._batch_after(batch_id)
            self._open_batch(
                next_batch.batch_id if next_batch is not None else None
            )
        self._set_status(
            f"Batch {batch_id} generation failed ({error}); marked pending."
        )

    @work(thread=True)
    def _regenerate(self, note_paths: list[str], *, notice: str) -> None:
        """Re-propose a subset of the current batch with corrections applied."""
        batch = self._batch
        if batch is None or not note_paths:
            return
        subset = Batch(
            batch_id=batch.batch_id,
            label=batch.label,
            note_paths=list(note_paths),
        )
        try:
            generated = generate_batch_proposals(
                subset,
                self._inventory,
                catalog=self._catalog,
                rubric=self._rubric,
                completer=self._services.completer,
                model=self._services.proposal_model,
                corrections=tuple(self._corrections),
                max_workers=self._services.max_workers,
            )
        except LlmError as error:
            self.app.call_from_thread(self._set_status, f"Re-propose failed: {error}")
            return
        self.app.call_from_thread(self._on_regenerated, generated, notice)

    def _on_regenerated(self, generated: BatchProposals, notice: str) -> None:
        for proposal in generated.proposals:
            self._proposals[proposal.note_path] = proposal
            self._pending.pop(proposal.note_path, None)
        batch = self._batch
        if batch is not None and generated.batch_id == batch.batch_id:
            write_batch_proposals(
                self._services.paths,
                BatchProposals(
                    batch_id=batch.batch_id,
                    rubric_version=self._rubric.version,
                    proposals=[
                        self._proposals[path]
                        for path in batch.note_paths
                        if path in self._proposals
                    ],
                ),
            )
        self._save_session()
        self._refresh_view()
        self._set_status(notice)

    # -- view and session state ----------------------------------------------

    def _current_path(self) -> str | None:
        batch = self._batch
        if batch is None or not batch.note_paths:
            return None
        return batch.note_paths[self._index]

    def _advance_to_open_note(self) -> None:
        batch = self._batch
        if batch is None:
            return
        for index, path in enumerate(batch.note_paths):
            if path not in self._pending:
                self._index = index
                return
        self._index = 0

    def _advance(self) -> None:
        batch = self._batch
        if batch is None:
            return
        count = len(batch.note_paths)
        for offset in range(1, count + 1):
            candidate = (self._index + offset) % count
            if batch.note_paths[candidate] not in self._pending:
                self._index = candidate
                self._refresh_view()
                return
        self._refresh_view()
        self._set_status(
            f"Batch {batch.batch_id} fully decided. b confirms, u undoes."
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)

    def _refresh_view(self) -> None:
        batch = self._batch
        path = self._current_path()
        if batch is None or path is None:
            return
        decided = sum(1 for p in batch.note_paths if p in self._pending)
        total = len(batch.note_paths)
        self._set_status(
            f"batch {batch.batch_id} | note {self._index + 1}/{total}"
            f" | decided {decided}/{total} | rubric v{self._rubric.version}"
        )
        note_file = self._services.paths.vault_root / path
        body = ""
        if note_file.exists():
            _, body = split_frontmatter(note_file.read_text(encoding="utf-8"))
        note = self._notes.get(path)
        title = note.title if note is not None else path
        self.query_one(NotePanel).show_note(title, body)
        pending = self._pending.get(path)
        self.query_one(ProposalPanel).show_proposal(
            self._proposals.get(path),
            promising=path in self._promising,
            pending_action=pending.action if pending is not None else "",
        )

    def _save_session(self) -> None:
        batch = self._batch
        if batch is None:
            return
        save_session(
            self._services.paths.session_path,
            SessionState(
                batch_id=batch.batch_id,
                pending=dict(self._pending),
                corrections=list(self._corrections),
                extra_events=list(self._extra_events),
            ),
        )

    def _record(self, path: str, decision: PendingDecision) -> None:
        self._undo_stack.append((path, self._pending.get(path)))
        self._pending[path] = decision
        self._save_session()
        self._advance()

    def _is_movable(self, path: str) -> bool:
        """Meetings/weekly notes are annotate-only: no trash, area targets only."""
        note = self._notes.get(path)
        return note is None or note.population in MOVABLE_POPULATIONS

    # -- key actions ----------------------------------------------------------

    def action_approve(self) -> None:
        path = self._current_path()
        if path is None:
            return
        proposal = self._proposals.get(path)
        if proposal is None:
            return
        self._record(
            path,
            PendingDecision(
                proposal=proposal,
                action="approve",
                promising=path in self._promising,
            ),
        )

    def action_skip(self) -> None:
        self._override_decision("skip", reason="skipped")

    def action_trash(self) -> None:
        path = self._current_path()
        if path is not None and not self._is_movable(path):
            self._set_status(
                "Annotate-only note (meetings/weekly); trash unavailable."
            )
            return
        self._override_decision("trash", reason="trashed")

    def _override_decision(
        self, decision: ProposalDecision, *, reason: str
    ) -> None:
        path = self._current_path()
        if path is None:
            return
        proposal = self._proposals.get(path)
        if proposal is None:
            proposal = Proposal(note_path=path, decision="skip")
        if proposal.decision == decision:
            self._record(
                path,
                PendingDecision(
                    proposal=proposal,
                    action="approve",
                    promising=path in self._promising,
                ),
            )
            return
        update: dict[str, str] = {"decision": decision}
        if decision == "trash":
            update["target"] = ""
        self._record(
            path,
            PendingDecision(
                proposal=proposal.model_copy(update=update),
                action="edit",
                promising=path in self._promising,
                reason=reason,
            ),
        )

    def action_promising(self) -> None:
        path = self._current_path()
        if path is None:
            return
        if path in self._promising:
            self._promising.discard(path)
        else:
            self._promising.add(path)
        pending = self._pending.get(path)
        if pending is not None:
            self._pending[path] = pending.model_copy(
                update={"promising": path in self._promising}
            )
        self._save_session()
        self._refresh_view()

    def action_edit(self) -> None:
        path = self._current_path()
        if path is None or path not in self._proposals:
            return
        options = [f"area:{entry.slug}" for entry in self._catalog.areas]
        if self._is_movable(path):
            options += [
                f"resource:{topic}" for topic in self._catalog.resource_topics
            ]
            options += ["archive:notes", "trash:"]
        self.app.push_screen(TargetPicker(options), callback=self._on_target_picked)

    def _on_target_picked(self, result: str | None) -> None:
        if not result:
            return
        path = self._current_path()
        if path is None or path not in self._proposals:
            return
        decision, _, target = result.partition(":")
        if decision not in ("area", "resource", "archive", "trash"):
            decision, target = "area", result
        edited = self._proposals[path].model_copy(
            update={"decision": decision, "target": target.strip()}
        )
        new_area = edited.new_area
        if new_area is not None and new_area.slug != edited.target:
            edited = edited.model_copy(update={"new_area": None})
        self._record(
            path,
            PendingDecision(
                proposal=edited,
                action="edit",
                promising=path in self._promising,
            ),
        )

    def action_undo(self) -> None:
        if not self._undo_stack:
            return
        path, previous = self._undo_stack.pop()
        if previous is None:
            self._pending.pop(path, None)
        else:
            self._pending[path] = previous
        batch = self._batch
        if batch is not None and path in batch.note_paths:
            self._index = batch.note_paths.index(path)
        self._save_session()
        self._refresh_view()
```

- [ ] **Step 7: Write the implementation: app shell**

Create `src/alex/lib/triage/tui/app.py`:

```python
"""Textual application shell for the triage and atomic review screens."""

from __future__ import annotations

from textual.app import App

from alex.lib.triage.models import ClusterMap, Inventory
from alex.lib.triage.tui.services import TriageServices
from alex.lib.triage.tui.triage_screen import TriageScreen


class TriageApp(App[None]):
    """Hosts the review screens over a prepared inventory and cluster map."""

    CSS = """
    #status-bar {
        height: 1;
        background: $panel;
    }
    #panels {
        height: 1fr;
    }
    #note-panel {
        width: 3fr;
    }
    #proposal-panel {
        width: 2fr;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        services: TriageServices,
        inventory: Inventory,
        cluster_map: ClusterMap,
        *,
        mode: str = "triage",
    ) -> None:
        super().__init__()
        self._services = services
        self._inventory = inventory
        self._cluster_map = cluster_map
        self._tui_mode = mode

    def on_mount(self) -> None:
        if self._tui_mode != "triage":
            raise ValueError(f"Unknown TUI mode: {self._tui_mode}")
        self.push_screen(
            TriageScreen(self._services, self._inventory, self._cluster_map)
        )
```

- [ ] **Step 8: Run test to verify it passes**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_tui.py -v
```

Expected: **10 passed**.
- [ ] **Step 9: Write the failing tests (reject-repropose, batch confirm, chat, annotate-only)**

In `tests/test_triage_tui.py`, add `import os` to the stdlib import block (after `import json`) and three imports to the `alex` group (keeping alphabetical order):

```python
from alex.lib.triage.frontmatter import read_triage_block
from alex.lib.triage.ledger import read_events
from alex.lib.triage.rubric import load_rubric
```

(`frontmatter` sorts before `models`, `ledger` before `models`, `rubric` between `proposals` and `session`.)

The batch-confirm tests reach `exclusive_lock`, whose lock file lives under `Path.home()`; each of them redirects HOME to `tmp_path` with the explicit os.environ save/restore try/finally pattern (repo convention: `tmp_path` only, no monkeypatch fixture).

Append these four tests at the end of the file:

```python
async def test_reject_reason_triggers_repropose_with_correction(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(
        routes=[
            ("Team offsite", proposal_json("area", "writing", "recheck")),
            ("actually python", proposal_json("area", "python", "corrected")),
        ],
        default=RUBRIC_REPLY,
    )
    services = make_services(vault, completer)
    write_batch_proposals(
        services.paths,
        BatchProposals(
            batch_id=1,
            rubric_version=1,
            proposals=[
                Proposal(
                    note_path=NOTE_ONE,
                    decision="area",
                    target="leadership",
                    confidence="high",
                    why="misread",
                ),
                Proposal(
                    note_path=NOTE_TWO,
                    decision="area",
                    target="leadership",
                    confidence="medium",
                    why="team note",
                ),
            ],
        ),
    )
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        await pilot.press(*"actually python")
        await pilot.press("enter")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        panel = screen.query_one(ProposalPanel)
        assert "target: python" in panel.body_text
        assert "corrected" in panel.body_text
        status = str(screen.query_one("#status-bar", Static).renderable)
        assert "re-proposed 2 notes" in status
        await pilot.press("a")
        await pilot.pause()
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.pending[NOTE_ONE].proposal.target == "python"
    assert session.corrections == [f"{NOTE_ONE}: actually python"]
    assert [event.event for event in session.extra_events] == ["reject"]
    cached = load_batch_proposals(services.paths, 1, 1)
    assert cached is not None
    by_path = {p.note_path: p for p in cached.proposals}
    assert by_path[NOTE_ONE].target == "python"
    assert by_path[NOTE_TWO].target == "writing"


async def test_chat_message_then_repropose_updates_proposal(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(
        routes=[
            ("You are helping triage", "consider the python area"),
            ("Team offsite", proposal_json("area", "writing", "chat fix two")),
            ("should be python", proposal_json("area", "python", "chat fix")),
        ],
        default=RUBRIC_REPLY,
    )
    services = make_services(vault, completer)
    write_batch_proposals(
        services.paths,
        BatchProposals(
            batch_id=1,
            rubric_version=1,
            proposals=[
                Proposal(
                    note_path=NOTE_ONE,
                    decision="area",
                    target="leadership",
                    confidence="high",
                    why="misread",
                ),
                Proposal(
                    note_path=NOTE_TWO,
                    decision="area",
                    target="leadership",
                    confidence="medium",
                    why="team note",
                ),
            ],
        ),
    )
    app = TriageApp(services, build_inventory(), build_cluster_map())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        await pilot.press(*"should be python")
        await pilot.press("enter")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TriageScreen)
        assert "target: python" in screen.query_one(ProposalPanel).body_text
    session = load_session(services.paths.session_path)
    assert session is not None
    assert session.corrections
    assert "should be python" in session.corrections[0]
    assert [event.event for event in session.extra_events] == ["repropose"]
    cached = load_batch_proposals(services.paths, 1, 1)
    assert cached is not None
    targets = {p.note_path: p.target for p in cached.proposals}
    assert targets[NOTE_ONE] == "python"
    assert targets[NOTE_TWO] == "writing"


async def test_batch_confirm_writes_frontmatter_ledger_and_bumps_rubric(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    seed_proposals(services.paths)
    app = TriageApp(services, build_inventory(), build_cluster_map())
    home_before = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("p")
            await pilot.press("s")
            await pilot.pause()
            await pilot.press("b")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
    finally:
        if home_before is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home_before

    block_one = read_triage_block((vault / NOTE_ONE).read_text(encoding="utf-8"))
    assert block_one is not None
    assert block_one.decision == "area"
    assert block_one.target == "python"
    assert block_one.status == "decided"
    assert block_one.decided == "2026-07-12"

    block_two = read_triage_block((vault / NOTE_TWO).read_text(encoding="utf-8"))
    assert block_two is not None
    assert block_two.decision is None
    assert block_two.promising is True

    events = read_events(services.paths.ledger_path)
    assert [event.event for event in events] == ["approve", "edit"]
    assert events[0].note == NOTE_ONE
    assert events[1].correction == {"decision": "skip", "target": "leadership"}

    assert load_session(services.paths.session_path) is None
    assert load_rubric(services.paths.rubric_path).version == 2


async def test_annotate_only_note_blocks_trash_and_confirms_as_applied(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    weekly_path = "Weekly/2026-W28.md"
    weekly_file = vault / weekly_path
    weekly_file.parent.mkdir()
    weekly_file.write_text(
        "---\ncreated: 2026-07-06\n---\nWeekly review notes.\n",
        encoding="utf-8",
    )
    completer = RoutedCompleter(routes=[], default=RUBRIC_REPLY)
    services = make_services(vault, completer)
    inventory = Inventory(
        generated="2026-07-12T00:00:00",
        notes=[
            NoteEvidence(
                path=weekly_path,
                title="2026-W28",
                population="weekly",
                snippet="Weekly review notes.",
            )
        ],
    )
    cluster_map = ClusterMap(
        generated="2026-07-12T00:00:00",
        clusters=[
            Cluster(cluster_id=1, label="reviews", note_paths=[weekly_path])
        ],
        batches=[Batch(batch_id=1, note_paths=[weekly_path])],
    )
    write_batch_proposals(
        services.paths,
        BatchProposals(
            batch_id=1,
            rubric_version=1,
            proposals=[
                Proposal(
                    note_path=weekly_path,
                    decision="area",
                    target="leadership",
                    confidence="high",
                    why="weekly review ties to leadership",
                )
            ],
        ),
    )
    app = TriageApp(services, inventory, cluster_map)
    home_before = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("t")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TriageScreen)
            status = str(screen.query_one("#status-bar", Static).renderable)
            assert "trash unavailable" in status
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("b")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
    finally:
        if home_before is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home_before

    block = read_triage_block(weekly_file.read_text(encoding="utf-8"))
    assert block is not None
    assert block.decision == "area"
    assert block.target == "leadership"
    assert block.status == "applied"
    assert block.decided == "2026-07-12"
    assert block.applied == "2026-07-12"
    events = read_events(services.paths.ledger_path)
    assert [event.event for event in events] == ["approve"]
```

- [ ] **Step 10: Run test to verify it fails**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_tui.py -v
```

Expected: **4 failed, 10 passed**. The `r`, `c`, `ctrl+r`, and `b` keys are unbound at this point (only Step 6's bindings exist): the reject test fails on `assert "target: python" in panel.body_text`, the confirm test fails on `assert block_one is not None`, the chat test fails on its `"target: python"` panel assertion (the keystrokes fall through to the screen's Step 6 bindings), and the annotate-only test passes its trash-notice assertion (the guard landed in Step 6) but fails on `assert block is not None` because `b` never confirms.

- [ ] **Step 11: Write the implementation: reject, chat, confirm, distill**

Modify `src/alex/lib/triage/tui/triage_screen.py`.

First, replace the whole import block and add the module helper plus the private confirm modal. The file now begins:

```python
"""Batch review screen: one note, one proposal, keyboard-first decisions."""

from __future__ import annotations

import datetime as dt
from typing import Any, ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Static

from alex.lib.llm import LlmError
from alex.lib.locking import LockHeldError, exclusive_lock
from alex.lib.triage.catalog import catalog_prompt_text, load_or_build_catalog
from alex.lib.triage.distill import distill_rubric
from alex.lib.triage.frontmatter import (
    read_triage_block,
    split_frontmatter,
    write_triage_block,
)
from alex.lib.triage.inventory import MOVABLE_POPULATIONS, extract_evidence
from alex.lib.triage.ledger import append_event, read_events
from alex.lib.triage.models import (
    Batch,
    BatchProposals,
    Catalog,
    ClusterMap,
    Inventory,
    LedgerEvent,
    NoteEvidence,
    PendingAreas,
    PendingDecision,
    Proposal,
    ProposalDecision,
    Rubric,
    SessionState,
    TriageBlock,
)
from alex.lib.triage.proposals import (
    generate_batch_proposals,
    load_batch_proposals,
    write_batch_proposals,
)
from alex.lib.triage.rubric import load_rubric, save_rubric
from alex.lib.triage.session import clear_session, load_session, save_session
from alex.lib.triage.storage import (
    atomic_write_text,
    read_yaml_model,
    write_yaml_model,
)
from alex.lib.triage.tui.services import TriageServices
from alex.lib.triage.tui.widgets import (
    ChatPane,
    NotePanel,
    ProposalPanel,
    ReasonInput,
    TargetPicker,
)


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class _ConfirmSummary(ModalScreen[bool]):
    """Batch summary; y or enter confirms, escape goes back."""

    DEFAULT_CSS = """
    #confirm-summary {
        width: 70;
        max-height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "confirm", "Confirm"),
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(self, summary: str) -> None:
        super().__init__()
        self._summary = summary

    def compose(self) -> ComposeResult:
        yield Static(self._summary, id="confirm-summary")

    def on_mount(self) -> None:
        self.styles.align = ("center", "middle")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
```

Second, replace the `BINDINGS` list of `TriageScreen` with the full contracted set:

```python
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "approve", "Approve"),
        Binding("r", "reject", "Reject"),
        Binding("e", "edit", "Edit target"),
        Binding("p", "promising", "Promising"),
        Binding("t", "trash", "Trash"),
        Binding("s", "skip", "Skip"),
        Binding("c", "chat", "Chat"),
        Binding("u", "undo", "Undo"),
        Binding("b", "confirm_batch", "Confirm batch"),
        Binding("enter", "confirm_batch", "Confirm batch", show=False),
        Binding("q", "app.quit", "Quit"),
    ]
```

Third, append these methods at the end of `TriageScreen` (after `action_undo`):

```python
    # -- reject / chat / confirm ----------------------------------------------

    def _unreviewed_paths(self) -> list[str]:
        """Batch notes with no pending decision; corrections re-propose these."""
        batch = self._batch
        if batch is None:
            return []
        return [path for path in batch.note_paths if path not in self._pending]

    def action_reject(self) -> None:
        path = self._current_path()
        if path is None or path not in self._proposals:
            return
        self.app.push_screen(
            ReasonInput("Why is this proposal wrong?"),
            callback=self._on_reject_reason,
        )

    def _on_reject_reason(self, reason: str | None) -> None:
        if not reason:
            return
        path = self._current_path()
        batch = self._batch
        if path is None or batch is None or path not in self._proposals:
            return
        self._extra_events.append(
            LedgerEvent(
                ts=_now_iso(),
                note=path,
                batch=batch.batch_id,
                rubric_version=self._rubric.version,
                event="reject",
                proposal=self._proposals[path].model_dump(mode="json"),
                reason=reason,
            )
        )
        self._corrections.append(f"{path}: {reason}")
        self._save_session()
        self.query_one(ProposalPanel).show_proposal(
            None, promising=path in self._promising, pending_action=""
        )
        targets = self._unreviewed_paths()
        self._regenerate(
            targets,
            notice=f"re-proposed {len(targets)} notes with your correction",
        )

    def action_chat(self) -> None:
        path = self._current_path()
        if path is None:
            return
        note = self._notes.get(path)
        proposal = self._proposals.get(path)
        context = "\n\n".join(
            [
                "You are helping triage one Obsidian note into PARA.",
                f"## Rubric\n{self._rubric.text}",
                catalog_prompt_text(self._catalog),
                f"## Note\npath: {path}"
                f"\ntitle: {note.title if note is not None else path}"
                f"\nsnippet: {note.snippet if note is not None else ''}",
                "## Current proposal\n"
                + (
                    proposal.model_dump_json()
                    if proposal is not None
                    else "none yet"
                ),
            ]
        )
        services = self._services

        def send(transcript: str) -> str:
            return services.completer.complete(
                prompt=transcript,
                model=services.atomic_model,
                max_tokens=1000,
            )

        self.app.push_screen(ChatPane(context, send), callback=self._on_chat_done)

    def _on_chat_done(self, result: str | None) -> None:
        if result is None or not result.startswith("REPROPOSE:"):
            return
        path = self._current_path()
        batch = self._batch
        if path is None or batch is None or path not in self._proposals:
            return
        transcript = result.removeprefix("REPROPOSE:")
        self._extra_events.append(
            LedgerEvent(
                ts=_now_iso(),
                note=path,
                batch=batch.batch_id,
                rubric_version=self._rubric.version,
                event="repropose",
                proposal=self._proposals[path].model_dump(mode="json"),
                reason=transcript,
            )
        )
        self._corrections.append(f"{path}: {transcript}")
        self._save_session()
        targets = self._unreviewed_paths()
        self._regenerate(
            targets,
            notice=f"re-proposed {len(targets)} notes with your correction",
        )

    def action_confirm_batch(self) -> None:
        batch = self._batch
        if batch is None:
            return
        counts: dict[str, int] = {}
        for path in batch.note_paths:
            pending = self._pending.get(path)
            if pending is None:
                continue
            key = pending.proposal.decision
            counts[key] = counts.get(key, 0) + 1
        lines = [f"Confirm batch {batch.batch_id}?"]
        for decision, count in sorted(counts.items()):
            lines.append(f"  {decision}: {count}")
        manual = [
            path
            for path in batch.note_paths
            if (proposal := self._proposals.get(path)) is not None
            and proposal.needs_manual
        ]
        if manual:
            lines.append("needs manual: " + ", ".join(manual))
        undecided = [p for p in batch.note_paths if p not in self._pending]
        if undecided:
            lines.append("left undecided: " + ", ".join(undecided))
        lines.append("y/enter to confirm, esc to go back")
        self.app.push_screen(
            _ConfirmSummary("\n".join(lines)), callback=self._on_confirm
        )

    def _on_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self._confirm_batch()

    def _confirm_batch(self) -> None:
        batch = self._batch
        if batch is None:
            return
        paths = self._services.paths
        rubric_version = self._rubric.version
        try:
            with exclusive_lock(paths.lock_path):
                for path in batch.note_paths:
                    pending = self._pending.get(path)
                    if pending is None:
                        continue
                    self._write_decision(path, pending)
                    correction: dict[str, Any] | None = None
                    if pending.action == "edit":
                        correction = {
                            "decision": pending.proposal.decision,
                            "target": pending.proposal.target,
                        }
                    original = self._proposals.get(path, pending.proposal)
                    append_event(
                        paths.ledger_path,
                        LedgerEvent(
                            ts=_now_iso(),
                            note=path,
                            batch=batch.batch_id,
                            rubric_version=rubric_version,
                            event=pending.action,
                            proposal=original.model_dump(mode="json"),
                            correction=correction,
                            reason=pending.reason,
                        ),
                    )
                    self._register_new_area(pending)
                for extra in self._extra_events:
                    append_event(paths.ledger_path, extra)
                clear_session(paths.session_path)
        except LockHeldError:
            self._set_status("Vault lock held by another process; try again.")
            return
        self._pending.clear()
        self._corrections.clear()
        self._extra_events.clear()
        self._promising.clear()
        self._distill()
        next_batch = self._batch_after(batch.batch_id)
        self._open_batch(next_batch.batch_id if next_batch is not None else None)

    def _write_decision(self, path: str, pending: PendingDecision) -> None:
        note_file = self._services.paths.vault_root / path
        if not note_file.exists():
            return
        decision = pending.proposal.decision
        if decision == "skip":
            if not pending.promising:
                return
            block = TriageBlock(promising=True)
        elif not self._is_movable(path):
            # Annotate-only populations (meetings/weekly): the decision records
            # the area association and there is nothing to move, so the note
            # goes straight to applied at confirm.
            block = TriageBlock(
                decision=decision,
                target=pending.proposal.target,
                promising=pending.promising,
                status="applied",
                decided=self._services.today,
                applied=self._services.today,
            )
        else:
            block = TriageBlock(
                decision=decision,
                target=pending.proposal.target,
                promising=pending.promising,
                status="decided",
                decided=self._services.today,
            )
        text = note_file.read_text(encoding="utf-8")
        atomic_write_text(note_file, write_triage_block(text, block))

    def _register_new_area(self, pending: PendingDecision) -> None:
        new_area = pending.proposal.new_area
        if new_area is None or pending.proposal.decision != "area":
            return
        pending_areas_path = self._services.paths.pending_areas_path
        existing = read_yaml_model(pending_areas_path, PendingAreas)
        if existing is None:
            existing = PendingAreas()
        if any(area.slug == new_area.slug for area in existing.areas):
            return
        existing.areas.append(new_area)
        write_yaml_model(pending_areas_path, existing)

    @work(thread=True)
    def _distill(self) -> None:
        # Load the rubric fresh from disk so hand edits made while the TUI is
        # open survive distillation.
        paths = self._services.paths
        current = load_rubric(paths.rubric_path)
        events = read_events(paths.ledger_path, since_version=current.version)
        updated = distill_rubric(
            current, events, self._services.completer, self._services.distill_model
        )
        if updated.version == current.version:
            self.app.call_from_thread(
                self._set_status,
                "Rubric distillation made no update; keeping the current rubric.",
            )
            return
        save_rubric(paths.rubric_path, updated)
        self.app.call_from_thread(self._on_distilled, updated)

    def _on_distilled(self, updated: Rubric) -> None:
        self._rubric = updated
        if self._batch is not None:
            self._refresh_view()
```

- [ ] **Step 12: Run test to verify it passes**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_tui.py -v
```

Expected: **14 passed**.

- [ ] **Step 13: Lint and typecheck**

```bash
cd /home/alex/code/alex && just lint && uv run mypy
```

Expected: ruff check clean, ruff format --check clean, mypy clean (`Success: no issues found`).

- [ ] **Step 14: Commit**

```bash
cd /home/alex/code/alex && git add pyproject.toml uv.lock \
  src/alex/lib/triage/tui/__init__.py \
  src/alex/lib/triage/tui/services.py \
  src/alex/lib/triage/tui/widgets.py \
  src/alex/lib/triage/tui/triage_screen.py \
  src/alex/lib/triage/tui/app.py \
  tests/test_triage_tui.py && \
git commit -m "feat(triage): add textual review TUI with batch triage screen

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
### Task 16: Atomic review screen

**Files:**
- Create: `src/alex/lib/triage/tui/atomic_screen.py`
- Modify: `src/alex/lib/triage/tui/app.py` (import block; `on_mount` at end of file; two CSS selectors)
- Test: `tests/test_triage_atomic_tui.py`

All paths relative to repo root `/home/alex/code/alex`.

**Interfaces:**

Consumes (exact contract signatures):
- Task 13 atomic: `AtomicParseError(ValueError)`, `atomic_queue(vault_root: Path) -> list[str]`, `draft_atomic_notes(note_text: str, note: NoteEvidence, *, rubric: Rubric, permanent_titles: Sequence[str], completer: Completer, model: str, feedback: str = "") -> list[AtomicDraft]`, `verify_related(drafts: list[AtomicDraft], vault_root: Path) -> list[AtomicDraft]`, `write_atomic_note(vault_root: Path, draft: AtomicDraft, created: str) -> Path`, `mark_atomic_done(vault_root: Path, source_rel: str, written: Sequence[Path]) -> None`
- Task 5 inventory: `extract_evidence(vault_root: Path, md_path: Path, population: Population) -> NoteEvidence`
- Task 7 ledger: `append_event`, Task 8 rubric: `load_rubric`
- Task 15: `TriageServices`, `TriageApp`, widgets `NotePanel`, `ReasonInput`, `ChatPane`
- Repo: `exclusive_lock` / `LockHeldError`

Produces (Task 17 relies on this):
- `AtomicScreen(Screen[None])` with `__init__(self, services: TriageServices, inventory: Inventory) -> None`
- `TriageApp(..., mode="atomic")` now pushes `AtomicScreen` instead of raising

Design notes: the queue comes from `atomic_queue()`; evidence is taken from the passed inventory when the path is known, else re-extracted with the population guessed from the path prefix. `atomic_approve`/`atomic_revise` ledger events use `batch=0` (atomic mode has no batch). Approve and drop take the vault lock because `mark_atomic_done` writes frontmatter.

- [ ] **Step 1: Write the failing test (approve flow)**

Create `tests/test_triage_atomic_tui.py`. Approve and drop take `exclusive_lock`, whose lock file lives under `Path.home()`, so every test that presses `a` or `d` redirects HOME to `tmp_path` with the explicit os.environ save/restore try/finally pattern (repo convention: `tmp_path` only, no monkeypatch fixture):

```python
"""Pilot tests for the atomic-note drafting screen."""

from __future__ import annotations

import json
import os
from pathlib import Path

from alex.lib.triage.frontmatter import read_triage_block
from alex.lib.triage.ledger import read_events
from alex.lib.triage.models import ClusterMap, Inventory, NoteEvidence
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.tui.app import TriageApp
from alex.lib.triage.tui.atomic_screen import AtomicScreen
from alex.lib.triage.tui.services import TriageServices
from helpers import BagOfWordsEmbedder

SOURCE = "Deep work insight.md"
PERMANENT = "Attention is a finite budget"

DRAFT_JSON = json.dumps(
    [
        {
            "title": "Silence is a precondition for deep work",
            "body": "Deep work needs silence. I protect it on my calendar.",
            "tags": ["focus", "deep-work"],
            "related": [f"resources/permanent-notes/{PERMANENT}"],
        }
    ]
)
REVISED_JSON = json.dumps(
    [
        {
            "title": "Deep work depends on unbroken silence",
            "body": "Revised body in my own words.",
            "tags": ["focus"],
            "related": [],
        }
    ]
)


class RoutedCompleter:
    """Returns the first canned response whose marker appears in the prompt."""

    def __init__(self, routes: list[tuple[str, str]], default: str) -> None:
        self.routes = routes
        self.default = default
        self.prompts: list[str] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        for marker, response in self.routes:
            if marker in prompt:
                return response
        return self.default


def build_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    notes_dir = vault / "resources" / "permanent-notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / f"{PERMANENT}.md").write_text(
        "---\ntype: permanent-note\n---\nAttention is finite.\n",
        encoding="utf-8",
    )
    (vault / SOURCE).write_text(
        "---\ncreated: 2026-07-01\ntriage:\n"
        '  promising: true\n  decided: "2026-07-10"\n---\n'
        "Deep work happens in silence.\n",
        encoding="utf-8",
    )
    return vault


def build_inventory() -> Inventory:
    return Inventory(
        generated="2026-07-12T00:00:00",
        notes=[
            NoteEvidence(
                path=SOURCE,
                title="Deep work insight",
                population="root",
                snippet="Deep work happens in silence.",
            )
        ],
    )


def make_services(vault: Path, completer: RoutedCompleter) -> TriageServices:
    return TriageServices(
        paths=TriagePaths(vault_root=vault),
        completer=completer,
        embedder=BagOfWordsEmbedder(),
        proposal_model="test-proposal",
        atomic_model="test-atomic",
        distill_model="test-distill",
        max_workers=1,
        today="2026-07-12",
    )


def make_app(services: TriageServices) -> TriageApp:
    cluster_map = ClusterMap(generated="2026-07-12T00:00:00")
    return TriageApp(services, build_inventory(), cluster_map, mode="atomic")


async def test_atomic_approve_writes_notes_and_marks_source_done(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(
        routes=[("Deep work happens in silence", DRAFT_JSON)], default="[]"
    )
    services = make_services(vault, completer)
    app = make_app(services)
    home_before = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, AtomicScreen)
            assert (
                screen.drafts[0].title
                == "Silence is a precondition for deep work"
            )
            await pilot.press("a")
            await pilot.pause()
    finally:
        if home_before is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home_before

    written = (
        vault
        / "resources"
        / "permanent-notes"
        / "Silence is a precondition for deep work.md"
    )
    assert written.exists()
    assert "provenance" in written.read_text(encoding="utf-8")

    source_text = (vault / SOURCE).read_text(encoding="utf-8")
    block = read_triage_block(source_text)
    assert block is not None
    assert block.promising is False
    assert "Silence is a precondition for deep work" in source_text

    events = read_events(services.paths.ledger_path)
    assert [event.event for event in events] == ["atomic_approve"]
    assert events[0].note == SOURCE
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_atomic_tui.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'alex.lib.triage.tui.atomic_screen'`.

- [ ] **Step 3: Write the implementation: atomic screen (queue, drafting, approve, skip)**

Create `src/alex/lib/triage/tui/atomic_screen.py`:

```python
"""Second-pass screen: draft atomic permanent notes from promising sources."""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Static

from alex.lib.locking import LockHeldError, exclusive_lock
from alex.lib.triage.atomic import (
    AtomicParseError,
    atomic_queue,
    draft_atomic_notes,
    mark_atomic_done,
    verify_related,
    write_atomic_note,
)
from alex.lib.triage.frontmatter import split_frontmatter
from alex.lib.triage.inventory import extract_evidence
from alex.lib.triage.ledger import append_event
from alex.lib.triage.models import (
    AtomicDraft,
    Inventory,
    LedgerEvent,
    NoteEvidence,
    Population,
    Rubric,
)
from alex.lib.triage.rubric import load_rubric
from alex.lib.triage.tui.services import TriageServices
from alex.lib.triage.tui.widgets import NotePanel


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class AtomicScreen(Screen[None]):
    """Approves or revises LLM-drafted atomic notes, one source at a time."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "approve", "Approve drafts"),
        Binding("s", "skip", "Skip"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, services: TriageServices, inventory: Inventory) -> None:
        super().__init__()
        self._services = services
        self._notes: dict[str, NoteEvidence] = {
            note.path: note for note in inventory.notes
        }
        self._rubric: Rubric = load_rubric(services.paths.rubric_path)
        self._queue: list[str] = []
        self._position = 0
        self.drafts: list[AtomicDraft] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="status-bar")
        with Horizontal(id="panels"):
            yield NotePanel(id="source-panel")
            yield NotePanel(id="drafts-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._queue = atomic_queue(self._services.paths.vault_root)
        self._open_current()

    def _set_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)

    def _current_path(self) -> str | None:
        if self._position >= len(self._queue):
            return None
        return self._queue[self._position]

    def _open_current(self) -> None:
        path = self._current_path()
        if path is None:
            self._set_status("Atomic queue drained. q to quit.")
            self.query_one("#source-panel", NotePanel).show_note("Done", "")
            self.query_one("#drafts-panel", NotePanel).show_note("Done", "")
            return
        self.drafts = []
        self._set_status(
            f"note {self._position + 1}/{len(self._queue)}: {path} (drafting...)"
        )
        note_text = (self._services.paths.vault_root / path).read_text(
            encoding="utf-8"
        )
        _, body = split_frontmatter(note_text)
        self.query_one("#source-panel", NotePanel).show_note(path, body)
        self.query_one("#drafts-panel", NotePanel).show_note("Drafts", "Drafting...")
        self._draft(path, note_text, feedback="")

    def _evidence_for(self, path: str) -> NoteEvidence:
        note = self._notes.get(path)
        if note is not None:
            return note
        population: Population = "root"
        if path.startswith("Clippings/"):
            population = "clippings"
        elif path.startswith("Meetings/"):
            population = "meetings"
        elif path.startswith("Weekly/"):
            population = "weekly"
        return extract_evidence(
            self._services.paths.vault_root,
            self._services.paths.vault_root / path,
            population,
        )

    def _permanent_titles(self) -> list[str]:
        notes_dir = self._services.paths.vault_root / "resources" / "permanent-notes"
        if not notes_dir.is_dir():
            return []
        return sorted(
            md.stem for md in notes_dir.glob("*.md") if md.name != "index.md"
        )

    @work(thread=True)
    def _draft(self, path: str, note_text: str, *, feedback: str) -> None:
        try:
            drafts = draft_atomic_notes(
                note_text,
                self._evidence_for(path),
                rubric=self._rubric,
                permanent_titles=self._permanent_titles(),
                completer=self._services.completer,
                model=self._services.atomic_model,
                feedback=feedback,
            )
        except AtomicParseError as error:
            self.app.call_from_thread(
                self._set_status, f"Draft failed: {error}. s skips this note."
            )
            return
        drafts = verify_related(drafts, self._services.paths.vault_root)
        self.app.call_from_thread(self._show_drafts, path, drafts)

    def _show_drafts(self, path: str, drafts: list[AtomicDraft]) -> None:
        if path != self._current_path():
            return
        self.drafts = drafts
        rendered = [
            f"# {draft.title}\n\n{draft.body}\n\n"
            f"tags: {', '.join(draft.tags)}\nrelated: {', '.join(draft.related)}"
            for draft in drafts
        ]
        self.query_one("#drafts-panel", NotePanel).show_note(
            f"{len(drafts)} draft(s)", "\n\n---\n\n".join(rendered)
        )
        self._set_status(f"note {self._position + 1}/{len(self._queue)}: {path}")

    def _next(self) -> None:
        self._position += 1
        self._open_current()

    def action_approve(self) -> None:
        path = self._current_path()
        if path is None or not self.drafts:
            return
        services = self._services
        try:
            with exclusive_lock(services.paths.lock_path):
                written = [
                    write_atomic_note(
                        services.paths.vault_root, draft, services.today
                    )
                    for draft in self.drafts
                ]
                mark_atomic_done(services.paths.vault_root, path, written)
        except LockHeldError:
            self._set_status("Vault lock held by another process; try again.")
            return
        append_event(
            services.paths.ledger_path,
            LedgerEvent(
                ts=_now_iso(),
                note=path,
                batch=0,
                rubric_version=self._rubric.version,
                event="atomic_approve",
                proposal={
                    "drafts": [
                        draft.model_dump(mode="json") for draft in self.drafts
                    ]
                },
            ),
        )
        self._next()

    def action_skip(self) -> None:
        if self._current_path() is None:
            return
        self._next()
```

- [ ] **Step 4: Write the implementation: wire atomic mode into the app**

Modify `src/alex/lib/triage/tui/app.py`.

Add the import (first line of the `alex` import group, before the `models` import):

```python
from alex.lib.triage.models import ClusterMap, Inventory
from alex.lib.triage.tui.atomic_screen import AtomicScreen
from alex.lib.triage.tui.services import TriageServices
from alex.lib.triage.tui.triage_screen import TriageScreen
```

Extend the two panel CSS selectors so the atomic screen shares the layout. `#note-panel {` becomes `#note-panel, #source-panel {` and `#proposal-panel {` becomes `#proposal-panel, #drafts-panel {`:

```css
    #note-panel, #source-panel {
        width: 3fr;
    }
    #proposal-panel, #drafts-panel {
        width: 2fr;
        padding: 0 1;
    }
```

Replace `on_mount` with:

```python
    def on_mount(self) -> None:
        if self._tui_mode == "atomic":
            self.push_screen(AtomicScreen(self._services, self._inventory))
            return
        if self._tui_mode != "triage":
            raise ValueError(f"Unknown TUI mode: {self._tui_mode}")
        self.push_screen(
            TriageScreen(self._services, self._inventory, self._cluster_map)
        )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_atomic_tui.py -v
```

Expected: **1 passed**.

- [ ] **Step 6: Write the failing tests (revise and drop flows)**

Append to `tests/test_triage_atomic_tui.py`:

```python
async def test_atomic_revise_redrafts_with_feedback_and_logs_event(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(
        routes=[
            ("make the title a claim", REVISED_JSON),
            ("Deep work happens in silence", DRAFT_JSON),
        ],
        default="[]",
    )
    services = make_services(vault, completer)
    app = make_app(services)
    home_before = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            await pilot.press(*"make the title a claim")
            await pilot.press("enter")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, AtomicScreen)
            assert (
                screen.drafts[0].title
                == "Deep work depends on unbroken silence"
            )
            await pilot.press("a")
            await pilot.pause()
    finally:
        if home_before is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home_before

    events = read_events(services.paths.ledger_path)
    assert [event.event for event in events] == ["atomic_revise", "atomic_approve"]
    assert events[0].reason == "make the title a claim"
    revised = (
        vault
        / "resources"
        / "permanent-notes"
        / "Deep work depends on unbroken silence.md"
    )
    assert revised.exists()


async def test_atomic_drop_unflags_promising_without_writing_notes(
    tmp_path: Path,
) -> None:
    vault = build_vault(tmp_path)
    completer = RoutedCompleter(
        routes=[("Deep work happens in silence", DRAFT_JSON)], default="[]"
    )
    services = make_services(vault, completer)
    app = make_app(services)
    home_before = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
    finally:
        if home_before is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home_before

    notes_dir = vault / "resources" / "permanent-notes"
    assert sorted(md.name for md in notes_dir.glob("*.md")) == [f"{PERMANENT}.md"]
    block = read_triage_block((vault / SOURCE).read_text(encoding="utf-8"))
    assert block is not None
    assert block.promising is False
```

- [ ] **Step 7: Run test to verify it fails**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_atomic_tui.py -v
```

Expected: **2 failed, 1 passed**. `r` and `d` are unbound. In the revise test the stray `a` inside the typed feedback approves the original drafts, so `screen.drafts[0]` raises `IndexError`; the drop test fails on `block.promising is False`.

- [ ] **Step 8: Write the implementation: revise, chat, drop**

Modify `src/alex/lib/triage/tui/atomic_screen.py`.

Change the widgets import to:

```python
from alex.lib.triage.tui.widgets import ChatPane, NotePanel, ReasonInput
```

Replace the `BINDINGS` list with the full contracted set:

```python
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "approve", "Approve drafts"),
        Binding("r", "revise", "Revise"),
        Binding("c", "chat", "Chat"),
        Binding("s", "skip", "Skip"),
        Binding("d", "drop", "Drop"),
        Binding("q", "app.quit", "Quit"),
    ]
```

Append these methods at the end of `AtomicScreen` (after `action_skip`):

```python
    def action_revise(self) -> None:
        if self._current_path() is None:
            return
        self.app.push_screen(
            ReasonInput("What should change in the drafts?"),
            callback=self._on_revise_reason,
        )

    def _on_revise_reason(self, reason: str | None) -> None:
        if not reason:
            return
        self._redraft(reason)

    def _redraft(self, feedback: str) -> None:
        path = self._current_path()
        if path is None:
            return
        append_event(
            self._services.paths.ledger_path,
            LedgerEvent(
                ts=_now_iso(),
                note=path,
                batch=0,
                rubric_version=self._rubric.version,
                event="atomic_revise",
                proposal={
                    "drafts": [
                        draft.model_dump(mode="json") for draft in self.drafts
                    ]
                },
                reason=feedback,
            ),
        )
        self.drafts = []
        self.query_one("#drafts-panel", NotePanel).show_note(
            "Drafts", "Redrafting..."
        )
        note_text = (self._services.paths.vault_root / path).read_text(
            encoding="utf-8"
        )
        self._draft(path, note_text, feedback=feedback)

    def action_chat(self) -> None:
        path = self._current_path()
        if path is None:
            return
        drafts_text = (
            "\n".join(draft.model_dump_json() for draft in self.drafts)
            or "none yet"
        )
        context = "\n\n".join(
            [
                "You are helping draft atomic permanent notes from one source.",
                f"## Rubric\n{self._rubric.text}",
                f"## Source note\n{path}",
                f"## Current drafts\n{drafts_text}",
            ]
        )
        services = self._services

        def send(transcript: str) -> str:
            return services.completer.complete(
                prompt=transcript,
                model=services.atomic_model,
                max_tokens=1000,
            )

        self.app.push_screen(ChatPane(context, send), callback=self._on_chat_done)

    def _on_chat_done(self, result: str | None) -> None:
        if result is None or not result.startswith("REPROPOSE:"):
            return
        self._redraft(result.removeprefix("REPROPOSE:"))

    def action_drop(self) -> None:
        path = self._current_path()
        if path is None:
            return
        try:
            with exclusive_lock(self._services.paths.lock_path):
                mark_atomic_done(self._services.paths.vault_root, path, [])
        except LockHeldError:
            self._set_status("Vault lock held by another process; try again.")
            return
        self._next()
```

- [ ] **Step 9: Run test to verify it passes**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_atomic_tui.py -v
```

Expected: **3 passed**. Also re-run the triage screen tests to confirm the app.py change broke nothing:

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_tui.py -v
```

Expected: **14 passed**.

- [ ] **Step 10: Lint and typecheck**

```bash
cd /home/alex/code/alex && just lint && uv run mypy
```

Expected: ruff check clean, ruff format --check clean, mypy clean.

- [ ] **Step 11: Commit**

```bash
cd /home/alex/code/alex && git add \
  src/alex/lib/triage/tui/atomic_screen.py \
  src/alex/lib/triage/tui/app.py \
  tests/test_triage_atomic_tui.py && \
git commit -m "feat(triage): add atomic-note drafting screen to the TUI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
### Task 17: Triage CLI command group (`alex triage`)

**Files:**
- Create: `src/alex/commands/triage.py`
- Modify: `src/alex/commands/main.py` (import block, after line 18 `from alex.commands.transcribe import transcribe`; registration block, after line 33 `main.add_command(transcribe)`)
- Test: `tests/test_triage_command.py`

**Interfaces:**

Consumes (all exist after Tasks 1-16):
- `alex.lib.llm`: `Completer` / `Embedder` protocols, `LiteLlmCompleter`, `LiteLlmEmbedder`, `resolve_embedding_model() -> str`, `resolve_triage_label_model() -> str`, `resolve_triage_proposal_model() -> str`, `resolve_triage_atomic_model() -> str`, `resolve_triage_distill_model() -> str`, `resolve_triage_cluster_threshold() -> float`, `resolve_triage_batch_size() -> int`
- `alex.lib.locking`: `LockHeldError`, `exclusive_lock(lock_path: Path) -> Iterator[None]`
- `alex.lib.asset_folders`: `OBSIDIAN_ROOT_ENV`, `path_from_env(name: str) -> Path | None`
- `alex.lib.triage.paths.TriagePaths` (frozen dataclass, `vault_root: Path`, properties per contract)
- `alex.lib.triage.storage`: `read_yaml_model[T](path, model_type) -> T | None`, `write_yaml_model(path, model) -> None`
- `alex.lib.triage.models`: `Inventory`, `ClusterMap`, `ApplyReport`
- `alex.lib.triage.inventory`: `build_inventory(vault_root, previous) -> Inventory`, `discover_population_files(vault_root) -> list[tuple[Population, Path]]`, `is_eligible(fm: dict[str, Any]) -> bool`
- `alex.lib.triage.clustering.build_cluster_map(inventory, embedder, completer, *, embed_model, label_model, threshold, batch_size, cache_path, generated) -> ClusterMap`
- `alex.lib.triage.catalog.build_catalog(vault_root) -> Catalog`
- `alex.lib.triage.frontmatter`: `read_frontmatter(text) -> dict[str, Any]`, `read_triage_block(text) -> TriageBlock | None`
- `alex.lib.triage.ledger`: `read_events(ledger_path, *, since_version=None) -> list[LedgerEvent]`, `append_event(ledger_path, event) -> None` (tests only)
- `alex.lib.triage.rubric`: `load_rubric(path) -> Rubric`, `save_rubric(path, rubric) -> None`
- `alex.lib.triage.distill.distill_rubric(rubric, events, completer, model) -> Rubric`
- `alex.lib.triage.apply`: `build_apply_plan(vault_root) -> ApplyPlan`, `execute_apply_plan(plan, vault_root, *, write) -> ApplyReport`, `format_apply_plan(plan) -> str`
- `alex.lib.triage.tui.app.TriageApp(services, inventory, cluster_map, *, mode="triage")`
- `alex.lib.triage.tui.services.TriageServices` (frozen dataclass per contract)

Produces (Task 18 relies on these):
- `build_triage_group(*, completer_factory: Callable[[], Completer] = LiteLlmCompleter, embedder_factory: Callable[[], Embedder] = LiteLlmEmbedder, app_runner: Callable[[TriageApp], None] | None = None) -> click.Group` in `src/alex/commands/triage.py`
- module attribute `triage = build_triage_group()` registered on `main`
- Subcommands: `inventory`, `cluster`, `catalog`, `review` (`--mode triage|atomic`), `distill`, `apply` (`--write`), `status`; every subcommand takes `--vault-root`
- Vault root resolution: flag > `OBSIDIAN_ROOT` env > `click.UsageError("Provide --vault-root or set OBSIDIAN_ROOT")`; non-directory raises `click.UsageError(f"Vault root is not a directory: {resolved}")`
- Lock-held skip message (exact): `"Another triage run is in progress; skipping."`

Design note (binding for this task): `cluster`, `distill`, and `apply` run their whole body under `exclusive_lock(paths.lock_path)`. `review` holds the lock only while reading `inventory.yaml` / `cluster-map.yaml` and releases it before launching the TUI, because the TUI's batch confirm acquires the same lock file and flock treats a second fd in the same process as a conflict (see the `locking.py` docstring). Holding the lock across `app.run()` would make every confirm fail with `LockHeldError`.

- [ ] **Step 1: Write the failing tests, part 1 (fakes, fixture helpers, vault-root resolution, help text)**

Create `tests/test_triage_command.py`:

```python
"""CLI wiring tests for the alex triage command group."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from click.testing import CliRunner

from alex.commands.main import main
from alex.commands.triage import build_triage_group
from alex.lib.locking import exclusive_lock
from alex.lib.triage.ledger import append_event
from alex.lib.triage.models import (
    Batch,
    Cluster,
    ClusterMap,
    Inventory,
    LedgerEvent,
    NoteEvidence,
)
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.rubric import load_rubric
from alex.lib.triage.storage import write_yaml_model
from alex.lib.triage.tui.app import TriageApp
from helpers import BagOfWordsEmbedder

SUBCOMMANDS = (
    "inventory",
    "cluster",
    "catalog",
    "review",
    "distill",
    "apply",
    "status",
)


@dataclass
class ScriptedCompleter:
    response: str = "misc"
    calls: list[str] = field(default_factory=list)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append(prompt)
        return self.response


def make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def write_note(vault: Path, name: str, text: str) -> Path:
    note = vault / name
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(text, encoding="utf-8")
    return note


def write_pipeline_state(vault: Path) -> TriagePaths:
    paths = TriagePaths(vault_root=vault)
    note = NoteEvidence(
        path="Kube upgrade plan.md",
        title="Kube upgrade plan",
        population="root",
    )
    write_yaml_model(
        paths.inventory_path,
        Inventory(generated="2026-07-12T00:00:00", notes=[note]),
    )
    write_yaml_model(
        paths.cluster_map_path,
        ClusterMap(
            generated="2026-07-12T00:00:00",
            clusters=[Cluster(cluster_id=0, label="misc", note_paths=[note.path])],
            batches=[Batch(batch_id=1, note_paths=[note.path])],
        ),
    )
    return paths


def write_decided_note(vault: Path) -> Path:
    write_note(
        vault,
        "areas/testing/index.md",
        "---\ntype: area\ndescription: Software testing practice.\n---\n# Testing\n",
    )
    return write_note(
        vault,
        "Kube upgrade plan.md",
        "---\n"
        "type: note\n"
        "triage:\n"
        "  decision: area\n"
        "  target: testing\n"
        "  status: decided\n"
        "  decided: 2026-07-01\n"
        "---\n"
        "Upgrade the cluster.\n",
    )


def test_missing_vault_root_and_env_raises_usage_error() -> None:
    result = CliRunner().invoke(
        build_triage_group(),
        ["status"],
        env={"OBSIDIAN_ROOT": None},
    )

    assert result.exit_code == 2
    assert "Provide --vault-root or set OBSIDIAN_ROOT" in result.output


def test_obsidian_root_env_supplies_vault_root(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)

    result = CliRunner().invoke(
        build_triage_group(),
        ["status"],
        env={"OBSIDIAN_ROOT": str(vault)},
    )

    assert result.exit_code == 0
    assert "Eligible: 0" in result.output


def test_vault_root_flag_beats_obsidian_root_env(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    missing = tmp_path / "does-not-exist"

    result = CliRunner().invoke(
        build_triage_group(),
        ["status", "--vault-root", str(vault)],
        env={"OBSIDIAN_ROOT": str(missing)},
    )

    assert result.exit_code == 0


def test_vault_root_must_be_an_existing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "nope"

    result = CliRunner().invoke(
        build_triage_group(),
        ["status", "--vault-root", str(missing)],
        env={"OBSIDIAN_ROOT": None},
    )

    assert result.exit_code == 2
    assert "Vault root is not a directory" in result.output


def test_triage_group_help_lists_all_subcommands() -> None:
    result = CliRunner().invoke(build_triage_group(), ["--help"])

    assert result.exit_code == 0
    for name in SUBCOMMANDS:
        assert name in result.output


def test_every_subcommand_help_shows_vault_root_option() -> None:
    for name in SUBCOMMANDS:
        result = CliRunner().invoke(build_triage_group(), [name, "--help"])

        assert result.exit_code == 0, name
        assert "--vault-root" in result.output, name


def test_apply_help_shows_write_flag() -> None:
    result = CliRunner().invoke(build_triage_group(), ["apply", "--help"])

    assert result.exit_code == 0
    assert "--write" in result.output


def test_review_help_shows_mode_choices() -> None:
    result = CliRunner().invoke(build_triage_group(), ["review", "--help"])

    assert result.exit_code == 0
    assert "--mode" in result.output
    assert "triage" in result.output
    assert "atomic" in result.output
```

- [ ] **Step 2: Write the failing tests, part 2 (inventory, cluster, catalog, review wiring)**

Append to `tests/test_triage_command.py`:

```python
def test_inventory_scans_eligible_notes_and_writes_cache(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    write_note(vault, "Loose thought.md", "A loose thought about gardens.\n")
    write_note(vault, "Done already.md", "---\nprocessed: true\n---\nDone.\n")

    result = CliRunner().invoke(
        build_triage_group(), ["inventory", "--vault-root", str(vault)]
    )

    assert result.exit_code == 0
    assert "1 eligible" in result.output
    assert TriagePaths(vault_root=vault).inventory_path.exists()


def test_cluster_builds_cluster_map_from_inventory(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    write_note(vault, "Kube one.md", "kubernetes cluster upgrade plan for staging.\n")
    write_note(vault, "Kube two.md", "kubernetes cluster upgrade retro for staging.\n")
    inventory_result = CliRunner().invoke(
        build_triage_group(), ["inventory", "--vault-root", str(vault)]
    )
    assert inventory_result.exit_code == 0
    completer = ScriptedCompleter(response="kubernetes")

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=lambda: completer,
            embedder_factory=BagOfWordsEmbedder,
        ),
        ["cluster", "--vault-root", str(vault)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Clustered 2 notes into 1 clusters, 1 batches." in result.output
    assert TriagePaths(vault_root=vault).cluster_map_path.exists()


def test_cluster_without_inventory_explains_prerequisite(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=ScriptedCompleter,
            embedder_factory=BagOfWordsEmbedder,
        ),
        ["cluster", "--vault-root", str(vault)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "run `alex triage inventory` first" in result.output


def test_catalog_reports_areas_and_resource_topics(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    write_note(
        vault,
        "areas/testing/index.md",
        "---\ntype: area\ndescription: Software testing practice.\n---\n# Testing\n",
    )
    (vault / "resources" / "gardening").mkdir(parents=True)

    result = CliRunner().invoke(
        build_triage_group(), ["catalog", "--vault-root", str(vault)]
    )

    assert result.exit_code == 0
    assert "1 areas" in result.output
    assert "1 resource topics" in result.output
    assert TriagePaths(vault_root=vault).catalog_path.exists()


def test_review_passes_app_to_injected_runner_without_running_tui(
    tmp_path: Path,
) -> None:
    vault = make_vault(tmp_path)
    write_pipeline_state(vault)
    captured: list[TriageApp] = []

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=ScriptedCompleter,
            embedder_factory=BagOfWordsEmbedder,
            app_runner=captured.append,
        ),
        ["review", "--vault-root", str(vault)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(captured) == 1
    assert isinstance(captured[0], TriageApp)


def test_review_atomic_mode_runs_without_cluster_state(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    captured: list[TriageApp] = []

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=ScriptedCompleter,
            embedder_factory=BagOfWordsEmbedder,
            app_runner=captured.append,
        ),
        ["review", "--vault-root", str(vault), "--mode", "atomic"],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(captured) == 1


def test_review_without_inventory_explains_prerequisite(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    captured: list[TriageApp] = []

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=ScriptedCompleter,
            embedder_factory=BagOfWordsEmbedder,
            app_runner=captured.append,
        ),
        ["review", "--vault-root", str(vault)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "run `alex triage inventory` first" in result.output
    assert captured == []


def test_review_rejects_unknown_mode(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=ScriptedCompleter,
            embedder_factory=BagOfWordsEmbedder,
            app_runner=lambda app: None,
        ),
        ["review", "--vault-root", str(vault), "--mode", "bogus"],
    )

    assert result.exit_code == 2
    assert "Invalid value for '--mode'" in result.output
```

- [ ] **Step 3: Write the failing tests, part 3 (lock skip, apply dry-run/write, status, distill)**

Append to `tests/test_triage_command.py`:

```python
def test_lock_held_skips_cleanly_for_locking_subcommands(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    write_pipeline_state(vault)
    group = build_triage_group(
        completer_factory=ScriptedCompleter,
        embedder_factory=BagOfWordsEmbedder,
        app_runner=lambda app: None,
    )
    original_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)  # lock_path derives from Path.home()
    try:
        with exclusive_lock(TriagePaths(vault_root=vault).lock_path):
            args_list = (["cluster"], ["review"], ["distill"], ["apply", "--write"])
            for args in args_list:
                result = CliRunner().invoke(
                    group,
                    [*args, "--vault-root", str(vault)],
                    env={"HOME": str(tmp_path)},
                )

                assert result.exit_code == 0, args
                assert (
                    "Another triage run is in progress; skipping." in result.output
                )
    finally:
        if original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = original_home


def test_apply_dry_run_prints_plan_without_moving(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    note = write_decided_note(vault)

    result = CliRunner().invoke(
        build_triage_group(),
        ["apply", "--vault-root", str(vault)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Kube upgrade plan" in result.output
    assert "areas/testing" in result.output
    assert note.exists()


def test_apply_write_moves_note_and_marks_applied(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    note = write_decided_note(vault)

    result = CliRunner().invoke(
        build_triage_group(),
        ["apply", "--vault-root", str(vault), "--write"],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    moved = vault / "areas" / "testing" / "Kube upgrade plan.md"
    assert moved.exists()
    assert not note.exists()
    assert "status: applied" in moved.read_text(encoding="utf-8")
    assert "Moved Kube upgrade plan.md -> areas/testing/Kube upgrade plan.md" in (
        result.output
    )
    assert "Done: 1 moved, 0 failed." in result.output
    log = vault / "_meta" / "processing-log.md"
    assert "triage: moved" in log.read_text(encoding="utf-8")


def test_status_reports_progress_counts(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    write_note(vault, "Fresh idea.md", "An unfiled idea.\n")
    write_note(
        vault,
        "Decided note.md",
        "---\ntriage:\n  decision: area\n  target: testing\n"
        "  status: decided\n  decided: 2026-07-01\n---\nBody.\n",
    )
    write_note(
        vault,
        "Applied note.md",
        "---\ntriage:\n  decision: archive\n  target: notes\n"
        "  status: applied\n  decided: 2026-06-20\n  applied: 2026-06-27\n---\nBody.\n",
    )
    write_note(
        vault,
        "Promising idea.md",
        "---\ntriage:\n  promising: true\n---\nWorth an atomic note.\n",
    )

    result = CliRunner().invoke(
        build_triage_group(), ["status", "--vault-root", str(vault)]
    )

    assert result.exit_code == 0
    assert "Eligible: 2" in result.output
    assert "Decided: 1" in result.output
    assert "Applied: 1" in result.output
    assert "Promising: 1" in result.output
    assert "Rubric: v1" in result.output
    assert "Batches done: 0/0" in result.output


def test_status_batches_done_ignores_atomic_events(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    paths = write_pipeline_state(vault)
    append_event(
        paths.ledger_path,
        LedgerEvent(
            ts="2026-07-12T09:00:00",
            note="Kube upgrade plan.md",
            batch=1,
            rubric_version=1,
            event="approve",
            proposal={"decision": "area", "target": "testing"},
        ),
    )
    append_event(
        paths.ledger_path,
        LedgerEvent(
            ts="2026-07-12T09:05:00",
            note="Kube upgrade plan.md",
            batch=0,
            rubric_version=1,
            event="atomic_approve",
        ),
    )

    result = CliRunner().invoke(
        build_triage_group(), ["status", "--vault-root", str(vault)]
    )

    assert result.exit_code == 0
    assert "Batches done: 1/1" in result.output


def test_distill_without_events_reports_nothing_to_distill(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=ScriptedCompleter,
            embedder_factory=BagOfWordsEmbedder,
        ),
        ["distill", "--vault-root", str(vault)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "nothing to distill" in result.output
    assert TriagePaths(vault_root=vault).rubric_path.exists()


def test_distill_with_events_bumps_rubric_version(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    paths = TriagePaths(vault_root=vault)
    append_event(
        paths.ledger_path,
        LedgerEvent(
            ts="2026-07-12T09:00:00",
            note="Kube upgrade plan.md",
            batch=1,
            rubric_version=1,
            event="reject",
            proposal={"decision": "area", "target": "testing"},
            reason="wrong area",
        ),
    )
    new_text = (
        "## Triage rules\n\n1. Meetings are weak area evidence.\n\n"
        "## Atomic note rules\n\n1. One claim per note.\n"
    )

    result = CliRunner().invoke(
        build_triage_group(
            completer_factory=lambda: ScriptedCompleter(response=new_text),
            embedder_factory=BagOfWordsEmbedder,
        ),
        ["distill", "--vault-root", str(vault)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "Rubric distilled: v1 -> v2." in result.output
    assert load_rubric(paths.rubric_path).version == 2
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_command.py -v
```

Expected failure mode: collection error, `ModuleNotFoundError: No module named 'alex.commands.triage'` (the test module imports `build_triage_group` at the top).

- [ ] **Step 5: Write the implementation**

Create `src/alex/commands/triage.py` in full:

```python
"""Click command group for the vault triage pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import click

from alex.lib.asset_folders import OBSIDIAN_ROOT_ENV, path_from_env
from alex.lib.llm import (
    Completer,
    Embedder,
    LiteLlmCompleter,
    LiteLlmEmbedder,
    resolve_embedding_model,
    resolve_triage_atomic_model,
    resolve_triage_batch_size,
    resolve_triage_cluster_threshold,
    resolve_triage_distill_model,
    resolve_triage_label_model,
    resolve_triage_proposal_model,
)
from alex.lib.locking import LockHeldError, exclusive_lock
from alex.lib.triage.apply import (
    build_apply_plan,
    execute_apply_plan,
    format_apply_plan,
)
from alex.lib.triage.catalog import build_catalog
from alex.lib.triage.clustering import build_cluster_map
from alex.lib.triage.distill import distill_rubric
from alex.lib.triage.frontmatter import read_frontmatter, read_triage_block
from alex.lib.triage.inventory import (
    build_inventory,
    discover_population_files,
    is_eligible,
)
from alex.lib.triage.ledger import read_events
from alex.lib.triage.models import ApplyReport, ClusterMap, Inventory
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.rubric import load_rubric, save_rubric
from alex.lib.triage.storage import read_yaml_model, write_yaml_model
from alex.lib.triage.tui.app import TriageApp
from alex.lib.triage.tui.services import TriageServices

_LOCK_HELD_MESSAGE = "Another triage run is in progress; skipping."


def _run_app(app: TriageApp) -> None:
    app.run()


def _resolve_vault_root(vault_root: Path | None) -> Path:
    resolved = vault_root or path_from_env(OBSIDIAN_ROOT_ENV)
    if resolved is None:
        raise click.UsageError("Provide --vault-root or set OBSIDIAN_ROOT")
    if not resolved.is_dir():
        raise click.UsageError(f"Vault root is not a directory: {resolved}")
    return resolved


def _vault_root_option(command: Callable[..., None]) -> Callable[..., None]:
    return click.option(
        "--vault-root",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        show_default="$OBSIDIAN_ROOT",
        help="Vault root containing the notes to triage.",
    )(command)


@dataclass(frozen=True)
class _TriageStatus:
    eligible: int
    decided: int
    applied: int
    promising: int
    rubric_version: int
    batches_done: int
    batches_total: int


def _collect_status(paths: TriagePaths) -> _TriageStatus:
    eligible = decided = applied = promising = 0
    for _population, md_path in discover_population_files(paths.vault_root):
        text = md_path.read_text(encoding="utf-8")
        if is_eligible(read_frontmatter(text)):
            eligible += 1
        block = read_triage_block(text)
        if block is None:
            continue
        if block.status == "decided":
            decided += 1
        elif block.status == "applied":
            applied += 1
        if block.promising:
            promising += 1
    rubric_version = (
        load_rubric(paths.rubric_path).version if paths.rubric_path.exists() else 1
    )
    cluster_map = read_yaml_model(paths.cluster_map_path, ClusterMap)
    batches_total = len(cluster_map.batches) if cluster_map is not None else 0
    # Atomic-mode events log batch=0; only real triage batches count as done.
    events = read_events(paths.ledger_path)
    batches_done = len({event.batch for event in events if event.batch > 0})
    return _TriageStatus(
        eligible=eligible,
        decided=decided,
        applied=applied,
        promising=promising,
        rubric_version=rubric_version,
        batches_done=batches_done,
        batches_total=batches_total,
    )


def _echo_apply_report(report: ApplyReport) -> None:
    for slug in report.areas_created:
        click.echo(f"Created area {slug}")
    moved = 0
    failed = 0
    for result in report.results:
        if result.status == "failed":
            failed += 1
            click.echo(f"FAILED {result.note_path}: {result.error}")
            continue
        moved += 1
        renamed = " (renamed)" if result.status == "collision_renamed" else ""
        click.echo(
            f"Moved {result.note_path} -> {result.destination}{renamed}"
            f" ({result.links_rewritten} links updated)"
        )
    click.echo(f"Done: {moved} moved, {failed} failed.")


def build_triage_group(
    *,
    completer_factory: Callable[[], Completer] = LiteLlmCompleter,
    embedder_factory: Callable[[], Embedder] = LiteLlmEmbedder,
    app_runner: Callable[[TriageApp], None] | None = None,
) -> click.Group:
    runner = app_runner or _run_app

    @click.group("triage")
    def group() -> None:
        """Triage vault notes into their PARA homes."""

    @group.command("inventory")
    @_vault_root_option
    def inventory_command(vault_root: Path | None) -> None:
        """Scan eligible notes and refresh the inventory cache."""
        root = _resolve_vault_root(vault_root)
        paths = TriagePaths(vault_root=root)
        try:
            previous = read_yaml_model(paths.inventory_path, Inventory)
            inventory = build_inventory(root, previous)
            write_yaml_model(paths.inventory_path, inventory)
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(
            f"Inventory: {len(inventory.notes)} eligible notes"
            f" -> {paths.inventory_path}"
        )

    @group.command("cluster")
    @_vault_root_option
    def cluster_command(vault_root: Path | None) -> None:
        """Embed, cluster, and batch the inventoried notes."""
        root = _resolve_vault_root(vault_root)
        paths = TriagePaths(vault_root=root)
        inventory = read_yaml_model(paths.inventory_path, Inventory)
        if inventory is None:
            raise click.ClickException(
                "No inventory found; run `alex triage inventory` first."
            )
        try:
            # LockHeldError must be caught before RuntimeError (it is one).
            with exclusive_lock(paths.lock_path):
                cluster_map = build_cluster_map(
                    inventory,
                    embedder_factory(),
                    completer_factory(),
                    embed_model=resolve_embedding_model(),
                    label_model=resolve_triage_label_model(),
                    threshold=resolve_triage_cluster_threshold(),
                    batch_size=resolve_triage_batch_size(),
                    cache_path=paths.embeddings_cache_path,
                    generated=datetime.now().isoformat(timespec="seconds"),
                )
                write_yaml_model(paths.cluster_map_path, cluster_map)
        except LockHeldError:
            click.echo(_LOCK_HELD_MESSAGE)
            return
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(
            f"Clustered {len(inventory.notes)} notes into"
            f" {len(cluster_map.clusters)} clusters,"
            f" {len(cluster_map.batches)} batches."
        )

    @group.command("catalog")
    @_vault_root_option
    def catalog_command(vault_root: Path | None) -> None:
        """Rebuild the area catalog cache from areas/*/index.md."""
        root = _resolve_vault_root(vault_root)
        paths = TriagePaths(vault_root=root)
        try:
            catalog = build_catalog(root)
            write_yaml_model(paths.catalog_path, catalog)
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(
            f"Catalog: {len(catalog.areas)} areas,"
            f" {len(catalog.resource_topics)} resource topics."
        )

    @group.command("review")
    @_vault_root_option
    @click.option(
        "--mode",
        type=click.Choice(["triage", "atomic"]),
        default="triage",
        show_default=True,
        help="Review filing proposals (triage) or draft atomic notes (atomic).",
    )
    def review_command(vault_root: Path | None, mode: str) -> None:
        """Open the keyboard-first review TUI."""
        root = _resolve_vault_root(vault_root)
        paths = TriagePaths(vault_root=root)
        try:
            # Hold the lock only while reading pipeline state.  The TUI takes
            # the same lock file on every batch confirm, and flock treats a
            # second fd in this process as a conflict, so holding it across
            # the whole app run would break confirm.
            with exclusive_lock(paths.lock_path):
                inventory = read_yaml_model(paths.inventory_path, Inventory)
                cluster_map = read_yaml_model(paths.cluster_map_path, ClusterMap)
        except LockHeldError:
            click.echo(_LOCK_HELD_MESSAGE)
            return
        if mode == "triage":
            if inventory is None:
                raise click.ClickException(
                    "No inventory found; run `alex triage inventory` first."
                )
            if cluster_map is None:
                raise click.ClickException(
                    "No cluster map found; run `alex triage cluster` first."
                )
        if inventory is None:
            inventory = Inventory(generated="", notes=[])
        if cluster_map is None:
            cluster_map = ClusterMap(generated="", clusters=[], batches=[])
        services = TriageServices(
            paths=paths,
            completer=completer_factory(),
            embedder=embedder_factory(),
            proposal_model=resolve_triage_proposal_model(),
            atomic_model=resolve_triage_atomic_model(),
            distill_model=resolve_triage_distill_model(),
            today=date.today().isoformat(),
        )
        app = TriageApp(services, inventory, cluster_map, mode=mode)
        runner(app)

    @group.command("distill")
    @_vault_root_option
    def distill_command(vault_root: Path | None) -> None:
        """Distill ledger corrections into the next rubric version."""
        root = _resolve_vault_root(vault_root)
        paths = TriagePaths(vault_root=root)
        try:
            # LockHeldError must be caught before RuntimeError (it is one).
            with exclusive_lock(paths.lock_path):
                rubric = load_rubric(paths.rubric_path)
                events = read_events(
                    paths.ledger_path, since_version=rubric.version
                )
                if not events:
                    click.echo(
                        f"No ledger events since rubric v{rubric.version};"
                        " nothing to distill."
                    )
                    return
                new_rubric = distill_rubric(
                    rubric,
                    events,
                    completer_factory(),
                    resolve_triage_distill_model(),
                )
                if new_rubric.version == rubric.version:
                    click.echo(
                        "Distillation failed; rubric unchanged"
                        f" (v{rubric.version})."
                    )
                    return
                save_rubric(paths.rubric_path, new_rubric)
        except LockHeldError:
            click.echo(_LOCK_HELD_MESSAGE)
            return
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Rubric distilled: v{rubric.version} -> v{new_rubric.version}.")

    @group.command("apply")
    @_vault_root_option
    @click.option(
        "--write",
        is_flag=True,
        help="Execute the move plan instead of printing it.",
    )
    def apply_command(vault_root: Path | None, write: bool) -> None:
        """Print the move plan for decided notes; execute with --write."""
        root = _resolve_vault_root(vault_root)
        paths = TriagePaths(vault_root=root)
        try:
            # LockHeldError must be caught before RuntimeError (it is one).
            with exclusive_lock(paths.lock_path):
                plan = build_apply_plan(root)
                if not write:
                    click.echo(format_apply_plan(plan))
                    return
                report = execute_apply_plan(plan, root, write=True)
        except LockHeldError:
            click.echo(_LOCK_HELD_MESSAGE)
            return
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        for reason in plan.skipped:
            click.echo(f"Skipped: {reason}")
        _echo_apply_report(report)

    @group.command("status")
    @_vault_root_option
    def status_command(vault_root: Path | None) -> None:
        """Print triage progress counts."""
        root = _resolve_vault_root(vault_root)
        paths = TriagePaths(vault_root=root)
        try:
            status = _collect_status(paths)
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Eligible: {status.eligible}")
        click.echo(f"Decided: {status.decided}")
        click.echo(f"Applied: {status.applied}")
        click.echo(f"Promising: {status.promising}")
        click.echo(f"Rubric: v{status.rubric_version}")
        click.echo(f"Batches done: {status.batches_done}/{status.batches_total}")

    return group


triage = build_triage_group()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_command.py -v
```

Expected: **23 passed**.

- [ ] **Step 7: Write the failing test for main.py registration**

Append to `tests/test_triage_command.py`:

```python
def test_main_group_registers_triage() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "triage" in result.output
```

- [ ] **Step 8: Run the new test to verify it fails**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_command.py::test_main_group_registers_triage -v
```

Expected failure mode: `AssertionError` on `assert "triage" in result.output` (main's help does not list the unregistered group).

- [ ] **Step 9: Register the group in main.py**

In `src/alex/commands/main.py`, change the import block (the `triage` import sorts between `transcribe` and `version`):

```python
from alex.commands.transcribe import transcribe
from alex.commands.triage import triage
from alex.commands.version import version
```

and add the registration directly after `main.add_command(transcribe)`:

```python
main.add_command(transcribe)
main.add_command(triage)
```

- [ ] **Step 10: Run the full command test file to verify all pass**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_command.py -v
```

Expected: **24 passed**.

- [ ] **Step 11: Run lint and typecheck expecting clean**

```bash
cd /home/alex/code/alex && just lint && uv run mypy
```

Expected: ruff reports no violations, `ruff format --check` reports all files already formatted, mypy reports `Success: no issues found`. If `ruff format --check` flags a file, run `just fmt` and re-run.

- [ ] **Step 12: Commit**

```bash
cd /home/alex/code/alex && git add src/alex/commands/triage.py src/alex/commands/main.py tests/test_triage_command.py && git commit -m "feat(triage): add alex triage command group with vault-root resolution and locking

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 18: End-to-end pipeline test, README docs, final check

**Files:**
- Test: `tests/test_triage_e2e.py` (create)
- Modify: `README.md` (insert a `### triage` section immediately before the `### eval-summary` heading, currently line 135)

**Interfaces:**

Consumes:
- `alex.commands.triage.build_triage_group(...)` (Task 17)
- `alex.lib.triage.tui.app.TriageApp(services, inventory, cluster_map, *, mode="triage")` and Textual's `app.run_test()` pilot (Task 15; `asyncio_mode = "auto"` already set in pyproject by Task 15)
- `alex.lib.triage.tui.services.TriageServices` (Task 15)
- `alex.lib.triage.proposals`: `generate_batch_proposals(batch, inventory, *, catalog, rubric, completer, model, corrections=(), max_workers=4) -> BatchProposals`, `write_batch_proposals(paths, proposals) -> None`
- `alex.lib.triage.catalog.load_or_build_catalog(paths) -> Catalog`
- `alex.lib.triage.rubric.load_rubric(path) -> Rubric`
- `alex.lib.triage.ledger.read_events(ledger_path, *, since_version=None) -> list[LedgerEvent]`
- `alex.lib.triage.storage.read_yaml_model`, `alex.lib.triage.paths.TriagePaths`, models `Inventory` / `ClusterMap`
- `alex.lib.vault_links.WIKI_LINK_PATTERN` (Task 11; single source of truth for wiki-link syntax in the link audit)
- `helpers.BagOfWordsEmbedder`

Produces: no new public names (integration test plus docs).

Fixture design notes (why the assertions are deterministic):
- Note bodies are engineered for `BagOfWordsEmbedder` word overlap: 4 kube notes cluster together, 2 garden notes cluster together, the clipping and the meeting are singletons ("misc"). The contract's cluster ordering (size desc, then first path; misc pooled last) fixes batch 1's note order exactly.
- The fake completer sniffs prompt kind by contract-fixed markers: proposal prompts embed the catalog (`catalog_prompt_text` always emits a `## Areas` heading), the distill prompt embeds the rubric but no catalog (`## Triage rules` from the rubric body), and label prompts carry only titles.
- The contract's e2e line asks for "a path-style link to another root note", but a root note's vault-relative path contains no `/`, so a path-style wiki link to it cannot exist (and per `vault_links`, bare-name links survive moves untouched). The testable intent, a path-style link rewritten by apply, is covered by `Kube upgrade 2.md` linking path-style to `[[Clippings/Saved article.md]]`, which is rewritten when the clipping archives; the bare `[[Kube upgrade 3]]` link is asserted to survive unchanged.
- The pilot edits Kube upgrade 4's target to `writing` (an existing catalog area, all-lowercase letters so `pilot.press(*"writing")` needs no named keys). Whether TargetPicker's Enter submits the Input free text or the filtered OptionList row, the result is the same string.
- `HOME` is pointed at `tmp_path` for the whole test so `TriagePaths.lock_path` never touches the real home directory (the TUI confirm and the CLI subcommands both flock it).
- The meeting note exercises the annotate-only path end to end: confirm writes `status: applied` (plus `applied:` date) directly per Task 15's `_write_decision` population branch, and apply must leave the file in `Meetings/`. The e2e asserts both, so a regression to `status: decided` (stuck forever, since apply never moves meetings) fails loudly.
- `assert_all_wiki_links_resolve` is the spec's link audit: after apply it walks every `.md` in the vault, parses each wiki link with `WIKI_LINK_PATTERN`, resolves path-style targets as vault-relative files and bare names by note stem, and fails listing every unresolved link. It subsumes the two spot-checks (which stay, because they pin the exact rewrite output, not just resolvability).

- [ ] **Step 1: Write the e2e test, part 1 (scripted completer and fixture vault)**

Create `tests/test_triage_e2e.py`:

```python
"""End-to-end triage pipeline: inventory -> cluster -> review TUI -> apply."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from click.testing import CliRunner

from alex.commands.triage import build_triage_group
from alex.lib.triage.catalog import load_or_build_catalog
from alex.lib.triage.ledger import read_events
from alex.lib.triage.models import ClusterMap, Inventory
from alex.lib.triage.paths import TriagePaths
from alex.lib.triage.proposals import generate_batch_proposals, write_batch_proposals
from alex.lib.triage.rubric import load_rubric
from alex.lib.triage.storage import read_yaml_model
from alex.lib.triage.tui.app import TriageApp
from alex.lib.triage.tui.services import TriageServices
from alex.lib.vault_links import WIKI_LINK_PATTERN
from helpers import BagOfWordsEmbedder

NEW_RUBRIC_TEXT = (
    "## Triage rules\n"
    "\n"
    "1. Kubernetes operations notes belong in platform-engineering.\n"
    "2. Prefer archive over force-fit when nothing matches confidently.\n"
    "\n"
    "## Atomic note rules\n"
    "\n"
    "1. One claim per note, stated in the title.\n"
)

PROCESSED_TEXT = (
    "---\n"
    "processed: true\n"
    "---\n"
    "# Old processed capture\n"
    "\n"
    "Already went through the old pipeline; triage must not touch it.\n"
)

EXPECTED_BATCH_ORDER = [
    "Kube upgrade 1.md",
    "Kube upgrade 2.md",
    "Kube upgrade 3.md",
    "Kube upgrade 4.md",
    "Garden soil notes.md",
    "Garden tomato plan.md",
    "Clippings/Saved article.md",
    "Meetings/Team sync.md",
]


def _proposal(decision: str, target: str, why: str) -> dict[str, object]:
    return {
        "decision": decision,
        "target": target,
        "confidence": "high",
        "why": why,
        "alternatives": [],
        "new_area": None,
    }


PROPOSAL_RESPONSES: list[tuple[str, dict[str, object]]] = [
    ("Kube upgrade 1", _proposal("area", "platform-engineering", "K8s ops.")),
    ("Kube upgrade 2", _proposal("area", "platform-engineering", "K8s ops.")),
    ("Kube upgrade 3", _proposal("area", "platform-engineering", "K8s ops.")),
    ("Kube upgrade 4", _proposal("area", "platform-engineering", "K8s ops.")),
    ("Garden soil", _proposal("resource", "gardening", "Reference material.")),
    ("Garden tomato", _proposal("resource", "gardening", "Reference material.")),
    ("Saved article", _proposal("archive", "clippings", "Read clipping.")),
    ("Team sync", _proposal("area", "platform-engineering", "Upgrade talk.")),
]


@dataclass
class PipelineCompleter:
    """Scripted fake covering label, proposal, and distill prompts.

    Prompt kinds are sniffed by contract-fixed markers: proposal prompts
    embed the catalog ("## Areas"), the distill prompt embeds the rubric
    without the catalog ("## Triage rules"), label prompts carry only
    note titles.
    """

    calls: list[str] = field(default_factory=list)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append(prompt)
        if "## Areas" in prompt:
            for marker, payload in PROPOSAL_RESPONSES:
                if marker in prompt:
                    return json.dumps(payload)
            raise AssertionError(f"unscripted proposal prompt: {prompt[:120]}")
        if "## Triage rules" in prompt:
            return NEW_RUBRIC_TEXT
        if "Kube upgrade" in prompt:
            return "kubernetes"
        if "Garden" in prompt:
            return "gardening"
        raise AssertionError(f"unscripted prompt: {prompt[:120]}")


def build_fixture_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for folder in (
        "areas/platform-engineering",
        "areas/writing",
        "resources/permanent-notes",
        "resources/gardening",
        "Clippings",
        "Meetings",
    ):
        (vault / folder).mkdir(parents=True)
    (vault / "areas" / "platform-engineering" / "index.md").write_text(
        "---\n"
        "type: area\n"
        "created: 2026-06-05\n"
        "description: Running and upgrading production Kubernetes platforms.\n"
        "---\n"
        "# Platform Engineering\n"
        "\n"
        "## Discovery Evidence\n"
        "\n"
        "- Recurring upgrade postmortems in meeting notes\n",
        encoding="utf-8",
    )
    (vault / "areas" / "writing" / "index.md").write_text(
        "---\n"
        "type: area\n"
        "created: 2026-06-05\n"
        "description: Writing practice and prose craft.\n"
        "---\n"
        "# Writing\n",
        encoding="utf-8",
    )
    permanent = vault / "resources" / "permanent-notes"
    (permanent / "index.md").write_text("# Permanent Notes\n", encoding="utf-8")
    (permanent / "Small batches reduce risk.md").write_text(
        "---\n"
        "type: permanent-note\n"
        "created: 2026-05-01\n"
        "---\n"
        "Small batches reduce risk because feedback arrives sooner.\n",
        encoding="utf-8",
    )
    (vault / "resources" / "gardening" / "index.md").write_text(
        "# Gardening\n", encoding="utf-8"
    )
    for number in (1, 3, 4):
        (vault / f"Kube upgrade {number}.md").write_text(
            f"# Kube upgrade {number}\n"
            "\n"
            "kubernetes cluster upgrade control plane node pool rollout"
            " maintenance window.\n",
            encoding="utf-8",
        )
    (vault / "Kube upgrade 2.md").write_text(
        "# Kube upgrade 2\n"
        "\n"
        "kubernetes cluster upgrade control plane node pool rollout"
        " maintenance window.\n"
        "Coordinates with [[Kube upgrade 3]] and the clipped guide at"
        " [[Clippings/Saved article.md]].\n",
        encoding="utf-8",
    )
    (vault / "Garden soil notes.md").write_text(
        "# Garden soil notes\n"
        "\n"
        "garden soil compost mulch watering beds spring planting schedule.\n",
        encoding="utf-8",
    )
    (vault / "Garden tomato plan.md").write_text(
        "# Garden tomato plan\n"
        "\n"
        "garden tomato seedling compost soil watering beds spring planting"
        " schedule.\n",
        encoding="utf-8",
    )
    (vault / "Clippings" / "Saved article.md").write_text(
        "---\n"
        "type: article\n"
        "created: 2026-06-15\n"
        "---\n"
        "# Saved article\n"
        "\n"
        "Espresso brewing basics: grind size, water pressure, extraction"
        " timing.\n",
        encoding="utf-8",
    )
    (vault / "Meetings" / "Team sync.md").write_text(
        "---\n"
        "type: meeting\n"
        "created: 2026-07-01\n"
        "---\n"
        "# Team sync\n"
        "\n"
        "Quarterly planning discussion covering roadmap priorities plus open"
        " action items.\n",
        encoding="utf-8",
    )
    (vault / "Old processed capture.md").write_text(PROCESSED_TEXT, encoding="utf-8")
    return vault


def assert_all_wiki_links_resolve(vault: Path) -> None:
    """Audit every wiki link in the vault and fail on any unresolved target.

    Path-style targets (containing "/") must exist as vault-relative files;
    bare-name targets must match some note's stem, mirroring how Obsidian
    resolves links (see vault_links.py).
    """
    stems = {md.stem for md in vault.rglob("*.md")}
    unresolved: list[str] = []
    for md in vault.rglob("*.md"):
        for match in WIKI_LINK_PATTERN.finditer(md.read_text(encoding="utf-8")):
            target = match.group(2).replace("\\", "/").strip()
            if "/" in target:
                rel = target if target.endswith(".md") else f"{target}.md"
                if not (vault / rel).is_file():
                    unresolved.append(f"{md.relative_to(vault)}: [[{target}]]")
            elif target.removesuffix(".md") not in stems:
                unresolved.append(f"{md.relative_to(vault)}: [[{target}]]")
    assert unresolved == [], unresolved
```

- [ ] **Step 2: Write the e2e test, part 2 (the pipeline test)**

Append to `tests/test_triage_e2e.py`:

```python
async def test_triage_pipeline_end_to_end(tmp_path: Path) -> None:
    vault = build_fixture_vault(tmp_path)
    paths = TriagePaths(vault_root=vault)
    completer = PipelineCompleter()
    embedder = BagOfWordsEmbedder()
    group = build_triage_group(
        completer_factory=lambda: completer,
        embedder_factory=lambda: embedder,
    )
    original_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)  # keep the flock out of the real home
    try:
        cli = CliRunner()
        result = cli.invoke(group, ["inventory", "--vault-root", str(vault)])
        assert result.exit_code == 0, result.output
        assert "8 eligible notes" in result.output

        result = cli.invoke(group, ["cluster", "--vault-root", str(vault)])
        assert result.exit_code == 0, result.output

        inventory = read_yaml_model(paths.inventory_path, Inventory)
        cluster_map = read_yaml_model(paths.cluster_map_path, ClusterMap)
        assert inventory is not None
        assert cluster_map is not None
        batch = cluster_map.batches[0]
        assert batch.note_paths == EXPECTED_BATCH_ORDER

        catalog = load_or_build_catalog(paths)
        rubric = load_rubric(paths.rubric_path)
        assert rubric.version == 1
        proposals = generate_batch_proposals(
            batch,
            inventory,
            catalog=catalog,
            rubric=rubric,
            completer=completer,
            model="test/proposal-model",
            max_workers=1,
        )
        by_note = {p.note_path: p for p in proposals.proposals}
        assert by_note["Kube upgrade 4.md"].target == "platform-engineering"
        assert by_note["Clippings/Saved article.md"].decision == "archive"
        assert not any(p.needs_manual for p in proposals.proposals)
        write_batch_proposals(paths, proposals)
        assert paths.proposals_path(batch.batch_id, rubric.version).exists()

        services = TriageServices(
            paths=paths,
            completer=completer,
            embedder=embedder,
            proposal_model="test/proposal-model",
            atomic_model="test/atomic-model",
            distill_model="test/distill-model",
            max_workers=1,
            today="2026-07-12",
        )
        app = TriageApp(services, inventory, cluster_map, mode="triage")
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.press("p", "a")  # Kube 1: flag promising, approve
            await pilot.press("a", "a")  # Kube 2 and Kube 3: approve
            await pilot.press("e")  # Kube 4: edit target
            await pilot.pause()
            await pilot.press(*"writing")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("a", "a")  # garden notes: approve
            await pilot.press("a")  # clipping: approve archive
            await pilot.press("a")  # meeting: approve (annotate-only)
            await pilot.press("b")  # batch summary
            await pilot.pause()
            await pilot.press("enter")  # confirm the batch
            await pilot.pause()
            await app.workers.wait_for_complete()  # background rubric distill

        decided = (vault / "Kube upgrade 1.md").read_text(encoding="utf-8")
        assert "decision: area" in decided
        assert "target: platform-engineering" in decided
        assert "promising: true" in decided
        assert "status: decided" in decided

        result = cli.invoke(group, ["apply", "--vault-root", str(vault), "--write"])
        assert result.exit_code == 0, result.output

        platform = vault / "areas" / "platform-engineering"
        assert (platform / "Kube upgrade 1.md").exists()
        assert (platform / "Kube upgrade 2.md").exists()
        assert (platform / "Kube upgrade 3.md").exists()
        assert (vault / "areas" / "writing" / "Kube upgrade 4.md").exists()
        assert (vault / "resources" / "gardening" / "Garden soil notes.md").exists()
        assert (vault / "resources" / "gardening" / "Garden tomato plan.md").exists()
        assert (vault / "archives" / "clippings" / "Saved article.md").exists()
        assert not (vault / "Kube upgrade 1.md").exists()

        kube_one = (platform / "Kube upgrade 1.md").read_text(encoding="utf-8")
        assert "promising: true" in kube_one  # survives the move for atomic mode
        kube_two = (platform / "Kube upgrade 2.md").read_text(encoding="utf-8")
        assert "[[archives/clippings/Saved article.md]]" in kube_two
        assert "[[Kube upgrade 3]]" in kube_two  # bare-name links survive moves
        assert "status: applied" in kube_two
        kube_four = (vault / "areas" / "writing" / "Kube upgrade 4.md").read_text(
            encoding="utf-8"
        )
        assert "target: writing" in kube_four
        assert "status: applied" in kube_four

        # Annotate-only population: the meeting is annotated in place, goes
        # straight to applied at confirm, and is never moved by apply.
        meeting_path = vault / "Meetings" / "Team sync.md"
        assert meeting_path.exists()
        assert not (platform / "Team sync.md").exists()
        meeting = meeting_path.read_text(encoding="utf-8")
        assert "decision: area" in meeting
        assert "status: applied" in meeting
        assert "applied: 2026-07-12" in meeting
        assert "Quarterly planning discussion" in meeting

        processed = vault / "Old processed capture.md"
        assert processed.read_text(encoding="utf-8") == PROCESSED_TEXT

        assert_all_wiki_links_resolve(vault)  # zero broken links after apply

        events = read_events(paths.ledger_path)
        assert len(events) == 8
        assert sum(1 for event in events if event.event == "approve") == 7
        edits = [event for event in events if event.event == "edit"]
        assert [event.note for event in edits] == ["Kube upgrade 4.md"]

        assert load_rubric(paths.rubric_path).version == 2

        log_text = (vault / "_meta" / "processing-log.md").read_text(encoding="utf-8")
        assert "triage: moved" in log_text
    finally:
        if original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = original_home
```

- [ ] **Step 3: Run the e2e test, expecting it to pass**

```bash
cd /home/alex/code/alex && uv run pytest tests/test_triage_e2e.py -v
```

Expected: **1 passed**. This is an integration test over Tasks 1-17; there is no new implementation step. If it fails, the failing assertion localizes the bug: a wrong `EXPECTED_BATCH_ORDER` points at clustering/batching (Task 6), a missing rewrite of `[[Clippings/Saved article.md]]` or an `assert_all_wiki_links_resolve` failure (it lists every unresolved link) points at `vault_links`/apply (Tasks 11-12), a meeting note stuck at `status: decided` points at the `_write_decision` population branch (Task 15), an unbumped rubric points at the confirm-time distill worker (Task 15), and a hung pilot points at the TargetPicker or summary-confirm bindings (Task 15). Fix the owning module, not the test; the test encodes the contract.

- [ ] **Step 4: Add the README triage section**

In `README.md`, insert the following block immediately before the `### eval-summary` heading (use an exact-match edit: replace the line `### eval-summary` with the new section followed by `### eval-summary`):

````markdown
### triage

```bash
alex triage inventory --vault-root ~/Documents/Alex3
alex triage cluster        # embed, cluster, slice into batches
alex triage catalog        # rebuild the area catalog cache
alex triage review         # keyboard-first Textual review TUI
alex triage review --mode atomic   # draft atomic notes from promising ones
alex triage distill        # ledger corrections -> rubric vN+1
alex triage apply          # print the move plan (dry run)
alex triage apply --write  # move notes + rewrite wiki links
alex triage status         # progress counts
```

Drains the Obsidian vault's loose-note backlog: scan eligible notes
(`inventory`), batch them by topic (`cluster`), review LLM filing proposals
batch by batch in a TUI (`review`), then move approved notes into their PARA
homes with wiki-link rewriting (`apply`). Decisions are recorded as `triage:`
frontmatter first; `apply` is a separate idempotent step that prints a
dry-run plan unless `--write` is passed. Review corrections append to
`projects/vault-triage/ledger.jsonl` and are distilled into a versioned
rubric (`projects/vault-triage/rubric.md`) injected into every proposal
prompt. Pipeline caches live under `.claude/triage/` inside the vault.

Vault root resolution: `--vault-root` flag, else `$OBSIDIAN_ROOT`, else an
error. Model roles follow the usual env-override pattern:

| Role | Env var | Default |
| --- | --- | --- |
| Cluster labels | `ALEX_TRIAGE_LABEL_MODEL` | `anthropic/claude-haiku-4-5` |
| Filing proposals | `ALEX_TRIAGE_PROPOSAL_MODEL` | `anthropic/claude-sonnet-4-6` |
| Atomic-note drafts + chat | `ALEX_TRIAGE_ATOMIC_MODEL` | `anthropic/claude-sonnet-4-6` |
| Rubric distillation | `ALEX_TRIAGE_DISTILL_MODEL` | `anthropic/claude-opus-4-8` |

Embeddings reuse `ALEX_EMBEDDING_MODEL`. Tuning knobs:
`ALEX_TRIAGE_CLUSTER_THRESHOLD` (cosine cutoff for topic clusters, default
`0.45`) and `ALEX_TRIAGE_BATCH_SIZE` (notes per review batch, default `40`).

### eval-summary
````

(The final `### eval-summary` line above is the existing heading; everything before it is new.)

- [ ] **Step 5: Run the full check expecting everything green**

```bash
cd /home/alex/code/alex && just check
```

Expected: ruff check clean, `ruff format --check` clean, mypy `Success: no issues found`, and the entire pytest suite passes (all pre-existing tests plus every `test_triage_*` file from Tasks 1-18). This is the plan's final gate; nothing may be red.

- [ ] **Step 6: Commit**

```bash
cd /home/alex/code/alex && git add tests/test_triage_e2e.py README.md && git commit -m "test(triage): end-to-end pipeline test plus README triage docs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
