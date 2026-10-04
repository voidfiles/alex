# Advisor implementation plans

Implementation plans live here, separately from the summarization experiments
in `plans/`. Read each plan and its implementation record before follow-up work.

## Execution order and status

| Plan | Title | Priority | Effort | Depends on | Status |
|---|---|---|---|---|---|
| [002](002-enrich-book-ontology-standard-vocabularies.md) | Enrich book extraction with standard vocabularies | P1 | L | Existing schema-2 ontology work | DONE — implemented; book regenerated |

Status values: TODO | IN PROGRESS | DONE | BLOCKED (with one-line reason) |
REJECTED (with one-line rationale)

## Dependency notes

- Plan 002 was added on 2026-10-04 against commit `f75f59c` and the uncommitted
  ontology generator/exporter. It preserves all existing JSON fields and adds
  an optional, versioned `enrichment` section, following the user's preference.
  It is independent of plan 001. The user authorized implementation and book
  regeneration on 2026-10-04. Static checks and the requested live extraction,
  source checks, SHACL validation, and RDF round trips passed; regression tests
  and the planned two-source fixtures were not run. See its implementation record.
