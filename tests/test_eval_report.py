import json
import os
from pathlib import Path

import pytest

from alex.lib.eval_report import read_eval_artifacts, write_eval_report


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def standard_run(run_id: str, doc_name: str, blended: float) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_versions": {"chunk_summary": "v001"},
        "mean_blended": blended,
        "docs": [
            {
                "doc_name": doc_name,
                "coverage": 0.8,
                "faithfulness": 0.9,
                "density": 1.0,
                "rubric": 0.75,
                "blended": blended,
                "error": None,
            }
        ],
    }


def graph_run(run_id: str, doc_name: str, blended: float) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_versions": {"graph_guided_summary": "v001"},
        "mean_blended": blended,
        "docs": [
            {
                "doc_name": doc_name,
                "score": {
                    "coverage": 0.85,
                    "faithfulness": 0.95,
                    "density": 1.0,
                    "rubric": 0.75,
                    "blended": blended,
                    "error": None,
                },
            }
        ],
    }


def merged_run(run_id: str, doc_name: str, blended: float) -> dict[str, object]:
    payload = graph_run(run_id, doc_name, blended)
    payload["prompt_versions"] = {"merged_summary": "v001"}
    payload["repair"] = False
    return payload


def test_read_eval_artifacts_handles_standard_and_graph_schemas(
    tmp_path: Path,
) -> None:
    evals_dir = tmp_path / "evals"
    write_json(
        evals_dir / "runs" / "20260101.json", standard_run("20260101", "a.md", 0.7)
    )
    write_json(
        evals_dir / "claim_graph" / "20260102" / "run.json",
        graph_run("20260102", "a.md", 0.8),
    )

    artifacts = read_eval_artifacts(evals_dir)

    assert [artifact.kind for artifact in artifacts] == ["standard", "claim_graph"]
    assert artifacts[0].docs[0].blended == pytest.approx(0.7)
    assert artifacts[1].docs[0].blended == pytest.approx(0.8)


def test_write_eval_report_compares_latest_graph_to_standard(
    tmp_path: Path,
) -> None:
    evals_dir = tmp_path / "evals"
    old_standard = evals_dir / "runs" / "20260101.json"
    new_standard = evals_dir / "runs" / "20260103.json"
    write_json(old_standard, standard_run("20260101", "a.md", 0.9))
    write_json(new_standard, standard_run("20260103", "a.md", 0.7))
    os.utime(old_standard, (1, 1))
    os.utime(new_standard, (2, 2))
    old_graph = evals_dir / "claim_graph" / "zz-old" / "run.json"
    new_graph = evals_dir / "claim_graph" / "aa-new" / "run.json"
    latest_merged = evals_dir / "merged_summary" / "merged-new" / "run.json"
    write_json(old_graph, graph_run("zz-old", "a.md", 0.6))
    write_json(new_graph, graph_run("aa-new", "a.md", 0.8))
    write_json(latest_merged, merged_run("merged-new", "a.md", 0.85))
    os.utime(old_graph, (3, 3))
    os.utime(new_graph, (4, 4))
    os.utime(latest_merged, (5, 5))

    report = write_eval_report(evals_dir=evals_dir)

    assert report.report_path.is_file()
    assert report.mean_chart_path.is_file()
    assert report.doc_chart_path.is_file()
    assert report.latest_graph_vs_latest_standard[0].candidate_run == "aa-new"
    assert report.latest_graph_vs_latest_standard[0].delta == pytest.approx(0.1)
    assert report.latest_merged_vs_latest_standard[0].candidate_run == "merged-new"
    assert report.latest_merged_vs_latest_standard[0].delta == pytest.approx(0.15)
    assert report.latest_merged_vs_latest_graph[0].delta == pytest.approx(0.05)
    assert report.best_standard_by_doc[0].delta == pytest.approx(-0.05)

    markdown = report.report_path.read_text(encoding="utf-8")
    assert "Latest graph run `aa-new` vs latest standard run `20260103`" in markdown
    assert (
        "Latest merged run `merged-new` vs latest standard run `20260103`" in markdown
    )
    assert "Latest merged run `merged-new` vs latest graph run `aa-new`" in markdown
    assert "| a.md | 0.800 | 0.700 | +0.100 | yes |" in markdown
    assert "| a.md | 0.850 | 0.800 | +0.050 | yes |" in markdown
    assert "| a.md | 0.850 | 0.900 | -0.050 | no |" in markdown
    assert "<svg" in report.mean_chart_path.read_text(encoding="utf-8")
