# Plan 002: Enrich book extraction with standard vocabularies

> Selected and implemented following the user's 2026-10-04 instruction.
> The original design and verification gates are retained below; the implementation
> record distinguishes completed checks from verification still outstanding.

## Status and scope

- **Status:** DONE — implementation and requested book regeneration complete;
  regression tests and two-source fixtures remain unverified.
- **Priority:** P1, product direction.
- **Effort:** L; deliver through the milestones below.
- **Risk:** Medium, primarily semantic mappings and identity handling.
- **Depends on:** the existing schema-2 ontology generator and exporter in the
  current worktree; no dependency on advisor plan 001.
- **Planned at:** commit `f75f59c`, 2026-10-04, including uncommitted ontology work.
- **User-selected compatibility policy:** allow optional new fields in
  `ontology.json`, while preserving every existing field and its meaning.
  Add a single optional, independently versioned `enrichment` section.

## Purpose and competency questions

Make independently extracted book graphs queryable using shared terminology,
while preserving the author's specialized vocabulary, logical qualifications,
and exact evidence. Use standard vocabularies for document infrastructure and
an explicit vocabulary catalog for semantic alignment. Shared prefixes alone
will not reconcile different meanings of a domain concept.

The initial graph should answer:

1. Which books discuss a given accepted shared concept?
2. Which passages express a particular claim, and where are those passages?
3. Which people, organizations, and document parts appear in a book?
4. Which themes classify a passage or claim?
5. Which claims are explicit statements, interpretations, or externally sourced?
6. Which extraction activity, model, and prompt produced an assertion?
7. Which claims does the source explicitly describe as supporting or contradicting
   other claims?
8. Which events or claims describe a supplied date or interval?
9. Which mappings remain proposed, and what evidence supports them?

Scope is the supplied book, source-grounded entities and claims, document
structure, metadata, and extraction provenance. Missing content stays missing.
Do not derive publication dates from copyright years, pages from EPUB part
numbers, an entity's identity from its label, or contradictions from differences
in wording. No automatic truth adjudication is intended.

## Baseline before implementation

Relevant files:

- `src/alex/lib/ontology_models.py`: strict model response and artifact records.
- `src/alex/lib/ontology.py`: prompt budgeting, source passes, evidence alignment,
  merging, logical validation, and atomic single-file output.
- `src/alex/prompts/ontology_extraction/v003.md`: current extraction contract.
- `src/alex/lib/ontology_export.py`: strict artifact loading, logical mappings,
  local IRIs, evidence annotations, and RDF serialization.
- `src/alex/commands/ontology.py`, `ontology_export.py`: injectable Click wrappers.
- `src/alex/lib/markdown_structure.py`: existing header parsing helpers.
- `tests/test_ontology.py`, `test_ontology_export.py`, `test_cli.py`: offline
  generator, exporter, and lightweight-help patterns.

The response contract rejects additions:

```python
# src/alex/lib/ontology_models.py
class OntologyResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class OntologyResponse(OntologyResponseModel):
    concepts: list[ConceptResponse]
    relation_types: list[RelationTypeResponse]
    relationships: list[RelationshipResponse]
```

The persisted artifact is also strict:

```python
# src/alex/lib/ontology_export.py:45
class OntologyArtifact(OntologyResponseModel):
    schema_version: Literal[2]
    created_at: Text
    source: ArtifactSource
    generation: dict[str, object]
    concepts: list[OntologyConcept]
    relation_types: list[OntologyRelationType]
    relationships: list[OntologyRelationship]
```

Relationship logic already distinguishes subject and object quantifiers,
polarity, categorical/typical/possible/conditional strength, conditions, and
rationale. Preserve these fields and their meanings. Source evidence uses
zero-based Python character offsets with exclusive ends into **raw Markdown**,
plus one-based inclusive line numbers. Whitespace alignment retains the exact
source substring and records the original model quote.

`merge_ontology_response` currently hashes concept kind plus normalized label
and relation label, and returns `None`. Those labels cannot establish identity
across books; they can also collide for homonyms within one book. Enrichment
needs explicit reference remapping and ambiguity checks.

The exporter currently emits all `kind="class"` concepts as OWL classes and
all instances as named individuals. Only `subclass_of` and `instance_of` receive
standard predicates. Most evidence and generation information uses
`urn:alex:ontology:metadata:`. Formats are `.ttl`, `.owl`, and `.rdf`;
JSON-LD is not implemented yet.

The existing *How We Learn to Move* artifact has schema 2, 126 concepts and
54 relationships. Keep its existing JSON, Turtle, OWL, and v1 backup as reference
artifacts. The ontology files and other quote/vault work are uncommitted; a
commit-only drift check is insufficient. Read live files and record their hashes
before implementation.

