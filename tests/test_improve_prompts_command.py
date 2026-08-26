from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from alex.commands.improve_prompts import (
    BUNDLE_CRITIC_MODEL_B_ENV,
    build_improve_prompts_command,
)
from alex.lib.llm import Completer
from alex.lib.prompt_bundle_improvement import (
    BundleImprovementReport,
    BundleImprovementSettings,
)
from alex.lib.summarize import SummaryPrompts
from alex.lib.summary_eval import (
    DocScore,
    EvalConfig,
    EvalRun,
    GeneratedSummary,
    Progress,
    SummaryEvaluator,
    no_progress,
)


def score() -> DocScore:
    return DocScore(
        doc_name="a.md",
        coverage=0.8,
        faithfulness=0.9,
        density=1.0,
        rubric=0.7,
        blended=0.85,
        missed_facts=(),
        unsupported_claims=(),
        rubric_notes="",
        summary="Summary.",
    )


def run(run_id: str) -> EvalRun:
    return EvalRun(
        run_id=run_id,
        prompt_versions={},
        judge_model="judge",
        fact_extractor_model="extractor",
        summary_fast_model="fast",
        summary_final_model="final",
        doc_scores=(score(),),
        mean_blended=0.85,
    )


def canned_report(tmp_path: Path) -> BundleImprovementReport:
    return BundleImprovementReport(
        run_id_prefix="bundle",
        baseline_run=run("bundle-baseline"),
        candidate_run=run("bundle-candidate"),
        changed_versions={"chunk_summary": "v002"},
        doc_deltas={"a.md": 0.05},
        delta=0.05,
        promoted=False,
        rejected_reason=None,
        artifact_dir=tmp_path / "evals" / "prompt_bundles" / "bundle",
    )


class DummyCritic:
    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        raise AssertionError("not used")


class DummyEvaluator:
    def evaluate(
        self, *, prompts: SummaryPrompts, run_id: str, progress: Progress = no_progress
    ) -> EvalRun:
        raise AssertionError("not used")

    def rescore(
        self,
        *,
        summaries: Sequence[GeneratedSummary],
        prompt_versions: dict[str, str],
        run_id: str,
        progress: Progress = no_progress,
    ) -> EvalRun:
        raise AssertionError("not used")


def dummy_evaluator_factory(
    config: EvalConfig,
    docs: tuple[str, ...] | None,
) -> SummaryEvaluator:
    return DummyEvaluator()


def test_improve_prompts_command_passes_settings_and_reports(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_improver(
        *,
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
        evaluator_factory: Any,
        critic: Completer,
        settings: BundleImprovementSettings,
        run_id_prefix: str,
        lineage_dir: Path,
        artifact_dir: Path,
        progress: Progress,
    ) -> BundleImprovementReport:
        captured.update(
            config=config,
            doc_names=doc_names,
            settings=settings,
            run_id_prefix=run_id_prefix,
            lineage_dir=lineage_dir,
            artifact_dir=artifact_dir,
        )
        return canned_report(tmp_path)

    result = CliRunner().invoke(
        build_improve_prompts_command(
            improver=fake_improver,
            evaluator_factory=dummy_evaluator_factory,
            critic_factory=DummyCritic,
        ),
        [
            "--critic-model-a",
            "anthropic/a",
            "--critic-model-b",
            "openai/b",
            "--synthesis-model",
            "openai/s",
            "--critic-max-tokens",
            "123",
            "--min-delta",
            "0.05",
            "--docs",
            "a.md",
            "--run-id",
            "bundle",
            "--evals-dir",
            str(tmp_path / "evals"),
        ],
    )

    assert result.exit_code == 0, result.output
    settings = captured["settings"]
    assert settings.critic_model_a == "anthropic/a"
    assert settings.critic_model_b == "openai/b"
    assert settings.synthesis_model == "openai/s"
    assert settings.critic_max_tokens == 123
    assert settings.min_delta == 0.05
    assert captured["doc_names"] == ("a.md",)
    assert captured["run_id_prefix"] == "bundle"
    assert "Changed prompts: chunk_summary=v002" in result.output
    assert "Outcome: passed gate; rerun with --promote to activate" in result.output


def test_improve_prompts_command_uses_env_model_b(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_improver(
        *,
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
        evaluator_factory: Any,
        critic: Completer,
        settings: BundleImprovementSettings,
        run_id_prefix: str,
        lineage_dir: Path,
        artifact_dir: Path,
        progress: Progress,
    ) -> BundleImprovementReport:
        captured["settings"] = settings
        return canned_report(tmp_path)

    monkeypatch.setenv(BUNDLE_CRITIC_MODEL_B_ENV, "openai/env")
    result = CliRunner().invoke(
        build_improve_prompts_command(
            improver=fake_improver,
            evaluator_factory=dummy_evaluator_factory,
            critic_factory=DummyCritic,
        ),
        ["--run-id", "bundle", "--evals-dir", str(tmp_path / "evals")],
    )

    assert result.exit_code == 0, result.output
    assert captured["settings"].critic_model_b == "openai/env"


def test_improve_prompts_requires_second_model(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        build_improve_prompts_command(),
        ["--evals-dir", str(tmp_path / "evals")],
    )

    assert result.exit_code == 2
    assert "--critic-model-b is required" in result.output
