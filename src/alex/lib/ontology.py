"""Generate a per-document ontology with as few source passes as possible."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from bisect import bisect_right
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from alex.lib.llm import (
    Completer,
    LiteLlmCompleter,
    LiteLlmTokenCounter,
    ModelTokenLimits,
    TokenCounter,
    model_token_limits,
    resolve_ontology_model,
)
from alex.lib.ontology_models import (
    OntologyBudget,
    OntologyConcept,
    OntologyOutput,
    OntologyPass,
    OntologyRelationship,
    OntologyRelationType,
    OntologyResponse,
    SourceEvidence,
)
from alex.lib.prompt_templates import PromptTemplate, load_prompt

DEFAULT_ONTOLOGY_OUTPUT_TOKENS = 32_768
DEFAULT_ONTOLOGY_SAFETY_MARGIN = 2_048


class OntologyError(ValueError):
    pass


@dataclass(frozen=True)
class OntologyConfig:
    source: Path
    output_path: Path | None = None
    model: str = field(default_factory=resolve_ontology_model)
    context_window: int | None = None
    max_output_tokens: int | None = None
    safety_margin: int = DEFAULT_ONTOLOGY_SAFETY_MARGIN
    reasoning_effort: str | None = None
    force: bool = False
    dry_run: bool = False
    enrich: bool = False
    metadata: Path | None = None
    vocabulary: Path | None = None
    requirements: Path | None = None
    application_iri: str = "urn:alex:ontology:book:"
    response_dir: Path | None = None


@dataclass(frozen=True)
class OntologyMergeResult:
    concept_ids: dict[str, str]
    relation_ids: dict[str, str]
    relationship_ids: dict[int, str]


@dataclass
class OntologyState:
    concepts: dict[str, OntologyConcept] = field(default_factory=dict)
    relation_types: dict[str, OntologyRelationType] = field(default_factory=dict)
    relationships: dict[str, OntologyRelationship] = field(default_factory=dict)

    def vocabulary(self) -> str:
        """Carry definitions and identity forward without repeating evidence/edges."""
        return json.dumps(
            {
                "concepts": [
                    {
                        "id": item.id,
                        "label": item.label,
                        "kind": item.kind,
                        **({"type": item.type} if item.type is not None else {}),
                        "definition": item.definition,
                        "aliases": item.aliases,
                    }
                    for item in self.concepts.values()
                ],
                "relation_types": [
                    {
                        "id": item.id,
                        "label": item.label,
                        "definition": item.definition,
                        "domain": item.domain,
                        "range": item.range,
                    }
                    for item in self.relation_types.values()
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def resolve_ontology_budget(
    config: OntologyConfig, limits: ModelTokenLimits
) -> OntologyBudget:
    context = (
        config.context_window
        if config.context_window is not None
        else limits.input_tokens
    )
    if context is None or context <= 0:
        raise OntologyError(
            f"No input limit is known for {config.model}; set --context-window "
            "to the provider's supported token limit."
        )
    output = config.max_output_tokens
    if output is None:
        output = min(
            DEFAULT_ONTOLOGY_OUTPUT_TOKENS,
            limits.output_tokens or DEFAULT_ONTOLOGY_OUTPUT_TOKENS,
        )
    if output <= 0 or config.safety_margin < 0:
        raise OntologyError(
            "Output tokens must be positive; safety margin cannot be negative."
        )
    if limits.output_tokens is not None and output > limits.output_tokens:
        raise OntologyError(
            f"{config.model} supports at most {limits.output_tokens} output tokens; "
            "lower --max-output-tokens."
        )
    input_budget = context - output - config.safety_margin
    if input_budget <= 0:
        raise OntologyError(
            "No room for input after reserving output tokens and the safety margin; "
            "lower --max-output-tokens or increase --context-window."
        )
    return OntologyBudget(context, output, config.safety_margin, input_budget)


def generate_ontology(
    config: OntologyConfig,
    *,
    completer: Completer | None = None,
    token_counter: TokenCounter | None = None,
    limits_resolver: Callable[[str], ModelTokenLimits] = model_token_limits,
    progress: Callable[[str], None] | None = None,
) -> OntologyOutput:
    if config.source.suffix.casefold() not in {".md", ".markdown"}:
        raise OntologyError(
            "Ontology input must be a Markdown file (.md or .markdown)."
        )
    output_path = config.output_path or config.source.with_suffix(".ontology.json")
    if output_path.resolve() == config.source.resolve() or (
        output_path.exists() and output_path.samefile(config.source)
    ):
        raise OntologyError("The ontology output cannot replace the source Markdown.")
    if output_path.suffix.casefold() != ".json":
        raise OntologyError("The ontology output path must end in .json.")
    if (
        output_path.exists()
        and not config.dry_run
        and (output_path.is_dir() or not config.force)
    ):
        raise OntologyError(
            f"Output already exists: {output_path}. Use --force to replace it."
        )
    source_bytes = config.source.read_bytes()
    markdown = source_bytes.decode("utf-8")
    if not markdown.strip():
        raise OntologyError("The source Markdown is empty.")
    budget = resolve_ontology_budget(config, limits_resolver(config.model))
    counter = token_counter if token_counter is not None else LiteLlmTokenCounter()
    client = (
        completer
        if completer is not None
        else LiteLlmCompleter(reasoning_effort=config.reasoning_effort)
    )
    template = load_prompt(
        "ontology_enriched_extraction" if config.enrich else "ontology_extraction"
    )
    enrichment_state = None
    prompt_values: dict[str, str] = {}
    if not config.enrich and (
        config.metadata is not None
        or config.vocabulary is not None
        or config.requirements is not None
    ):
        raise OntologyError("Metadata, vocabulary, and requirements need --enrich.")
    if config.enrich:
        from alex.lib.ontology_enrichment import (
            EnrichmentState,
            enrichment_prompt_context,
        )
        from alex.lib.ontology_enrichment_models import BookMetadata, Scope
        from alex.lib.ontology_vocabularies import load_catalog

        metadata = (
            BookMetadata.model_validate_json(config.metadata.read_text())
            if config.metadata is not None
            else None
        )
        scope = (
            Scope.model_validate_json(config.requirements.read_text())
            if config.requirements is not None
            else Scope()
        )
        catalog = load_catalog(config.vocabulary)
        enrichment_state = EnrichmentState.create(
            markdown,
            hashlib.sha256(source_bytes).hexdigest(),
            catalog,
            scope,
            metadata,
            config.application_iri,
        )
        prompt_values["context"] = enrichment_prompt_context(catalog, metadata, scope)
    response_directory = (
        config.response_dir / datetime.now(UTC).strftime("run-%Y%m%dT%H%M%S%fZ")
        if config.response_dir is not None
        else None
    )
    line_offsets = [0, *(match.end() for match in re.finditer("\n", markdown))]
    state = OntologyState()
    passes: list[OntologyPass] = []
    start = 0
    while start < len(markdown):
        end, prompt, tokens = select_source_pass(
            markdown=markdown,
            start=start,
            vocabulary=state.vocabulary(),
            template=template,
            model=config.model,
            input_budget=budget.input_budget,
            counter=counter,
            prompt_values=prompt_values,
        )
        record = OntologyPass(
            number=len(passes) + 1,
            char_start=start,
            char_end=end,
            line_start=bisect_right(line_offsets, start),
            line_end=bisect_right(line_offsets, end - 1),
            prompt_tokens=tokens,
        )
        if progress is not None:
            action = "Planned" if config.dry_run else "Extracting"
            progress(
                f"{action} pass {record.number}: lines "
                f"{record.line_start}-{record.line_end}, "
                f"{tokens:,}/{budget.input_budget:,} input tokens."
            )
        if not config.dry_run:
            started_at = datetime.now(UTC).isoformat()
            raw = client.complete(
                prompt=prompt, model=config.model, max_tokens=budget.max_output_tokens
            )
            ended_at = datetime.now(UTC).isoformat()
            if response_directory is not None:
                write_ontology_text(
                    response_directory / f"pass-{record.number:03d}.response.txt",
                    raw,
                    force=False,
                )
                write_ontology_artifact(
                    response_directory / f"pass-{record.number:03d}.request.json",
                    {
                        "model": config.model,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "started_at": started_at,
                        "ended_at": ended_at,
                        "pass": asdict(record),
                    },
                    force=False,
                )
            try:
                response = parse_ontology_response(raw, enrich=config.enrich)
                locator = None
                if enrichment_state is not None:
                    from alex.lib.ontology_enrichment import (
                        EvidenceLocator,
                        prepare_enriched_response,
                    )
                    from alex.lib.ontology_enrichment_models import (
                        EnrichedOntologyResponse,
                        ExtractionActivity,
                    )

                    assert isinstance(response, EnrichedOntologyResponse)
                    prepare_enriched_response(response)
                    locator = EvidenceLocator(
                        markdown[start:end], response.enrichment.evidence_hints
                    )
                merged = merge_ontology_response(
                    state,
                    response,
                    passage=markdown[start:end],
                    start=start,
                    line_offsets=line_offsets,
                    evidence_locator=locator,
                )
                if enrichment_state is not None:
                    assert isinstance(response, EnrichedOntologyResponse)
                    assert locator is not None
                    activity = ExtractionActivity(
                        id=stable_id("activity", started_at, str(record.number)),
                        pass_number=record.number,
                        model=config.model,
                        prompt_name=template.name,
                        prompt_version=template.version,
                        prompt_sha256=hashlib.sha256(
                            template.text.encode()
                        ).hexdigest(),
                        started_at=started_at,
                        ended_at=ended_at,
                        char_start=start,
                        char_end=end,
                    )
                    enrichment_state.merge(response, merged, state, locator, activity)
                    activity.ended_at = datetime.now(UTC).isoformat()
            except ValueError as error:
                raise OntologyError(f"Pass {record.number}: {error}") from error
        passes.append(record)
        start = end
    if not config.dry_run:
        artifact: dict[str, object] = {
            "schema_version": 2,
            "created_at": datetime.now(UTC).isoformat(),
            "source": {
                "path": str(config.source.resolve()),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "characters": len(markdown),
            },
            "generation": {
                "model": config.model,
                "reasoning_effort": config.reasoning_effort,
                "prompt": {
                    "name": template.name,
                    "version": template.version,
                    "sha256": hashlib.sha256(template.text.encode()).hexdigest(),
                },
                "budget": asdict(budget),
                "passes": [asdict(record) for record in passes],
                "model_calls": len(passes),
                "validation": [
                    "json_schema",
                    "references",
                    "exact_source_quotes",
                    "taxonomy_kinds",
                    "logical_quantifiers",
                    "acyclic_subclass_hierarchy",
                ],
            },
            "concepts": [concept_record(item) for item in state.concepts.values()],
            "relation_types": [asdict(item) for item in state.relation_types.values()],
            "relationships": [asdict(item) for item in state.relationships.values()],
        }
        if enrichment_state is not None:
            from alex.lib.ontology_export import parse_ontology_artifact

            artifact["enrichment"] = enrichment_state.artifact().model_dump(mode="json")
            validated = parse_ontology_artifact(
                json.dumps(artifact, ensure_ascii=False)
            )
            from alex.lib.ontology_standard_export import (
                application_graph,
                standard_graph,
                validate_standard_graph,
            )

            graph, _ = standard_graph(
                validated, f"urn:alex:ontology:sha256:{validated.source.sha256}"
            )
            graph += application_graph(config.application_iri, graph)
            validate_standard_graph(graph, config.application_iri)
        write_ontology_artifact(output_path, artifact, force=config.force)
    return OntologyOutput(
        output_path=None if config.dry_run else output_path,
        model=config.model,
        budget=budget,
        passes=tuple(passes),
        concept_count=len(state.concepts),
        relation_type_count=len(state.relation_types),
        relationship_count=len(state.relationships),
    )


def select_source_pass(
    *,
    markdown: str,
    start: int,
    vocabulary: str,
    template: PromptTemplate,
    model: str,
    input_budget: int,
    counter: TokenCounter,
    prompt_values: dict[str, str] | None = None,
) -> tuple[int, str, int]:
    def candidate(end: int) -> tuple[str, int]:
        prompt = template.render(
            vocabulary=vocabulary, source=markdown[start:end], **(prompt_values or {})
        )
        return prompt, counter.count(prompt=prompt, model=model)

    end = len(markdown)
    prompt, tokens = candidate(end)
    if tokens <= input_budget:
        return end, prompt, tokens
    _, overhead = candidate(start)
    if overhead >= input_budget:
        raise OntologyError(
            "The prompt and accumulated vocabulary fill the input budget; "
            "increase --context-window or lower --max-output-tokens."
        )
    # Pack the longest fitting prefix, rather than splitting by chapter or using
    # the summary pipeline's much smaller chunk sizes. Never discard source text.
    low, high = start, end
    while low + 1 < high:
        middle = (low + high) // 2
        _, tokens = candidate(middle)
        if tokens <= input_budget:
            low = middle
        else:
            high = middle
    if low == start:
        raise OntologyError("The input budget cannot fit any source text.")
    # Prefer a paragraph/line boundary in the last 5% of the fitting prefix.
    floor = start + int((low - start) * 0.95)
    boundary = markdown.rfind("\n\n", floor, low)
    if boundary >= 0:
        low = boundary + 2
    else:
        boundary = markdown.rfind("\n", floor, low)
        if boundary >= 0:
            low = boundary + 1
    prompt, tokens = candidate(low)
    # Tokenization at a new boundary can change slightly; check the actual prompt.
    while tokens > input_budget and low > start:
        low -= 1
        prompt, tokens = candidate(low)
    if low == start:
        raise OntologyError("The input budget cannot fit any source text.")
    return low, prompt, tokens


def parse_ontology_response(raw: str, *, enrich: bool = False) -> OntologyResponse:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.partition("\n")[2].removesuffix("```").strip()
    try:
        if enrich:
            from alex.lib.ontology_enrichment_models import EnrichedOntologyResponse

            return EnrichedOntologyResponse.model_validate_json(text)
        response = OntologyResponse.model_validate_json(text)
        if any(item.type is not None for item in response.concepts):
            raise OntologyError("Semantic type selection requires --enrich.")
        return response
    except ValidationError as error:
        detail = error.errors(include_input=False)[0]
        raise OntologyError(
            f"Invalid ontology JSON ({detail['type']}). "
            "If the response was truncated, increase --max-output-tokens "
            "or lower --context-window."
        ) from error


def normalize_term(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:16]
    return f"{prefix}_{digest}"


def merge_ontology_response(
    state: OntologyState,
    response: OntologyResponse,
    *,
    passage: str,
    start: int,
    line_offsets: list[int],
    evidence_locator: Callable[[str], tuple[int, str]] | None = None,
) -> OntologyMergeResult:
    def evidence(quotes: list[str]) -> tuple[SourceEvidence, ...]:
        records: list[SourceEvidence] = []
        for quote in dict.fromkeys(quotes):
            if evidence_locator is not None:
                offset, source_quote = evidence_locator(quote)
            else:
                offset, source_quote = passage.find(quote), quote
            if offset < 0:
                # Models normalize NBSPs and line wraps. Align whitespace only,
                # keeping every word and punctuation character unchanged, then
                # store the exact original substring and retain the model text.
                pattern = r"\s+".join(re.escape(word) for word in quote.split())
                match = re.search(pattern, passage)
                if match is None:
                    raise OntologyError(
                        "An evidence quote does not occur verbatim "
                        "in this source passage."
                    )
                offset = match.start()
                source_quote = match.group()
            begin = start + offset
            end = begin + len(source_quote)
            records.append(
                SourceEvidence(
                    source_quote,
                    begin,
                    end,
                    bisect_right(line_offsets, begin),
                    bisect_right(line_offsets, end - 1),
                    quote if source_quote != quote else None,
                    "whitespace_normalized" if source_quote != quote else "exact",
                )
            )
        return tuple(records)

    # Validate against a copy so a rejected pass never partly changes the graph.
    concepts = dict(state.concepts)
    relation_types = dict(state.relation_types)
    relationships = dict(state.relationships)
    concept_refs = {key: key for key in concepts}
    seen: set[str] = set()
    for item in response.concepts:
        if item.id in seen:
            raise OntologyError(f"Duplicate concept ID: {item.id}")
        seen.add(item.id)
        key = stable_id("c", item.kind, normalize_term(item.label))
        if item.id in state.concepts:
            existing = state.concepts[item.id]
            names = {
                normalize_term(name) for name in (existing.label, *existing.aliases)
            }
            if existing.kind != item.kind or normalize_term(item.label) not in names:
                raise OntologyError(
                    f"Concept ID {item.id} was reused for a different meaning."
                )
            key = item.id
        concept_refs[item.id] = key
        quotes = evidence(item.evidence)
        previous = concepts.get(key)
        if previous is None:
            concepts[key] = OntologyConcept(
                key,
                item.label,
                item.kind,
                item.definition,
                unique(item.aliases),
                quotes,
            )
        else:
            aliases = (*previous.aliases, *item.aliases)
            if item.label != previous.label:
                aliases = (*aliases, item.label)
            concepts[key] = replace(
                previous,
                aliases=unique(aliases),
                evidence=unique((*previous.evidence, *quotes)),
            )
    relation_refs = {key: key for key in relation_types}
    seen.clear()
    for item_type in response.relation_types:
        if item_type.id in seen:
            raise OntologyError(f"Duplicate relation type ID: {item_type.id}")
        seen.add(item_type.id)
        if re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", item_type.label) is None:
            raise OntologyError("Relation type labels must be snake_case.")
        key = stable_id("r", item_type.label)
        if item_type.id in state.relation_types:
            if state.relation_types[item_type.id].label != item_type.label:
                raise OntologyError(f"Relation type ID {item_type.id} changed meaning.")
            key = item_type.id
        relation_refs[item_type.id] = key
        domain = resolve_class_refs(item_type.domain, concept_refs, concepts)
        range_ids = resolve_class_refs(item_type.range, concept_refs, concepts)
        quotes = evidence(item_type.evidence)
        previous_type = relation_types.get(key)
        if previous_type is None:
            relation_types[key] = OntologyRelationType(
                key,
                item_type.label,
                item_type.definition,
                domain,
                range_ids,
                quotes,
            )
        else:
            relation_types[key] = replace(
                previous_type,
                domain=unique((*previous_type.domain, *domain)),
                range=unique((*previous_type.range, *range_ids)),
                evidence=unique((*previous_type.evidence, *quotes)),
            )
    edge_refs: dict[int, str] = {}
    for index, edge in enumerate(response.relationships):
        source = resolve_ref(edge.source, concept_refs, "concept")
        target = resolve_ref(edge.target, concept_refs, "concept")
        relation = resolve_ref(edge.relation, relation_refs, "relation type")
        label = relation_types[relation].label
        if label == "subclass_of" and (
            concepts[source].kind != "class" or concepts[target].kind != "class"
        ):
            raise OntologyError("subclass_of requires two classes.")
        if label == "instance_of" and (
            concepts[source].kind != "instance" or concepts[target].kind != "class"
        ):
            raise OntologyError("instance_of requires an instance and a class.")
        key = stable_id(
            "e",
            source,
            relation,
            target,
            normalize_term(edge.description),
            json.dumps(asdict(edge.logic), sort_keys=True, ensure_ascii=False),
        )
        quotes = evidence(edge.evidence)
        edge_refs[index] = key
        previous_edge = relationships.get(key)
        relationships[key] = OntologyRelationship(
            key,
            source,
            relation,
            target,
            edge.description,
            quotes
            if previous_edge is None
            else unique((*previous_edge.evidence, *quotes)),
            edge.logic,
        )
        validate_relationship_logic(relationships[key], concepts, relation_types)
    validate_subclass_hierarchy(concepts, relation_types, relationships)
    state.concepts = concepts
    state.relation_types = relation_types
    state.relationships = relationships
    return OntologyMergeResult(concept_refs, relation_refs, edge_refs)


def unique[T](items: Iterable[T]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(items))


def concept_record(item: OntologyConcept) -> dict[str, object]:
    """Preserve legacy fields; put optional standard names/types first."""
    record = asdict(item)
    native = {}
    for field_name in ("type", "name", "title"):
        value = record.pop(field_name)
        if value is not None:
            native[field_name] = value
    return {"id": record.pop("id"), **native, **record}


def resolve_ref(reference: str, references: dict[str, str], kind: str) -> str:
    try:
        return references[reference]
    except KeyError as error:
        raise OntologyError(f"Unknown {kind} reference: {reference}") from error


def resolve_class_refs(
    references: list[str], ids: dict[str, str], concepts: dict[str, OntologyConcept]
) -> tuple[str, ...]:
    resolved = unique(
        resolve_ref(reference, ids, "concept") for reference in references
    )
    if any(concepts[key].kind != "class" for key in resolved):
        raise OntologyError("Relation domain and range must reference classes.")
    return resolved


def validate_subclass_hierarchy(
    concepts: dict[str, OntologyConcept],
    relation_types: dict[str, OntologyRelationType],
    relationships: dict[str, OntologyRelationship],
) -> None:
    parents: dict[str, set[str]] = {key: set() for key in concepts}
    incoming = dict.fromkeys(concepts, 0)
    for edge in relationships.values():
        if (
            relation_types[edge.relation].label == "subclass_of"
            and edge.logic.subject_quantifier == "all"
            and edge.logic.polarity == "positive"
            and edge.logic.strength == "categorical"
        ):
            parents[edge.source].add(edge.target)
    for targets in parents.values():
        for target in targets:
            incoming[target] += 1
    ready = deque(key for key, count in incoming.items() if count == 0)
    visited = 0
    while ready:
        key = ready.popleft()
        visited += 1
        for target in parents[key]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if visited != len(concepts):
        raise OntologyError("The subclass hierarchy contains a cycle.")


def validate_relationship_logic(
    edge: OntologyRelationship,
    concepts: dict[str, OntologyConcept],
    relation_types: dict[str, OntologyRelationType],
) -> None:
    logic = edge.logic
    source_kind = concepts[edge.source].kind
    target_kind = concepts[edge.target].kind
    if source_kind == "class" and logic.subject_quantifier == "individual":
        raise OntologyError("An individual subject quantifier requires an instance.")
    if source_kind == "instance" and logic.subject_quantifier in {"all", "some"}:
        raise OntologyError("An all/some subject quantifier requires a class.")
    if logic.object_quantifier in {"some", "only"} and target_kind != "class":
        raise OntologyError("A some/only object quantifier requires a target class.")
    if logic.object_quantifier == "value" and target_kind != "instance":
        raise OntologyError("A value object quantifier requires a target instance.")
    if (logic.strength == "conditional") != (logic.condition is not None):
        raise OntologyError("Only conditional relationships must specify a condition.")
    label = relation_types[edge.relation].label
    if label in {"subclass_of", "instance_of"}:
        if logic.object_quantifier != "unspecified":
            raise OntologyError(
                "Taxonomy and membership do not use property filler quantifiers."
            )
        expected = "all" if label == "subclass_of" else "individual"
        if logic.subject_quantifier not in {expected, "unspecified"}:
            raise OntologyError(f"{label} requires a {expected} subject quantifier.")


def write_ontology_artifact(
    path: Path, artifact: dict[str, object], *, force: bool
) -> None:
    write_ontology_text(
        path, json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", force=force
    )


def write_ontology_text(path: Path, text: str, *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        if force:
            temporary_path.replace(path)
        else:
            # Atomic publication also prevents a concurrent run being overwritten.
            os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
