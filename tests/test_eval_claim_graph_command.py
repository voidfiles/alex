import json
from pathlib import Path

from click.testing import CliRunner

from alex.commands.eval_claim_graph import build_eval_claim_graph_command


class GraphEvalCompleter:
    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
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
            return (
                "Graph summaries preserve provenance "
                "(claim:graph-summaries-preserve-provenance:1)."
            )
        if "expert analyst building one section of the answer key" in prompt:
            return json.dumps({"facts": ["Graph summaries preserve provenance."]})
        if "grading whether a summary covers" in prompt:
            return json.dumps(
                {"verdicts": [{"covered": True, "evidence": "summary says provenance"}]}
            )
        if "extracting factual claims from a summary" in prompt:
            return json.dumps({"claims": ["Graph summaries preserve provenance."]})
        if "verifying summary claims against the source document" in prompt:
            return json.dumps(
                {
                    "verdicts": [
                        {"supported": True, "evidence": "document says provenance"}
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


class FailingGraphEvalCompleter(GraphEvalCompleter):
    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if "Broken" in prompt:
            raise RuntimeError("model timed out")
        return super().complete(prompt=prompt, model=model, max_tokens=max_tokens)


def test_eval_claim_graph_writes_artifacts_and_reports_scores(tmp_path: Path) -> None:
    evals_dir = tmp_path / "evals"
    corpus_dir = evals_dir / "corpus"
    corpus_dir.mkdir(parents=True)
    (corpus_dir / "graph.md").write_text(
        "# Graphs\n\nGraph summaries preserve provenance.\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        build_eval_claim_graph_command(lambda: GraphEvalCompleter()),
        [
            "--evals-dir",
            str(evals_dir),
            "--docs",
            "graph.md",
            "--judge-model",
            "judge/x",
            "--fact-extractor-model",
            "extractor/y",
            "--max-claims",
            "3",
            "--run-id",
            "testrun",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "graph.md: blended=" in result.output
    assert "Graph:" in result.output
    assert f"Run artifact: {evals_dir / 'claim_graph' / 'testrun' / 'run.json'}" in (
        result.output
    )

    artifact_dir = evals_dir / "claim_graph" / "testrun" / "graph"
    assert (artifact_dir / "graph.json").is_file()
    assert (artifact_dir / "selected_subgraph.json").is_file()
    assert (artifact_dir / "selected_subgraph.md").is_file()
    assert (artifact_dir / "graph_summary.md").is_file()

    run = json.loads(
        (evals_dir / "claim_graph" / "testrun" / "run.json").read_text(encoding="utf-8")
    )
    assert run["run_id"] == "testrun"
    assert run["judge_model"] == "judge/x"
    assert run["fact_extractor_model"] == "extractor/y"
    assert run["max_claims"] == 3
    assert run["docs"][0]["doc_name"] == "graph.md"


def test_eval_claim_graph_records_failed_docs_and_continues(tmp_path: Path) -> None:
    evals_dir = tmp_path / "evals"
    corpus_dir = evals_dir / "corpus"
    corpus_dir.mkdir(parents=True)
    (corpus_dir / "broken.md").write_text(
        "# Broken\n\nBroken graph extraction.\n",
        encoding="utf-8",
    )
    (corpus_dir / "graph.md").write_text(
        "# Graphs\n\nGraph summaries preserve provenance.\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        build_eval_claim_graph_command(lambda: FailingGraphEvalCompleter()),
        [
            "--evals-dir",
            str(evals_dir),
            "--run-id",
            "partial",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "broken.md: FAILED (model timed out)" in result.output
    assert "graph.md: blended=" in result.output

    run = json.loads(
        (evals_dir / "claim_graph" / "partial" / "run.json").read_text(encoding="utf-8")
    )
    by_name = {doc["doc_name"]: doc for doc in run["docs"]}
    assert by_name["broken.md"]["score"]["error"] == "model timed out"
    assert by_name["graph.md"]["score"]["error"] is None
