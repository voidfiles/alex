from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

METRICS = ("blended", "coverage", "faithfulness", "density", "rubric")


@dataclass(frozen=True)
class EvalDoc:
    doc_name: str
    blended: float
    coverage: float
    faithfulness: float
    density: float
    rubric: float
    error: str | None = None


@dataclass(frozen=True)
class EvalArtifact:
    run_id: str
    kind: str
    path: Path
    mean_blended: float
    prompt_versions: dict[str, str]
    docs: tuple[EvalDoc, ...]


@dataclass(frozen=True)
class EvalDelta:
    doc_name: str
    candidate_run: str
    baseline_run: str
    candidate: float
    baseline: float

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline


@dataclass(frozen=True)
class EvalReport:
    artifacts: tuple[EvalArtifact, ...]
    latest_standard: EvalArtifact | None
    latest_graph: EvalArtifact | None
    latest_merged: EvalArtifact | None
    latest_graph_vs_latest_standard: tuple[EvalDelta, ...]
    latest_merged_vs_latest_standard: tuple[EvalDelta, ...]
    latest_merged_vs_latest_graph: tuple[EvalDelta, ...]
    best_standard_by_doc: tuple[EvalDelta, ...]
    report_path: Path
    mean_chart_path: Path
    doc_chart_path: Path


def write_eval_report(*, evals_dir: Path, output_dir: Path | None = None) -> EvalReport:
    artifacts = read_eval_artifacts(evals_dir)
    if not artifacts:
        raise ValueError(f"No eval run artifacts found under {evals_dir}")

    output_root = output_dir or evals_dir / "reports"
    output_root.mkdir(parents=True, exist_ok=True)

    standard_runs = tuple(
        artifact for artifact in artifacts if artifact.kind == "standard"
    )
    graph_runs = tuple(
        artifact for artifact in artifacts if artifact.kind == "claim_graph"
    )
    merged_runs = tuple(
        artifact for artifact in artifacts if artifact.kind == "merged_summary"
    )
    latest_standard = latest_run(standard_runs)
    latest_graph = latest_run(graph_runs)
    latest_merged = latest_run(merged_runs)

    graph_deltas = (
        compare_by_doc(candidate=latest_graph, baseline=latest_standard)
        if latest_graph is not None and latest_standard is not None
        else ()
    )
    merged_standard_deltas = (
        compare_by_doc(candidate=latest_merged, baseline=latest_standard)
        if latest_merged is not None and latest_standard is not None
        else ()
    )
    merged_graph_deltas = (
        compare_by_doc(candidate=latest_merged, baseline=latest_graph)
        if latest_merged is not None and latest_graph is not None
        else ()
    )
    best_deltas = (
        compare_to_best_standard(candidate=latest_merged, standards=standard_runs)
        if latest_merged is not None
        else (
            compare_to_best_standard(candidate=latest_graph, standards=standard_runs)
            if latest_graph is not None
            else ()
        )
    )

    mean_chart_path = output_root / "mean-blended.svg"
    doc_chart_path = output_root / "latest-doc-blended.svg"
    write_mean_chart(artifacts, mean_chart_path)
    write_latest_doc_chart(
        standard=latest_standard,
        graph=latest_graph,
        merged=latest_merged,
        path=doc_chart_path,
    )

    report_path = output_root / "eval-report.md"
    report_path.write_text(
        render_report(
            artifacts=artifacts,
            latest_standard=latest_standard,
            latest_graph=latest_graph,
            latest_merged=latest_merged,
            graph_deltas=graph_deltas,
            merged_standard_deltas=merged_standard_deltas,
            merged_graph_deltas=merged_graph_deltas,
            best_deltas=best_deltas,
            mean_chart_path=mean_chart_path,
            doc_chart_path=doc_chart_path,
            report_path=report_path,
        ),
        encoding="utf-8",
    )

    return EvalReport(
        artifacts=artifacts,
        latest_standard=latest_standard,
        latest_graph=latest_graph,
        latest_merged=latest_merged,
        latest_graph_vs_latest_standard=graph_deltas,
        latest_merged_vs_latest_standard=merged_standard_deltas,
        latest_merged_vs_latest_graph=merged_graph_deltas,
        best_standard_by_doc=best_deltas,
        report_path=report_path,
        mean_chart_path=mean_chart_path,
        doc_chart_path=doc_chart_path,
    )


