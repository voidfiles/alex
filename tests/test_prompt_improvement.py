import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from alex.lib.prompt_improvement import (
    ImprovementSettings,
    PromptImprovementError,
    improve_prompt,
    paired_deltas,
    promotion_gate,
)
from alex.lib.summarize import SUMMARY_PROMPT_NAMES, SummaryPrompts
from alex.lib.summary_eval import (
    DocScore,
    EvalRun,
    GeneratedSummary,
    Progress,
    doc_score_line,
    mean_blended,
    no_progress,
)

STUB_TEMPLATES = {
    "chunk_summary": "Summarize {{chunk}} of {{title}} by {{authors}} via {{headers}}.",
    "compression_summary": "Compress {{content}} from {{title}} by {{authors}}.",
    "final_summary": (
        "Synthesize {{section_summaries}} for {{title}} by {{authors}} "
        "with {{chunk_reference_list}}."
    ),
}

IMPROVED_CHUNK_TEMPLATE = (
    "Exhaustively summarize {{chunk}} of {{title}} by {{authors}} "
    "via {{headers}}. Be precise."
)


def make_prompts_root(tmp_path: Path) -> Path:
    root = tmp_path / "prompts"
    for name in SUMMARY_PROMPT_NAMES:
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "v001.md").write_text(STUB_TEMPLATES[name], encoding="utf-8")
        (directory / "active.txt").write_text("v001\n", encoding="utf-8")
    return root


def doc_score(name: str, blended: float, *, error: str | None = None) -> DocScore:
    return DocScore(
        doc_name=name,
        coverage=blended,
        faithfulness=blended,
        density=blended,
        rubric=blended,
        blended=blended,
        missed_facts=(f"Missed fact for {name}.",),
        unsupported_claims=(f"Unsupported claim for {name}.",),
        rubric_notes=f"Notes for {name}.",
        summary=f"Summary text for {name}.",
        error=error,
    )


def eval_run(run_id: str, scores: tuple[DocScore, ...]) -> EvalRun:
    return EvalRun(
        run_id=run_id,
        prompt_versions={},
        judge_model="judge",
        fact_extractor_model="extractor",
        summary_fast_model="fast",
        summary_final_model="final",
        doc_scores=scores,
        mean_blended=mean_blended(scores),
        generated_summaries=tuple(
            GeneratedSummary(
                doc_name=score.doc_name,
                doc_text=f"Document text for {score.doc_name}.",
                summary=score.summary,
            )
            for score in scores
            if score.error is None
        ),
    )


@dataclass
class ScriptedEvaluator:
    runs: list[EvalRun]
    received: list[tuple[dict[str, str], str]] = field(default_factory=list)
    rescore_runs: list[EvalRun] = field(default_factory=list)
    rescore_received: list[str] = field(default_factory=list)

    def evaluate(
        self, *, prompts: SummaryPrompts, run_id: str, progress: Progress = no_progress
    ) -> EvalRun:
        versions = {
            "chunk_summary": prompts.chunk_summary.version,
            "compression_summary": prompts.compression_summary.version,
            "final_summary": prompts.final_summary.version,
        }
        self.received.append((versions, run_id))
        run = self.runs.pop(0)
        # Mirror the real evaluator so the loop's progress wiring is exercised.
        for index, score in enumerate(run.doc_scores, 1):
            progress(f"scoring ({index}/{len(run.doc_scores)}) {score.doc_name}")
            progress(doc_score_line(score))
        return run

    def rescore(
        self,
        *,
        summaries: Sequence[GeneratedSummary],
        prompt_versions: dict[str, str],
        run_id: str,
        progress: Progress = no_progress,
    ) -> EvalRun:
        self.rescore_received.append(run_id)
        run = self.rescore_runs.pop(0)
        for index, score in enumerate(run.doc_scores, 1):
            progress(f"scoring ({index}/{len(run.doc_scores)}) {score.doc_name}")
            progress(doc_score_line(score))
        return run


@dataclass
class ScriptedCritic:
    """Returns scripted responses in order, repeating the last one."""

    responses: list[str]
    prompts: list[str] = field(default_factory=list)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self.responses) - 1)
        return self.responses[index]


