from __future__ import annotations

import hashlib
import json
import re
import sys
import types
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from alex.commands.main import main
from alex.commands.ontology import build_ontology_command
from alex.lib.llm import (
    LiteLlmTokenCounter,
    LlmError,
    ModelTokenLimits,
    model_token_limits,
    resolve_ontology_model,
)
from alex.lib.ontology import (
    OntologyConfig,
    OntologyError,
    OntologyState,
    generate_ontology,
    merge_ontology_response,
    parse_ontology_response,
    resolve_ontology_budget,
)
from alex.lib.ontology_models import OntologyOutput
from alex.lib.prompt_templates import load_prompt
from helpers import CompletionCall

SOURCE = "# Plants\n\nA tree is a plant.\nTrees are also called woody plants.\n"
QUOTE = "A tree is a plant."


class CharacterCounter:
    def count(self, *, prompt: str, model: str) -> int:
        return len(prompt)


class FakeCompleter:
    def __init__(self, response: Callable[[str, int], str]) -> None:
        self.response = response
        self.calls: list[CompletionCall] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append(CompletionCall(prompt, model, max_tokens))
        return self.response(prompt, len(self.calls))


def ontology_payload(quote: str = QUOTE) -> dict[str, Any]:
    return {
        "concepts": [
            {
                "id": "tree",
                "label": "Tree",
                "kind": "class",
                "definition": "A plant.",
                "aliases": ["Woody plant"],
                "evidence": [quote],
            },
            {
                "id": "plant",
                "label": "Plant",
                "kind": "class",
                "definition": "The broader category containing trees.",
                "aliases": [],
                "evidence": [quote],
            },
        ],
        "relation_types": [
            {
                "id": "is_a",
                "label": "subclass_of",
                "definition": "A specialization of a broader class.",
                "domain": ["tree"],
                "range": ["plant"],
                "evidence": [quote],
            },
        ],
        "relationships": [
            {
                "source": "tree",
                "relation": "is_a",
                "target": "plant",
                "description": "Trees are plants.",
                "logic": {
                    "subject_quantifier": "all",
                    "object_quantifier": "unspecified",
                    "polarity": "positive",
                    "strength": "categorical",
                    "condition": None,
                    "rationale": "The source classifies trees as plants.",
                },
                "evidence": [quote],
            },
        ],
    }


def source_config(tmp_path: Path, text: str = SOURCE) -> OntologyConfig:
    source = tmp_path / "book.md"
    source.write_bytes(text.encode("utf-8"))
    return OntologyConfig(
        source=source,
        context_window=100_000,
        max_output_tokens=1_000,
        safety_margin=100,
    )


def run(
    config: OntologyConfig,
    client: FakeCompleter,
) -> OntologyOutput:
    return generate_ontology(
        config,
        completer=client,
        token_counter=CharacterCounter(),
        limits_resolver=lambda _: ModelTokenLimits(100_000, 40_000),
    )


