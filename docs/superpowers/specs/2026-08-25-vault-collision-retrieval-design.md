# Vault Collision Retrieval Design

## Goal

Make collision queries draw from the whole vault and require a materially novel connection between source notes.

## Discovery

Only folders immediately below `<vault>/assets` are document assets. Their chunk files are indexed as the asset's retrieval units. A root-level `chunks` folder is ordinary vault content, so all root-level Markdown files and chunks remain independently indexable.

## Retrieval

Hybrid search collects a wider candidate pool, then selects close notes across available scopes: root, assets, and other folders. It preserves query relevance within each scope. Distant notes come from the same candidate pool, rank by vector distance from close notes when fresh embeddings are available, and fall back to deterministic domain diversity when they are not. A distant note cannot share the same vault domain as a close note.

## Generation and Judging

The generation prompt requires a mechanism-level connection between distinct sources. The judge separately evaluates grounding, specificity, and novelty, and only admits candidates with an explicit novelty score above the acceptance threshold.

## Embeddings

Indexing continues through all stale batches after successful embedding calls. If a batch fails, the command stops after retaining completed batches and reports the failure, avoiding an infinite retry loop.

## Constraints

- No dependencies.
- Preserve deterministic behavior in tests.
- Existing caches must be rebuilt after the discovery semantic change.
