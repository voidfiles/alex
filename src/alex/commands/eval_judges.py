from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from alex.commands.eval_summary import with_eval_model_overrides
from alex.lib.llm import Completer, LiteLlmCompleter
from alex.lib.summary_eval import (
    EvalConfig,
    EvalJudgeError,
    EvalPrompts,
    EvalSettings,
    judge_fact_coverage,
    verify_claims,
)


@dataclass(frozen=True)
class CalibrationCase:
    name: str
    facts: tuple[str, ...]
    summary: str
    expected_covered: tuple[bool, ...]
    claims: tuple[str, ...]
    document: str
    expected_supported: tuple[bool, ...]


@dataclass(frozen=True)
class CalibrationResult:
    case_count: int
    coverage_correct: int
    coverage_total: int
    support_correct: int
    support_total: int
    failures: tuple[str, ...]

    def accuracy(self) -> float:
        total = self.coverage_total + self.support_total
        if total == 0:
            return 0.0
        correct = self.coverage_correct + self.support_correct
        return correct / total


def build_eval_judges_command(
    completer_factory: Callable[[], Completer] = LiteLlmCompleter,
) -> click.Command:
    @click.command("eval-judges")
    @click.option(
        "--evals-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=Path("evals"),
        show_default=True,
        help="Eval data directory holding calibration/.",
    )
    @click.option(
        "--judge-model",
        type=str,
        default=None,
        help="Model for coverage and faithfulness judges.",
    )
    @click.option(
        "--fact-extractor-model",
        type=str,
        default=None,
        help="Accepted for consistency; not used by calibration cases.",
    )
    @click.option(
        "--fail-under",
        type=float,
        default=None,
        help="Exit non-zero if combined judge accuracy is below this value.",
    )
    def command(
        evals_dir: Path,
        judge_model: str | None,
        fact_extractor_model: str | None,
        fail_under: float | None,
    ) -> None:
        config = with_eval_model_overrides(
            EvalConfig(
                corpus_dir=evals_dir / "corpus",
                facts_dir=evals_dir / "facts",
                runs_dir=evals_dir / "runs",
            ),
            judge_model=judge_model,
            fact_extractor_model=fact_extractor_model,
        )
        try:
            result = evaluate_judges(
                calibration_dir=evals_dir / "calibration",
                settings=config.settings,
                completer=completer_factory(),
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Cases: {result.case_count}")
        click.echo(
            "Coverage: "
            f"{result.coverage_correct}/{result.coverage_total} correct"
        )
        click.echo(
            f"Support: {result.support_correct}/{result.support_total} correct"
        )
        click.echo(f"Combined accuracy: {result.accuracy():.3f}")
        for failure in result.failures:
            click.echo(f"FAIL {failure}")
        if fail_under is not None and result.accuracy() < fail_under:
            raise click.ClickException(
                f"Judge accuracy {result.accuracy():.3f} is below {fail_under:.3f}"
            )

    return command


def evaluate_judges(
    *,
    calibration_dir: Path,
    settings: EvalSettings,
    completer: Completer,
) -> CalibrationResult:
    cases = read_calibration_cases(calibration_dir)
    prompts = EvalPrompts.load()
    coverage_correct = 0
    coverage_total = 0
    support_correct = 0
    support_total = 0
    failures: list[str] = []
    for case in cases:
        coverage = judge_fact_coverage(
            facts=case.facts,
            summary=case.summary,
            template=prompts.fact_coverage_judge,
            completer=completer,
            settings=settings,
        )
        coverage_actual = tuple(verdict.covered for verdict in coverage)
        for index, (actual, expected) in enumerate(
            zip(coverage_actual, case.expected_covered, strict=True),
            1,
        ):
            coverage_total += 1
            if actual == expected:
                coverage_correct += 1
            else:
                failures.append(
                    f"{case.name}: coverage #{index} expected {expected}, got {actual}"
                )

        support = verify_claims(
            doc_text=case.document,
            claims=case.claims,
            template=prompts.claim_verification,
            completer=completer,
            settings=settings,
        )
        support_actual = tuple(verdict.supported for verdict in support)
        for index, (actual, expected) in enumerate(
            zip(support_actual, case.expected_supported, strict=True),
            1,
        ):
            support_total += 1
            if actual == expected:
                support_correct += 1
            else:
                failures.append(
                    f"{case.name}: support #{index} expected {expected}, got {actual}"
                )

    return CalibrationResult(
        case_count=len(cases),
        coverage_correct=coverage_correct,
        coverage_total=coverage_total,
        support_correct=support_correct,
        support_total=support_total,
        failures=tuple(failures),
    )


def read_calibration_cases(calibration_dir: Path) -> tuple[CalibrationCase, ...]:
    if not calibration_dir.is_dir():
        raise EvalJudgeError(f"Calibration directory not found: {calibration_dir}")
    paths = tuple(sorted(calibration_dir.glob("*.json")))
    if not paths:
        raise EvalJudgeError(f"No calibration cases in {calibration_dir}")
    return tuple(read_calibration_case(path) for path in paths)


def read_calibration_case(path: Path) -> CalibrationCase:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvalJudgeError(f"Calibration case must be a JSON object: {path}")
    name = string_field(payload, "name")
    facts = string_tuple(payload, "facts")
    claims = string_tuple(payload, "claims")
    expected_covered = bool_tuple(payload, "expected_covered")
    expected_supported = bool_tuple(payload, "expected_supported")
    if len(facts) != len(expected_covered):
        raise EvalJudgeError(f"{name}: facts and expected_covered lengths differ")
    if len(claims) != len(expected_supported):
        raise EvalJudgeError(f"{name}: claims and expected_supported lengths differ")
    return CalibrationCase(
        name=name,
        facts=facts,
        summary=string_field(payload, "summary"),
        expected_covered=expected_covered,
        claims=claims,
        document=string_field(payload, "document"),
        expected_supported=expected_supported,
    )


def string_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvalJudgeError(f"Calibration field {key!r} must be a non-empty string.")
    return value


def string_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EvalJudgeError(f"Calibration field {key!r} must be a list of strings.")
    return tuple(value)


def bool_tuple(payload: dict[str, Any], key: str) -> tuple[bool, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, bool) for item in value):
        raise EvalJudgeError(f"Calibration field {key!r} must be a list of booleans.")
    return tuple(value)


eval_judges = build_eval_judges_command()
