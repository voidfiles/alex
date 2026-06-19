# Chunk-First Claim Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build claim/evidence graphs from raw chunks before chunk summarization, use those graphs to improve chunk summaries, and merge chunk graphs into the document graph used by the final graph-guided summary.

**Architecture:** Generalize `claim_graph.py` around a `GraphSource` so graph construction can root at chunks or documents. The summary pipeline will build chunk graphs before chunk summaries, render selected chunk subgraphs into a new `chunk_summary_with_graph` prompt, then merge full chunk graphs into a document graph for the existing final graph summary, merge, and faithfulness filter.

**Tech Stack:** Python 3.13, dataclasses, existing `uv`/pytest tooling, existing prompt template loader, existing LiteLLM completer interfaces.

---

## Files

- Modify: `src/alex/lib/claim_graph.py`
  - Add `GraphSource`.
  - Generalize `build_claim_graph()`.
  - Add `merge_chunk_graphs()`.
  - Respect `GraphSettings.similarity_threshold` instead of hardcoded `0.28`.
- Modify: `src/alex/lib/summarize.py`
  - Load and use `chunk_summary_with_graph`.
  - Build chunk graphs before chunk summary calls.
  - Pass merged document graph into the final graph-enhanced summary path.
  - Write chunk and document graph artifacts.
- Add: `src/alex/prompts/chunk_summary_with_graph/active.txt`
- Add: `src/alex/prompts/chunk_summary_with_graph/v001.md`
- Modify: `tests/test_claim_graph.py`
  - Cover chunk graph IDs and document graph merge.
- Modify: `tests/helpers.py`
  - Make fake completer recognize graph-enhanced chunk prompts.
- Modify: `tests/test_summary_assets.py`
  - Cover chunk graph first ordering, artifacts, and prompt contents.
- Modify: `README.md`
  - Update summary graph artifact description.

No git commit steps are included because `AGENTS.md` forbids git write operations without explicit authorization.

---

### Task 1: Generalize Claim Graph Sources

**Files:**
- Modify: `src/alex/lib/claim_graph.py`
- Test: `tests/test_claim_graph.py`

- [ ] **Step 1: Write failing tests for chunk-rooted graphs**

Add tests that call `build_claim_graph()` with a chunk source and assert the graph root is a `chunk`, IDs include chunk index, and evidence still supports claims.

```python
from alex.lib.claim_graph import GraphSource


def test_build_claim_graph_supports_chunk_source() -> None:
    graph = build_claim_graph(
        source=GraphSource(
            id="chunk:note:1",
            kind="chunk",
            label="001_note.md",
            text=DOC,
            source_path="chunks/001_note.md",
            chunk_index=1,
            chunk_filename="001_note.md",
        ),
        prompts=GraphPrompts.load(),
        completer=ClaimCompleter(),
        eval_settings=EvalSettings(
            judge_model="judge/test",
            fact_extractor_model="extractor/test",
        ),
    )

    root = graph.nodes[0]
    assert root.id == "chunk:note:1"
    assert root.type == "chunk"
    assert root.label == "001_note.md"
    assert root.metadata["source_path"] == "chunks/001_note.md"
    assert root.metadata["chunk_filename"] == "001_note.md"
    assert any(node.id.startswith("section:note:1:") for node in graph.nodes)
    assert any(node.id.startswith("evidence:note:1:") for node in graph.nodes)
    assert any(node.id.startswith("claim:note:1:") for node in graph.nodes)
    assert any(edge.type == "supports" for edge in graph.edges)
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest tests/test_claim_graph.py::test_build_claim_graph_supports_chunk_source -q
```

Expected: fail because `GraphSource` and the new `source=` parameter do not exist.

- [ ] **Step 3: Implement `GraphSource` and source-aware graph IDs**

In `src/alex/lib/claim_graph.py`, add:

