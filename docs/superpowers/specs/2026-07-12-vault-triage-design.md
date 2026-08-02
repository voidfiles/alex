# Vault Triage Design

## Context

The Obsidian vault at the heart of Alex's second brain has roughly 3,000
unprocessed notes sitting at the vault root, plus clippings and meeting notes
that have never been placed in the PARA structure. The 2026-06 area-discovery
work (projects/secondbrain-cleanup) established 33 stable areas, each with an
index.md carrying a description and discovery evidence, but explicitly
deferred "moving notes into areas" to a future version. This tool is that
future version.

Two research projects in the vault constrain the design:

- pkm-research concluded that wholesale backlog reorganization is
  productivity theater, that atomic notes only pay off for ideas actually in
  use, and that the right AI division of labor is "machine suggests, human
  commits."
- writing-as-cognition concluded that the cognitive value of an atomic note
  lives in the human formulating it, and that a review flow must keep the
  human doing generative work, not approval-clicking.

The design responds with a triage-first sweep: fast, cheap filing decisions
over everything, with atomic-note creation reserved for notes the human flags
as promising, LLM-drafted but human-reviewed with a low-friction revision
loop. Corrections persist in a ledger and are distilled into a rubric so
proposals improve over time.

The tool lives in the `alex` CLI (~/code/alex), which already provides the
LiteLLM model layer with per-role defaults, embeddings, versioned prompt
files, vault locking, and a fake-LLM test harness.

## Goals

- Drain the vault-root backlog through batch-by-batch human review in a
  keyboard-first Textual TUI.
