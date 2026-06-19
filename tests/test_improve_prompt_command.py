from pathlib import Path
from typing import Any

from click.testing import CliRunner

from alex.commands.improve_prompt import build_improve_prompt_command
from alex.lib.llm import Completer
from alex.lib.prompt_improvement import (
    ImprovementReport,
    ImprovementSettings,
    IterationResult,
)
from alex.lib.summary_eval import Progress, SummaryEvaluator


def canned_report() -> ImprovementReport:
    return ImprovementReport(
        prompt_name="chunk_summary",
        iterations=(
            IterationResult(
                iteration=1,
                parent_version="v001",
                candidate_version="v002",
                parent_score=0.65,
                candidate_score=0.715,
                delta=0.065,
                doc_deltas={"a.md": 0.05, "b.md": 0.08},
                promoted=True,
                rejected_reason=None,
            ),
            IterationResult(
                iteration=2,
                parent_version="v002",
                candidate_version=None,
                parent_score=0.715,
                candidate_score=None,
                delta=None,
                doc_deltas={},
                promoted=False,
                rejected_reason="candidate placeholders do not match",
            ),
        ),
    )


def test_improve_prompt_command_reports_each_iteration(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_improver(
        *,
        prompt_name: str,
        evaluator: SummaryEvaluator,
        critic: Completer,
        settings: ImprovementSettings,
        lineage_dir: Path,
        run_id_prefix: str,
        progress: Progress,
    ) -> ImprovementReport:
        captured.update(
            prompt_name=prompt_name,
            settings=settings,
            lineage_dir=lineage_dir,
            run_id_prefix=run_id_prefix,
        )
        return canned_report()

    result = CliRunner().invoke(
        build_improve_prompt_command(fake_improver),
        [
            "chunk_summary",
            "--iterations",
            "2",
            "--min-delta",
            "0.05",
            "--promote",
            "--judge-model",
            "judge/x",
            "--fact-extractor-model",
            "extractor/y",
            "--adjudication-margin",
            "0.03",
            "--adjudication-repeats",
            "2",
            "--evals-dir",
            str(tmp_path / "evals"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["prompt_name"] == "chunk_summary"
    settings = captured["settings"]
    assert settings.iterations == 2
    assert settings.min_delta == 0.05
    assert settings.promote is True
    assert settings.adjudication_margin == 0.03
    assert settings.adjudication_repeats == 2
    assert captured["lineage_dir"] == tmp_path / "evals" / "lineage"

    assert (
        "[1] v001 -> v002: parent 0.650, candidate 0.715, delta +0.065 (promoted)"
    ) in result.output
    assert "[2] v002: rejected (candidate placeholders do not match)" in result.output
    assert (
        f"Lineage: {tmp_path / 'evals' / 'lineage' / 'chunk_summary.jsonl'}"
        in result.output
    )


def test_improve_prompt_command_wraps_loop_errors(tmp_path: Path) -> None:
    def failing_improver(
        *,
        prompt_name: str,
        evaluator: SummaryEvaluator,
        critic: Completer,
        settings: ImprovementSettings,
        lineage_dir: Path,
        run_id_prefix: str,
        progress: Progress,
    ) -> ImprovementReport:
        raise ValueError("Cannot improve unknown summary prompt: nope")

    result = CliRunner().invoke(
        build_improve_prompt_command(failing_improver),
        ["nope", "--evals-dir", str(tmp_path / "evals")],
    )

    assert result.exit_code == 1
    assert "Cannot improve unknown summary prompt: nope" in result.output