```python
from typing import Any, Literal


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

Change `ClaimGraph` to keep `doc_name` for compatibility and add optional root metadata only if needed later. Change `build_claim_graph()` to accept `source: GraphSource` and construct IDs through small helpers:

```python
def build_claim_graph(
    *,
    source: GraphSource,
    prompts: GraphPrompts,
    completer: Completer,
    eval_settings: EvalSettings,
    settings: GraphSettings = GraphSettings(),
) -> ClaimGraph:
    sections = fact_sections(source.text)
    source_slug = graph_source_slug(source)
    nodes = [
        GraphNode(
            id=source.id,
            type=source.kind,
            label=source.label,
            source=source.source_path,
            metadata=graph_source_metadata(source),
        )
    ]
    edges: list[GraphEdge] = []
    claim_counts: Counter[str] = Counter()

    for section_index, section in enumerate(sections, 1):
        section_id = section_node_id(source, source_slug, section_index)
        section_node = GraphNode(
            id=section_id,
            type="section",
            label=section.title,
            source=source.source_path,
            text=trim_text(section.text),
            section_index=section_index,
            metadata=graph_source_metadata(source),
        )
        nodes.append(section_node)
        edges.append(GraphEdge(source=source.id, target=section_id, type="contains"))

        for claim_index, item in enumerate(
            extract_source_claims(
                section=section,
                template=prompts.source_claim_extraction,
                completer=completer,
                settings=eval_settings,
            ),
            1,
        ):
            normalized = slugify(item.claim, limit=72)
            claim_counts[normalized] += 1
            suffix = claim_counts[normalized]
            claim_id = claim_node_id(source, source_slug, normalized, suffix)
            evidence_id = evidence_node_id(
                source,
                source_slug,
                section_index,
                claim_index,
            )
            score = claim_score(item.claim, item.evidence)
            metadata = {
                **graph_source_metadata(source),
                "section": section.title,
            }
            nodes.append(
                GraphNode(
                    id=evidence_id,
                    type="evidence",
                    label=f"{section.title} evidence {claim_index}",
                    source=source.source_path,
                    text=item.evidence,
                    section_index=section_index,
                    score=score,
                    metadata=metadata,
                )
            )
            nodes.append(
                GraphNode(
                    id=claim_id,
                    type="claim",
                    label=trim_text(item.claim, limit=120),
                    source=source.source_path,
                    text=item.claim,
                    section_index=section_index,
                    score=score,
                    metadata={**metadata, "evidence_id": evidence_id},
                )
            )
            edges.append(GraphEdge(source=section_id, target=evidence_id, type="contains"))
            edges.append(
                GraphEdge(
                    source=evidence_id,
                    target=claim_id,
                    type="supports",
                    evidence=item.evidence,
                )
            )

    edges.extend(similar_claim_edges(nodes, threshold=settings.similarity_threshold))
    return ClaimGraph(doc_name=source.label, nodes=tuple(nodes), edges=tuple(edges))
```

Add helpers:

```python
def graph_source_metadata(source: GraphSource) -> dict[str, str]:
    metadata = {"source_path": source.source_path}
    if source.chunk_index is not None:
        metadata["chunk_index"] = str(source.chunk_index)
    if source.chunk_filename is not None:
        metadata["chunk_filename"] = source.chunk_filename
    return metadata


def graph_source_slug(source: GraphSource) -> str:
    if source.kind == "chunk" and source.chunk_index is not None:
        base = source.chunk_filename or source.label
        return f"{slugify(base)}:{source.chunk_index}"
    return slugify(source.label)
```

Add `section_node_id()`, `evidence_node_id()`, and `claim_node_id()` so chunk IDs match the test.

- [ ] **Step 4: Preserve old call sites temporarily**

To keep existing code compiling while task 2 updates callers, either update the current tests immediately or add a compatibility wrapper:

```python
def document_graph_source(*, doc_name: str, doc_text: str) -> GraphSource:
    return GraphSource(
        id=f"document:{slugify(doc_name)}",
        kind="document",
        label=doc_name,
        text=doc_text,
        source_path=doc_name,
    )
