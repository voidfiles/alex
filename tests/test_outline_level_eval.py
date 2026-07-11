import hashlib
import json
from pathlib import Path

import pytest

from alex.lib.markdown_structure import infer_chapter_level
from alex.lib.outline_level_eval import (
    OutlineLevelEvalError,
    evaluate_outline_level,
)


def test_infer_chapter_level_returns_h2_for_single_h1_and_repeated_h2() -> None:
    # Given
    headers = "\n".join(
        (
            "Title (H1, line 1)",
            "First chapter (H2, line 10)",
            "Second chapter (H2, line 40)",
        )
    )

    # When
    chapter_level = infer_chapter_level(headers=headers, markdown="")

    # Then
    assert chapter_level == 2


def _write_case(
    evals_dir: Path,
    *,
    case_id: str,
    outline: str,
    annotation: str,
    body: str | None = None,
) -> None:
    case_dir = evals_dir / "outline_level" / "cases" / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "input.md").write_text(outline, encoding="utf-8")
    retained_outline = outline if body is None else body
    (case_dir / "output.md").write_text(
        f"<!-- chapter-level: {annotation} -->\n"
        "Replace TODO with H1-H6. Keep the outline below unchanged.\n\n"
        f"{retained_outline}",
        encoding="utf-8",
    )
    manifest_path = evals_dir / "outline_level" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"version": 1, "cases": []}
    input_bytes = outline.encode()
    manifest["cases"].append(
        {
            "id": case_id,
            "source": f"fixtures/{case_id}/headers.md",
            "sha256": hashlib.sha256(input_bytes).hexdigest(),
            "entry_count": len(outline.splitlines()),
            "size_bytes": len(input_bytes),
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_evaluate_outline_level_scores_annotated_and_pending_cases(
    tmp_path: Path,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    h2_outline = "Title (H1, line 1)\nOne (H2, line 2)\nTwo (H2, line 3)"
    _write_case(
        evals_dir,
        case_id="correct",
        outline=h2_outline,
        annotation="H2",
    )
    _write_case(
        evals_dir,
        case_id="pending",
        outline="One (H1, line 1)\nTwo (H1, line 2)",
        annotation="TODO",
    )

    # When
    result = evaluate_outline_level(evals_dir=evals_dir, run_id="test-run")

    # Then
    assert result.accuracy == 1.0
    assert result.annotated_count == 1
    assert result.pending_count == 1
    assert [
        (case.case_id, case.predicted, case.expected, case.status)
        for case in result.cases
    ] == [
        ("correct", "H2", "H2", "correct"),
        ("pending", "H1", None, "pending"),
    ]
    artifact = json.loads(result.run_path.read_text(encoding="utf-8"))
    assert artifact["accuracy"] == 1.0
    assert artifact["pending_count"] == 1
    assert artifact["cases"][0]["status"] == "correct"


def test_evaluate_outline_level_reports_null_accuracy_when_all_pending(
    tmp_path: Path,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="pending",
        outline="One (H1, line 1)",
        annotation="TODO",
    )

    # When
    result = evaluate_outline_level(evals_dir=evals_dir, run_id="pending-run")

    # Then
    assert result.accuracy is None
    assert result.pending_count == 1


@pytest.mark.parametrize(
    "run_id",
    ("../escape", "/absolute", "nested/run", r"nested\run", ".", "..", "a" * 65),
)
def test_evaluate_outline_level_rejects_unsafe_run_id(
    tmp_path: Path,
    run_id: str,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="pending",
        outline="One (H1, line 1)",
        annotation="TODO",
    )

    # When / Then
    with pytest.raises(OutlineLevelEvalError, match="unsafe run ID"):
        evaluate_outline_level(evals_dir=evals_dir, run_id=run_id)


def test_evaluate_outline_level_rejects_input_and_output_changed_together(
    tmp_path: Path,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="changed",
        outline="One (H1, line 1)",
        annotation="H1",
    )
    case_dir = evals_dir / "outline_level" / "cases" / "changed"
    changed = "Changed (H2, line 1)"
    (case_dir / "input.md").write_text(changed, encoding="utf-8")
    (case_dir / "output.md").write_text(
        "<!-- chapter-level: H2 -->\n"
        "Replace TODO with H1-H6. Keep the outline below unchanged.\n\n"
        f"{changed}",
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(OutlineLevelEvalError, match="SHA-256 mismatch"):
        evaluate_outline_level(evals_dir=evals_dir, run_id="changed-run")


def test_evaluate_outline_level_rejects_added_case_directory(tmp_path: Path) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="manifest-case",
        outline="One (H1, line 1)",
        annotation="H1",
    )
    extra = evals_dir / "outline_level" / "cases" / "extra"
    extra.mkdir()

    # When / Then
    with pytest.raises(OutlineLevelEvalError, match="case directory set"):
        evaluate_outline_level(evals_dir=evals_dir, run_id="added-run")


def test_evaluate_outline_level_rejects_removed_case_directory(tmp_path: Path) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="missing",
        outline="One (H1, line 1)",
        annotation="H1",
    )
    case_dir = evals_dir / "outline_level" / "cases" / "missing"
    (case_dir / "input.md").unlink()
    (case_dir / "output.md").unlink()
    case_dir.rmdir()

    # When / Then
    with pytest.raises(OutlineLevelEvalError, match="case directory set"):
        evaluate_outline_level(evals_dir=evals_dir, run_id="removed-run")


def test_evaluate_outline_level_rejects_malformed_manifest(tmp_path: Path) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="case",
        outline="One (H1, line 1)",
        annotation="H1",
    )
    manifest_path = evals_dir / "outline_level" / "manifest.json"
    manifest_path.write_text('{"version": 2, "cases": []}', encoding="utf-8")

    # When / Then
    with pytest.raises(OutlineLevelEvalError, match="manifest version 1"):
        evaluate_outline_level(evals_dir=evals_dir, run_id="malformed-run")


def test_evaluate_outline_level_records_manifest_sha256(tmp_path: Path) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="case",
        outline="One (H1, line 1)",
        annotation="H1",
    )
    manifest_path = evals_dir / "outline_level" / "manifest.json"
    expected_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    # When
    result = evaluate_outline_level(evals_dir=evals_dir, run_id="digest-run")

    # Then
    assert result.corpus_sha256 == expected_digest
    artifact = json.loads(result.run_path.read_text(encoding="utf-8"))
    assert artifact["corpus_sha256"] == expected_digest


@pytest.mark.parametrize(
    ("annotation", "body", "message"),
    [
        ("H7", None, "first line"),
        ("H2", "Changed (H2, line 1)", "does not retain exact input"),
    ],
)
def test_evaluate_outline_level_rejects_malformed_output(
    tmp_path: Path,
    annotation: str,
    body: str | None,
    message: str,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="broken",
        outline="One (H2, line 1)",
        annotation=annotation,
        body=body,
    )

    # When / Then
    with pytest.raises(OutlineLevelEvalError, match=message) as error:
        evaluate_outline_level(evals_dir=evals_dir, run_id="broken-run")
    assert "broken/output.md" in str(error.value)
