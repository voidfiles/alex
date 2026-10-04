from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from alex.lib.quote_eval import (
    QuoteCase,
    QuoteEvalError,
    QuoteEvalSettings,
    compare_quote_runs,
    evaluate_quotes,
    reference_positions,
    score_extraction,
)
from alex.lib.quotes import QuoteSettings, extract_quotes, markdown_to_text, sha256
from helpers import RecordingCompleter

SOURCE = (
    "# Sample\n\nThe first passage is useful.\n\nThe second passage is different.\n"
)
FIRST = "The first passage is useful."
SECOND = "The second passage is different."


def case_payload(case_id: str = "sample", source: str = SOURCE) -> dict[str, Any]:
    return {
        "id": case_id,
        "split": "dev",
        "source_markdown": source,
        "source_sha256": sha256(source),
        "reference_quote": "[HIDDEN_LABEL] " + FIRST,
        "validation": {
            "status": "verified",
            "segments": [{"normalized_segment": "the first passage is useful"}],
        },
    }


def write_dataset(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "examples.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def prediction(quote: str = FIRST) -> RecordingCompleter:
    return RecordingCompleter(
        compression_response=json.dumps({"quotes": [{"segments": [quote]}]})
    )


def test_perfect_reference_score_and_other_passage_score() -> None:
    case = QuoteCase.model_validate(case_payload())
    source = markdown_to_text(SOURCE)
    reference = reference_positions(case, source)
    correct = extract_quotes(SOURCE, completer=prediction())
    unrelated = extract_quotes(SOURCE, completer=prediction(SECOND))
    assert score_extraction(correct, source, reference)["span_f1"] == 1.0
    assert score_extraction(unrelated, source, reference)["span_f1"] == 0.0
    assert score_extraction(unrelated, source, reference)["source_valid"] is True


def test_whole_document_quote_is_penalized_for_low_precision() -> None:
    case = QuoteCase.model_validate(case_payload())
    source = markdown_to_text(SOURCE)
    result = extract_quotes(SOURCE, completer=prediction(source))
    metrics = score_extraction(result, source, reference_positions(case, source))
    assert metrics["span_recall"] == 1.0
    assert 0 < metrics["span_f1"] < 1


def test_editorial_gaps_reference_multiple_source_spans() -> None:
    payload = case_payload()
    payload["validation"]["segments"].append(
        {"normalized_segment": "the second passage is different"}
    )
    case = QuoteCase.model_validate(payload)
    reference = reference_positions(case, markdown_to_text(SOURCE))
    assert len(reference) == 10


def test_eval_records_failures_in_denominator_and_never_leaks_labels(
    tmp_path: Path,
) -> None:
    dataset = write_dataset(
        tmp_path, [case_payload(), case_payload("second", SOURCE + "\nMore context.\n")]
    )
    good, bad = prediction(), prediction("Invented sentence.")
    fakes = iter([good, bad])
    settings = QuoteEvalSettings(dataset=dataset, workers=1)
    output = tmp_path / "run.json"
    run = evaluate_quotes(
        settings,
        output,
        completer_factory=lambda _: next(fakes),
        cost_estimator=lambda *_: 0.01,
    )
    assert run["summary"]["span_f1"] == 0.5
    assert run["summary"]["source_valid"] == 0.5
    assert run["summary"]["error_count"] == 1
    assert run["cases"][1]["raw_response"] is not None
    assert "HIDDEN_LABEL" not in good.calls[0].prompt
    assert json.loads(output.read_text())["summary"] == run["summary"]
    with pytest.raises(QuoteEvalError, match="already exists"):
        evaluate_quotes(settings, output)


def test_cost_ceiling_is_checked_before_calls(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path, [case_payload()])
    completer = prediction()
    settings = QuoteEvalSettings(dataset=dataset, max_cost=0.25)
    with pytest.raises(QuoteEvalError, match="no model calls"):
        evaluate_quotes(
            settings,
            tmp_path / "run.json",
            completer_factory=lambda _: completer,
            cost_estimator=lambda *_: 0.5,
        )
    assert completer.calls == []


@pytest.mark.parametrize("max_cost", [float("nan"), float("inf"), 0.0, -1.0])
def test_invalid_cost_ceiling_fails_before_calls(
    tmp_path: Path, max_cost: float
) -> None:
    dataset = write_dataset(tmp_path, [case_payload()])
    completer = prediction()
    with pytest.raises(QuoteEvalError, match="positive and finite"):
        evaluate_quotes(
            QuoteEvalSettings(dataset=dataset, max_cost=max_cost),
            tmp_path / "run.json",
            completer_factory=lambda _: completer,
            cost_estimator=lambda *_: 0,
        )
    assert completer.calls == []


def test_bad_hash_or_missing_reference_fails_before_calls(tmp_path: Path) -> None:
    for mutation in ("hash", "reference"):
        row = case_payload()
        if mutation == "hash":
            row["source_sha256"] = "wrong"
        else:
            row["validation"]["segments"][0]["normalized_segment"] = "absent words"
        dataset = write_dataset(tmp_path, [row])
        completer = prediction()

        def factory(
            _: QuoteSettings, selected: RecordingCompleter = completer
        ) -> RecordingCompleter:
            return selected

        with pytest.raises(QuoteEvalError):
            evaluate_quotes(
                QuoteEvalSettings(dataset=dataset),
                tmp_path / "run.json",
                completer_factory=factory,
                cost_estimator=lambda *_: 0,
            )
        assert completer.calls == []


def test_repeated_generations_are_preserved_and_averaged(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path, [case_payload()])
    run = evaluate_quotes(
        QuoteEvalSettings(dataset=dataset, repeats=3, workers=1),
        tmp_path / "run.json",
        completer_factory=lambda _: prediction(),
        cost_estimator=lambda *_: 0,
    )
    assert run["summary"]["generation_count"] == 3
    assert run["summary"]["case_count"] == 1
    assert [r["repeat"] for r in run["cases"]] == [1, 2, 3]


def test_run_does_not_overwrite_artifact_created_during_generation(
    tmp_path: Path,
) -> None:
    dataset = write_dataset(tmp_path, [case_payload()])
    output = tmp_path / "run.json"

    def factory(_: QuoteSettings) -> RecordingCompleter:
        output.write_text("Another run's artifact")
        return prediction()

    with pytest.raises(FileExistsError):
        evaluate_quotes(
            QuoteEvalSettings(dataset=dataset),
            output,
            completer_factory=factory,
            cost_estimator=lambda *_: 0,
        )
    assert output.read_text() == "Another run's artifact"


def test_paired_comparison_checks_config_and_reports_gate(tmp_path: Path) -> None:
    dataset = write_dataset(tmp_path, [case_payload()])
    settings = QuoteEvalSettings(dataset=dataset)
    baseline = evaluate_quotes(
        settings,
        tmp_path / "base.json",
        completer_factory=lambda _: prediction(SECOND),
        cost_estimator=lambda *_: 0,
    )
    candidate = evaluate_quotes(
        settings,
        tmp_path / "candidate.json",
        completer_factory=lambda _: prediction(),
        cost_estimator=lambda *_: 0,
    )
    comparison = compare_quote_runs(baseline, candidate)
    assert comparison["passes_gate"] is True
    assert comparison["mean_f1_delta"] == 1.0
    assert comparison["wins"] == 1
    different = copy.deepcopy(candidate)
    different["extraction"]["model"] = "different-model"
    with pytest.raises(QuoteEvalError, match="different model"):
        compare_quote_runs(baseline, different)


def test_new_source_errors_block_promotion_even_if_mean_improves(
    tmp_path: Path,
) -> None:
    dataset = write_dataset(tmp_path, [case_payload()])
    settings = QuoteEvalSettings(dataset=dataset)
    baseline = evaluate_quotes(
        settings,
        tmp_path / "base.json",
        completer_factory=lambda _: prediction(),
        cost_estimator=lambda *_: 0,
    )
    candidate = copy.deepcopy(baseline)
    candidate["cases"][0]["error"] = "invalid source quote"
    candidate["cases"][0]["metrics"]["source_valid"] = False
    assert compare_quote_runs(baseline, candidate)["passes_gate"] is False