```

- [ ] **Step 5: Run claim graph tests**

Run:

```bash
uv run pytest tests/test_claim_graph.py -q
```

Expected: pass after tests are updated to use `document_graph_source()` or explicit `GraphSource`.

---

### Task 2: Merge Chunk Graphs Into a Document Graph

**Files:**
- Modify: `src/alex/lib/claim_graph.py`
- Test: `tests/test_claim_graph.py`

- [ ] **Step 1: Write failing merge test**

Add:

```python
def test_merge_chunk_graphs_creates_document_graph_with_chunk_edges() -> None:
    prompts = GraphPrompts.load()
    eval_settings = EvalSettings(
        judge_model="judge/test",
        fact_extractor_model="extractor/test",
    )
    first = build_claim_graph(
        source=GraphSource(
            id="chunk:note:1",
            kind="chunk",
            label="001_note.md",
            text=DOC,
            source_path="chunks/001_note.md",
            chunk_index=1,
            chunk_filename="001_note.md",
        ),
        prompts=prompts,
        completer=ClaimCompleter(),
        eval_settings=eval_settings,
    )
    second = build_claim_graph(
        source=GraphSource(
            id="chunk:note:2",
            kind="chunk",
            label="002_note.md",
            text=DOC,
            source_path="chunks/002_note.md",
            chunk_index=2,
            chunk_filename="002_note.md",
        ),
        prompts=prompts,
        completer=ClaimCompleter(),
        eval_settings=eval_settings,
    )

    merged = merge_chunk_graphs(
        doc_name="note.md",
        source_path="note.md",
        chunk_graphs=(first, second),
    )

    assert merged.nodes[0].id == "document:note-md"
    assert merged.nodes[0].type == "document"
    assert sum(node.type == "chunk" for node in merged.nodes) == 2
    assert any(
        edge.source == "document:note-md"
        and edge.target == "chunk:note:1"
        and edge.type == "contains"
        for edge in merged.edges
    )
    assert any(edge.type == "similar_to" for edge in merged.edges)
```

- [ ] **Step 2: Run failing merge test**

Run:

```bash
uv run pytest tests/test_claim_graph.py::test_merge_chunk_graphs_creates_document_graph_with_chunk_edges -q
```

Expected: fail because `merge_chunk_graphs()` does not exist.

- [ ] **Step 3: Implement `merge_chunk_graphs()`**

Add:

```python
def merge_chunk_graphs(
    *,
    doc_name: str,
    source_path: str,
    chunk_graphs: Sequence[ClaimGraph],
    settings: GraphSettings = GraphSettings(),
) -> ClaimGraph:
    document_id = f"document:{slugify(doc_name)}"
    nodes: list[GraphNode] = [
        GraphNode(
            id=document_id,
            type="document",
            label=doc_name,
            source=source_path,
            metadata={"source_path": source_path},
        )
    ]
    edges: list[GraphEdge] = []
    seen_node_ids = {document_id}

    for graph in chunk_graphs:
        chunk_nodes = [node for node in graph.nodes if node.type == "chunk"]
        if len(chunk_nodes) != 1:
            raise ValueError(f"Expected exactly one chunk root in {graph.doc_name}.")
        chunk_node = chunk_nodes[0]
        edges.append(GraphEdge(source=document_id, target=chunk_node.id, type="contains"))
        for node in graph.nodes:
            if node.id in seen_node_ids:
                raise ValueError(f"Duplicate graph node id while merging: {node.id}")
            seen_node_ids.add(node.id)
            nodes.append(node)
        edges.extend(edge for edge in graph.edges if edge.type != "similar_to")

    edges.extend(similar_claim_edges(nodes, threshold=settings.similarity_threshold))
    return ClaimGraph(doc_name=doc_name, nodes=tuple(nodes), edges=tuple(edges))
