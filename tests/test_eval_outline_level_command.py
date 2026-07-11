import json
from pathlib import Path

from click.testing import CliRunner

from alex.commands.eval_outline_level import build_eval_outline_level_command
from alex.lib.outline_level_eval import (
    OutlineLevelCaseResult,
    OutlineLevelRunResult,
)


def test_eval_command_reports_cases_and_run_artifact(tmp_path: Path) -> None:
    # Given
    run_path = tmp_path / "outline_level" / "runs" / "cli-run" / "run.json"

    def fake_evaluate(*, evals_dir: Path, run_id: str) -> OutlineLevelRunResult:
        run_path.parent.mkdir(parents=True)
        run_path.write_text(json.dumps({"accuracy": 0.5}), encoding="utf-8")
        return OutlineLevelRunResult(
            run_id=run_id,
            run_path=run_path,
            cases=(
                OutlineLevelCaseResult("one", "H2", "H2", "correct"),
                OutlineLevelCaseResult("two", "H3", None, "pending"),
            ),
            accuracy=1.0,
            annotated_count=1,
            pending_count=1,
        )

    # When
    result = CliRunner().invoke(
        build_eval_outline_level_command(fake_evaluate),
        ["--evals-dir", str(tmp_path), "--run-id", "cli-run"],
    )

    # Then
    assert result.exit_code == 0
    assert "one: predicted=H2 expected=H2 status=correct" in result.output
    assert "two: predicted=H3 expected=TODO status=pending" in result.output
    assert "Accuracy: 1.0000 (1 annotated)" in result.output
    assert "Pending: 1" in result.output
    assert f"Run artifact: {run_path}" in result.output


def test_eval_command_allows_pending_cases(tmp_path: Path) -> None:
    # Given
    run_path = tmp_path / "run.json"

    def fake_evaluate(*, evals_dir: Path, run_id: str) -> OutlineLevelRunResult:
        return OutlineLevelRunResult(
            run_id=run_id,
            run_path=run_path,
            cases=(OutlineLevelCaseResult("one", "H2", None, "pending"),),
            accuracy=None,
            annotated_count=0,
            pending_count=1,
        )

    # When
    result = CliRunner().invoke(
        build_eval_outline_level_command(fake_evaluate),
        ["--run-id", "pending"],
    )

    # Then
    assert result.exit_code == 0
    assert "Accuracy: n/a (0 annotated)" in result.output


def test_eval_command_reports_path_specific_malformed_annotation(
    tmp_path: Path,
) -> None:
    # Given
    output_path = tmp_path / "outline_level" / "cases" / "bad" / "output.md"

    def failing_evaluate(*, evals_dir: Path, run_id: str) -> OutlineLevelRunResult:
        raise ValueError(f"{output_path}: malformed first line")

    # When
    result = CliRunner().invoke(
        build_eval_outline_level_command(failing_evaluate),
        ["--evals-dir", str(tmp_path), "--run-id", "broken"],
    )

    # Then
    assert result.exit_code != 0
    assert str(output_path) in result.output
    assert "malformed first line" in result.output


def test_eval_command_rejects_unsafe_run_id_before_evaluation(tmp_path: Path) -> None:
    # Given
    evaluated = False

    def fake_evaluate(*, evals_dir: Path, run_id: str) -> OutlineLevelRunResult:
        nonlocal evaluated
        evaluated = True
        raise AssertionError("unsafe run ID reached evaluator")

    # When
    result = CliRunner().invoke(
        build_eval_outline_level_command(fake_evaluate),
        ["--evals-dir", str(tmp_path), "--run-id", "../escape"],
    )

    # Then
    assert result.exit_code != 0
    assert "unsafe run ID" in result.output
    assert not evaluated