def read_eval_artifacts(evals_dir: Path) -> tuple[EvalArtifact, ...]:
    standard_paths = sorted((evals_dir / "runs").glob("*.json"))
    graph_paths = sorted((evals_dir / "claim_graph").glob("*/run.json"))
    merged_paths = sorted((evals_dir / "merged_summary").glob("*/run.json"))
    artifacts = [
        read_standard_artifact(path) for path in standard_paths if path.is_file()
    ]
    artifacts.extend(
        read_graph_artifact(path) for path in graph_paths if path.is_file()
    )
    artifacts.extend(
        read_merged_artifact(path) for path in merged_paths if path.is_file()
    )
    return tuple(
        sorted(artifacts, key=lambda artifact: (artifact.run_id, artifact.kind))
    )


def read_standard_artifact(path: Path) -> EvalArtifact:
    payload = read_json_object(path)
    return EvalArtifact(
        run_id=string_field(payload, "run_id", fallback=path.stem),
        kind="standard",
        path=path,
        mean_blended=float_field(payload, "mean_blended"),
        prompt_versions=dict_field(payload, "prompt_versions"),
        docs=tuple(read_standard_doc(doc) for doc in list_field(payload, "docs")),
    )


def read_graph_artifact(path: Path) -> EvalArtifact:
    payload = read_json_object(path)
    return EvalArtifact(
        run_id=string_field(payload, "run_id", fallback=path.parent.name),
        kind="claim_graph",
        path=path,
        mean_blended=float_field(payload, "mean_blended"),
        prompt_versions=dict_field(payload, "prompt_versions"),
        docs=tuple(read_graph_doc(doc) for doc in list_field(payload, "docs")),
    )


def read_merged_artifact(path: Path) -> EvalArtifact:
    payload = read_json_object(path)
    return EvalArtifact(
        run_id=string_field(payload, "run_id", fallback=path.parent.name),
        kind="merged_summary",
        path=path,
        mean_blended=float_field(payload, "mean_blended"),
        prompt_versions=dict_field(payload, "prompt_versions"),
        docs=tuple(read_graph_doc(doc) for doc in list_field(payload, "docs")),
    )


def read_standard_doc(payload: Any) -> EvalDoc:
    if not isinstance(payload, dict):
        raise ValueError("Standard eval doc entries must be JSON objects.")
    return EvalDoc(
        doc_name=string_field(payload, "doc_name"),
        blended=float_field(payload, "blended"),
        coverage=float_field(payload, "coverage"),
        faithfulness=float_field(payload, "faithfulness"),
        density=float_field(payload, "density"),
        rubric=float_field(payload, "rubric"),
        error=optional_string(payload.get("error")),
    )


def read_graph_doc(payload: Any) -> EvalDoc:
    if not isinstance(payload, dict):
        raise ValueError("Graph eval doc entries must be JSON objects.")
    score = payload.get("score")
    if not isinstance(score, dict):
        raise ValueError("Graph eval doc entries must include a score object.")
    return EvalDoc(
        doc_name=string_field(payload, "doc_name"),
        blended=float_field(score, "blended"),
        coverage=float_field(score, "coverage"),
        faithfulness=float_field(score, "faithfulness"),
        density=float_field(score, "density"),
        rubric=float_field(score, "rubric"),
        error=optional_string(score.get("error")),
    )


def latest_run(artifacts: tuple[EvalArtifact, ...]) -> EvalArtifact | None:
    if not artifacts:
        return None
    return max(artifacts, key=lambda artifact: artifact.path.stat().st_mtime)


def compare_by_doc(
    *,
    candidate: EvalArtifact,
    baseline: EvalArtifact,
) -> tuple[EvalDelta, ...]:
    baseline_docs = clean_docs_by_name(baseline)
    deltas: list[EvalDelta] = []
    for doc in candidate.docs:
        baseline_doc = baseline_docs.get(doc.doc_name)
        if doc.error is None and baseline_doc is not None:
            deltas.append(
                EvalDelta(
                    doc_name=doc.doc_name,
                    candidate_run=candidate.run_id,
                    baseline_run=baseline.run_id,
                    candidate=doc.blended,
                    baseline=baseline_doc.blended,
                )
            )
    return tuple(deltas)