def test_winning_candidate_is_saved_but_not_promoted_by_default(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60), doc_score("b.md", 0.70))),
            eval_run("r2", (doc_score("a.md", 0.65), doc_score("b.md", 0.78))),
        ]
    )
    critic = ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE])

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=critic,
        settings=ImprovementSettings(iterations=1),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    result = report.iterations[0]
    assert result.parent_version == "v001"
    assert result.candidate_version == "v002"
    assert result.parent_score == pytest.approx(0.65)
    assert result.candidate_score == pytest.approx(0.715)
    assert result.delta == pytest.approx(0.065)
    assert result.doc_deltas == {
        "a.md": pytest.approx(0.05),
        "b.md": pytest.approx(0.08),
    }
    assert result.rejected_reason is None
    assert result.promoted is False

    candidate_file = root / "chunk_summary" / "v002.md"
    assert candidate_file.read_text(encoding="utf-8") == IMPROVED_CHUNK_TEMPLATE
    active = (root / "chunk_summary" / "active.txt").read_text(encoding="utf-8")
    assert active == "v001\n"

    assert [versions["chunk_summary"] for versions, _ in evaluator.received] == [
        "v001",
        "v002",
    ]
    assert [run_id for _, run_id in evaluator.received] == [
        "t-i01-v001",
        "t-i01-v002",
    ]

    # The critic sees the incumbent text and the worst document's evidence.
    critic_prompt = critic.prompts[0]
    assert STUB_TEMPLATES["chunk_summary"] in critic_prompt
    assert "Summary text for a.md." in critic_prompt
    assert "- Missed fact for a.md." in critic_prompt
    assert "- Unsupported claim for a.md." in critic_prompt
    assert "Notes for a.md." in critic_prompt

    lineage_lines = (
        (tmp_path / "lineage" / "chunk_summary.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lineage_lines) == 1
    record = json.loads(lineage_lines[0])
    assert record["run_id_prefix"] == "t"
    assert record["parent_version"] == "v001"
    assert record["candidate_version"] == "v002"
    assert record["promoted"] is False
    assert record["rejected_reason"] is None


def test_improve_prompt_streams_progress_logs(tmp_path: Path) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60), doc_score("b.md", 0.70))),
            eval_run("r2", (doc_score("a.md", 0.65), doc_score("b.md", 0.78))),
        ]
    )
    lines: list[str] = []

    improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE]),
        settings=ImprovementSettings(iterations=1, promote=True),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        progress=lines.append,
        prompts_root=root,
    )

    assert "iteration 1/1: evaluating incumbent v001" in lines
    assert lines.count("iteration 1/1: saved candidate v002; evaluating") == 1
    # a.md (0.60) is worse than b.md (0.70), so it drives the critique.
    assert any(
        line.startswith("iteration 1/1: worst document is a.md (blended 0.600)")
        for line in lines
    )
    # Per-document scores from the evaluator stream indented beneath the milestone.
    assert "  scoring (1/2) a.md" in lines
    assert any(line.startswith("  a.md: blended=0.600") for line in lines)
    assert any(
        "iteration 1/1: v001 -> v002" in line and "(promoted)" in line for line in lines
    )


def test_promote_flag_rewrites_active_version_when_gate_passes(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60), doc_score("b.md", 0.70))),
            eval_run("r2", (doc_score("a.md", 0.65), doc_score("b.md", 0.78))),
        ]
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE]),
        settings=ImprovementSettings(iterations=1, promote=True),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    assert report.iterations[0].promoted is True
    active = (root / "chunk_summary" / "active.txt").read_text(encoding="utf-8")
    assert active == "v002\n"