- Propose a PARA filing decision per note (area, resource, archive, trash)
  with confidence, reasoning, and alternatives, grounded in a live area
  catalog built from areas/*/index.md descriptions.
- Record decisions as frontmatter annotations first; physically move notes in
  a separate, idempotent, dry-run-by-default apply step with wiki-link
  rewriting.
- Support ad-hoc pushback: reject with a reason, edit the target, or chat
  with the model about a note, triggering immediate re-proposal.
- Learn from corrections: append every review event to a ledger, distill the
  ledger into a versioned, hand-editable rubric injected into every proposal
  prompt.
- Queue human-flagged "promising" notes for a second, slower pass that drafts
  atomic permanent notes for approval or revision.
- Batch by topic cluster so consecutive decisions are similar and corrections
  generalize within a batch.

## Non-Goals

- No reorganization of resources/ topic folders (a later expansion once the
  tool has earned trust).
- No changes to the existing process-vault highlight/extract pipeline; the
  two coordinate only through frontmatter (this tool skips notes with
  `processed: true`).
- No automatic filing without human approval, and no automatic atomic-note
  publication without human review.
- No moves for Meetings/ and Weekly/ notes, ever; those populations are
  annotate-only per vault convention. Same for daily/.
- No new areas created silently; the model may propose one, but it is created
  only after explicit approval, and only at apply time.
- No note bodies modified by this tool. Frontmatter only. Bold and highlight
  layers are progressive-summarization data and must survive untouched.
- No deletion. The strongest action is a move to trash/.
- No embeddings database or external service; embeddings are computed via the
  existing LiteLLM layer and cached to files.

## Scope

In-scope populations for v1:

- Loose .md files at the vault root (the ~3,000-note inbox). Movable.
- Clippings/ (saved articles). Movable; archived clippings go to
  archives/clippings/. Skipped when mid-flight in the old pipeline
  (`workflow:` state present but not terminal) or already `processed: true`.
- Meetings/ and Weekly/. Annotate-only: area links and the promising flag,
  no moves.

Excluded: resources/, areas/, projects/, assets/, daily/, archives/,
archive/, trash/, attachments/, dotfolders.

## Decisions Already Made

Settled during brainstorming with Alex, recorded here so implementation does
not relitigate them:

1. Triage-first sweep with a separate atomic-note queue (not full treatment
   per batch, not just-in-time only).
2. LLM drafts atomic notes; Alex approves and can demand revisions. The UI
   must make "suggest changes" the path of least resistance.
3. Annotate now, move later (two-phase decide/apply).
4. Textual TUI, keyboard-first.
5. Learning via corrections ledger distilled into a rubric (exemplar
   retrieval is a possible later addition; the ledger schema must not
   preclude it).
6. Topic-clustered batches.
7. Live batch-ahead proposal generation (architecture B): while batch N is
   reviewed, batch N+1 is generated with the current rubric. Proposals are
   cached to files keyed by batch and rubric version for crash-safety, but
   there is no staleness-regeneration machinery.
8. Code lives in ~/code/alex as an `alex triage` command group.

## Data Model

All durable state lives in the vault so it syncs across machines. Repo code
holds no state.

### Area catalog (derived, regenerated each session)

Built at TUI startup and by `alex triage catalog`:

- One entry per areas/<slug>/index.md: slug, name, frontmatter description,
  and the Discovery Evidence bullets when present.
- The list of resources/ top-level topic folders, for resource decisions.

Cached as YAML under `.claude/triage/catalog.yaml` in the vault, with the
source file mtimes recorded so a stale cache is detected and rebuilt. The
2026-06-05 area-candidates file in projects/secondbrain-cleanup is history
and is never read or written by this tool.

### Inventory and cluster map

`.claude/triage/inventory.yaml`: one record per eligible note with path,
title, tags, wikilinks, first ~200 words, presence of bold/highlight marks,
mtime, word count, and population (root, clippings, meetings, weekly).

`.claude/triage/cluster-map.yaml`: note path to cluster id, cluster id to
label, and the ordered batch list (batch id, cluster ids, note paths,
~30-50 notes per batch). Deterministic given the same inventory and
embeddings.

### Proposal cache

`.claude/triage/proposals/batch-NNN.rubric-vNN.yaml`: the generated
proposals for a batch. Per note: decision (area | resource | archive |
trash | skip), target slug or topic, confidence (high | medium | low), a
one-to-two sentence why, up to two alternatives, and an optional new-area
proposal (slug, name, description) when nothing in the catalog fits.
Validated against a pydantic schema on read and write.

### Triage frontmatter block (the decision of record)

Written to each note at batch confirm, separate from the existing
`workflow:` block so the two pipelines cannot corrupt each other. Only this
tool writes `triage:`.

```yaml
triage:
  decision: area          # area | resource | archive | trash
  target: organizational-design
  promising: true         # optional; queues the note for atomic mode
  status: decided         # decided | applied
  decided: 2026-07-12
  applied: 2026-07-19     # set by apply
```

For annotate-only populations, `decision` records the area association and
`status` goes straight to `applied` (there is nothing to move).

Skip semantics: skipping writes no `triage:` block, unless the promising
flag was toggled, in which case a block containing only `promising: true`
is written. A note remains sweep-eligible while it has no
`triage.decision`; the atomic queue selects on `triage.promising: true`
regardless of filing decision. `skip` can appear in model proposals but is
never persisted as a frontmatter decision.

### Corrections ledger

`projects/vault-triage/ledger.jsonl`, append-only. One JSON object per
review event:

```json
{"ts": "...", "note": "path.md", "batch": 12, "rubric_version": 4,
 "event": "approve|reject|edit|repropose|atomic_approve|atomic_revise",
 "proposal": {...}, "correction": {...}, "reason": "free text"}
```

Approvals are logged too; they are signal about what works and future
exemplar-bank material.

### Rubric

`projects/vault-triage/rubric.md`. Human-readable, hand-editable markdown
with `version: N` frontmatter and two sections: triage rules and
atomic-note rules. Each rule is numbered with a terse rationale. The
distiller rewrites the whole file each time and must compress rather than
append; the rubric stays within roughly 2K tokens permanently. Hand edits
are legitimate and survive distillation (the distiller reads the current
file as input).

### Atomic notes

Approved drafts are written to `resources/permanent-notes/<Claim Title>.md`
using plain human titles (no timestamp prefix), matching the files already
there and settling the naming conflict between the two existing skills.
Frontmatter includes type, created, source wikilink, tags, and a provenance
marker (`provenance: llm-drafted, human-approved`) per the pkm-research rule
that AI text in permanent notes must be unambiguously marked. The source
note gains a `permanent_notes:` list of wikilinks. Related links in the
draft may only point to files verified to exist.

## CLI Surface

```
alex triage inventory [--vault-root PATH]     # scan + evidence extraction
alex triage cluster                            # embed, cluster, batch
alex triage review                             # the Textual TUI
alex triage distill                            # ledger window -> rubric vN+1
alex triage apply [--write]                    # plan moves; execute with --write
alex triage status                             # progress dashboard
alex triage catalog                            # rebuild the area catalog cache
```

Vault root resolution: `--vault-root` flag, else the repo's existing
`OBSIDIAN_ROOT` env var, else error. No hardcoded machine-specific default.

Code layout follows repo conventions: thin Click factories in
`src/alex/commands/triage.py` registered in `main.py`; logic in
`src/alex/lib/triage/` (inventory.py, clustering.py, catalog.py,
proposals.py, ledger.py, rubric.py, frontmatter.py, apply.py, session.py);
TUI in `src/alex/lib/triage/tui/`; prompts as versioned markdown in
`src/alex/prompts/`.

## Pipeline

### Inventory

Walks the in-scope populations, applies eligibility rules (not `processed:
true`, no `triage.decision` in frontmatter, not mid-flight in the old
pipeline),
extracts evidence, writes inventory.yaml. Re-runs append newly arrived
notes and refresh changed ones; notes that vanished are dropped.

### Clustering

Embeds each note's evidence text with the existing embedding layer
(`DEFAULT_EMBEDDING_MODEL`), clusters by cosine similarity using the
existing vector helpers (greedy agglomerative with a tuned threshold;
singletons pool into mixed batches last), labels each cluster with the fast
model, slices into batches. Embeddings cache to disk keyed by note mtime so
re-clustering is cheap.

### Review TUI

Two screens in one Textual app.

Triage mode:

- Layout: note list sidebar, note view (rendered markdown, highlights
  visible), proposal panel (decision, target, confidence, why,
  alternatives), status bar with batch progress.
- Keys: a approve, e edit target (fuzzy picker over the catalog plus
  new-area entry), p toggle promising, t trash, s skip, r reject (prompts
  for a one-line reason, then re-proposes this note immediately), c chat,
  u undo last action, b batch summary, q quit.
- Chat opens a pane scoped to the current note: the conversation context is
  the rubric, the catalog, the note evidence, and the current proposal. A
  chat exchange can end with a revised structured proposal; the takeaway is
  logged to the ledger as a repropose event with the user's words as the
  reason.
- Rubric-level learning timing: batch N+1 is generated during review of
  batch N using the rubric as of the start of batch N. In-batch corrections
  apply immediately: after a reject or chat correction, remaining
  unreviewed proposals in the current batch are regenerated with the
  correction appended to the prompt context. Worst-case rubric lag is one
  batch.
- Batch confirm shows the decision summary (including any "needs manual"
  notes), then writes all `triage:` blocks under the vault lock, appends
  ledger events, kicks off distillation in the background, and opens the
  next batch (whose proposals are normally already generated).

Atomic mode:

- Queue: notes with `promising: true`, oldest decisions first.
- Per note, the draft model produces one or more atomic-note drafts per the
  vault's conventions (concept-oriented claim title, self-contained body in
  Alex's register, tags, source anchor, verified Related links).
- Keys: a approve (writes the file, updates source frontmatter, logs), r
  request changes (one-line direction, immediate redraft), c chat, s skip,
  d drop (unflag promising).
- The revision path is one keypress; approval and revision are equally
  cheap by design.

Session state (current batch, pending decisions) persists to
`.claude/triage/session.yaml` after every action so a crash or quit loses
nothing.

### Distillation

Reads the ledger events since the last distillation plus the current
rubric, produces the next rubric version. Runs in the background after each
batch confirm and on demand via `alex triage distill`. If distillation
fails, the old rubric stands; failure is reported, never blocking review.

### Apply

Dry-run by default: prints the move plan grouped by destination. With
`--write`:

1. Create any approved new areas (areas/<slug>/index.md with description
   and an evidence section matching the existing 33).
2. Move each note with a filing decision and `status: decided` to its
   destination with wiki-link rewriting. Collisions get a ` (2)` style suffix and a report line; no
   overwrites.
3. Flip that note's `triage.status` to applied immediately after its move,
   so interruption and re-run are safe.
4. Append each move to `_meta/processing-log.md`.

The wiki-link rewriting logic is ported from the move-file skill script
into `src/alex/lib/` as a tested module (aliases, embeds, relative links,
extension variants). This port becomes the canonical implementation; a
follow-up (outside this spec) will point the move-file skill at the CLI to
avoid drift.

## LLM Roles

Following the existing role-default-plus-env-override pattern in
lib/llm.py:

- Cluster labeling: `openai/gpt-5.6-luna` default,
  `ALEX_TRIAGE_LABEL_MODEL`.
- Triage proposals: `openai/gpt-5.6-terra` default,
  `ALEX_TRIAGE_PROPOSAL_MODEL`.
- Atomic-note drafting and chat: `openai/gpt-5.6-terra` default,
  `ALEX_TRIAGE_ATOMIC_MODEL`.
- Rubric distillation: `openai/gpt-5.6-sol` default,
  `ALEX_TRIAGE_DISTILL_MODEL`.
- Embeddings: existing `ALEX_EMBEDDING_MODEL`.

Prompts live in `src/alex/prompts/` as versioned markdown per repo
convention. Every proposal and drafting prompt receives the rubric and the
area catalog.

## Safety and Concurrency

- The ob-sync daemon syncs the vault continuously. All frontmatter writes
  and the apply step take the existing lib/locking.py vault lock. Cache and
  state files are written atomically (write to temp, rename).
- Frontmatter editing preserves the note byte-for-byte outside the YAML
  block, and preserves unrelated frontmatter keys and their order.
- At batch open, each note's mtime is checked against inventory; changed
  notes get fresh evidence, vanished notes are ejected with a notice.
- The tool never edits anything under archives/, archive/, trash/,
  .obsidian/, or .smart-env/ (moves land INTO archives/ and trash/ only).

## Error Handling

- LLM calls retry with backoff via the existing LLM layer. A failed batch
  generation marks the batch pending and the TUI continues with the next
  available batch.
- Model output that fails pydantic validation gets one repair attempt
  (error fed back); on second failure the note is marked "needs manual" and
  surfaced in the batch summary. No silent drops.
- Apply validates every destination before moving anything; an invalid
  target (approved area whose index creation failed, malformed slug) skips
  that note with a report line and continues.

## Testing

Repo conventions apply: pytest with tests/helpers.py fakes, strict mypy,
ruff, all via `just check`. LLM and embedding calls are faked (external
system; mocks permitted).

- Unit: inventory eligibility per population; triage frontmatter roundtrip
  (body byte-identical, other keys preserved); deterministic batching from
  a fake embedder; proposal schema validation and repair path; ledger
  append/read; rubric version bump and compression contract; apply planner
  output for a fixture vault; link-rewrite port against move-file's case
  matrix.
- TUI: Textual Pilot tests for each keybinding, the reject-with-reason
  flow, batch confirm, and session resume.
- End-to-end: a fixture mini-vault plus scripted fake LLM responses driven
  through inventory, cluster, review (Pilot), and apply, asserting the
  final vault state including rewritten links.
- Later, the ledger doubles as a labeled corpus for proposal-quality evals
  using the repo's existing evals machinery; not part of v1.

## Success Criteria

- The vault-root loose-note count visibly drains batch over batch.
- Review pace stays fast enough that Alex keeps using the tool; the TUI is
  judged by sustained throughput, not demo quality.
- Rejection and edit rates fall across rubric versions (measurable from the
  ledger), demonstrating the learning loop works.
- Zero broken wiki links after apply runs (verifiable by link audit on the
  fixture vault and spot checks on the real one).

## Follow-ups Outside This Spec

- Point the move-file skill at the CLI's link-rewriting module once ported.
- Fix the vault CLAUDE.md reference to a `notes` CLI at .claude/scripts/
  (stale; the alex CLI is the real automation home).
- projects/secondbrain-cleanup/CLAUDE.md is a 111KB unrelated document that
  gets injected as project instructions for any agent working in that
  folder; move it (via move-file).
- The areas writing and writing-practice overlap noted during research is a
  vault-content decision for Alex, not a tool concern.
- Expansion candidates once trusted: resources/ re-triage, exemplar-bank
  retrieval on top of the ledger, eval-gated rubric changes.
