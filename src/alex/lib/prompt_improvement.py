"""Hand-rolled prompt improvement: critique, candidate, paired eval, gate.

Each iteration evaluates the incumbent prompt, has a critic model rewrite
it based on the worst-scoring document's failures, persists the rewrite as
the next ``vNNN.md``, and re-evaluates on the same documents against the
same cached facts. The promotion gate requires both a mean improvement of
at least ``min_delta`` and wins-or-ties on a strict majority of documents,
and even then ``active.txt`` is only rewritten when promotion was
explicitly requested. Every iteration is appended to the lineage log.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path

from alex.lib.llm import Completer, resolve_prompt_critic_model
from alex.lib.prompt_templates import (
    PromptTemplate,
    load_prompt,
    next_version,
    save_prompt_version,
    set_active_version,
)
from alex.lib.summarize import SUMMARY_PROMPT_NAMES, SummaryPrompts
from alex.lib.summary_eval import (
    DocScore,
    EvalRun,
    Progress,
    SummaryEvaluator,
    no_progress,
    strip_code_fence,
)


class PromptImprovementError(ValueError):
    pass


@dataclass(frozen=True)
class ImprovementSettings:
    iterations: int = 3
    min_delta: float = 0.02
    promote: bool = False
    critic_model: str = field(default_factory=resolve_prompt_critic_model)
    critic_max_tokens: int = 16_000
    max_consecutive_failures: int = 2


@dataclass(frozen=True)
class IterationResult:
    iteration: int
    parent_version: str
    candidate_version: str | None
    parent_score: float
    candidate_score: float | None
    delta: float | None
    doc_deltas: dict[str, float]
    promoted: bool
    rejected_reason: str | None

    def improved(self) -> bool:
        return self.candidate_version is not None and self.rejected_reason is None


@dataclass(frozen=True)
class ImprovementReport:
    prompt_name: str
    iterations: tuple[IterationResult, ...]


def improve_prompt(
    *,
    prompt_name: str,
    evaluator: SummaryEvaluator,
    critic: Completer,
    settings: ImprovementSettings,
    lineage_dir: Path,
    run_id_prefix: str,
    progress: Progress = no_progress,
    prompts_root: Traversable | None = None,
) -> ImprovementReport:
    if prompt_name not in SUMMARY_PROMPT_NAMES:
        raise PromptImprovementError(
            f"Cannot improve unknown summary prompt: {prompt_name}"
        )
    critic_template = load_prompt("prompt_critic")

    results: list[IterationResult] = []
    consecutive_failures = 0
    for iteration in range(1, settings.iterations + 1):
        result = run_iteration(
            iteration=iteration,
            prompt_name=prompt_name,
            evaluator=evaluator,
            critic=critic,
            critic_template=critic_template,
            settings=settings,
            run_id_prefix=run_id_prefix,
            progress=progress,
            prompts_root=prompts_root,
        )
        results.append(result)
        append_lineage(
            lineage_dir=lineage_dir,
            prompt_name=prompt_name,
            run_id_prefix=run_id_prefix,
            result=result,
        )
        if result.improved():
            consecutive_failures = 0
            continue
        consecutive_failures += 1
        if consecutive_failures >= settings.max_consecutive_failures:
            break
    return ImprovementReport(prompt_name=prompt_name, iterations=tuple(results))


def run_iteration(
    *,
    iteration: int,
    prompt_name: str,
    evaluator: SummaryEvaluator,
    critic: Completer,
    critic_template: PromptTemplate,
    settings: ImprovementSettings,
    run_id_prefix: str,
    progress: Progress,
    prompts_root: Traversable | None,
) -> IterationResult:
    tag = f"iteration {iteration}/{settings.iterations}"

    # Per-document scores stream indented beneath their evaluation milestone.
    def scoring(message: str) -> None:
        progress(f"  {message}")

    incumbent = load_prompt(prompt_name, root=prompts_root)
    progress(f"{tag}: evaluating incumbent {incumbent.version}")
    incumbent_run = evaluator.evaluate(
        prompts=SummaryPrompts.load(root=prompts_root),
        run_id=f"{run_id_prefix}-i{iteration:02d}-{incumbent.version}",
        progress=scoring,
    )

    worst = worst_scored_doc(incumbent_run)
    if worst is None:
        progress(f"{tag}: rejected, every corpus document failed evaluation")
        return rejected_result(
            iteration=iteration,
            incumbent=incumbent,
            parent_score=incumbent_run.mean_blended,
            reason="every corpus document failed evaluation",
        )

    progress(
        f"{tag}: worst document is {worst.doc_name} "
        f"(blended {worst.blended:.3f}); critiquing with {settings.critic_model}"
    )
    candidate_text = critique(
        critic=critic,
        critic_template=critic_template,
        settings=settings,
        incumbent=incumbent,
        worst=worst,
    )
    candidate_placeholders = PromptTemplate(
        name=prompt_name, version="candidate", text=candidate_text
    ).placeholders()
    if candidate_placeholders != incumbent.placeholders():
        progress(f"{tag}: rejected, candidate changed the placeholder set")
        return rejected_result(
            iteration=iteration,
            incumbent=incumbent,
            parent_score=incumbent_run.mean_blended,
            reason=(
                "candidate placeholders "
                f"{sorted(candidate_placeholders)} do not match incumbent "
                f"{sorted(incumbent.placeholders())}"
            ),
        )

    candidate_version = next_version(prompt_name, root=prompts_root)
    save_prompt_version(
        prompt_name,
        version=candidate_version,
        text=candidate_text,
        root=prompts_root,
    )

    progress(f"{tag}: saved candidate {candidate_version}; evaluating")
    candidate_run = evaluator.evaluate(
        prompts=SummaryPrompts.load(
            overrides={prompt_name: candidate_version}, root=prompts_root
        ),
        run_id=f"{run_id_prefix}-i{iteration:02d}-{candidate_version}",
        progress=scoring,
    )
    doc_deltas = paired_deltas(incumbent_run, candidate_run)
    if not doc_deltas:
        progress(f"{tag}: rejected, no document scored cleanly in both runs")
        return IterationResult(
            iteration=iteration,
            parent_version=incumbent.version,
            candidate_version=candidate_version,
            parent_score=incumbent_run.mean_blended,
            candidate_score=candidate_run.mean_blended,
            delta=None,
            doc_deltas={},
            promoted=False,
            rejected_reason="no document scored cleanly in both runs",
        )
    delta = sum(doc_deltas.values()) / len(doc_deltas)
    gate_passed, gate_reason = promotion_gate(
        delta=delta, doc_deltas=doc_deltas, settings=settings
    )

    promoted = False
    if gate_passed and settings.promote:
        set_active_version(prompt_name, candidate_version, root=prompts_root)
        promoted = True

    progress(
        f"{tag}: {incumbent.version} -> {candidate_version}, "
        f"mean delta {delta:+.3f} ({outcome_label(promoted, gate_reason)})"
    )
    return IterationResult(
        iteration=iteration,
        parent_version=incumbent.version,
        candidate_version=candidate_version,
        parent_score=incumbent_run.mean_blended,
        candidate_score=candidate_run.mean_blended,
        delta=delta,
        doc_deltas=doc_deltas,
        promoted=promoted,
        rejected_reason=gate_reason,
    )


def rejected_result(
    *,
    iteration: int,
    incumbent: PromptTemplate,
    parent_score: float,
    reason: str,
) -> IterationResult:
    return IterationResult(
        iteration=iteration,
        parent_version=incumbent.version,
        candidate_version=None,
        parent_score=parent_score,
        candidate_score=None,
        delta=None,
        doc_deltas={},
        promoted=False,
        rejected_reason=reason,
    )


def outcome_label(promoted: bool, gate_reason: str | None) -> str:
    if promoted:
        return "promoted"
    if gate_reason is None:
        return "passed gate; rerun with --promote to activate"
    return f"gate failed: {gate_reason}"


def worst_scored_doc(run: EvalRun) -> DocScore | None:
    scored = [score for score in run.doc_scores if score.error is None]
    if not scored:
        return None
    return min(scored, key=lambda score: score.blended)


def critique(
    *,
    critic: Completer,
    critic_template: PromptTemplate,
    settings: ImprovementSettings,
    incumbent: PromptTemplate,
    worst: DocScore,
) -> str:
    prompt = critic_template.render(
        prompt_name=incumbent.name,
        prompt_text=incumbent.text,
        summary=worst.summary,
        missed_facts=bulleted(worst.missed_facts),
        unsupported_claims=bulleted(worst.unsupported_claims),
        rubric_notes=worst.rubric_notes or "(none recorded)",
    )
    raw = critic.complete(
        prompt=prompt,
        model=settings.critic_model,
        max_tokens=settings.critic_max_tokens,
    )
    return strip_code_fence(raw)


def bulleted(items: Sequence[str]) -> str:
    if not items:
        return "(none recorded)"
    return "\n".join(f"- {item}" for item in items)


def paired_deltas(incumbent: EvalRun, candidate: EvalRun) -> dict[str, float]:
    """Per-doc blended deltas over docs that scored cleanly in both runs.

    A doc that failed evaluation in either run carries a meaningless 0.0,
    so including it would let a transient judge failure swing the gate;
    such docs are excluded instead.
    """
    incumbent_by_doc = {
        score.doc_name: score for score in incumbent.doc_scores if score.error is None
    }
    deltas: dict[str, float] = {}
    for score in candidate.doc_scores:
        parent = incumbent_by_doc.get(score.doc_name)
        if parent is not None and score.error is None:
            deltas[score.doc_name] = score.blended - parent.blended
    return deltas


def promotion_gate(
    *,
    delta: float,
    doc_deltas: dict[str, float],
    settings: ImprovementSettings,
) -> tuple[bool, str | None]:
    if delta < settings.min_delta:
        return False, (
            f"mean delta {delta:+.4f} is below min delta {settings.min_delta:+.4f}"
        )
    wins_or_ties = sum(1 for value in doc_deltas.values() if value >= 0)
    if wins_or_ties * 2 <= len(doc_deltas):
        return False, (
            f"candidate wins or ties on only {wins_or_ties} of "
            f"{len(doc_deltas)} documents"
        )
    return True, None


def append_lineage(
    *,
    lineage_dir: Path,
    prompt_name: str,
    run_id_prefix: str,
    result: IterationResult,
) -> None:
    lineage_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id_prefix": run_id_prefix,
        "iteration": result.iteration,
        "parent_version": result.parent_version,
        "candidate_version": result.candidate_version,
        "parent_score": result.parent_score,
        "candidate_score": result.candidate_score,
        "delta": result.delta,
        "doc_deltas": result.doc_deltas,
        "promoted": result.promoted,
        "rejected_reason": result.rejected_reason,
    }
    with (lineage_dir / f"{prompt_name}.jsonl").open(
        "a", encoding="utf-8"
    ) as lineage_file:
        lineage_file.write(json.dumps(record) + "\n")
