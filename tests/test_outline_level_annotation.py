import hashlib
import json
from pathlib import Path

import pytest

from alex.lib.outline_level_eval import (
    OutlineLevelEvalError,
    evaluate_outline_level,
)


def _write_case(
    evals_dir: Path,
    *,
    case_id: str,
    outline: str,
    annotation: str,
) -> None:
    case_dir = evals_dir / "outline_level" / "cases" / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "input.md").write_text(outline, encoding="utf-8")
    (case_dir / "output.md").write_text(
        "---\n"
        "document:\n"
        '  title: "Title"\n'
        "  level: TODO\n"
        "  line: TODO\n\n"
        "section:\n"
        "  level: TODO\n"
        "  first_heading: TODO\n"
        "  line: TODO\n\n"
        "chapter:\n"
        f"  level: {annotation}\n"
        "  first_heading: TODO\n"
        "  line: TODO\n\n"
        "subchapter:\n"
        "  level: TODO\n"
        "  first_heading: TODO\n"
        "  line: TODO\n"
        "---\n"
        f"{outline}",
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


def test_evaluate_outline_level_scores_complete_nested_h2_annotation(
    tmp_path: Path,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    outline = "Book (H1, line 1)\nPart I (H2, line 5)\nOne (H2, line 10)"
    _write_case(
        evals_dir,
        case_id="complete",
        outline=outline,
        annotation="H2",
    )
    output_path = evals_dir / "outline_level" / "cases" / "complete" / "output.md"
    output_path.write_text(
        "---\n"
        "document:\n"
        '  title: "Book"\n'
        "  level: H1\n"
        "  line: 1\n\n"
        "section:\n"
        "  level: H1\n"
        '  first_heading: "Part I"\n'
        "  line: 5\n\n"
        "chapter:\n"
        "  level: H2\n"
        '  first_heading: "One"\n'
        "  line: 10\n\n"
        "subchapter:\n"
        "  level: H3\n"
        '  first_heading: "Detail"\n'
        "  line: 11\n"
        "---\n"
        f"{outline}",
        encoding="utf-8",
    )

    # When
    result = evaluate_outline_level(evals_dir=evals_dir, run_id="complete-run")

    # Then
    assert result.cases[0].expected == "H2"
    assert result.cases[0].status == "correct"


def test_evaluate_outline_level_accepts_json_quoted_colon_and_backslash_title(
    tmp_path: Path,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    outline = "Title (H1, line 1)\nOne (H2, line 2)"
    _write_case(
        evals_dir,
        case_id="quoted",
        outline=outline,
        annotation="H2",
    )
    output_path = evals_dir / "outline_level" / "cases" / "quoted" / "output.md"
    output_path.write_text(
        output_path.read_text(encoding="utf-8").replace(
            '  title: "Title"', '  title: "A: C:\\\\docs"'
        ),
        encoding="utf-8",
    )

    # When
    result = evaluate_outline_level(evals_dir=evals_dir, run_id="quoted-run")

    # Then
    assert result.annotated_count == 1


def test_evaluate_outline_level_rejects_noncanonical_map_order(
    tmp_path: Path,
) -> None:
    # Given
    evals_dir = tmp_path / "evals"
    _write_case(
        evals_dir,
        case_id="shape",
        outline="One (H1, line 1)",
        annotation="H1",
    )
    output_path = evals_dir / "outline_level" / "cases" / "shape" / "output.md"
    output_path.write_text(
        output_path.read_text(encoding="utf-8").replace("document:\n", "chapter:\n", 1),
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(OutlineLevelEvalError, match="expected document"):
        evaluate_outline_level(evals_dir=evals_dir, run_id="shape-run")
