"""Audit and summarize the frozen expanded-corpus benchmark without model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alex.lib.prompt_templates import load_prompt
from alex.lib.quote_eval import (
    SCORER_VERSION,
    QuoteEvalSettings,
    compare_quote_runs,
    load_cases,
    reference_positions,
    score_extraction,
    summarize_scores,
)
from alex.lib.quotes import (
    QuoteError,
    QuoteExtraction,
    markdown_to_text,
    parse_selected_quotes,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def group_run(run: dict[str, Any], ids: set[str]) -> dict[str, Any]:
    records = [row for row in run["cases"] if row["id"] in ids]
    return {
        **run,
        "case_ids": [case_id for case_id in run["case_ids"] if case_id in ids],
        "cases": records,
        "summary": summarize_scores(records),
    }


def audit_and_summarize(plan: dict[str, Any]) -> dict[str, Any]:
    dataset = ROOT / plan["dataset"]
    assert digest(dataset) == plan["dataset_sha256"], "Dataset changed after lock"
    cases = load_cases(QuoteEvalSettings(dataset=dataset, split="all"))
    ids = {case.id for case in cases}
    source = {case.id: markdown_to_text(case.source_markdown) for case in cases}
    reference = {case.id: reference_positions(case, source[case.id]) for case in cases}
    labels = {case.id: case.reference_quote for case in cases}
    source_hashes = {case.id: case.source_sha256 for case in cases}
    old_ids = {
        case.id
        for case in load_cases(
            QuoteEvalSettings(
                dataset=ROOT / "evals/quote_extraction/simonwillison/examples.jsonl",
                split="all",
            )
        )
    }
    groups = {
        "all": ids,
        "dev": set(plan["splits"]["dev"]),
        "test": set(plan["splits"]["test"]),
        "original_simonwillison": old_ids,
        "new_quotebacks": ids - old_ids,
        "fresh_new_test": set(plan["fresh_new_test_ids"]),
        "previously_evaluated_simon_test": old_ids & set(plan["splits"]["test"]),
    }
    expected = {
        (case_id, repeat) for case_id in ids for repeat in range(1, plan["repeats"] + 1)
    }
    runs = {}
    run_evidence = {}
    valid, invalid, unavailable = 0, 0, 0
    for version in plan["prompt_versions"]:
        path = ROOT / plan["run_paths"][version]
        run = json.loads(path.read_text())
        assert run["dataset_sha256"] == plan["dataset_sha256"]
        assert run["scorer_version"] == plan["scorer_version"] == SCORER_VERSION
        assert set(run["case_ids"]) == ids
        assert run["repeats"] == plan["repeats"]
        assert len(run["cases"]) == len(expected)
        assert {(row["id"], row["repeat"]) for row in run["cases"]} == expected
        assert run["started_at"] >= plan["created_at"]
        assert run["extraction"]["prompt_version"] == version
        for setting in ("model", "count", "max_output_tokens", "reasoning_effort"):
            assert run["extraction"][setting] == plan[setting]
        template = load_prompt("quote_extraction", version=version)
        assert template.placeholders() == {"source", "count"}
        assert (
            run["prompt_sha256"]
            == hashlib.sha256(template.text.encode()).hexdigest()
            == plan["prompt_sha256"][version]
        )
        for row in run["cases"]:
            assert row["source_sha256"] == source_hashes[row["id"]]
            text = source[row["id"]]
            if row["raw_response"] is None:
                assert row["error"] is not None
                assert row["prediction"] is None
                assert not any(row["metrics"].values())
                unavailable += 1
                continue
            try:
                quotes = parse_selected_quotes(
                    row["raw_response"],
                    text,
                    count=plan["count"],
                    allow_extra_quotes=True,
                )
            except QuoteError:
                assert row["error"] is not None
                assert row["prediction"] is None
                assert not any(row["metrics"].values())
                invalid += 1
                continue
            assert row["error"] is None
            result = QuoteExtraction(
                source_sha256=source_hashes[row["id"]],
                source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                model=run["extraction"]["model"],
                prompt_version=version,
                prompt_sha256=run["prompt_sha256"],
                quotes=quotes,
            )
            assert result.to_dict() == row["prediction"]
            for quote in quotes:
                for segment in quote.segments:
                    assert text[segment.char_start : segment.char_end] == segment.text
            assert (
                score_extraction(result, text, reference[row["id"]], labels[row["id"]])
                == row["metrics"]
            )
            valid += 1
        assert summarize_scores(run["cases"]) == run["summary"]
        runs[version] = run
        run_evidence[version] = {
            "run": plan["run_paths"][version],
            "run_sha256": digest(path),
            "prompt_sha256": run["prompt_sha256"],
            "started_at": run["started_at"],
            "completed_at": run["completed_at"],
        }
    baseline = runs[plan["active_before"]]
    for run in runs.values():
        assert run["scoring_contract"] == baseline["scoring_contract"]
        compare_quote_runs(baseline, run)
    grouped = {
        group: {version: group_run(run, selected) for version, run in runs.items()}
        for group, selected in groups.items()
    }
    active = (ROOT / "src/alex/prompts/quote_extraction/active.txt").read_text().strip()
    assert active == plan["active_before"], "Active prompt changed during benchmark"
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "plan": "evals/quote_extraction/round3/benchmark_plan.json",
        "plan_sha256": digest(HERE / "benchmark_plan.json"),
        "dataset": plan["dataset"],
        "dataset_sha256": plan["dataset_sha256"],
        "scorer_version": plan["scorer_version"],
        "scoring_contract": baseline["scoring_contract"],
        "settings": {
            key: plan[key]
            for key in (
                "model",
                "count",
                "max_output_tokens",
                "reasoning_effort",
                "repeats",
                "workers_per_run",
            )
        },
        "renderer_version": baseline["renderer_version"],
        "system_prompt": baseline["system_prompt"],
        "run_evidence": run_evidence,
        "groups": {
            group: {
                "case_ids": sorted(groups[group]),
                "versions": {
                    version: {
                        "summary": run["summary"],
                        "exact_counts": {
                            metric: sum(row["metrics"][metric] for row in run["cases"])
                            for metric in ("exact_quote_match", "exact_span_match")
                        },
                    }
                    for version, run in group_runs.items()
                },
                "comparisons_to_v001": {
                    version: compare_quote_runs(group_runs["v001"], run)
                    for version, run in group_runs.items()
                    if version != "v001"
                },
            }
            for group, group_runs in grouped.items()
        },
        "totals": {
            **{
                metric: sum(run["summary"][metric] for run in runs.values())
                for metric in (
                    "generation_count",
                    "error_count",
                    "input_tokens",
                    "output_tokens",
                )
            },
            "actual_cost_usd": (
                sum(run["summary"]["actual_cost_usd"] for run in runs.values())
                if all(
                    run["summary"]["actual_cost_usd"] is not None
                    for run in runs.values()
                )
                else None
            ),
            "known_recorded_cost_usd": sum(
                row["usage"]["cost_usd"] or 0
                for run in runs.values()
                for row in run["cases"]
            ),
            "generations_with_missing_cost": sum(
                row["usage"]["cost_usd"] is None
                for run in runs.values()
                for row in run["cases"]
            ),
        },
        "audit": {
            "reparsed_and_rescored_valid_generations": valid,
            "rejected_provider_outputs_revalidated": invalid,
            "failed_requests_without_provider_text": unavailable,
            "total_verified_generations": valid + invalid + unavailable,
            "dataset_and_frozen_prompt_hashes_match": True,
            "source_offsets_and_stored_scores_match": True,
            "stored_aggregates_match_recomputed_metrics": True,
        },
        "active_prompt": active,
        "promotion_policy": plan["promotion_policy"],
        "fresh_new_test_evaluated": True,
        "fresh_new_test_case_count": len(groups["fresh_new_test"]),
        "interpretation": (
            "Fixed-prompt benchmark; previously unseen labels were not used to edit "
            "prompts. Multiple candidate comparisons are descriptive. These test "
            "sources are now evaluated and cannot be called untouched in later tuning."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    plan = json.loads((HERE / "benchmark_plan.json").read_text())
    output = HERE / "benchmark_summary.json"
    if output.exists() and not args.check_only:
        parser.error("Summary exists; use --check-only to audit without overwriting")
    summary = audit_and_summarize(plan)
    if not args.check_only:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps({"totals": summary["totals"], "audit": summary["audit"]}, indent=2)
    )


if __name__ == "__main__":
    main()
