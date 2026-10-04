"""Reference-passage evaluation of the real quote extractor, without LLM judges."""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alex.lib.llm import (
    Completer,
    CompletionUsage,
    LiteLlmCompleter,
    preflight_completion_cost,
)
from alex.lib.prompt_templates import load_prompt
from alex.lib.quotes import (
    QUOTE_SYSTEM_PROMPT,
    QuoteExtraction,
    QuoteSettings,
    extract_quotes,
    prepare_quote_prompt,
    quote_completer,
    sha256,
)

SCORER_VERSION = "source-span-f1/v1"
DEFAULT_QUOTE_DATASET = Path("evals/quote_extraction/simonwillison/examples.jsonl")
Progress = Callable[[str], None]


class QuoteEvalError(ValueError):
    pass


class ReferenceSegment(BaseModel):
    model_config = ConfigDict(strict=True)
    normalized_segment: str = Field(min_length=1)


class ReferenceValidation(BaseModel):
    model_config = ConfigDict(strict=True)
    status: Literal["verified"]
    segments: list[ReferenceSegment] = Field(min_length=1)


class QuoteCase(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str = Field(min_length=1)
    split: Literal["dev", "test"]
    source_markdown: str = Field(min_length=1)
    source_sha256: str
    reference_quote: str
    validation: ReferenceValidation


@dataclass(frozen=True)
class QuoteEvalSettings:
    dataset: Path = DEFAULT_QUOTE_DATASET
    split: Literal["dev", "test", "all"] = "dev"
    extraction: QuoteSettings = field(default_factory=lambda: QuoteSettings(count=1))
    repeats: int = 1
    workers: int = 4
    max_cost: float = 5.0


def words(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())


def reference_positions(case: QuoteCase, source_text: str) -> set[int]:
    """Locate label segments in this renderer, rather than reuse foreign offsets."""
    source = " ".join(words(source_text))
    positions: set[int] = set()
    cursor = 0
    for segment in case.validation.segments:
        needle = segment.normalized_segment
        match = re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", source[cursor:])
        if match is None:
            raise QuoteEvalError(
                f"Reference segment is absent from input for {case.id}."
            )
        start = cursor + match.start()
        first_word = len(source[:start].split())
        positions.update(range(first_word, first_word + len(needle.split())))
        cursor += match.end()
    return positions


def score_extraction(
    result: QuoteExtraction, source_text: str, reference: set[int]
) -> dict[str, float | bool]:
    selected: set[int] = set()
    for quote in result.quotes:
        for segment in quote.segments:
            first = len(words(source_text[: segment.char_start]))
            selected.update(range(first, first + len(words(segment.text))))
    common = len(selected & reference)
    precision = common / len(selected) if selected else 0.0
    recall = common / len(reference) if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "span_precision": precision,
        "span_recall": recall,
        "span_f1": f1,
        "exact_span_match": selected == reference,
        "source_valid": True,
        "nonempty": bool(result.quotes),
    }


def load_cases(settings: QuoteEvalSettings) -> list[QuoteCase]:
    cases = []
    ids: set[str] = set()
    sources: set[str] = set()
    for line_no, line in enumerate(
        settings.dataset.read_text(encoding="utf-8").splitlines(), 1
    ):
        try:
            case = QuoteCase.model_validate_json(line)
        except ValidationError as error:
            raise QuoteEvalError(
                f"Invalid dataset record on line {line_no}."
            ) from error
        if sha256(case.source_markdown) != case.source_sha256:
            raise QuoteEvalError(f"Source checksum differs for {case.id}.")
        if case.id in ids or case.source_sha256 in sources:
            raise QuoteEvalError("Dataset contains duplicate IDs or source documents.")
        ids.add(case.id)
        sources.add(case.source_sha256)
        if settings.split == "all" or case.split == settings.split:
            cases.append(case)
    if not cases:
        raise QuoteEvalError(f"Dataset has no {settings.split} cases.")
    return cases