```

Change `similar_claim_edges()` signature:

```python
def similar_claim_edges(
    nodes: Sequence[GraphNode],
    *,
    threshold: float = 0.28,
) -> tuple[GraphEdge, ...]:
```

- [ ] **Step 4: Run claim graph tests**

Run:

```bash
uv run pytest tests/test_claim_graph.py -q
```

Expected: pass.

---

### Task 3: Add Graph-Enhanced Chunk Summary Prompt

**Files:**
- Add: `src/alex/prompts/chunk_summary_with_graph/active.txt`
- Add: `src/alex/prompts/chunk_summary_with_graph/v001.md`
- Modify: `src/alex/lib/summarize.py`
- Test: `tests/test_prompt_templates.py`

- [ ] **Step 1: Add prompt files**

Create `active.txt` containing:

```text
v001
```

Create `v001.md`:

```markdown
You are creating a rigorous, source-faithful summary of one document chunk.

Title: {{title}}
Authors: {{authors}}

Document outline:
{{headers}}

<selected_chunk_graph>
{{selected_chunk_graph}}
</selected_chunk_graph>

<section_content>
{{chunk}}
</section_content>

Use the raw section content as the source of truth. The selected chunk graph is an extraction aid that highlights important claims and evidence, but it is not a replacement for the raw text.

Requirements:
- Preserve the important claims represented in the selected chunk graph when the raw section content supports them.
- Include important raw-text details even when they are not represented in the graph.
- Do not introduce claims that are unsupported by the raw section content.
- Do not cite graph node IDs in the summary.
- Do not append file references, chunk indices, navigation links, or boilerplate.

Write a clear, information-dense summary for a downstream synthesis step.
```

- [ ] **Step 2: Extend `SUMMARY_PROMPT_NAMES` and `SummaryPrompts`**

In `src/alex/lib/summarize.py`, include `chunk_summary_with_graph`:

```python
SUMMARY_PROMPT_NAMES = (
    "chunk_summary",
    "chunk_summary_with_graph",
    "compression_summary",
    "final_summary",
)
```

Add field:

```python
chunk_summary_with_graph: PromptTemplate
```

Load it in `SummaryPrompts.load()` using `load_prompt("chunk_summary_with_graph", ...)`.

- [ ] **Step 3: Run prompt template tests**

Run:

```bash
uv run pytest tests/test_prompt_templates.py -q
```

Expected: pass.

---

### Task 4: Build Chunk Graphs Before Chunk Summaries

**Files:**
- Modify: `src/alex/lib/summarize.py`
- Modify: `tests/helpers.py`
- Modify: `tests/test_summary_assets.py`

- [ ] **Step 1: Add failing summary pipeline assertions**

In `tests/test_summary_assets.py`, extend `test_process_markdown_summary_runs_the_full_pipeline()`:

```python
    source_claim_calls = [
        call for call in completer.calls if "source-grounded claims" in call.prompt
    ]
    assert source_claim_calls
    first_chunk_call_index = next(
        index
        for index, call in enumerate(completer.calls)
        if "<section_content>" in call.prompt
    )
    first_graph_call_index = completer.calls.index(source_claim_calls[0])
    assert first_graph_call_index < first_chunk_call_index
    assert "<selected_chunk_graph>" in completer.chunk_calls()[0].prompt
    assert "The document preserves important claims." in completer.chunk_calls()[0].prompt
```

- [ ] **Step 2: Update fake completer only if needed**

If `RecordingCompleter.chunk_calls()` already keys on `<section_content>`, no change is required. If graph prompts are misrouted, keep this ordering:

```python
if "source-grounded claims" in prompt:
    return json.dumps(...)
if "<section_content>" in prompt:
    ...