## Design decisions

### 1. Preserve existing fields; add optional enrichment in the same artifact

Existing commands without enrichment retain their response contract and behavior.
New extraction with `--enrich` produces one atomic JSON artifact:

```text
ontology.json
  schema_version: 2
  created_at, source, generation, concepts, relation_types, relationships
  enrichment:                 optional new field
    schema_version: 1         independent version for this extension
    profile, scope, documents, passages, activities, alignments, ...
```

Keep all existing required fields, nested record shapes, quantifiers, and source
coordinates unchanged. Existing schema-2 files without `enrichment` must continue
to load and export. Omit the field entirely on the legacy generation path; do not
add a null field to its output. This does not promise identical extracted contents
between different model runs.

The existing strict loader must be deliberately extended to recognize this one
optional field, while rejecting all other unknown fields. Older binaries with the
old `extra="forbid"` validator will reject enriched files; document that they need
an updated reader. This is additive compatibility for the updated application,
not a promise that an old validator accepts a new field.

The optional section contains:

| Section | Responsibility |
| --- | --- |
| `source_sha256` | Must equal the existing `source.sha256`; bind spans to the supplied text |
| `profile` | Application ontology version, namespace, catalog version and digest |
| `scope` | Purpose, assumptions, competency questions, explicit omissions |
| `documents` | Book/source representation metadata and deterministic structural parts |
| `passages` | Stable spans, source IDs, raw locators, optional normalized selectors |
| `activities` | Extraction run/pass IDs, model agent, prompt/budget, actual timestamps |
| `alignments` | Core entity/predicate IDs, selected standard term, mapping kind, evidence, status |
| `schemes` | SKOS schemes and concept membership, including themes and epistemic statuses |
| `assertions` | Core relationship ID, passage/activity IDs, assertion origin, optional extraction confidence |
| `temporal_references` | Supported temporal expressions, precision, normalized values, evidence |
| `claim_links` | Grounded supports/contradicts links between claim IDs, when available |
| `interpretations` | Optional separate interpretations and their premises; empty by default |

Do not let the model supply timestamps, hashes, final URIs, or source offsets.
Code supplies these. Use typed Pydantic models with `extra="forbid"` and strict
validation for the extension as well. Do not embed a hash of the complete JSON
inside itself. Store vocabulary, prompt, source, and representation hashes instead.

### 2. Use a small, versioned vocabulary catalog

Ship a curated registry of approximately 30–50 relevant terms. Each entry has
its full IRI, vocabulary, term kind, definition, allowed mapping operation,
compatible roles, and any type/usage guard. Prompt using short registry keys;
expand keys into full IRIs in code. Add user-supplied catalogs later through
the same validated format. Never accept invented standard IRIs or fetch remote
ontology documents during extraction/export.

| Concern | Preferred terms and constraints |
| --- | --- |
| Books and named entities | `schema:Book`, `schema:Person`, `schema:Organization`; `schema:Article`, `schema:CreativeWork`, `schema:Event` when supported |
| Structure and metadata | `schema:Chapter`, `dcterms:title`, `creator`, `identifier`, `language`, `hasPart`, `isPartOf`, `subject`, `created`, `issued` |
| Provenance | `prov:Entity`, `Activity`, `SoftwareAgent`, `used`, `wasGeneratedBy`, `wasDerivedFrom`, `wasAssociatedWith` |
| Annotation and spans | `oa:Annotation`, `SpecificResource`, `hasBody`, `hasTarget`, `hasSource`, `hasSelector`, `TextQuoteSelector`, `TextPositionSelector` |
| Themes/classification | `skos:ConceptScheme`, `Concept`, `prefLabel`, `altLabel`, `definition`, `inScheme`, `broader`, `related` |
| Temporal content | `time:hasTime`, `Instant`, `Interval`, `hasBeginning`, `hasEnd`; precision-appropriate XSD literals |