@dataclass
class RecordingCompleter:
    inner: Completer
    response: str | None = None
    usage: CompletionUsage = field(default_factory=CompletionUsage)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if isinstance(self.inner, LiteLlmCompleter):
            response = self.inner.complete_metered(
                prompt=prompt, model=model, max_tokens=max_tokens
            )
            self.response, self.usage = response.text, response.usage
        else:
            self.response = self.inner.complete(
                prompt=prompt, model=model, max_tokens=max_tokens
            )
        return self.response


def estimate_quote_cost(prompt: str, settings: QuoteSettings) -> float:
    return preflight_completion_cost(
        prompt=prompt,
        model=settings.model,
        max_tokens=settings.max_output_tokens,
        system_prompt=QUOTE_SYSTEM_PROMPT,
    )


def summarize_scores(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = (
        "span_f1",
        "span_precision",
        "span_recall",
        "exact_span_match",
        "source_valid",
        "nonempty",
    )
    costs = [r["usage"]["cost_usd"] for r in records]
    return {
        "case_count": len({r["id"] for r in records}),
        "generation_count": len(records),
        "error_count": sum(r["error"] is not None for r in records),
        **{
            metric: sum(r["metrics"][metric] for r in records) / len(records)
            for metric in metrics
        },
        "actual_cost_usd": sum(costs) if all(c is not None for c in costs) else None,
        "input_tokens": sum(r["usage"]["input_tokens"] or 0 for r in records),
        "output_tokens": sum(r["usage"]["output_tokens"] or 0 for r in records),
    }


def evaluate_quotes(
    settings: QuoteEvalSettings,
    output: Path,
    *,
    completer_factory: Callable[[QuoteSettings], Completer] = quote_completer,
    cost_estimator: Callable[[str, QuoteSettings], float] = estimate_quote_cost,
    progress: Progress = lambda _: None,
) -> dict[str, Any]:
    if output.exists():
        raise QuoteEvalError(f"Run artifact already exists: {output}")
    if (
        settings.repeats < 1
        or settings.workers < 1
        or not math.isfinite(settings.max_cost)
        or settings.max_cost <= 0
    ):
        raise QuoteEvalError(
            "Repeats and workers must be positive; cost ceiling must be "
            "positive and finite."
        )
    started = datetime.now(UTC).isoformat()
    cases = load_cases(settings)
    template = load_prompt(
        "quote_extraction", version=settings.extraction.prompt_version
    )
    extraction = replace(settings.extraction, prompt_version=template.version)
    prepared = []
    total_estimate = 0.0
    # All labels, hashes and request-cost ceilings are checked before any calls.
    for case in cases:
        source, prompt = prepare_quote_prompt(
            case.source_markdown, extraction, template
        )
        reference = reference_positions(case, source)
        total_estimate += cost_estimator(prompt, extraction) * settings.repeats
        prepared.append((case, source, prompt, reference))
    if total_estimate > settings.max_cost:
        raise QuoteEvalError(
            f"Estimated ceiling ${total_estimate:.3f} exceeds --max-cost "
            f"${settings.max_cost:.3f}; no model calls were made."
        )
    progress(
        f"{len(cases)} {settings.split} cases x {settings.repeats} repeats; "
        f"{template.version}, {extraction.model}; ceiling ${total_estimate:.3f}"
    )

    def run_one(job: tuple[int, int]) -> dict[str, Any]:
        case_index, repeat = job
        case, source, prompt, reference = prepared[case_index]
        recorder = RecordingCompleter(completer_factory(extraction))
        begin = time.monotonic()
        error = None
        artifact = None
        try:
            result = extract_quotes(
                case.source_markdown, extraction, completer=recorder, template=template
            )
            artifact = result.to_dict()
            metrics = score_extraction(result, source, reference)
        except (OSError, RuntimeError, ValueError) as failure:
            error = str(failure)
            metrics = {
                "span_f1": 0.0,
                "span_precision": 0.0,
                "span_recall": 0.0,
                "exact_span_match": False,
                "source_valid": False,
                "nonempty": False,
            }
        progress(
            f"{case.id} #{repeat}: F1 {metrics['span_f1']:.3f}"
            + (f" ERROR {error}" if error else "")
        )
        return {
            "id": case.id,
            "repeat": repeat,
            "split": case.split,
            "source_sha256": case.source_sha256,
            "request_sha256": sha256(prompt),
            "reference_quote": case.reference_quote,
            "reference_word_count": len(reference),
            "prediction": artifact,
            "raw_response": recorder.response,
            "error": error,
            "metrics": metrics,
            "usage": asdict(recorder.usage),
            "seconds": time.monotonic() - begin,
        }

    jobs = [
        (index, repeat)
        for repeat in range(1, settings.repeats + 1)
        for index in range(len(cases))
    ]
    with ThreadPoolExecutor(max_workers=settings.workers) as pool:
        records = list(pool.map(run_one, jobs))
    run = {
        "schema_version": 1,
        "scorer_version": SCORER_VERSION,
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "dataset": str(settings.dataset.resolve()),
        "dataset_sha256": sha256(settings.dataset.read_text(encoding="utf-8")),
        "renderer_version": version("markdown-it-py"),
        "split": settings.split,
        "case_ids": [c.id for c in cases],
        "extraction": asdict(extraction),
        "prompt_text": template.text,
        "prompt_sha256": sha256(template.text),
        "system_prompt": QUOTE_SYSTEM_PROMPT,
        "repeats": settings.repeats,
        "estimated_ceiling_usd": total_estimate,
        "summary": summarize_scores(records),
        "cases": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Another run can create this path while model calls are in flight.
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
    return run


def compare_quote_runs(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    for key in (
        "dataset_sha256",
        "scorer_version",
        "renderer_version",
        "system_prompt",
    ):
        if baseline[key] != candidate[key]:
            raise QuoteEvalError(f"Cannot compare runs with different {key}.")
    for key in ("model", "count", "max_output_tokens", "reasoning_effort"):
        if baseline["extraction"][key] != candidate["extraction"][key]:
            raise QuoteEvalError(f"Cannot compare runs with different {key}.")
    if set(baseline["case_ids"]) != set(candidate["case_ids"]):
        raise QuoteEvalError("Cannot compare runs on different cases.")
    deltas = []
    newly_failed = []
    validity_regressions = []
    for case_id in baseline["case_ids"]:
        before = [r for r in baseline["cases"] if r["id"] == case_id]
        after = [r for r in candidate["cases"] if r["id"] == case_id]

        def average(rows: list[dict[str, Any]], metric: str) -> float:
            return float(sum(r["metrics"][metric] for r in rows) / len(rows))

        delta = average(after, "span_f1") - average(before, "span_f1")
        deltas.append({"id": case_id, "delta": delta})
        if any(r["error"] for r in after) and not any(r["error"] for r in before):
            newly_failed.append(case_id)
        if average(after, "source_valid") < average(before, "source_valid"):
            validity_regressions.append(case_id)
    wins = sum(d["delta"] > 1e-9 for d in deltas)
    ties = sum(abs(d["delta"]) <= 1e-9 for d in deltas)
    mean_delta = sum(d["delta"] for d in deltas) / len(deltas)
    return {
        "mean_f1_delta": mean_delta,
        "wins": wins,
        "ties": ties,
        "losses": len(deltas) - wins - ties,
        "newly_failed": newly_failed,
        "source_validity_regressions": validity_regressions,
        "passes_gate": mean_delta >= 0.02
        and wins + ties > len(deltas) / 2
        and not newly_failed
        and not validity_regressions,
        "paired_cases": deltas,
    }
