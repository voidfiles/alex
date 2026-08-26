# Vault Collision Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Index root notes correctly and generate genuinely cross-domain collision ideas.

**Architecture:** Discovery receives the vault context so it recognizes only canonical asset folders. Collision retrieval uses scoped, hybrid-ranked candidates for relevance and semantic distance for contrast. The judge evaluates novelty independently.

**Tech Stack:** Python, SQLite FTS5/sqlite-vec, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-vault-collision-retrieval-design.md`

## Global Constraints

- No new dependencies.
- Test real index behavior with local fixtures and deterministic embedders.
- Do not perform git write operations.

---

### Task 1: Correct discovery and embedding completion

**Files:**
- Modify: `src/alex/lib/brain.py`
- Test: `tests/test_brain.py`

- [ ] Write tests proving root Markdown is not treated as an asset when the vault has `chunks/`, canonical asset chunks are discovered, and successful embedding batches continue beyond 2,000 rows.
- [ ] Run `just test tests/test_brain.py -q` and observe each new test fail.
- [ ] Limit asset recognition to the direct `assets/<name>` directory; continue embedding batches unless a batch fails.
- [ ] Re-run `just test tests/test_brain.py -q`.

### Task 2: Select diverse, distant sources

**Files:**
- Modify: `src/alex/lib/brain.py`
- Modify: `src/alex/lib/collisions.py`
- Test: `tests/test_brain.py`

- [ ] Write tests proving collision close sources include available root, asset, and nested scopes, while far sources exclude close domains and use vector distance when vectors exist.
- [ ] Run the named tests and observe failure.
- [ ] Add scoped candidate selection and semantic-distance ranking with deterministic fallback behavior.
- [ ] Re-run `just test tests/test_brain.py -q`.

### Task 3: Enforce novelty in generation and judgement

**Files:**
- Modify: `src/alex/lib/collisions.py`
- Test: `tests/test_brain.py`

- [ ] Write a failing test for a candidate rejected solely because its novelty score is too low.
- [ ] Run the named test and observe failure.
- [ ] Add novelty requirements to prompts and reject candidates below the novelty threshold.
- [ ] Re-run `just test tests/test_brain.py -q`.

### Task 4: Verify the integrated behavior

**Files:**
- Modify: `Justfile`
- Test: `tests/test_brain.py`

- [ ] Ensure the query workflow gives an actionable rebuild instruction when its cache predates the discovery version.
- [ ] Run `just test tests/test_brain.py tests/test_cli.py -q`, `just lint`, and `just typecheck`.