These are selected from [Schema.org Book](https://schema.org/Book),
[Chapter](https://schema.org/Chapter),
[DCMI terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/),
[PROV-O](https://www.w3.org/TR/prov-o/),
[Web Annotation](https://www.w3.org/TR/annotation-model/),
[SKOS](https://www.w3.org/TR/skos-reference/), and
[OWL-Time](https://www.w3.org/TR/owl-time/).

Use the namespaces from the user's request, including `https://schema.org/`
and the standard HTTP IRIs for the W3C vocabularies. Prefix spelling alone is
not identity; persist full IRIs.

Keep source-supported labels, definitions, and aliases even when a mapping is
available. An assertion about “movement variability” must not become an
assertion about a broader standard term just to increase reuse. `part_of` is
not automatically document containment: its use and endpoint types must match.

### 3. Keep the reusable application ontology small

Use a fixed application namespace, initially `urn:alex:ontology:book:`, separate
from the per-source instance namespace. Allow a user-owned absolute namespace
through `--application-iri`; never invent a public HTTPS domain. Use the existing
source-hash namespace for instances unless `--base-iri` is supplied.

Initial custom definitions, created only when used:

| Term | Definition | Parent / domain / range | Purpose |
| --- | --- | --- | --- |
| `book:Claim` | A source-attributed proposition represented by extraction | parent `prov:Entity` | Assertion/provenance |
| `book:Interpretation` | A proposition produced by interpreting supplied evidence | parent `book:Claim` | Interpretive assertion |
| `book:Argument` | A source-supported grouping of claims and their argumentative connections | parent `prov:Entity`; optional | Argument description |
| `book:epistemicStatus` | Records the origin/status of a represented proposition, rather than its objective truth | `book:Claim` → `skos:Concept` | Classification |
| `book:extractionConfidence` | Estimated confidence in accurately extracting an annotation's body | `oa:Annotation` → `xsd:decimal` in [0,1] | Annotation quality |
| `book:interprets` | Identifies the claim interpreted by an interpretation | `book:Interpretation` → `book:Claim` | Interpretation |
| `book:supports` | Records a source-supported argumentative support relationship | `book:Claim` → `book:Claim` | Argument description |
| `book:contradicts` | Records a source-supported argumentative conflict relationship | `book:Claim` → `book:Claim` | Argument description |

Prefer `oa:SpecificResource` for passages, `skos:Concept` for themes,
`dcterms:hasPart` for structure, and `time:hasTime` for temporal references.
Do not add custom counterparts merely because they appeared in the supplied
examples. Keep existing `alex:` metadata terms where no appropriate standard
exists, including JSON IDs, logical qualifications, hashes, and raw line offsets.
Document these retained extensions too.

Each custom term must have an IRI, label, definition, term kind, intended use,
and applicable parent/domain/range. Candidate domains/ranges extracted from
the book remain alternatives in metadata; they do not become global RDFS
constraints. Do not redeclare reused standard properties as custom annotation
properties or import entire vocabularies.

### 4. Distinguish formal classes, topics, and named entities

An alignment record assigns a role such as `formal_class`, `named_entity`, or
`controlled_concept`, without changing the existing kind field's meaning.

- Named people/organizations/books remain `kind="instance"`; accepted standard
  typing adds `rdf:type schema:Person`, etc.
- Domain types used in class membership, taxonomy, or quantified restrictions
  remain `kind="class"`; subtype mappings may use `rdfs:subClassOf` when justified.
- Newly extracted themes/classifications are `kind="instance"`, representing
  `skos:Concept` individuals. Do not create an OWL class for each theme.
- An older class may have a separate SKOS topic descriptor for cross-reference;
  do not silently turn that class into an individual. Retain a documented link
  such as `rdfs:seeAlso` between the resources.
- A controlled concept cannot be used as an OWL restriction filler or domain
  class. Reject inconsistent role/kind/mapping combinations.

Source-defined formal classes remain local and retain their definitions. The
fixed application ontology provides reusable infrastructure, while local domain
terms describe the book's subject matter.

### 5. Make alignment and identity explicit

Vocabulary reuse and real-world identity are separate operations:

- `rdf_type`: type a source entity using an accepted standard class.
- `subclass_of`: relate a local formal type to an appropriate broader type.
- `reuse_property`: use a standard predicate only when its meaning, endpoint
  roles, and RDF/OWL property kind are compatible. Otherwise keep the local
  predicate and record a candidate alignment.
- `skos:closeMatch` / `exactMatch` / `broadMatch`: map controlled concepts in
  different schemes. These do not apply indiscriminately to people or OWL classes.
- Possible entity matches remain proposed records with an explanation; do not
  assert equality. `owl:sameAs`, `owl:equivalentClass`, and
  `owl:equivalentProperty` require explicit reviewed authorization.

Use `proposed`, `accepted`, and `rejected` mapping status. Deterministic catalog
rules can accept straightforward infrastructure mappings. Model-proposed domain
alignments start as proposed; a supplied curated mapping file can authorize them.
Only accepted mappings affect graph semantics and shared-concept queries.

Each semantic mapping records source evidence and the catalog/curated authority
that justifies the target term. Standard definitions are alignment guidance,
not evidence of new facts about the book. A supplied external source may justify
a mapping or external assertion but must have its own provenance.

Local IDs remain source-scoped in exported IRIs even if their label hashes match
another book. Do not silently merge homonyms within a source: enriched responses
must supply a sense discriminator when a label repeats with a different meaning;
disambiguate its core display label before normal merging or reject the conflict.
Apply the same policy to predicates with the same label but different meanings.
Do not retrofit new IDs into stored schema-2 artifacts.

SKOS mapping properties have specific concept-level semantics, and `exactMatch`
is transitive; it needs a stronger review bar than `closeMatch`.
[SKOS mapping specification](https://www.w3.org/TR/skos-reference/#mapping)

### 6. Ground every assertion and record the extraction activity

Build document parts deterministically from Markdown tokens and original line
boundaries. Use existing header helpers where correct, but exclude headings
inside fenced code. Preserve raw source text and coordinates. Recognize chapters,
figures, tables, appendices, and page locators only when the input actually labels
them. An unclassified heading is a section, not an invented chapter.

Passage IDs derive from source SHA-256 plus raw start/end coordinates; repeated
text at different positions produces different passage IDs. Extraction alignment
must select an unambiguous occurrence, not silently choose the first match.
For ambiguous quotes, enrichment proposals may supply copied prefix/suffix
context or a verified containing-section reference; they may not supply trusted
numeric offsets. Pass a locator into the enriched merge path so its core evidence
records use the verified occurrence too. Preserve the legacy default locator.
If repeated text cannot be located reliably, reject or retain an explicitly
unresolved locator for review; do not publish false precision.

Every relationship gets a `book:Claim` node. Use RDF statement fields to describe
its original subject/predicate/object and retain its logical qualifiers. Describing
a statement does not automatically assert it. Supported categorical claims can
still produce the existing formal axioms as book-sourced premises; link their
axiom nodes back to the claim. Typical/possible/conditional/unresolved assertions
keep their current conservative treatment.

Each claim has `prov:wasDerivedFrom` links to passage entities and
`prov:wasGeneratedBy` links to the relevant extraction activity. Each
`oa:Annotation` has the claim as `oa:hasBody` and passage as `oa:hasTarget`.
Do not attach annotation target properties to claims themselves.

Use separate SKOS statuses for explicit book statements, interpretations,
speculation, external assertions, and unknown legacy status. “Typical” is a
logical strength, not evidence that a statement is an interpretation. A faithful
paraphrase of an explicit assertion remains explicit.

Interpretation generation is disabled by default. If later enabled, store it in
the enrichment section with passage and premise references; do not inject inferred facts
into the source-only core relationships or automatically materialize OWL axioms.
Confidence is nullable and describes extraction fidelity, with its estimation
basis recorded. Exact quote matching alone is not a confidence of 1.0.

Correct the supplied timestamp example: put `prov:startedAtTime` and
`prov:endedAtTime` on activities, and `prov:generatedAtTime` on generated entities.
The latter has domain `prov:Entity`, not `prov:Activity`.
[PROV-O](https://www.w3.org/TR/prov-o/#generatedAtTime)

Do not backfill missing start times in legacy artifacts. Their artifact creation
timestamp is known, but it does not identify every model call's start/end.

Web Annotation selectors use normalized text, while existing offsets address raw
Markdown. Keep both coordinate systems explicitly separate. Generate a versioned
plain-text representation with an offset map before producing normalized
`oa:TextQuoteSelector`/`oa:TextPositionSelector` values; target that representation
using `oa:hasSource`. If an exact raw-to-normalized span cannot be mapped, retain
the raw locator and report the normalized selector as unavailable.
[Web Annotation selectors](https://www.w3.org/TR/annotation-model/#selectors)

Document creation, publication, extraction, annotation, and the time described
by an event are distinct. Use supplied dates with their actual precision;
never turn a year into an invented January 1 timestamp. Use `time:hasTime`
and temporal nodes for described time, leaving unresolved expressions intact.
[OWL-Time](https://www.w3.org/TR/owl-time/)

## Implementation milestones

### Milestone 1: Freeze compatibility and implement the enrichment contract

Add typed models in `ontology_enrichment_models.py`, a registry in
`ontology_vocabularies.py`, and the minimal application definitions under
`src/alex/ontologies/book/v001.ttl`. Define the extension's schema-1 models and
source-hash validation. Extend `OntologyArtifact` with a typed optional
`enrichment` field. Add fixtures and tests before connecting model calls.

**Verify:** `uv run pytest tests/test_ontology_enrichment.py tests/test_ontology.py
tests/test_ontology_export.py -q` → existing contracts pass; the known optional
extension loads; all other unknown fields, invalid extension versions, conflicting
source hashes, and dangling references fail.

### Milestone 2: Generate document structure and standard provenance locally

Add `ontology_documents.py` for structural parts, unique raw passages, a
normalized text representation/offset map, and explicit metadata resolution.
Metadata priority is explicit user metadata, source frontmatter, then supported
source statements; record origins and unresolved conflicts. Never use a filename
as a factual title or author. Add helpers in `ontology_enrichment.py` for activity,
agent, and evidence linkage.

Existing core artifacts can receive deterministic structure/provenance when the
exact source is supplied. Their semantic roles, claim origins, and identities
remain unknown unless evidence is reviewed; do not invent model extraction history.

**Verify:** `uv run pytest tests/test_ontology_documents.py
tests/test_ontology_enrichment.py -q` → fenced code, nested headings, CRLF, Unicode,
repeated passages, missing metadata, and raw/normalized offsets behave as specified.

### Milestone 3: Enrich extraction in the same source passes

Add a separate immutable prompt family
`src/alex/prompts/ontology_enriched_extraction/v001.md` with `active.txt`.
Do not rewrite or promote the existing v003 prompt. Define an enriched response
model by extending `OntologyResponse` with typed enrichment proposals. The three
existing arrays and every nested core field remain unchanged; enrichment is
required in the enriched response, and absent in the legacy response.

The prompt takes the source, accumulated core vocabulary, a bounded catalog,
metadata, and optional competency questions supplied through `--requirements`
(a small JSON input describing purpose, boundaries, and questions). It selects source evidence first,
then roles, standard-term keys, assertion status, themes, and temporal expressions.
It emits neither RDF nor JSON-LD. Unknown mappings stay absent/proposed.

In the enriched path, record local-to-canonical concept/relation ID maps and
response relationship-index-to-canonical-edge-ID maps. Prefer a typed merge result
from the existing merger over duplicating its stable-ID logic. Use these maps to
resolve enrichment references only after the core response passes validation.
Reject role, sense, and mapping conflicts before merging the pass.

Count the full rendered prompt, including the catalog and enrichment instructions,
in the current greedy source-budget algorithm. Reserve output for both sections;
retain the one-pass preference and minimal source-pass strategy. Do not add a
routine second semantic enrichment or synthesis call. Report input passes and
output-budget limits accurately; fitting the source does not guarantee coverage.

**Verify:** `uv run pytest tests/test_ontology.py
tests/test_ontology_enrichment.py tests/test_prompt_templates.py -q` → a fitting
source uses one fake completion; split sources preserve IDs and enrichment;
truncated/invalid output publishes nothing; the legacy path is unchanged.

### Milestone 4: Add standard graph projection and JSON-LD

Keep the legacy exporter path intact. Add a standard projection path that combines
validated core JSON and its optional enrichment. Separate application definitions,
book entities/claims, and provenance in code; export a portable combined graph
by default, with separate ontology and instance artifacts available in bundle mode.

Reuse `formalize_relationship` and preserve its quantifier mappings. Handle accepted
standard predicates using catalog property compatibility checks; an incompatible
mapping stays descriptive rather than becoming an OWL restriction. Do not reuse
the legacy blanket declaration of standard terms as annotation properties in the
standard projection.

Add `.jsonld` serialization to `ontology-export`, with an embedded, versioned
context that requires no network resolution. Serialize from the RDF graph and
check RDF isomorphism after parsing, exactly as for Turtle/RDF/XML. A compact
context is presentation; it does not replace the logical mappings.

**Verify:** `uv run pytest tests/test_ontology_export.py
tests/test_ontology_standard_export.py -q` → legacy expectations remain valid;
standard Turtle, RDF/XML, and JSON-LD parse to equivalent graphs; quantifier,
negation, qualified-claim, and provenance tests pass.

### Milestone 5: Expose the workflow and validate/report it

Proposed new flags, preserving existing positional arguments:

```bash
# One extraction workflow; writes schema-2 JSON with optional enrichment.
alex ontology book.md artifacts/book.ontology.json --enrich \
  --metadata book-metadata.json --vocabulary shared-vocabulary.json

# Enrichment is read from the same validated artifact.
alex ontology-export artifacts/book.ontology.json artifacts/book.jsonld

# Bundle/report options belong to the same exporter.
alex ontology-export artifacts/book.ontology.json artifacts/book.ttl \
  --report artifacts/book.ontology-report.md
```

Flags above are planned behavior, not commands currently available. Metadata and
vocabulary inputs are optional. The exporter defaults to the standard projection
when valid enrichment is present and to the existing projection otherwise;
provide `--profile standard|legacy` for explicit selection. A standard projection
without enrichment fails with a clear error. Never ignore invalid enrichment in
order to fall back silently.

An optional `--bundle OUTPUT_DIR` writes the application ontology, instance graph,
requested serialization, and A–H report together; keep it separate from the
normal single-export path. The instance graph includes the supporting provenance.
Bundle files share the same application namespace and source identities.

Keep output protection and `--force` behavior. Validate the complete combined
artifact before publishing it through the current atomic single-file writer.
Check output paths and input flags before paid calls. Additional bundle/report
files need staged writes and a completion manifest, but cannot compromise the
validity of the primary JSON artifact. Append optional config fields so existing
positional constructor use and injectable command factories keep working.

Generate the requested A–H report deterministically from the validated artifacts:
scope, competency questions, custom-term inventory, controlled schemes, application
Turtle, instance Turtle, evidence table, and validation. Link large Turtle sections
to accompanying files. Give every extracted relationship a row, including known
gaps and nullable confidence; do not let a prose report add facts.

Ship a small versioned SHACL shapes file covering claim evidence/provenance,
annotation body/target roles, selector coordinates, confidence bounds, timestamps,
mapping kinds, and custom definitions. If `pyshacl` is adopted, add it through uv
and run with inference disabled and remote imports disabled. Structural validation
does not establish the factual truth of a claim or complete logical consistency.
[SHACL specification](https://www.w3.org/TR/shacl/)

**Verify:** `uv run pytest tests/test_ontology_enrichment.py
tests/test_ontology_standard_export.py tests/test_cli.py -q` → CLI factories accept
fakes; help imports remain lightweight; invalid shapes and conflicting source hashes fail
before publication; report rows cover every relationship.

### Milestone 6: Demonstrate interoperability on two sources

Use deterministic two-book fixtures with a shared accepted topic and a same-label
homonym. Query the union using standard predicates and approved topic mappings.
The shared concept is discoverable across both sources, while the homonyms remain
separate. Assert passage provenance and extraction activity for every claim.

After offline gates pass, manually run the enriched Sol extractor on the existing
*How We Learn to Move* source into a **new experiment directory**, with enough
output reservation. Do not replace its current artifacts. Record prompt/model,
input/output budget, pass count, mapping proposals/acceptances, selector availability,
and validation results. Review a sample of accepted typings, domain mappings,
conditional claims, and purported contradictions against the original text.
One book validates extraction; two independent source fixtures validate cross-book
joins. Do not report semantic accuracy from syntax validation alone.

**Verify:** `uv run pytest tests/test_ontology_interoperability.py -q` → standard
SPARQL queries return the expected two sources and exclude the homonym. The manual
book output loads under the updated schema-2 loader, legacy fixtures still load,
and all enrichment references resolve.

## Files in scope for future implementation

Existing files: `README.md`, `pyproject.toml`, `uv.lock`,
`src/alex/commands/ontology.py`, `ontology_export.py`,
`src/alex/lib/ontology.py`, `ontology_export.py`, and related ontology/CLI tests.
Modify `ontology_models.py` only to add a separate enriched response model or
typed merge result; existing core fields and strictness remain unchanged. In
`ontology_export.py`, add the single typed optional artifact extension.

New files: `src/alex/lib/ontology_enrichment_models.py`,
`ontology_enrichment.py`, `ontology_vocabularies.py`, `ontology_documents.py`,
`src/alex/prompts/ontology_enriched_extraction/{active.txt,v001.md}`,
`src/alex/ontologies/book/v001.ttl`, `src/alex/ontologies/book/shapes-v001.ttl`,
and the test modules named in the milestones.

Do not change summary workflows, quote extraction/evals, `process_vault.py`,
historical prompts, the source book, existing vault artifacts, or unrelated
advisor plans. Preserve other workers' edits in shared files such as README and
dependency manifests. No graph database, indexing service, automatic web entity
search, or whole-ontology imports are required. Rich external-source ingestion,
automatic inference, a mapping-review UI, and named-graph dataset formats are
follow-up features, not requirements for this initial implementation.

## Verification commands and acceptance criteria

Before implementation, capture the current status and focused test baseline.
Prior work reported unrelated vault test failures; establish their current state
rather than treating that historical report as today's test result.

| Gate | Command | Expected |
| --- | --- | --- |
| Existing baseline | `uv run pytest tests/test_ontology.py tests/test_ontology_export.py tests/test_cli.py -q` | Existing tests pass |
| Full ontology suite | `uv run pytest tests/test_ontology*.py tests/test_cli.py tests/test_prompt_templates.py -q` | All relevant tests pass offline |
| Lint | `uv run ruff check` | No new errors; distinguish unrelated baseline issues |
| Formatting | `uv run ruff format --check` | Changed files conform |
| Types | `uv run mypy` | No new errors |
| Diff hygiene | `git diff --check` | Exit 0 |
| CLI help | `uv run alex ontology --help` and `uv run alex ontology-export --help` | New flags documented; no model calls |
| Integration regression | `uv run pytest` | No failures introduced over recorded baseline |

Done requires all of the following:

- Core schema version 2, existing fields, logical meanings, and legacy behavior
  are preserved; only the named optional extension is added to its strict model.
- Legacy files load unchanged; enriched files validate both their core and extension.
- Every enrichment reference resolves, and its source hash matches the core source.
- Straightforward standard vocabulary reuse is visible in exported triples;
  specialized concepts keep source-supported meanings.
- Every extracted claim links to source evidence and an extraction activity;
  unknown legacy history is explicitly unknown.
- Themes are SKOS individuals; formal classes remain valid restriction fillers.
- Proposed alignments do not assert identity or change logical axioms.
- No automatic `owl:sameAs` or semantic equivalence assertions are introduced.
- Raw offsets remain exact, normalized selectors address their declared text
  representation, and repeated quotes do not receive false locators.
- Source assertions, interpretations, external claims, and logical strength
  remain distinct dimensions.
- Turtle, RDF/XML, and JSON-LD represent equivalent output graphs.
- A–H reporting and SHACL validation are reproducible and offline.
- Two-source queries demonstrate shared accepted terminology without label merges.
- The manual book experiment is saved separately and its limitations recorded.
- No unrelated code or vault artifacts are changed by implementation.

## Stop conditions and maintenance

Stop and report if the current strict contracts or logical mappings differ
materially from these excerpts, source hashes do not
match, or a proposed mapping requires equality/equivalence without a reviewed
authority. Reject incomplete model output rather than publishing partial graphs.

Treat vocabulary catalogs, application definitions, normalization algorithms,
and enriched prompts as independently versioned contracts. Review catalog updates
for changes to meaning, not just additions. Keep legacy export available for
compatibility; compare its behavior explicitly whenever shared formalization code
changes. Future cross-book reasoning must retain provenance and avoid turning
source-attributed premises into globally accepted facts by accident.

## Implementation record — 2026-10-04

The user authorized implementation and regeneration of the existing book JSON.
That later instruction superseded this plan's experiment-only publication limit.
All existing schema-2 fields and logical quantifiers remain intact. Optional
`enrichment` schema version 1 records metadata, document structure, passages,
activities, alignment proposals, themes, assertions, and temporal references.

Implemented `--enrich`, metadata/catalog/requirements inputs, an application IRI,
and optional capture of original model responses. The versioned enriched prompt
uses the same source-pass budgeting as the existing extractor. Standard export
now supports Turtle, RDF/XML, JSON-LD, application/instance bundles, an A–H
report, SHACL validation, and serialization round trips. Legacy export remains
available. Curated catalogs permit shared topic mappings; uncertain alignments
stay proposed, and automatic identity/equivalence assertions are rejected.

### Requested book regeneration

- Source: *How We Learn to Move*, Rob Gray, in the existing Obsidian asset folder.
- Source SHA-256:
  `70e06226c672adcaefe3d6b822b29d431fa7376cd9609db243c7c9e8c03b3f67`.
- Model: `openai/gpt-6.1-sol`, model-default reasoning; one completed model call
  and one source pass. An initial `reasoning_effort=high` attempt was rejected
  locally by LiteLLM before a provider call.
- Prompt: `ontology_enriched_extraction/v001`; 83,205 prompt tokens, 65,536
  output tokens reserved, 854,416-token input budget.
- Output: 95 concepts, 17 relation types, 40 relationships, 7 themes, 136 source
  passages, and one extraction activity. Seven standard typings are accepted;
  the proposed author-property mapping remains proposed.
- Document structure: one book, one source, 15 chapters, four sections, and one
  appendix. Chapter recognition was refreshed from explicit converted-EPUB
  headings without another model call. EPUB part markers are not page numbers.
- Two year-precision temporal references; no unsupported publication date,
  interpretation, or argumentative links were added.
- Primary files: `ontology.json`, `ontology.ttl`, `ontology.owl`, and
  `ontology.jsonld`; supplementary files in `ontology-bundle/`. Full RDF graph:
  5,564 triples, 12 formalized relationships, 28 qualified annotation records.
- Previous JSON, Turtle, and OWL files were backed up with checked hashes to
  `ontology-backups/20261004T190322691408Z/` within the same asset folder.
  `ontology.v1.json` remains untouched. Staged files and the original Sol response
  remain in `ontology-enriched-experiment/`.

### Completed verification and limits

- `uv run ruff check`: passed; formatting check: 140 files formatted.
- `uv run mypy`: passed, 137 source files.
- `git diff --check` and both command help invocations: passed.
- Strict legacy and enriched loading, source SHA matching, and preservation of
  existing top-level/core-record fields: checked on the actual artifacts.
- All 291 core/enrichment evidence records match their exact raw-source slices
  and line coordinates. All 136 normalized text selectors match their declared
  representation. All 40 relationships have passage and activity provenance.
- SHACL conforms. Turtle, RDF/XML, and JSON-LD exports are isomorphic; bundle
  checksums match the files. Legacy JSON-LD export retains its 2,795 triples.
- No tests were added or run during this implementation turn. The planned
  regression suite and two-source interoperability fixtures remain outstanding.
  Successful source grounding and shape validation do not establish semantic
  accuracy, ontology completeness, or cross-book matching quality.

### Follow-up: native standard names and types

The user's next request was to expose common entity categories and metadata
directly in the local JSON, and embed a richer vocabulary in the prompt. Added
optional concept fields `type` (an array of approved compact vocabulary keys),
`name` (the source-grounded label), and `title` (the primary book's sourced title).
`kind` continues to specify the logical role for compatibility and quantifiers.
Formal classes use `owl:Class`; unsupported individual categories retain
`owl:NamedIndividual`. A defined-term or topic individual is kept distinct from
the formal class of things denoted by that term.

- Added immutable enriched prompt `v002`, with native type-selection examples
  and a 56-term embedded application profile. The richer Schema.org catalog
  includes Place, Product, DefinedTerm, Dataset, LearningResource, PodcastSeries,
  Action, and sports/education types. Supplied curated catalogs remain supported.
- Native type choices use exact concept evidence to create approved alignment
  records; unknown or unapproved type choices are rejected. Proposed mappings
  remain separate. Multiple types are supported, with person/organization
  ambiguity guards.
- The full book still fits in one source pass: 84,794 prompt tokens with the
  existing 65,536-token output reservation.
- A fresh `v002` Sol call was rejected by the provider because the API account
  had no remaining credits. No new model response was produced. The existing
  book JSON was instead refreshed deterministically from its seven previously
  accepted typings and source-grounded title. All prior core, enrichment,
  evidence, and quantifier values are preserved; generation provenance retains
  the actual `v001` extraction and records the native-field postprocessing.
- Primary JSON now contains five `schema:Person` entities, one `schema:Book`
  with `title`, and one `schema:CreativeWork`; all 95 concepts expose names and
  types. Existing formal classes were not reclassified from inferred labels.
- The updated standard graph contains 5,659 equivalent triples; the additional
  95 triples expose source-grounded `schema:name` values. Counts and logical
  formalization remain unchanged.
- Previous JSON and all three standard exports plus the bundle were backed up
  under `ontology-backups/20261004T192638486201Z/`, with a checksum manifest.
  Staged updated files remain under `ontology-native-terminology-experiment/`.
- Ruff, formatting, MyPy, source/field preservation, strict loading, SHACL, and
  RDF round-trip checks pass. No tests were added or run. The new prompt's live
  extraction quality remains unverified because of the credit failure.

### Requested fresh v002 regeneration

The user subsequently requested another full-book regeneration. The Sol request
completed in one source pass with the native-type prompt: 84,794 prompt tokens,
65,536 output tokens reserved, and one actual model call. The original response
and request metadata are retained in `ontology-regenerated-v002/responses/`.

Validation initially rejected two evidence issues. The article citation
"Gray, R. (2017). Transfer of training from virtual to real baseball batting.
Frontiers in Psychology." appears in a figure caption and in the bibliography;
an exact adjacent-context hint selects its explicit bibliography entry. One
theme quote used lowercase "this" where the source sentence starts with "This";
the initial capital was restored by copying the unique exact source sentence.
The original model response was preserved, and both corrections are documented
in `ontology-regenerated-v002/response-recovery.json` alongside the corrected
response and checksums. No additional model call was needed. The request prompt
SHA-256 was reproduced, and the original extraction start/end timestamps were
retained when rebuilding the artifact through the normal merge/validation helpers.

Published output now contains:

- 111 concepts (74 formal classes and 37 individuals), 20 relation types,
  45 relationships, 9 themes, and 182 source passages.
- Native types include 12 people, 3 organizations, 3 books, 2 articles,
  14 defined terms, one podcast series, one place, and one product. The primary
  book also has the LearningResource type and its source-grounded title.
- 38 accepted typings and one proposed mapping; no extracted temporal or
  argumentative links in this run.
- 7,869 equivalent RDF triples: 21 relationships formalized and 24 retained
  as qualified annotations. All 45 claims retain passage/activity provenance.
- All 399 core/enrichment evidence records match the actual source and line
  coordinates; all 182 normalized selectors match their declared representation.
  Strict JSON/catalog/native-field validation, SHACL, serialization round trips,
  and bundle checksums passed. These checks do not establish complete coverage
  or a semantic accuracy score.

The prior JSON, all three RDF exports, and the report bundle were preserved with
checksums under `ontology-backups/20261004T194559243195Z/`. Primary `ontology.json`,
Turtle, OWL, JSON-LD, and `ontology-bundle/` were refreshed from the new artifact.
No source code or tests were changed for this regeneration.
