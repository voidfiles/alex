# Chunk-First Claim Graph Design

## Context

The current summary pipeline builds chunk summaries first, creates a standard
final summary from those chunk summaries, then builds one claim/evidence graph
from the full source markdown as a late graph-enhancement pass.

That means the graph can improve the final synthesis, but it cannot help the
chunk summaries where many omissions are introduced. The new design moves graph
extraction earlier: every chunk gets a source-grounded graph before its chunk
summary is generated.

This follows the useful part of GraphRAG-style architectures: separate source
extraction/indexing from generation, then make generation consume structured
source evidence. Microsoft GraphRAG describes the pattern as combining text
extraction, graph/network analysis, prompting, and summarization in one
pipeline. The local repo should keep that idea, but use claim/evidence graphs
that match the existing summarization code rather than adding a new dependency
or generic knowledge-graph stack.

References:

- https://www.microsoft.com/en-us/research/project/graphrag/
- https://arxiv.org/abs/2404.16130
- https://microsoft.github.io/graphrag/query/local_search/

## Goals

- Extract claim/evidence graphs only from raw chunk markdown before chunk
  summarization.
- Feed each chunk summary prompt both the raw chunk text and the selected chunk
  subgraph.
- Merge chunk graphs into a document-wide graph for the final graph-guided
  summary pass.
- Preserve source provenance from document to chunk to section to evidence to
  claim.
- Keep artifacts inspectable so graph failures are diagnosable.
- Reuse the current `ClaimGraph`, graph rendering, claim scoring, graph summary,
  merge, and faithfulness-filtering concepts where practical.

## Non-Goals

- Do not extract graph claims from generated chunk summaries.
- Do not replace raw chunk text with graph-only input for chunk summaries.
- Do not add a graph database, vector database, or external indexing service.
- Do not add a new dependency unless a later implementation step proves the
  standard library and current helpers are not enough.
- Do not change the public `alex summary INPUT OUTPUT_PATH` workflow.

## Architecture

Add a chunk graph phase inside `summarize_doc_asset()` before the existing
`complete_all()` chunk summary call.

The new flow is:

1. Read all chunk markdown files.
2. Build a full claim graph for each chunk from the raw chunk markdown.
3. Select and render a bounded chunk subgraph for each chunk.
4. Generate chunk summaries from raw chunk text plus rendered chunk subgraph.
5. Write individual chunk summaries as today.
6. Concatenate and compress chunk summaries as today.
7. Merge all full chunk graphs into one document graph.
8. Select and render the document subgraph.
9. Generate the graph-guided final summary from the selected document subgraph.
10. Merge the standard final summary and graph-guided final summary.
11. Faithfulness-filter the merged summary against the full source markdown.

The important sequencing rule is that all graph extraction happens before the
LLM sees any chunk summary output.

## Graph Source Model

Refactor graph construction away from assuming every graph root is a document.
Introduce a small source descriptor:

```python
@dataclass(frozen=True)
class GraphSource:
    id: str
    kind: Literal["document", "chunk"]
    label: str
    text: str
    source_path: str
    chunk_index: int | None = None
    chunk_filename: str | None = None
```

`build_claim_graph()` should accept a `GraphSource` or equivalent fields and
produce a graph rooted at that source. For chunk graphs, the root node type is
`chunk`, not `document`.

Chunk graph node shape:

- `chunk:{doc_slug}:{chunk_index}` root node
- `section:{doc_slug}:{chunk_index}:{section_index}` section nodes
- `evidence:{doc_slug}:{chunk_index}:{section_index}:{claim_index}` evidence
  nodes
- `claim:{doc_slug}:{chunk_index}:{normalized_claim}:{suffix}` claim nodes

Document graph merge adds:

- one `document` node
- `document -> chunk` `contains` edges
- all chunk graph nodes and edges
- cross-chunk `similar_to` edges between claim nodes

This keeps IDs stable and avoids rewriting graph IDs after construction.

## Prompting

Add a new prompt template, `chunk_summary_with_graph`, instead of silently
changing the existing `chunk_summary` prompt contract.

Inputs:

- `title`
- `authors`
- `headers`
- `chunk`
- `selected_chunk_graph`

The prompt should tell the model:

- The raw chunk text is the source of truth.
- The selected graph is an extraction aid that highlights claims and evidence.
- Every substantive claim in the chunk summary must be supported by the raw
  chunk text.
- The summary should preserve important claims represented in the graph, but it
  may include raw-text details that are not represented in the graph.
- Do not cite graph IDs in chunk summaries unless we intentionally want noisy
  intermediate summaries. Default: no citations in chunk summaries.

The existing final `graph_guided_summary` prompt can keep using the selected
document subgraph and may keep inline graph IDs because that artifact is closer
to an audit trail.

## Settings

Extend `SummarySettings` with focused graph controls:

```python
chunk_graph_enhanced: bool = True
chunk_graph_max_claims: int = 12
document_graph_max_claims: int = 48
graph_artifacts: bool = True
```

Keep `graph_enhanced` as the top-level switch for the document graph final pass.
During implementation, either migrate `graph_max_claims` to
`document_graph_max_claims` or keep it as a backwards-compatible alias. Do not
leave two settings that fight each other.

## Artifacts

When `graph_artifacts` is true, write:

```text
summary_graph/
  chunks/
    001_deep_work/
      graph.json
      selected_subgraph.json
      selected_subgraph.md
    002_deep_work/
      graph.json
      selected_subgraph.json
      selected_subgraph.md
  document_graph.json
  selected_document_subgraph.json
  selected_document_subgraph.md
  standard_summary.md
  graph_summary.md
  merged_summary.md
  faithfulness_filtered_summary.md
  pre_filter_claim_verdicts.json
```

The current `graph.json` and `selected_subgraph.json` names are ambiguous once
chunk graphs exist. Prefer the explicit document names above. If compatibility
with existing tests or artifacts matters, the implementation can also write
legacy aliases for one release.

## Error Handling

Graph extraction failures should fail the summary by default. A graph-enhanced
summary that silently drops the graph would be hard to trust.

The implementation may later add an explicit `strict_graph: bool = True`
setting if we want fallback behavior, but this design keeps failure semantics
simple and visible.

If one chunk graph extraction fails, include the chunk filename and extraction
step in the raised error.

## Testing

Add focused tests for:

- Chunk graph extraction runs before chunk summary generation.
- Chunk summary prompts receive the selected chunk graph markdown.
- Graph extraction receives raw chunk text, not generated summaries.
- Merged document graph contains document, chunk, section, evidence, and claim
  nodes.
- Document graph includes `document -> chunk` containment edges.
- Cross-chunk similar claim edges are added after merge.
- Artifact paths are written under `summary_graph/chunks/...`.
- Existing `graph_enhanced=False` behavior still skips graph work.

Prefer deterministic fake completers, matching the existing test style in
`tests/helpers.py` and `tests/test_claim_graph.py`.

## Implementation Notes

The lowest-risk implementation sequence is:

1. Generalize claim graph construction around a graph source descriptor.
2. Add chunk graph construction and document graph merging helpers.
3. Add rendering/artifact support for chunk graphs and document graphs.
4. Add `chunk_summary_with_graph` prompt loading.
5. Thread selected chunk graph markdown into chunk summary prompts.
6. Replace the current full-document graph build in `graph_enhanced_summary()`
   with the merged document graph.
7. Update tests and README.

No new dependency is required for the first implementation.
