import json
from pathlib import Path

from click.testing import CliRunner

from alex.commands.eval_merged_summary import build_eval_merged_summary_command


class MergedEvalCompleter:
    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if "<section_content>" in prompt:
            return "Standard chunk summary."
        if "<section_summaries>" in prompt:
            return "Standard summary covers broad facts."
        if "source-grounded claims" in prompt:
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": "Graph summaries preserve provenance.",
                            "evidence": "Graph summaries cite claim nodes.",
                        }
                    ]
                }
            )
        if "graph-guided abstractive summary" in prompt:
            return "Graph summary preserves provenance."
        if "merging two independently generated summaries" in prompt:
            assert "Standard summary covers broad facts." in prompt
            assert "Graph summary preserves provenance." in prompt
            return "Merged summary covers broad facts and preserves provenance."
        if "revising a merged summary" in prompt:
            assert "Merged summary covers broad facts" in prompt
            return "Repaired merged summary covers broad facts and provenance."
        if "filtering a merged summary for source faithfulness" in prompt:
            assert "Merged summary preserves provenance." in prompt
            assert "Unsupported merged claim." in prompt
            return "Filtered merged summary preserves provenance."
        if "expert analyst building one section of the answer key" in prompt:
            return json.dumps(
                {"facts": ["Merged summary covers broad facts and provenance."]}
            )
        if "grading whether a summary covers" in prompt:
            return json.dumps({"verdicts": [{"covered": True, "evidence": "covered"}]})
        if "extracting factual claims from a summary" in prompt:
            return json.dumps(
                {
                    "claims": [
                        "Merged summary preserves provenance.",
                        "Unsupported merged claim.",
                    ]
                }
            )
        if "verifying summary claims against the source document" in prompt:
            return json.dumps(
                {
                    "verdicts": [
                        {"supported": True, "evidence": "supported"},
                        {"supported": False, "evidence": "unsupported"},
                    ]
                }
            )
        if "judging the writing quality" in prompt:
            return json.dumps(
                {
                    "coherence": 5,
                    "organization": 4,
                    "readability": 4,
                    "notes": "Clear.",
                }
            )
        raise AssertionError(f"Unexpected prompt: {prompt[:160]!r}")


class FailingMergedEvalCompleter(MergedEvalCompleter):
    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if "Broken" in prompt:
            raise RuntimeError("merge failed")
        return super().complete(prompt=prompt, model=model, max_tokens=max_tokens)


def write_doc(path: Path, title: str = "Graphs") -> None:
    path.write_text(
        f"# {title}\n\nGraph summaries preserve provenance.\n",
        encoding="utf-8",
    )


def test_eval_merged_summary_writes_artifacts_and_scores(tmp_path: Path) -> None:
    evals_dir = tmp_path / "evals"
    corpus_dir = evals_dir / "corpus"
    corpus_dir.mkdir(parents=True)
    write_doc(corpus_dir / "graph.md")

    result = CliRunner().invoke(
        build_eval_merged_summary_command(lambda: MergedEvalCompleter()),
        [
            "--evals-dir",
            str(evals_dir),
            "--docs",
            "graph.md",
            "--max-claims",
            "3",
            "--run-id",
            "merged",
            "--repair",
            "--faithfulness-filter",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "graph.md: blended=" in result.output
    assert f"Run artifact: {evals_dir / 'merged_summary' / 'merged' / 'run.json'}" in (
        result.output
    )

    artifact_dir = evals_dir / "merged_summary" / "merged" / "graph"
    assert (artifact_dir / "standard_summary.md").is_file()
    assert (artifact_dir / "graph_summary.md").is_file()
    assert (artifact_dir / "merged_summary.md").is_file()
    assert (artifact_dir / "repaired_summary.md").is_file()
    assert (artifact_dir / "faithfulness_filtered_summary.md").is_file()
    assert (artifact_dir / "graph.json").is_file()
    assert (artifact_dir / "selected_subgraph.json").is_file()
    assert (artifact_dir / "selected_subgraph.md").is_file()

    run = json.loads(
        (evals_dir / "merged_summary" / "merged" / "run.json").read_text(
            encoding="utf-8"
        )
    )
    assert run["run_id"] == "merged"
    assert run["max_claims"] == 3
    assert run["repair"] is True
    assert run["faithfulness_filter"] is True
    assert run["docs"][0]["doc_name"] == "graph.md"
    assert run["docs"][0]["repaired_summary"].startswith("Repaired merged")
    assert run["docs"][0]["faithfulness_filtered_summary"].startswith("Filtered")
    assert len(run["docs"][0]["pre_filter_claim_verdicts"]) == 2
    assert run["docs"][0]["summary"].startswith("Filtered")


def test_eval_merged_summary_records_failed_docs_and_continues(
    tmp_path: Path,
) -> None:
    evals_dir = tmp_path / "evals"
    corpus_dir = evals_dir / "corpus"
    corpus_dir.mkdir(parents=True)
    write_doc(corpus_dir / "broken.md", title="Broken")
    write_doc(corpus_dir / "graph.md")

    result = CliRunner().invoke(
        build_eval_merged_summary_command(lambda: FailingMergedEvalCompleter()),
        ["--evals-dir", str(evals_dir), "--run-id", "partial"],
    )

    assert result.exit_code == 0, result.output
    assert "broken.md: FAILED (merge failed)" in result.output
    assert "graph.md: blended=" in result.output

    run = json.loads(
        (evals_dir / "merged_summary" / "partial" / "run.json").read_text(
            encoding="utf-8"
        )
    )
    by_name = {doc["doc_name"]: doc for doc in run["docs"]}
    assert by_name["broken.md"]["score"]["error"] == "merge failed"
    assert by_name["graph.md"]["score"]["error"] is None