def test_single_pass_writes_grounded_ontology_and_provenance(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    client = FakeCompleter(lambda *_: json.dumps(ontology_payload()))

    result = run(config, client)

    assert result.output_path == tmp_path / "book.ontology.json"
    assert result.concept_count == 2
    assert result.relation_type_count == result.relationship_count == 1
    assert len(client.calls) == len(result.passes) == 1
    assert SOURCE in client.calls[0].prompt
    assert client.calls[0].max_tokens == 1_000
    assert result.output_path is not None
    artifact = json.loads(result.output_path.read_text())
    assert artifact["schema_version"] == 2
    assert artifact["source"]["sha256"] == hashlib.sha256(SOURCE.encode()).hexdigest()
    assert artifact["generation"]["model"] == config.model
    assert artifact["generation"]["prompt"]["version"] == "v003"
    assert artifact["relationships"][0]["logic"]["subject_quantifier"] == "all"
    assert artifact["generation"]["model_calls"] == 1
    concept_ids = {item["id"] for item in artifact["concepts"]}
    assert artifact["relationships"][0]["source"] in concept_ids
    assert artifact["relationships"][0]["target"] in concept_ids
    evidence = artifact["concepts"][0]["evidence"][0]
    assert SOURCE[evidence["char_start"] : evidence["char_end"]] == QUOTE
    assert evidence["line_start"] == evidence["line_end"] == 3
    assert result.passes[0].char_end == len(SOURCE)


@pytest.mark.parametrize("text", ["x" * 24_000, ("é文🙂 paragraph\n\n" * 1_500)])
def test_large_source_packs_near_limit_without_losing_text(
    tmp_path: Path,
    text: str,
) -> None:
    config = source_config(tmp_path, text)
    overhead = len(
        load_prompt("ontology_extraction").render(
            vocabulary=OntologyState().vocabulary(),
            source="",
        )
    )
    config = replace(config, context_window=overhead + 8_000 + 1_100)
    client = FakeCompleter(
        lambda *_: json.dumps(
            {
                "concepts": [],
                "relation_types": [],
                "relationships": [],
            }
        )
    )

    result = run(config, client)

    assert len(client.calls) == 3
    assert "".join(text[p.char_start : p.char_end] for p in result.passes) == text
    assert all(p.prompt_tokens <= result.budget.input_budget for p in result.passes)
    assert result.passes[0].char_start == 0
    for left, right in zip(result.passes, result.passes[1:], strict=False):
        assert left.char_end == right.char_start
    assert result.passes[-1].char_end == len(text)
    for record in result.passes[:-1]:
        assert record.prompt_tokens >= result.budget.input_budget * 0.95


def test_multi_pass_reuses_vocabulary_and_recounts_full_prompt(tmp_path: Path) -> None:
    paragraph = "A tree is a plant.\n\n"
    text = paragraph * 900
    config = source_config(tmp_path, text)
    overhead = len(
        load_prompt("ontology_extraction").render(
            vocabulary=OntologyState().vocabulary(),
            source="",
        )
    )
    config = replace(config, context_window=overhead + 8_000 + 1_100)
    vocabularies: list[dict[str, Any]] = []

    def respond(prompt: str, number: int) -> str:
        match = re.search(
            r"<existing_vocabulary>\n(.*?)\n</existing_vocabulary>",
            prompt,
            flags=re.DOTALL,
        )
        assert match is not None
        vocabulary = json.loads(match.group(1))
        vocabularies.append(vocabulary)
        payload = ontology_payload()
        if number > 1:
            # Existing IDs are valid references without returning the concepts again.
            payload["concepts"] = []
            payload["relation_types"] = []
            by_label = {item["label"]: item["id"] for item in vocabulary["concepts"]}
            payload["relationships"][0].update(
                {
                    "source": by_label["Tree"],
                    "target": by_label["Plant"],
                    "relation": vocabulary["relation_types"][0]["id"],
                }
            )
        return json.dumps(payload)

    client = FakeCompleter(respond)
    result = run(config, client)

    assert len(result.passes) == 3
    assert result.concept_count == 2
    assert result.relationship_count == 1
    assert vocabularies[0]["concepts"] == []
    assert len(vocabularies[1]["concepts"]) == 2
    assert result.passes[1].char_end - result.passes[1].char_start < 8_000
    assert all(call.prompt.count("<source_passage>") == 1 for call in client.calls)
    assert result.output_path is not None
    artifact = json.loads(result.output_path.read_text())
    records = artifact["relationships"][0]["evidence"]
    assert len(records) == 3
    assert all(text[e["char_start"] : e["char_end"]] == QUOTE for e in records)


@pytest.mark.parametrize(
    "failure",
    [
        "quote",
        "concept_ref",
        "relation_ref",
        "domain_ref",
        "domain_instance",
        "duplicate_concept",
        "duplicate_relation",
        "cycle",
        "self_cycle",
        "subclass_kind",
        "instance_kind",
        "relation_label",
        "json",
        "schema",
    ],
)
def test_rejects_invalid_output_and_preserves_existing_artifact(
    tmp_path: Path,
    failure: str,
) -> None:
    config = source_config(tmp_path)
    output = tmp_path / "book.ontology.json"
    output.write_text("prior artifact")
    config = replace(config, force=True)
    payload = ontology_payload()
    if failure == "quote":
        payload["concepts"][0]["evidence"] = ["An invented quote."]
    elif failure == "concept_ref":
        payload["relationships"][0]["target"] = "missing"
    elif failure == "relation_ref":
        payload["relationships"][0]["relation"] = "missing"
    elif failure == "domain_ref":
        payload["relation_types"][0]["domain"] = ["missing"]
    elif failure == "domain_instance":
        payload["concepts"][0]["kind"] = "instance"
    elif failure == "duplicate_concept":
        payload["concepts"].append(payload["concepts"][0])
    elif failure == "duplicate_relation":
        payload["relation_types"].append(payload["relation_types"][0])
    elif failure == "cycle":
        edge = dict(payload["relationships"][0])
        edge.update(source="plant", target="tree")
        payload["relationships"].append(edge)
    elif failure == "self_cycle":
        payload["relationships"][0]["target"] = "tree"
    elif failure == "subclass_kind":
        payload["concepts"][1]["kind"] = "instance"
        payload["relation_types"][0]["range"] = []
    elif failure == "instance_kind":
        payload["relation_types"][0]["label"] = "instance_of"
    elif failure == "relation_label":
        payload["relation_types"][0]["label"] = "IS A"
    elif failure == "schema":
        payload["concepts"][0]["extra"] = "unrecognized"
    raw = '{"concepts": [' if failure == "json" else json.dumps(payload)
    client = FakeCompleter(lambda *_: raw)

    with pytest.raises(OntologyError, match="Pass 1:"):
        run(config, client)

    assert output.read_text() == "prior artifact"
    assert len(client.calls) == 1
    assert list(tmp_path.glob(".book.ontology.json.*")) == []


def test_merging_normalizes_labels_and_keeps_class_and_instance_separate() -> None:
    payload = ontology_payload()
    payload["concepts"].append(
        {**payload["concepts"][0], "id": "another_tree", "label": "  TREE  "}
    )
    payload["concepts"].append(
        {**payload["concepts"][0], "id": "tree_instance", "kind": "instance"}
    )
    state = OntologyState()

    merge_ontology_response(
        state,
        parse_ontology_response(json.dumps(payload)),
        passage=SOURCE,
        start=0,
        line_offsets=[0, 9, 10],
    )

    assert len(state.concepts) == 3
    assert sum(c.kind == "instance" for c in state.concepts.values()) == 1


def test_dry_run_does_not_call_model_or_write_files(tmp_path: Path) -> None:
    config = replace(source_config(tmp_path), dry_run=True)
    client = FakeCompleter(lambda *_: pytest.fail("A dry run called the model"))

    result = run(config, client)

    assert result.output_path is None
    assert len(result.passes) == 1
    assert client.calls == []
    assert not (tmp_path / "book.ontology.json").exists()


@pytest.mark.parametrize("failure", ["exists", "source_output", "empty", "extension"])
def test_input_and_output_failures_happen_before_model_calls(
    tmp_path: Path,
    failure: str,
) -> None:
    config = source_config(tmp_path)
    if failure == "exists":
        (tmp_path / "book.ontology.json").write_text("existing")
    elif failure == "source_output":
        config = replace(config, output_path=config.source, force=True)
    elif failure == "empty":
        config.source.write_text(" \n\t")
    elif failure == "extension":
        other = tmp_path / "book.txt"
        config.source.rename(other)
        config = replace(config, source=other)
    client = FakeCompleter(lambda *_: pytest.fail("Should reject before model call"))

    with pytest.raises(OntologyError):
        run(config, client)

    assert client.calls == []


def test_budget_reserves_output_and_margin_and_caps_default_to_provider() -> None:
    config = OntologyConfig(source=Path("book.md"))
    budget = resolve_ontology_budget(config, ModelTokenLimits(100_000, 8_000))
    assert budget.max_output_tokens == 8_000
    assert budget.input_budget == 100_000 - 8_000 - 2_048
    with pytest.raises(OntologyError, match="--context-window"):
        resolve_ontology_budget(config, ModelTokenLimits())
    with pytest.raises(OntologyError, match="at most 8000"):
        resolve_ontology_budget(
            replace(config, max_output_tokens=9_000), ModelTokenLimits(100_000, 8_000)
        )
    with pytest.raises(OntologyError, match="No room"):
        resolve_ontology_budget(
            replace(config, context_window=1_000), ModelTokenLimits(100_000, 8_000)
        )


def test_cli_generation_and_model_options(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    client = FakeCompleter(lambda *_: json.dumps(ontology_payload()))
    configs: list[OntologyConfig] = []

    def generator(
        config: OntologyConfig,
        *,
        progress: Callable[[str], None] | None,
    ) -> OntologyOutput:
        configs.append(config)
        return generate_ontology(
            config,
            completer=client,
            token_counter=CharacterCounter(),
            limits_resolver=lambda _: ModelTokenLimits(100_000, 40_000),
            progress=progress,
        )

    output = tmp_path / "artifacts" / "ontology.json"
    result = CliRunner().invoke(
        build_ontology_command(generator),
        [
            str(config.source),
            str(output),
            "--model",
            "openai/gpt-6-sol",
            "--reasoning-effort",
            "high",
            "--context-window",
            "100000",
            "--max-output-tokens",
            "1000",
            "--force",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert (
        "Passes: 1; concepts: 2; relation types: 1; relationships: 1" in result.output
    )
    assert configs[0].model == "openai/gpt-6-sol"
    assert configs[0].reasoning_effort == "high"
    assert configs[0].force is True
    assert client.calls[0].model == "openai/gpt-6-sol"


def test_root_help_registers_ontology_and_command_reports_errors(
    tmp_path: Path,
) -> None:
    assert "ontology" in CliRunner().invoke(main, ["--help"]).output
    config = source_config(tmp_path)

    def failing_generator(
        config: OntologyConfig,
        *,
        progress: Callable[[str], None] | None,
    ) -> OntologyOutput:
        raise OntologyError("No input limit; set --context-window.")

    result = CliRunner().invoke(
        build_ontology_command(failing_generator), [str(config.source)]
    )
    assert result.exit_code == 1
    assert "Error: No input limit" in result.output


def test_model_env_override_and_lazy_token_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALEX_ONTOLOGY_MODEL", "localai/my-model")
    assert resolve_ontology_model() == "localai/my-model"
    fake = types.ModuleType("litellm")
    api: Any = fake
    api.get_model_info = lambda **_: {
        "max_input_tokens": 30_000,
        "max_output_tokens": 8_000,
    }
    api.token_counter = lambda **_: 321
    monkeypatch.setitem(sys.modules, "litellm", fake)

    assert model_token_limits("test") == ModelTokenLimits(30_000, 8_000)
    assert LiteLlmTokenCounter().count(prompt="source", model="test") == 321
    api.token_counter = lambda **_: True
    with pytest.raises(LlmError, match="Cannot count"):
        LiteLlmTokenCounter().count(prompt="source", model="test")
    api.get_model_info = lambda **_: (_ for _ in ()).throw(ValueError("unknown"))
    assert model_token_limits("unknown") == ModelTokenLimits()


def test_valid_json_fence_is_accepted() -> None:
    result = parse_ontology_response(
        "```json\n" + json.dumps(ontology_payload()) + "\n```"
    )
    assert result.concepts[0].label == "Tree"


@pytest.mark.parametrize(
    "change",
    [
        {"subject_quantifier": "individual"},
        {"object_quantifier": "some"},
        {"strength": "conditional"},
        {"condition": "When watered"},
        {"subject_quantifier": "probably"},
    ],
)
def test_rejects_incompatible_or_invalid_logic(
    tmp_path: Path,
    change: dict[str, str],
) -> None:
    config = source_config(tmp_path)
    payload = ontology_payload()
    payload["relationships"][0]["logic"].update(change)
    client = FakeCompleter(lambda *_: json.dumps(payload))
    with pytest.raises(OntologyError):
        run(config, client)
    assert not config.source.with_suffix(".ontology.json").exists()


def test_logical_scope_is_part_of_relationship_identity(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    payload = ontology_payload()
    payload["relation_types"][0]["label"] = "supports"
    first = payload["relationships"][0]
    first["logic"]["object_quantifier"] = "some"
    second = {**first, "logic": {**first["logic"], "subject_quantifier": "some"}}
    payload["relationships"].append(second)
    result = run(config, FakeCompleter(lambda *_: json.dumps(payload)))
    assert result.relationship_count == 2


def test_qualified_taxonomy_does_not_create_a_logical_cycle(tmp_path: Path) -> None:
    config = source_config(tmp_path)
    payload = ontology_payload()
    edge = payload["relationships"][0]
    qualified = {
        **edge,
        "source": "plant",
        "target": "tree",
        "logic": {**edge["logic"], "strength": "possible"},
    }
    payload["relationships"].append(qualified)
    result = run(config, FakeCompleter(lambda *_: json.dumps(payload)))
    assert result.relationship_count == 2


def test_new_responses_require_explicit_logic() -> None:
    payload = ontology_payload()
    del payload["relationships"][0]["logic"]
    with pytest.raises(OntologyError, match="Invalid ontology JSON"):
        parse_ontology_response(json.dumps(payload))


def test_evidence_whitespace_alignment_stores_the_exact_source_span(
    tmp_path: Path,
) -> None:
    text = "# Plants\n\nA tree is\u00a0a\nplant.\n"
    config = source_config(tmp_path, text)
    result = run(config, FakeCompleter(lambda *_: json.dumps(ontology_payload())))
    assert result.output_path is not None
    artifact = json.loads(result.output_path.read_text())
    evidence = artifact["relationships"][0]["evidence"][0]
    assert evidence["quote"] == "A tree is\u00a0a\nplant."
    assert text[evidence["char_start"] : evidence["char_end"]] == evidence["quote"]
    assert evidence["model_quote"] == QUOTE
    assert evidence["match_mode"] == "whitespace_normalized"
    assert evidence["line_start"] == 3
    assert evidence["line_end"] == 4


def test_evidence_alignment_rejects_changed_punctuation(tmp_path: Path) -> None:
    config = source_config(tmp_path, "A tree is a plant!")
    with pytest.raises(OntologyError, match="evidence quote"):
        run(config, FakeCompleter(lambda *_: json.dumps(ontology_payload())))
