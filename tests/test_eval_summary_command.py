from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from click.testing import CliRunner

from alex.commands.eval_summary import build_eval_summary_command
from alex.lib.summarize import SummaryPrompts
from alex.lib.summary_eval import (
    DocScore,
    EvalConfig,
    EvalRun,
    GeneratedSummary,
    Progress,
    no_progress,
)


def ok_score(doc_name: str, blended: float) -> DocScore:
    return DocScore(
        doc_name=doc_name,
        coverage=0.8,
        faithfulness=0.9,
        density=0.5,
        rubric=0.75,
        blended=blended,
        missed_facts=("A missed fact.",),
        unsupported_claims=(),
        rubric_notes="Fine.",
        summary="A summary.",
    )


def failed_score(doc_name: str) -> DocScore:
    return DocScore(
        doc_name=doc_name,
        coverage=0.0,
        faithfulness=0.0,
        density=0.0,
        rubric=0.0,
        blended=0.0,
        missed_facts=(),
        unsupported_claims=(),
        rubric_notes="",
        summary="",
        error="judge exploded",
    )


def canned_run() -> EvalRun:
    return EvalRun(
        run_id="placeholder",
        prompt_versions={
            "chunk_summary": "v001",
            "compression_summary": "v001",
            "final_summary": "v001",
        },
        judge_model="anthropic/claude-haiku-4-5",
        fact_extractor_model="anthropic/claude-sonnet-4-6",
        summary_fast_model="anthropic/claude-haiku-4-5",
        summary_final_model="anthropic/claude-opus-4-8",
        doc_scores=(ok_score("a.md", 0.7), failed_score("b.md")),
        mean_blended=0.7,
    )


@dataclass
class FakeEvaluator:
    run: EvalRun
    received: list[tuple[SummaryPrompts, str]] = field(default_factory=list)
    progress_messages: tuple[str, ...] = ()

    def evaluate(
        self, *, prompts: SummaryPrompts, run_id: str, progress: Progress = no_progress
    ) -> EvalRun:
        self.received.append((prompts, run_id))
        for message in self.progress_messages:
            progress(message)
        return replace(self.run, run_id=run_id)

    def rescore(
        self,
        *,
        summaries: Sequence[GeneratedSummary],
        prompt_versions: dict[str, str],
        run_id: str,
        progress: Progress = no_progress,
    ) -> EvalRun:
        return replace(self.run, run_id=run_id, prompt_versions=prompt_versions)


def test_eval_summary_reports_per_doc_scores_and_artifact(tmp_path: Path) -> None:
    captured: list[tuple[EvalConfig, tuple[str, ...] | None]] = []
    evaluator = FakeEvaluator(run=canned_run())

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> FakeEvaluator:
        captured.append((config, doc_names))
        return evaluator

    result = CliRunner().invoke(
        build_eval_summary_command(factory),
        [
            "--docs",
            "a.md",
            "--docs",
            "b.md",
            "--prompt",
            "chunk_summary=v001",
            "--judge-model",
            "judge/x",
            "--fact-extractor-model",
            "extractor/y",
            "--evals-dir",
            str(tmp_path / "evals"),
        ],
    )

    assert result.exit_code == 0, result.output
    config, doc_names = captured[0]
    assert config.corpus_dir == tmp_path / "evals" / "corpus"
    assert config.facts_dir == tmp_path / "evals" / "facts"
    assert config.runs_dir == tmp_path / "evals" / "runs"
    assert config.settings.judge_model == "judge/x"
    assert config.settings.fact_extractor_model == "extractor/y"
    assert doc_names == ("a.md", "b.md")

    prompts, run_id = evaluator.received[0]
    assert prompts.chunk_summary.version == "v001"

    assert "Starting eval-summary run:" in result.output
    assert "Docs: a.md, b.md" in result.output
    assert "Summary pipeline: graph=on" in result.output
    assert "Prompts: chunk_summary=v001" in result.output
    assert (
        "a.md: blended=0.700 coverage=0.80 faithfulness=0.90 density=0.50 rubric=0.75"
    ) in result.output
    assert "b.md: FAILED (judge exploded)" in result.output
    assert "Mean blended: 0.700" in result.output
    assert f"Run artifact: {config.runs_dir / (run_id + '.json')}" in result.output


