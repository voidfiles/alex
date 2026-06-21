import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from alex.lib.production_prompts import PRODUCTION_PROMPT_NAMES
from alex.lib.prompt_bundle_improvement import (
    BundleImprovementSettings,
    PromptBundleImprovementError,
    improve_prompt_bundle,
)
from alex.lib.prompt_templates import load_prompt
from alex.lib.summarize import SummaryPrompts
from alex.lib.summary_eval import (
    DocScore,
    EvalConfig,
    EvalRun,
    GeneratedSummary,
    Progress,
    mean_blended,
    no_progress,
)


def doc_score(name: str, blended: float) -> DocScore:
    return DocScore(
        doc_name=name,
        coverage=blended,
        faithfulness=blended,
        density=blended,
        rubric=blended,
        blended=blended,
        missed_facts=(f"Missed fact for {name}.",),
        unsupported_claims=(),
        rubric_notes="Notes.",
        summary=f"Summary for {name}.",
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
                doc_text=f"Text for {score.doc_name}.",
                summary=score.summary,
            )
            for score in scores
        ),
    )


@dataclass
class ScriptedEvaluator:
    runs: list[EvalRun]
    received_versions: list[dict[str, str]] = field(default_factory=list)
    received_overrides: list[dict[str, str]] = field(default_factory=list)

    def evaluate(
        self, *, prompts: SummaryPrompts, run_id: str, progress: Progress = no_progress
    ) -> EvalRun:
        self.received_versions.append(
            {
                "chunk_summary": prompts.chunk_summary.version,
                "chunk_summary_with_graph": prompts.chunk_summary_with_graph.version,
                "compression_summary": prompts.compression_summary.version,
                "final_summary": prompts.final_summary.version,
            }
        )
        run = self.runs.pop(0)
        return EvalRun(
            run_id=run_id,
            prompt_versions=run.prompt_versions,
            judge_model=run.judge_model,
            fact_extractor_model=run.fact_extractor_model,
            summary_fast_model=run.summary_fast_model,
            summary_final_model=run.summary_final_model,
            doc_scores=run.doc_scores,
            mean_blended=run.mean_blended,
            generated_summaries=run.generated_summaries,
        )

    def rescore(
        self,
        *,
        summaries: Sequence[GeneratedSummary],
        prompt_versions: dict[str, str],
        run_id: str,
        progress: Progress = no_progress,
    ) -> EvalRun:
        raise AssertionError("not used")


@dataclass
class ScriptedCritic:
    responses: list[str]
    calls: list[tuple[str, str, int]] = field(default_factory=list)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append((prompt, model, max_tokens))
        return self.responses.pop(0)


def make_prompts_root(tmp_path: Path) -> Path:
    root = tmp_path / "prompts"
    for name in PRODUCTION_PROMPT_NAMES:
        active = load_prompt(name)
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "v001.md").write_text(active.text, encoding="utf-8")
        (directory / "active.txt").write_text("v001\n", encoding="utf-8")
    for name in ("prompt_bundle_critic", "prompt_bundle_synthesizer"):
        active = load_prompt(name)
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "v001.md").write_text(active.text, encoding="utf-8")
        (directory / "active.txt").write_text("v001\n", encoding="utf-8")
    return root


def synthesis_payload(rewrite: str) -> str:
    prompts = {
        name: {"changed": False, "rewrite": load_prompt(name).text}
        for name in PRODUCTION_PROMPT_NAMES
    }
    prompts["chunk_summary"] = {
        "changed": True,
        "rewrite": rewrite,
        "rationale": "Improve missed fact coverage.",
        "risk": "May overfit.",
    }
    return json.dumps({"prompts": prompts})