```

- [ ] **Step 3: Run failing summary test**

Run:

```bash
uv run pytest tests/test_summary_assets.py::test_process_markdown_summary_runs_the_full_pipeline -q
```

Expected: fail because chunk summary prompts do not include selected graph markdown yet.

- [ ] **Step 4: Implement chunk graph preparation**

In `src/alex/lib/summarize.py`, add a small dataclass:

```python
@dataclass(frozen=True)
class ChunkGraphBundle:
    chunk_path: Path
    graph: ClaimGraph
    selected: ClaimGraph
    selected_markdown: str
```

Add `build_chunk_graph_bundles()` that loops over chunk paths, builds `GraphSource(kind="chunk")`, calls `build_claim_graph()`, selects with `GraphSettings(max_claims=settings.chunk_graph_max_claims)`, and renders with `render_selected_subgraph()`.

- [ ] **Step 5: Extend `SummarySettings`**

Add:

```python
chunk_graph_enhanced: bool = True
chunk_graph_max_claims: int = 12
document_graph_max_claims: int = 48
```

Replace uses of `settings.graph_max_claims` for document graph selection with `settings.document_graph_max_claims`. If preserving compatibility, leave `graph_max_claims` in place and initialize `document_graph_max_claims` to the same default.

- [ ] **Step 6: Thread chunk graph markdown into chunk summary prompts**

In `summarize_doc_asset()`, before constructing chunk prompts:

```python
chunk_graph_bundles = ()
selected_graph_by_chunk: dict[Path, str] = {}
if settings.graph_enhanced and settings.chunk_graph_enhanced:
    chunk_graph_bundles = build_chunk_graph_bundles(...)
    selected_graph_by_chunk = {
        bundle.chunk_path: bundle.selected_markdown for bundle in chunk_graph_bundles
    }
```

Change prompt creation to use `chunk_summary_with_graph` when a selected graph exists for the chunk:

```python
prompts = tuple(
    (
        settings.prompts.chunk_summary_with_graph.render(
            title=metadata.title,
            authors=authors,
            headers=headers,
            chunk=chunk_path.read_text(encoding="utf-8"),
            selected_chunk_graph=selected_graph_by_chunk[chunk_path],
        )
        if chunk_path in selected_graph_by_chunk
        else settings.prompts.chunk_summary.render(...)
    )
    for chunk_path in chunk_paths
)
```

- [ ] **Step 7: Run focused summary test**

Run:

```bash
uv run pytest tests/test_summary_assets.py::test_process_markdown_summary_runs_the_full_pipeline -q
```

Expected: pass.

---

### Task 5: Use Merged Chunk Graph for Final Graph Summary and Artifacts

**Files:**
- Modify: `src/alex/lib/summarize.py`
- Modify: `tests/test_summary_assets.py`

- [ ] **Step 1: Add failing artifact assertions**

Update `test_process_markdown_summary_runs_the_full_pipeline()`:

```python
    assert (result.graph_artifact_dir / "chunks" / "001_deep_work" / "graph.json").is_file()
    assert (
        result.graph_artifact_dir / "chunks" / "001_deep_work" / "selected_subgraph.md"
    ).is_file()
    assert (result.graph_artifact_dir / "document_graph.json").is_file()
    assert (result.graph_artifact_dir / "selected_document_subgraph.md").is_file()