def test_candidate_with_mismatched_placeholders_is_rejected(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(runs=[eval_run("r1", (doc_score("a.md", 0.60),))])

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=["A rewrite that dropped every placeholder."]),
        settings=ImprovementSettings(iterations=1),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    result = report.iterations[0]
    assert result.candidate_version is None
    assert result.rejected_reason is not None
    assert "placeholders" in result.rejected_reason
    assert not (root / "chunk_summary" / "v002.md").exists()
    assert len(evaluator.received) == 1

    record = json.loads(
        (tmp_path / "lineage" / "chunk_summary.jsonl").read_text(encoding="utf-8")
    )
    assert record["candidate_version"] is None
    assert "placeholders" in record["rejected_reason"]


def test_gate_rejects_candidate_below_min_delta_but_keeps_the_version(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60), doc_score("b.md", 0.70))),
            eval_run("r2", (doc_score("a.md", 0.55), doc_score("b.md", 0.65))),
        ]
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE]),
        settings=ImprovementSettings(iterations=1, promote=True),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    result = report.iterations[0]
    assert result.candidate_version == "v002"
    assert result.promoted is False
    assert result.rejected_reason is not None
    assert "below min delta" in result.rejected_reason
    # The candidate stays on disk for human review; active is untouched.
    assert (root / "chunk_summary" / "v002.md").exists()
    active = (root / "chunk_summary" / "active.txt").read_text(encoding="utf-8")
    assert active == "v001\n"


def test_gate_requires_wins_or_ties_on_a_strict_majority_of_docs(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run(
                "r1",
                (
                    doc_score("a.md", 0.50),
                    doc_score("b.md", 0.50),
                    doc_score("c.md", 0.50),
                ),
            ),
            eval_run(
                "r2",
                (
                    doc_score("a.md", 0.90),
                    doc_score("b.md", 0.45),
                    doc_score("c.md", 0.45),
                ),
            ),
        ]
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE]),
        settings=ImprovementSettings(iterations=1, promote=True),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    result = report.iterations[0]
    assert result.delta == pytest.approx(0.1)
    assert result.promoted is False
    assert result.rejected_reason is not None
    assert "only 1 of 3 documents" in result.rejected_reason


def test_near_threshold_candidate_is_adjudicated_before_promotion(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60), doc_score("b.md", 0.60))),
            eval_run("r2", (doc_score("a.md", 0.62), doc_score("b.md", 0.62))),
        ],
        rescore_runs=[
            eval_run("r1a", (doc_score("a.md", 0.60), doc_score("b.md", 0.60))),
            eval_run("r2a", (doc_score("a.md", 0.66), doc_score("b.md", 0.66))),
        ],
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE]),
        settings=ImprovementSettings(
            iterations=1,
            promote=True,
            min_delta=0.02,
            adjudication_margin=0.01,
            adjudication_repeats=1,
        ),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    result = report.iterations[0]
    assert result.adjudicated is True
    assert result.adjudication_run_ids == (
        "t-i01-adj01-parent",
        "t-i01-adj01-candidate",
    )
    assert result.delta == pytest.approx(0.04)
    assert result.promoted is True
    assert evaluator.rescore_received == list(result.adjudication_run_ids)

    record = json.loads(
        (tmp_path / "lineage" / "chunk_summary.jsonl").read_text(encoding="utf-8")
    )
    assert record["adjudicated"] is True
    assert record["adjudication_run_ids"] == list(result.adjudication_run_ids)


def test_loop_stops_after_two_consecutive_failures(tmp_path: Path) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60),)),
            eval_run("r2", (doc_score("a.md", 0.60),)),
            eval_run("r3", (doc_score("a.md", 0.60),)),
        ]
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=["No placeholders here either."]),
        settings=ImprovementSettings(iterations=5),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    assert len(report.iterations) == 2
    assert all(result.candidate_version is None for result in report.iterations)


def test_all_docs_failing_evaluation_rejects_the_iteration(tmp_path: Path) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.0, error="judge exploded"),)),
            eval_run("r2", (doc_score("a.md", 0.0, error="judge exploded"),)),
        ]
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE]),
        settings=ImprovementSettings(iterations=2),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    assert len(report.iterations) == 2
    assert all(
        result.rejected_reason == "every corpus document failed evaluation"
        for result in report.iterations
    )


