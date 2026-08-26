"""Two-critic production prompt bundle improvement."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from importlib.resources.abc import Traversable
from pathlib import Path

from alex.lib.llm import Completer
from alex.lib.production_prompts import (
    PRODUCTION_PROMPT_NAMES,
    PRODUCTION_PROMPT_ROLES,
    load_production_prompt_map,
    production_prompt_versions,
)
from alex.lib.prompt_improvement import paired_deltas
from alex.lib.prompt_templates import (
    PromptTemplate,
    load_prompt,
    next_version,
    save_prompt_version,
    set_active_version,
)
from alex.lib.summarize import SummaryPrompts
from alex.lib.summary_eval import EvalConfig, EvalRun, Progress, SummaryEvaluator

DEFAULT_BUNDLE_CRITIC_MODEL_A = "openai/gpt-5.6-sol"


class PromptBundleImprovementError(ValueError):
    pass


EvaluatorFactory = Callable[[EvalConfig, tuple[str, ...] | None], SummaryEvaluator]


@dataclass(frozen=True)
class BundleImprovementSettings:
    min_delta: float = 0.02
    promote: bool = False
    critic_model_a: str = DEFAULT_BUNDLE_CRITIC_MODEL_A
    critic_model_b: str = ""
    synthesis_model: str | None = None
    critic_max_tokens: int = 32_000

    def resolved_synthesis_model(self) -> str:
        return self.synthesis_model or self.critic_model_a


@dataclass(frozen=True)
class BundleCandidate:
    versions: dict[str, str]
    changed_prompts: tuple[str, ...]


@dataclass(frozen=True)
class BundleImprovementReport:
    run_id_prefix: str
    baseline_run: EvalRun
    candidate_run: EvalRun | None
    changed_versions: dict[str, str]
    doc_deltas: dict[str, float]
    delta: float | None
    promoted: bool
    rejected_reason: str | None
    artifact_dir: Path


def improve_prompt_bundle(
    *,
    config: EvalConfig,
    doc_names: tuple[str, ...] | None,
    evaluator_factory: EvaluatorFactory,
    critic: Completer,
    settings: BundleImprovementSettings,
    run_id_prefix: str,
    lineage_dir: Path,
    artifact_dir: Path,
    progress: Progress,
    prompts_root: Traversable | None = None,
) -> BundleImprovementReport:
    if not settings.critic_model_b:
        raise PromptBundleImprovementError("A second critic model is required.")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    record_git_status(artifact_dir)
    current_prompts = load_production_prompt_map(root=prompts_root)
    starting_versions = production_prompt_versions(current_prompts)
    write_json_artifact(
        artifact_dir / "starting_active_versions.json",
        starting_versions,
    )
    baseline_run = evaluate_bundle(
        config=config,
        doc_names=doc_names,
        evaluator_factory=evaluator_factory,
        prompt_versions={},
        run_id=f"{run_id_prefix}-baseline",
        progress=progress,
        prompts_root=prompts_root,
    )
    prompt_package = render_prompt_package(current_prompts)
    evidence = render_run_evidence(baseline_run)
    (artifact_dir / "prompt_package.md").write_text(prompt_package, encoding="utf-8")
    (artifact_dir / "baseline_evidence.md").write_text(evidence, encoding="utf-8")
    critic_template = load_prompt("prompt_bundle_critic", root=prompts_root)
    synthesis_template = load_prompt("prompt_bundle_synthesizer", root=prompts_root)

    critic_prompt = critic_template.render(
        pipeline_goal=PIPELINE_GOAL,
        prompt_package=prompt_package,
        baseline_evidence=evidence,
    )
    proposal_a_raw = critic.complete(
        prompt=critic_prompt,
        model=settings.critic_model_a,
        max_tokens=settings.critic_max_tokens,
    )
    proposal_b_raw = critic.complete(
        prompt=critic_prompt,
        model=settings.critic_model_b,
        max_tokens=settings.critic_max_tokens,
    )
    (artifact_dir / "critic_a.json").write_text(proposal_a_raw, encoding="utf-8")
    (artifact_dir / "critic_b.json").write_text(proposal_b_raw, encoding="utf-8")

    synthesis_prompt = synthesis_template.render(
        pipeline_goal=PIPELINE_GOAL,
        prompt_package=prompt_package,
        baseline_evidence=evidence,
        critic_a_model=settings.critic_model_a,
        critic_a_proposal=proposal_a_raw,
        critic_b_model=settings.critic_model_b,
        critic_b_proposal=proposal_b_raw,
    )
    synthesis_raw = critic.complete(
        prompt=synthesis_prompt,
        model=settings.resolved_synthesis_model(),
        max_tokens=settings.critic_max_tokens,
    )
    (artifact_dir / "synthesis.json").write_text(synthesis_raw, encoding="utf-8")
    rewrites = parse_bundle_rewrites(synthesis_raw, current_prompts=current_prompts)
    candidate = save_candidate_versions(
        rewrites,
        current_prompts=current_prompts,
        prompts_root=prompts_root,
    )

    if not candidate.changed_prompts:
        report = BundleImprovementReport(
            run_id_prefix=run_id_prefix,
            baseline_run=baseline_run,
            candidate_run=None,
            changed_versions={},
            doc_deltas={},
            delta=None,
            promoted=False,
            rejected_reason="synthesis produced no prompt changes",
            artifact_dir=artifact_dir,
        )
        append_bundle_lineage(lineage_dir=lineage_dir, report=report)
        write_bundle_audit_artifacts(
            artifact_dir=artifact_dir,
            report=report,
            starting_versions=starting_versions,
            final_versions=production_prompt_versions(
                load_production_prompt_map(root=prompts_root)
            ),
            candidate_versions={},
        )
        return report

    candidate_run = evaluate_bundle(
        config=config,
        doc_names=doc_names,
        evaluator_factory=evaluator_factory,
        prompt_versions=candidate.versions,
        run_id=f"{run_id_prefix}-candidate",
        progress=progress,
        prompts_root=prompts_root,
    )
    doc_deltas = paired_deltas(baseline_run, candidate_run)
    if not doc_deltas:
        rejected_reason: str | None = "no document scored cleanly in both runs"
        delta = None
        promoted = False
    else:
        delta = sum(doc_deltas.values()) / len(doc_deltas)
        gate_passed, rejected_reason = bundle_promotion_gate(
            delta=delta,
            doc_deltas=doc_deltas,
            min_delta=settings.min_delta,
        )
        promoted = bool(gate_passed and settings.promote)
        if promoted:
            promote_bundle(candidate, prompts_root=prompts_root)
    final_versions = production_prompt_versions(
        load_production_prompt_map(root=prompts_root)
    )

    report = BundleImprovementReport(
        run_id_prefix=run_id_prefix,
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        changed_versions={
            name: candidate.versions[name] for name in candidate.changed_prompts
        },
        doc_deltas=doc_deltas,
        delta=delta,
        promoted=promoted,
        rejected_reason=rejected_reason,
        artifact_dir=artifact_dir,
    )
    append_bundle_lineage(lineage_dir=lineage_dir, report=report)
    write_bundle_audit_artifacts(
        artifact_dir=artifact_dir,
        report=report,
        starting_versions=starting_versions,
        final_versions=final_versions,
        candidate_versions=candidate.versions,
    )
    return report


def evaluate_bundle(
    *,
    config: EvalConfig,
    doc_names: tuple[str, ...] | None,
    evaluator_factory: EvaluatorFactory,
    prompt_versions: Mapping[str, str],
    run_id: str,
    progress: Progress,
    prompts_root: Traversable | None = None,
) -> EvalRun:
    summary_overrides = {
        name: version
        for name, version in prompt_versions.items()
        if name
        in {
            "chunk_summary",
            "chunk_summary_with_graph",
            "compression_summary",
            "final_summary",
        }
    }
    bundle_config = replace(
        config,
        summary=replace(
            config.summary,
            prompt_overrides=dict(prompt_versions),
        ),
    )
    evaluator = evaluator_factory(bundle_config, doc_names)
    return evaluator.evaluate(
        prompts=SummaryPrompts.load(
            overrides=summary_overrides or None,
            root=prompts_root,
        ),
        run_id=run_id,
        progress=progress,
    )


def render_prompt_package(prompts: Mapping[str, PromptTemplate]) -> str:
    sections: list[str] = []
    for name in PRODUCTION_PROMPT_NAMES:
        prompt = prompts[name]
        sections.extend(
            [
                f"## {name} ({prompt.version})",
                f"Role: {PRODUCTION_PROMPT_ROLES[name]}",
                "Placeholders: " + ", ".join(sorted(prompt.placeholders())),
                "",
                "```text",
                prompt.text.strip(),
                "```",
                "",
            ]
        )
    return "\n".join(sections).strip()


def render_run_evidence(run: EvalRun) -> str:
    lines = [f"Run: {run.run_id}", f"Mean blended: {run.mean_blended:.4f}", ""]
    for score in sorted(run.doc_scores, key=lambda item: item.blended):
        if score.error is not None:
            lines.append(f"- {score.doc_name}: FAILED {score.error}")
            continue
        lines.append(
            f"- {score.doc_name}: blended={score.blended:.4f} "
            f"coverage={score.coverage:.3f} faithfulness={score.faithfulness:.3f} "
            f"density={score.density:.3f} rubric={score.rubric:.3f}"
        )
        if score.missed_facts:
            lines.append("  Missed facts:")
            lines.extend(f"  * {fact}" for fact in score.missed_facts[:8])
        if score.unsupported_claims:
            lines.append("  Unsupported claims:")
            lines.extend(f"  * {claim}" for claim in score.unsupported_claims[:8])
        if score.rubric_notes:
            lines.append(f"  Rubric notes: {score.rubric_notes}")
    return "\n".join(lines)


def parse_bundle_rewrites(
    raw: str,
    *,
    current_prompts: Mapping[str, PromptTemplate],
) -> dict[str, str]:
    try:
        payload = json.loads(strip_code_fence(raw))
    except json.JSONDecodeError as error:
        raise PromptBundleImprovementError(
            f"Bundle synthesis returned invalid JSON: {error}"
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("prompts"), dict):
        raise PromptBundleImprovementError(
            "Bundle synthesis must return a JSON object with a prompts object."
        )
    prompts_payload = payload["prompts"]
    rewrites: dict[str, str] = {}
    for name in PRODUCTION_PROMPT_NAMES:
        item = prompts_payload.get(name)
        if item is None:
            continue
        if not isinstance(item, dict):
            raise PromptBundleImprovementError(f"Prompt item {name} must be an object.")
        changed = item.get("changed", True)
        if not isinstance(changed, bool):
            raise PromptBundleImprovementError(
                f"Prompt item {name}.changed must be a boolean."
            )
        if not changed:
            continue
        rewrite = item.get("rewrite")
        if not isinstance(rewrite, str) or not rewrite.strip():
            raise PromptBundleImprovementError(
                f"Prompt item {name}.rewrite must be a non-empty string."
            )
        candidate = PromptTemplate(name=name, version="candidate", text=rewrite)
        if candidate.placeholders() != current_prompts[name].placeholders():
            raise PromptBundleImprovementError(
                f"Prompt {name} changed placeholders: "
                f"{sorted(candidate.placeholders())} != "
                f"{sorted(current_prompts[name].placeholders())}"
            )
        rewrites[name] = rewrite.strip() + "\n"
    return rewrites


def save_candidate_versions(
    rewrites: Mapping[str, str],
    *,
    current_prompts: Mapping[str, PromptTemplate],
    prompts_root: Traversable | None = None,
) -> BundleCandidate:
    versions: dict[str, str] = {}
    changed: list[str] = []
    for name in PRODUCTION_PROMPT_NAMES:
        rewrite = rewrites.get(name)
        if rewrite is None:
            continue
        if rewrite.strip() == current_prompts[name].text.strip():
            continue
        version = next_version(name, root=prompts_root)
        save_prompt_version(name, version=version, text=rewrite, root=prompts_root)
        versions[name] = version
        changed.append(name)
    return BundleCandidate(versions=versions, changed_prompts=tuple(changed))


def promote_bundle(
    candidate: BundleCandidate,
    *,
    prompts_root: Traversable | None = None,
) -> None:
    for name in candidate.changed_prompts:
        set_active_version(name, candidate.versions[name], root=prompts_root)


def bundle_promotion_gate(
    *,
    delta: float,
    doc_deltas: dict[str, float],
    min_delta: float,
) -> tuple[bool, str | None]:
    if delta < min_delta:
        return False, f"mean delta {delta:+.4f} is below min delta {min_delta:+.4f}"
    wins_or_ties = sum(1 for value in doc_deltas.values() if value >= 0)
    if wins_or_ties * 2 <= len(doc_deltas):
        return False, (
            f"candidate wins or ties on only {wins_or_ties} of "
            f"{len(doc_deltas)} documents"
        )
    return True, None


def append_bundle_lineage(
    *,
    lineage_dir: Path,
    report: BundleImprovementReport,
) -> None:
    lineage_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id_prefix": report.run_id_prefix,
        "baseline_run_id": report.baseline_run.run_id,
        "candidate_run_id": (
            report.candidate_run.run_id if report.candidate_run is not None else None
        ),
        "changed_versions": report.changed_versions,
        "doc_deltas": report.doc_deltas,
        "delta": report.delta,
        "promoted": report.promoted,
        "rejected_reason": report.rejected_reason,
        "artifact_dir": str(report.artifact_dir),
    }
    with (lineage_dir / "production_prompt_bundle.jsonl").open(
        "a", encoding="utf-8"
    ) as lineage_file:
        lineage_file.write(json.dumps(record) + "\n")


def record_git_status(artifact_dir: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        content = f"git status unavailable: {error}\n"
    else:
        content = result.stdout
        if result.stderr:
            content += "\n[stderr]\n" + result.stderr
        if result.returncode != 0:
            content += f"\n[exit_code] {result.returncode}\n"
    (artifact_dir / "git_status.txt").write_text(content, encoding="utf-8")


def write_bundle_audit_artifacts(
    *,
    artifact_dir: Path,
    report: BundleImprovementReport,
    starting_versions: Mapping[str, str],
    final_versions: Mapping[str, str],
    candidate_versions: Mapping[str, str],
) -> None:
    write_json_artifact(
        artifact_dir / "prompt_version_maps.json",
        {
            "starting_active_versions": dict(starting_versions),
            "baseline_run_versions": report.baseline_run.prompt_versions,
            "candidate_versions": dict(candidate_versions),
            "candidate_run_versions": (
                report.candidate_run.prompt_versions
                if report.candidate_run is not None
                else None
            ),
            "final_active_versions": dict(final_versions),
        },
    )
    write_json_artifact(
        artifact_dir / "gate_result.json",
        {
            "delta": report.delta,
            "doc_deltas": report.doc_deltas,
            "promoted": report.promoted,
            "rejected_reason": report.rejected_reason,
            "changed_versions": report.changed_versions,
        },
    )
    write_json_artifact(
        artifact_dir / "final_active_versions.json",
        dict(final_versions),
    )


def write_json_artifact(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


PIPELINE_GOAL = (
    "Produce dense, source-faithful, academically useful summaries that preserve "
    "document structure, central arguments, claims, evidence, caveats, key "
    "passages, and citation-worthy detail without unsupported inference or "
    "overcompression. The graph path should improve coverage without reducing "
    "faithfulness."
)