def test_bundle_improvement_blends_two_critics_and_promotes_winner(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("baseline", (doc_score("a.md", 0.50), doc_score("b.md", 0.60))),
            eval_run("candidate", (doc_score("a.md", 0.58), doc_score("b.md", 0.66))),
        ]
    )
    captured_configs: list[EvalConfig] = []

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> ScriptedEvaluator:
        captured_configs.append(config)
        evaluator.received_overrides.append(dict(config.summary.prompt_overrides))
        return evaluator

    current = load_prompt("chunk_summary").text
    rewrite = current + "\nBe especially complete about measured findings.\n"
    critic = ScriptedCritic(
        responses=[
            json.dumps({"prompts": {}}),
            json.dumps({"prompts": {}}),
            synthesis_payload(rewrite),
        ]
    )

    report = improve_prompt_bundle(
        config=EvalConfig(
            corpus_dir=tmp_path / "corpus",
            facts_dir=tmp_path / "facts",
            runs_dir=tmp_path / "runs",
        ),
        doc_names=("a.md", "b.md"),
        evaluator_factory=factory,
        critic=critic,
        settings=BundleImprovementSettings(
            promote=True,
            critic_model_a="anthropic/a",
            critic_model_b="openai/b",
            synthesis_model="openai/s",
            critic_max_tokens=123,
        ),
        run_id_prefix="bundle",
        lineage_dir=tmp_path / "lineage",
        artifact_dir=tmp_path / "artifacts",
        progress=no_progress,
        prompts_root=root,
    )

    assert [model for _, model, _ in critic.calls] == [
        "anthropic/a",
        "openai/b",
        "openai/s",
    ]
    assert all(max_tokens == 123 for _, _, max_tokens in critic.calls)
    assert report.promoted is True
    assert report.delta == pytest.approx(0.07)
    assert report.changed_versions == {"chunk_summary": "v002"}
    assert (root / "chunk_summary" / "v002.md").read_text(encoding="utf-8") == rewrite
    active = (root / "chunk_summary" / "active.txt").read_text(encoding="utf-8")
    assert active == "v002\n"
    assert evaluator.received_versions[1]["chunk_summary"] == "v002"
    assert evaluator.received_overrides[1] == {"chunk_summary": "v002"}
    assert (tmp_path / "artifacts" / "critic_a.json").is_file()
    assert (tmp_path / "artifacts" / "git_status.txt").is_file()
    assert (tmp_path / "artifacts" / "prompt_package.md").is_file()
    assert (tmp_path / "artifacts" / "baseline_evidence.md").is_file()
    assert (tmp_path / "artifacts" / "prompt_version_maps.json").is_file()
    assert (tmp_path / "artifacts" / "gate_result.json").is_file()
    assert (tmp_path / "artifacts" / "final_active_versions.json").is_file()
    assert (tmp_path / "lineage" / "production_prompt_bundle.jsonl").is_file()


def test_bundle_improvement_evaluates_graph_and_merge_prompt_versions(
    tmp_path: Path,
) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[
            eval_run("baseline", (doc_score("a.md", 0.50),)),
            eval_run("candidate", (doc_score("a.md", 0.55),)),
        ]
    )
    captured_overrides: list[dict[str, str]] = []

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> ScriptedEvaluator:
        captured_overrides.append(dict(config.summary.prompt_overrides))
        return evaluator

    graph_rewrite = (
        load_prompt("graph_guided_summary").text
        + "\nPreserve graph-supported caveats and key passages.\n"
    )
    repair_rewrite = (
        load_prompt("merged_summary_repair").text
        + "\nRestore graph-supported claims only when source-grounded.\n"
    )
    prompts = {
        name: {"changed": False, "rewrite": load_prompt(name).text}
        for name in PRODUCTION_PROMPT_NAMES
    }
    prompts["graph_guided_summary"] = {
        "changed": True,
        "rewrite": graph_rewrite,
    }
    prompts["merged_summary_repair"] = {
        "changed": True,
        "rewrite": repair_rewrite,
    }
    critic = ScriptedCritic(
        responses=[
            json.dumps({"prompts": {}}),
            json.dumps({"prompts": {}}),
            json.dumps({"prompts": prompts}),
        ]
    )

    report = improve_prompt_bundle(
        config=EvalConfig(
            corpus_dir=tmp_path / "corpus",
            facts_dir=tmp_path / "facts",
            runs_dir=tmp_path / "runs",
        ),
        doc_names=("a.md",),
        evaluator_factory=factory,
        critic=critic,
        settings=BundleImprovementSettings(
            critic_model_a="anthropic/a",
            critic_model_b="openai/b",
        ),
        run_id_prefix="bundle",
        lineage_dir=tmp_path / "lineage",
        artifact_dir=tmp_path / "artifacts",
        progress=no_progress,
        prompts_root=root,
    )

    assert report.changed_versions == {
        "graph_guided_summary": "v002",
        "merged_summary_repair": "v002",
    }
    assert captured_overrides[0] == {}
    assert captured_overrides[1] == report.changed_versions


def test_bundle_improvement_rejects_placeholder_changes(tmp_path: Path) -> None:
    root = make_prompts_root(tmp_path)
    evaluator = ScriptedEvaluator(
        runs=[eval_run("baseline", (doc_score("a.md", 0.50),))]
    )

    def factory(
        config: EvalConfig,
        doc_names: tuple[str, ...] | None,
    ) -> ScriptedEvaluator:
        return evaluator

    critic = ScriptedCritic(
        responses=[
            json.dumps({"prompts": {}}),
            json.dumps({"prompts": {}}),
            synthesis_payload("No placeholders here."),
        ]
    )

    with pytest.raises(PromptBundleImprovementError, match="changed placeholders"):
        improve_prompt_bundle(
            config=EvalConfig(
                corpus_dir=tmp_path / "corpus",
                facts_dir=tmp_path / "facts",
                runs_dir=tmp_path / "runs",
            ),
            doc_names=None,
            evaluator_factory=factory,
            critic=critic,
            settings=BundleImprovementSettings(
                critic_model_a="anthropic/a",
                critic_model_b="openai/b",
            ),
            run_id_prefix="bundle",
            lineage_dir=tmp_path / "lineage",
            artifact_dir=tmp_path / "artifacts",
            progress=no_progress,
            prompts_root=root,
        )

    assert not (root / "chunk_summary" / "v002.md").exists()