def test_eval_summary_streams_progress_messages(tmp_path: Path) -> None:
    evaluator = FakeEvaluator(
        run=canned_run(),
        progress_messages=("loaded 2 eval document(s)", "scoring (1/2) a.md"),
    )

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> FakeEvaluator:
        return evaluator

    result = CliRunner().invoke(
        build_eval_summary_command(factory),
        ["--evals-dir", str(tmp_path / "evals")],
    )

    assert result.exit_code == 0, result.output
    assert "loaded 2 eval document(s)" in result.output
    assert "scoring (1/2) a.md" in result.output


def test_eval_summary_no_graph_disables_graph_pass_and_labels_run(
    tmp_path: Path,
) -> None:
    captured: list[tuple[EvalConfig, tuple[str, ...] | None]] = []
    evaluator = FakeEvaluator(run=canned_run())

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> FakeEvaluator:
        captured.append((config, doc_names))
        return evaluator

    result = CliRunner().invoke(
        build_eval_summary_command(factory),
        [
            "--no-graph",
            "--run-id",
            "20260619T120000-nograph",
            "--evals-dir",
            str(tmp_path / "evals"),
        ],
    )

    assert result.exit_code == 0, result.output
    config, _ = captured[0]
    assert config.summary.graph_enhanced is False

    _, run_id = evaluator.received[0]
    assert run_id == "20260619T120000-nograph"
    assert (
        f"Run artifact: {config.runs_dir / '20260619T120000-nograph.json'}"
        in result.output
    )


def test_eval_summary_keeps_graph_pass_by_default(tmp_path: Path) -> None:
    captured: list[tuple[EvalConfig, tuple[str, ...] | None]] = []

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> FakeEvaluator:
        captured.append((config, doc_names))
        return FakeEvaluator(run=canned_run())

    result = CliRunner().invoke(
        build_eval_summary_command(factory),
        ["--evals-dir", str(tmp_path / "evals")],
    )

    assert result.exit_code == 0, result.output
    config, _ = captured[0]
    assert config.summary.graph_enhanced is True


def test_eval_summary_accepts_production_prompt_overrides(tmp_path: Path) -> None:
    captured: list[tuple[EvalConfig, tuple[str, ...] | None]] = []
    evaluator = FakeEvaluator(run=canned_run())

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> FakeEvaluator:
        captured.append((config, doc_names))
        return evaluator

    result = CliRunner().invoke(
        build_eval_summary_command(factory),
        [
            "--prompt",
            "graph_guided_summary=v001",
            "--prompt",
            "merged_summary=v001",
            "--evals-dir",
            str(tmp_path / "evals"),
        ],
    )

    assert result.exit_code == 0, result.output
    config, _ = captured[0]
    assert config.summary.prompt_overrides == {
        "graph_guided_summary": "v001",
        "merged_summary": "v001",
    }
    prompts, _ = evaluator.received[0]
    assert prompts.final_summary.version == "v003"
    assert "graph_guided_summary=v001" in result.output
    assert "merged_summary=v001" in result.output


def test_eval_summary_rejects_eval_prompt_override(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        build_eval_summary_command(),
        [
            "--prompt",
            "fact_coverage_judge=v001",
            "--evals-dir",
            str(tmp_path / "evals"),
        ],
    )

    assert result.exit_code == 2
    assert "unknown production prompt" in result.output


def test_eval_summary_no_coverage_repair_disables_repair_pass(tmp_path: Path) -> None:
    captured: list[tuple[EvalConfig, tuple[str, ...] | None]] = []

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> FakeEvaluator:
        captured.append((config, doc_names))
        return FakeEvaluator(run=canned_run())

    result = CliRunner().invoke(
        build_eval_summary_command(factory),
        ["--no-coverage-repair", "--evals-dir", str(tmp_path / "evals")],
    )

    assert result.exit_code == 0, result.output
    config, _ = captured[0]
    # Repair is gated independently of the graph pass.
    assert config.summary.coverage_repair is False
    assert config.summary.graph_enhanced is True


def test_eval_summary_rejects_malformed_prompt_override(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        build_eval_summary_command(),
        ["--prompt", "chunk_summary", "--evals-dir", str(tmp_path)],
    )

    assert result.exit_code == 2
    assert "NAME=VERSION" in result.output


def test_eval_summary_reports_unknown_prompt_override_cleanly(
    tmp_path: Path,
) -> None:
    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> FakeEvaluator:
        return FakeEvaluator(run=canned_run())

    result = CliRunner().invoke(
        build_eval_summary_command(factory),
        ["--prompt", "nope=v001", "--evals-dir", str(tmp_path)],
    )

    assert result.exit_code == 2
    assert "unknown production prompt" in result.output