def compare_to_best_standard(
    *,
    candidate: EvalArtifact,
    standards: tuple[EvalArtifact, ...],
) -> tuple[EvalDelta, ...]:
    best_by_doc: dict[str, tuple[EvalArtifact, EvalDoc]] = {}
    for run in standards:
        for doc in run.docs:
            if doc.error is not None:
                continue
            existing = best_by_doc.get(doc.doc_name)
            if existing is None or doc.blended > existing[1].blended:
                best_by_doc[doc.doc_name] = (run, doc)

    deltas: list[EvalDelta] = []
    for doc in candidate.docs:
        best = best_by_doc.get(doc.doc_name)
        if doc.error is None and best is not None:
            best_run, best_doc = best
            deltas.append(
                EvalDelta(
                    doc_name=doc.doc_name,
                    candidate_run=candidate.run_id,
                    baseline_run=best_run.run_id,
                    candidate=doc.blended,
                    baseline=best_doc.blended,
                )
            )
    return tuple(deltas)


def clean_docs_by_name(artifact: EvalArtifact) -> dict[str, EvalDoc]:
    return {doc.doc_name: doc for doc in artifact.docs if doc.error is None}


def render_report(
    *,
    artifacts: tuple[EvalArtifact, ...],
    latest_standard: EvalArtifact | None,
    latest_graph: EvalArtifact | None,
    latest_merged: EvalArtifact | None,
    graph_deltas: tuple[EvalDelta, ...],
    merged_standard_deltas: tuple[EvalDelta, ...],
    merged_graph_deltas: tuple[EvalDelta, ...],
    best_deltas: tuple[EvalDelta, ...],
    mean_chart_path: Path,
    doc_chart_path: Path,
    report_path: Path,
) -> str:
    lines = [
        "# Eval Report",
        "",
        f"![Mean blended by run]({relative_chart(mean_chart_path, report_path)})",
        "",
        f"![Latest per-doc blended]({relative_chart(doc_chart_path, report_path)})",
        "",
        "## Runs",
        "",
        "| Run | Kind | Mean blended | Prompts | Artifact |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for artifact in artifacts:
        lines.append(
            "| "
            f"{artifact.run_id} | "
            f"{artifact.kind} | "
            f"{artifact.mean_blended:.3f} | "
            f"{prompt_summary(artifact.prompt_versions)} | "
            f"`{artifact.path}` |"
        )

    lines.extend(["", "## Is The Graph Eval Better?", ""])
    if latest_graph is None:
        lines.append("No graph-guided eval runs were found.")
    elif latest_standard is None:
        lines.append("No standard eval runs were found for comparison.")
    elif not graph_deltas:
        lines.append(
            "The latest graph-guided run and latest standard run share no clean docs."
        )
    else:
        lines.append(
            f"Latest graph run `{latest_graph.run_id}` vs latest standard run "
            f"`{latest_standard.run_id}`:"
        )
        lines.extend(delta_table(graph_deltas))

    lines.extend(["", "## Is The Merged Eval Better?", ""])
    if latest_merged is None:
        lines.append("No merged-summary eval runs were found.")
    else:
        if latest_standard is not None and merged_standard_deltas:
            lines.append(
                f"Latest merged run `{latest_merged.run_id}` vs latest standard run "
                f"`{latest_standard.run_id}`:"
            )
            lines.extend(delta_table(merged_standard_deltas))
        elif latest_standard is not None:
            lines.append(
                "The latest merged run and latest standard run share no clean docs."
            )
        if latest_graph is not None and merged_graph_deltas:
            lines.extend(
                [
                    "",
                    f"Latest merged run `{latest_merged.run_id}` vs latest graph run "
                    f"`{latest_graph.run_id}`:",
                ]
            )
            lines.extend(delta_table(merged_graph_deltas))

    if best_deltas:
        lines.extend(
            [
                "",
                "Latest candidate against the best historical standard score "
                "for each matching doc:",
            ]
        )
        lines.extend(delta_table(best_deltas))

    lines.append("")
    return "\n".join(lines)


def delta_table(deltas: tuple[EvalDelta, ...]) -> list[str]:
    lines = [
        "",
        "| Document | Candidate | Baseline | Delta | Better? |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for delta in deltas:
        lines.append(
            "| "
            f"{delta.doc_name} | "
            f"{delta.candidate:.3f} | "
            f"{delta.baseline:.3f} | "
            f"{delta.delta:+.3f} | "
            f"{'yes' if delta.delta > 0 else 'no'} |"
        )
    mean_delta = sum(delta.delta for delta in deltas) / len(deltas)
    lines.append(
        f"| **Mean** |  |  | **{mean_delta:+.3f}** | "
        f"**{'yes' if mean_delta > 0 else 'no'}** |"
    )
    return lines


def prompt_summary(prompt_versions: dict[str, str]) -> str:
    return "<br>".join(
        f"`{name}={version}`" for name, version in sorted(prompt_versions.items())
    )


def relative_chart(chart_path: Path, report_path: Path) -> str:
    return chart_path.relative_to(report_path.parent).as_posix()


def write_mean_chart(artifacts: tuple[EvalArtifact, ...], path: Path) -> None:
    recent = artifacts[-18:]
    bars = [
        ChartBar(
            label=f"{artifact.run_id} ({artifact.kind})",
            value=artifact.mean_blended,
            color=color_for_kind(artifact.kind),
        )
        for artifact in recent
    ]
    path.write_text(
        render_bar_chart(bars, title="Mean blended by run"), encoding="utf-8"
    )


def write_latest_doc_chart(
    *,
    standard: EvalArtifact | None,
    graph: EvalArtifact | None,
    merged: EvalArtifact | None,
    path: Path,
) -> None:
    bars: list[ChartBar] = []
    if standard is not None:
        bars.extend(
            ChartBar(
                label=f"{doc.doc_name} standard",
                value=doc.blended,
                color=color_for_kind("standard"),
            )
            for doc in standard.docs
            if doc.error is None
        )
    if graph is not None:
        bars.extend(
            ChartBar(
                label=f"{doc.doc_name} graph",
                value=doc.blended,
                color=color_for_kind("claim_graph"),
            )
            for doc in graph.docs
            if doc.error is None
        )
    if merged is not None:
        bars.extend(
            ChartBar(
                label=f"{doc.doc_name} merged",
                value=doc.blended,
                color=color_for_kind("merged_summary"),
            )
            for doc in merged.docs
            if doc.error is None
        )
    path.write_text(
        render_bar_chart(bars, title="Latest per-doc blended"),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class ChartBar:
    label: str
    value: float
    color: str


def color_for_kind(kind: str) -> str:
    if kind == "standard":
        return "#5271a3"
    if kind == "claim_graph":
        return "#2f8f6f"
    if kind == "merged_summary":
        return "#9a6a2f"
    return "#59636e"


def render_bar_chart(bars: list[ChartBar], *, title: str) -> str:
    width = 960
    row_height = 28
    label_width = 390
    top = 46
    height = max(110, top + len(bars) * row_height + 28)
    chart_width = width - label_width - 90
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="28" font-family="Arial, sans-serif" '
        f'font-size="18" font-weight="700">{escape_xml(title)}</text>',
        f'<line x1="{label_width}" y1="{top - 12}" x2="{label_width + chart_width}" '
        f'y2="{top - 12}" stroke="#d8dee9"/>',
    ]
    for tick in range(6):
        x = label_width + (chart_width * tick / 5)
        value = tick / 5
        lines.append(
            f'<line x1="{x:.1f}" y1="{top - 16}" x2="{x:.1f}" y2="{height - 18}" '
            'stroke="#edf0f4"/>'
        )
        lines.append(
            f'<text x="{x:.1f}" y="{height - 5}" text-anchor="middle" '
            'font-family="Arial, sans-serif" font-size="10" fill="#59636e">'
            f"{value:.1f}</text>"
        )
    if not bars:
        lines.append(
            '<text x="24" y="72" font-family="Arial, sans-serif" font-size="13" '
            'fill="#59636e">No clean eval scores available.</text>'
        )
    for index, bar in enumerate(bars):
        y = top + index * row_height
        bar_width = max(0, min(1, bar.value)) * chart_width
        lines.append(
            f'<text x="24" y="{y + 16}" font-family="Arial, sans-serif" '
            f'font-size="11" fill="#222">{escape_xml(short_label(bar.label))}</text>'
        )
        lines.append(
            f'<rect x="{label_width}" y="{y}" width="{bar_width:.1f}" height="18" '
            f'fill="{bar.color}" rx="3"/>'
        )
        lines.append(
            f'<text x="{label_width + bar_width + 6:.1f}" y="{y + 14}" '
            f'font-family="Arial, sans-serif" font-size="11" fill="#222">'
            f"{bar.value:.3f}</text>"
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def short_label(label: str) -> str:
    if len(label) <= 58:
        return label
    return f"{label[:55]}..."


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Eval artifact must be a JSON object: {path}")
    return payload


def string_field(
    payload: dict[str, Any],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected non-empty string field {key!r}.")
    return value


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected error field to be a string or null.")
    return value


def float_field(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"Expected numeric field {key!r}.")
    return float(value)


def dict_field(payload: dict[str, Any], key: str) -> dict[str, str]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Expected object field {key!r}.")
    return {str(name): str(version) for name, version in value.items()}


def list_field(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Expected list field {key!r}.")
    return value