def test_unknown_prompt_name_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PromptImprovementError, match="unknown summary prompt"):
        improve_prompt(
            prompt_name="fact_extraction",
            evaluator=ScriptedEvaluator(runs=[]),
            critic=ScriptedCritic(responses=["x"]),
            settings=ImprovementSettings(),
            lineage_dir=tmp_path / "lineage",
            run_id_prefix="t",
        )


def test_promotion_gate_boundary_values() -> None:
    settings = ImprovementSettings(min_delta=0.02)

    # Mean delta exactly at min_delta passes; just under fails.
    passed, reason = promotion_gate(
        delta=0.02, doc_deltas={"a.md": 0.02, "b.md": 0.02}, settings=settings
    )
    assert passed and reason is None
    passed, reason = promotion_gate(
        delta=0.0199, doc_deltas={"a.md": 0.02, "b.md": 0.02}, settings=settings
    )
    assert not passed
    assert reason is not None and "below min delta" in reason

    # Wins-or-ties at exactly half is not a strict majority.
    half = {"a.md": 0.5, "b.md": 0.5, "c.md": -0.1, "d.md": -0.1}
    passed, reason = promotion_gate(delta=0.2, doc_deltas=half, settings=settings)
    assert not passed
    assert reason is not None and "only 2 of 4" in reason

    # A tie (delta == 0) counts toward the majority.
    majority = {"a.md": 0.5, "b.md": 0.0, "c.md": 0.0, "d.md": -0.1}
    passed, reason = promotion_gate(delta=0.1, doc_deltas=majority, settings=settings)
    assert passed and reason is None


def test_paired_deltas_excludes_docs_that_failed_in_either_run() -> None:
    incumbent = eval_run(
        "r1",
        (
            doc_score("a.md", 0.60),
            doc_score("b.md", 0.0, error="judge exploded"),
            doc_score("c.md", 0.50),
        ),
    )
    candidate = eval_run(
        "r2",
        (
            doc_score("a.md", 0.70),
            doc_score("b.md", 0.90),
            doc_score("c.md", 0.0, error="rate limited"),
        ),
    )

    assert paired_deltas(incumbent, candidate) == {"a.md": pytest.approx(0.1)}


def test_iteration_is_rejected_when_no_doc_scores_cleanly_in_both_runs(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60),)),
            eval_run("r2", (doc_score("a.md", 0.0, error="judge exploded"),)),
        ]
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=ScriptedCritic(responses=[IMPROVED_CHUNK_TEMPLATE]),
        settings=ImprovementSettings(iterations=1, promote=True),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    result = report.iterations[0]
    assert result.candidate_version == "v002"
    assert result.promoted is False
    assert result.delta is None
    assert result.rejected_reason == "no document scored cleanly in both runs"
    active = (root / "chunk_summary" / "active.txt").read_text(encoding="utf-8")
    assert active == "v001\n"


def test_a_success_resets_the_consecutive_failure_counter(tmp_path: Path) -> None:
    root = make_prompts_root(tmp_path)
    # i1: bad critic output (failure). i2: clean win (resets the counter).
    # i3 and i4: failures again -> stop. Without the reset, the loop would
    # have stopped after i3.
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("r1", (doc_score("a.md", 0.60),)),
            eval_run("r2", (doc_score("a.md", 0.60),)),
            eval_run("r3", (doc_score("a.md", 0.70),)),
            eval_run("r4", (doc_score("a.md", 0.70),)),
            eval_run("r5", (doc_score("a.md", 0.70),)),
        ]
    )
    critic = ScriptedCritic(
        responses=[
            "No placeholders.",
            IMPROVED_CHUNK_TEMPLATE,
            "No placeholders.",
            "No placeholders.",
        ]
    )

    report = improve_prompt(
        prompt_name="chunk_summary",
        evaluator=evaluator,
        critic=critic,
        settings=ImprovementSettings(iterations=6),
        lineage_dir=tmp_path / "lineage",
        run_id_prefix="t",
        prompts_root=root,
    )

    assert len(report.iterations) == 4
    outcomes = [result.improved() for result in report.iterations]
    assert outcomes == [False, True, False, False]