```

- [ ] **Step 2: Change `graph_enhanced_summary()` signature**

Replace `doc_text` graph building with a provided graph:

```python
def graph_enhanced_summary(
    *,
    settings: SummarySettings,
    asset_dir: Path,
    doc_name: str,
    doc_text: str,
    standard_summary: str,
    document_graph: ClaimGraph,
    chunk_graph_bundles: Sequence[ChunkGraphBundle],
    completer: Completer,
) -> GraphEnhancedSummary:
```

Inside it, remove the full-document `build_claim_graph()` call and select from `document_graph`:

```python
selected = select_claim_subgraph(
    document_graph,
    settings=GraphSettings(max_claims=settings.document_graph_max_claims),
)
```

- [ ] **Step 3: Merge chunk graphs before final graph summary**

In `summarize_doc_asset()` before calling `graph_enhanced_summary()`:

```python
document_graph = merge_chunk_graphs(
    doc_name=markdown_path.name,
    source_path=markdown_path.name,
    chunk_graphs=tuple(bundle.graph for bundle in chunk_graph_bundles),
)
```

Pass `document_graph` and `chunk_graph_bundles` into `graph_enhanced_summary()`.

- [ ] **Step 4: Write explicit artifacts**

In artifact writing, replace ambiguous graph files with:

```python
write_graph_json(artifact_dir / "document_graph.json", document_graph)
write_graph_json(artifact_dir / "selected_document_subgraph.json", selected)
(artifact_dir / "selected_document_subgraph.md").write_text(selected_markdown, encoding="utf-8")
```

Write per-chunk artifacts:

```python
chunks_dir = artifact_dir / "chunks"
chunks_dir.mkdir()
for bundle in chunk_graph_bundles:
    chunk_dir = chunks_dir / bundle.chunk_path.stem
    chunk_dir.mkdir()
    write_graph_json(chunk_dir / "graph.json", bundle.graph)
    write_graph_json(chunk_dir / "selected_subgraph.json", bundle.selected)
    (chunk_dir / "selected_subgraph.md").write_text(
        bundle.selected_markdown,
        encoding="utf-8",
    )
```

Optionally write legacy aliases `graph.json` and `selected_subgraph.json` as copies of document graph artifacts to keep existing tests and user muscle memory from breaking immediately.

- [ ] **Step 5: Run summary asset tests**

Run:

```bash
uv run pytest tests/test_summary_assets.py -q
```

Expected: pass.

---

### Task 6: Preserve Graph Disabled Behavior

**Files:**
- Modify: `tests/test_summary_assets.py`
- Modify: `src/alex/lib/summarize.py`

- [ ] **Step 1: Add graph-disabled test**

Add:

```python
def test_process_markdown_summary_skips_chunk_graph_when_graph_disabled(
    tmp_path: Path,
) -> None:
    source = tmp_path / "deep-work.md"
    source.write_text("# Deep Work\n\nBy Cal Newport\n\nBody text.\n", encoding="utf-8")
    completer = RecordingCompleter(
        chunk_responses=["Deep work chunk summary."],
        final_response="Deep work synthesis.",
    )

    result = process_summary_asset(
        SummaryAssetConfig(
            source=source,
            output_path=tmp_path / "summaries",
            summary=SummarySettings(max_workers=1, graph_enhanced=False),
        ),
        completer=completer,
    )

    assert result.graph_artifact_dir is None
    assert not any("source-grounded claims" in call.prompt for call in completer.calls)
    assert "<selected_chunk_graph>" not in completer.chunk_calls()[0].prompt
```

- [ ] **Step 2: Run the graph-disabled test**

Run:

```bash
uv run pytest tests/test_summary_assets.py::test_process_markdown_summary_skips_chunk_graph_when_graph_disabled -q
```

Expected: pass after pipeline checks `settings.graph_enhanced` before chunk graph work.

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update summary artifact docs**

Change the summary/process-doc descriptions to say the graph pass now builds chunk graphs first, writes per-chunk artifacts under `summary_graph/chunks/`, then writes merged document graph artifacts.

- [ ] **Step 2: No doc test needed**

No command required for README-only edits.

---

### Task 8: Final Verification

**Files:**
- All touched files

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_claim_graph.py tests/test_summary_assets.py tests/test_prompt_templates.py -q
```

Expected: pass.

- [ ] **Step 2: Run formatting/lint task if available**

Check `Justfile`. If there is a focused lint/format target, run it through `just`. If not, run:

```bash
uv run ruff check src tests
```

Expected: pass.

- [ ] **Step 3: Inspect git diff read-only**

Run:

```bash
git diff -- docs/superpowers src/alex/lib src/alex/prompts tests README.md
```

Expected: only chunk-first graph implementation, tests, prompts, docs.
