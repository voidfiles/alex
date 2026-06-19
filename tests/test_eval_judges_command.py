import json
from pathlib import Path

from click.testing import CliRunner

from alex.commands.eval_judges import build_eval_judges_command


class CalibrationCompleter:
    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if '"covered"' in prompt:
            return json.dumps(
                {
                    "verdicts": [
                        {"covered": True, "evidence": "summary covers it"},
                        {"covered": False, "evidence": "summary misses it"},
                    ]
                }
            )
        if '"supported"' in prompt:
            return json.dumps(
                {
                    "verdicts": [
                        {"supported": True, "evidence": "document supports it"},
                        {"supported": False, "evidence": "document contradicts it"},
                    ]
                }
            )
        raise AssertionError(f"Unexpected prompt: {prompt[:80]!r}")


def write_case(evals_dir: Path) -> None:
    calibration_dir = evals_dir / "calibration"
    calibration_dir.mkdir(parents=True)
    (calibration_dir / "case.json").write_text(
        json.dumps(
            {
                "name": "basic",
                "facts": ["Fact A.", "Fact B."],
                "summary": "Fact A only.",
                "expected_covered": [True, False],
                "claims": ["Claim A.", "Claim B."],
                "document": "Claim A is supported.",
                "expected_supported": [True, False],
            }
        ),
        encoding="utf-8",
    )


def test_eval_judges_reports_calibration_accuracy(tmp_path: Path) -> None:
    evals_dir = tmp_path / "evals"
    write_case(evals_dir)

    result = CliRunner().invoke(
        build_eval_judges_command(lambda: CalibrationCompleter()),
        [
            "--evals-dir",
            str(evals_dir),
            "--judge-model",
            "judge/x",
            "--fail-under",
            "1.0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Cases: 1" in result.output
    assert "Coverage: 2/2 correct" in result.output
    assert "Support: 2/2 correct" in result.output
    assert "Combined accuracy: 1.000" in result.output


def test_eval_judges_can_fail_under_threshold(tmp_path: Path) -> None:
    evals_dir = tmp_path / "evals"
    write_case(evals_dir)

    result = CliRunner().invoke(
        build_eval_judges_command(lambda: CalibrationCompleter()),
        [
            "--evals-dir",
            str(evals_dir),
            "--fail-under",
            "1.1",
        ],
    )

    assert result.exit_code == 1
    assert "below 1.100" in result.output
