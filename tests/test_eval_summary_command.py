from dataclasses import dataclass, field, replace
from pathlib import Path

from click.testing import CliRunner

from alex.commands.eval_summary import build_eval_summary_command
from alex.lib.summarize import SummaryPrompts
from alex.lib.summary_eval import DocScore, EvalConfig, EvalRun, Progress, no_progress


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

    def evaluate(
        self, *, prompts: SummaryPrompts, run_id: str, progress: Progress = no_progress
    ) -> EvalRun:
        self.received.append((prompts, run_id))
        return replace(self.run, run_id=run_id)


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
            "--evals-dir",
            str(tmp_path / "evals"),
        ],
    )

    assert result.exit_code == 0, result.output
    config, doc_names = captured[0]
    assert config.corpus_dir == tmp_path / "evals" / "corpus"
    assert config.facts_dir == tmp_path / "evals" / "facts"
    assert config.runs_dir == tmp_path / "evals" / "runs"
    assert doc_names == ("a.md", "b.md")

    prompts, run_id = evaluator.received[0]
    assert prompts.chunk_summary.version == "v001"

    assert "Prompts: chunk_summary=v001" in result.output
    assert (
        "a.md: blended=0.700 coverage=0.80 faithfulness=0.90 density=0.50 rubric=0.75"
    ) in result.output
    assert "b.md: FAILED (judge exploded)" in result.output
    assert "Mean blended: 0.700" in result.output
    assert f"Run artifact: {config.runs_dir / (run_id + '.json')}" in result.output


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

    assert result.exit_code == 1
    assert "Unknown summary prompts" in result.output
