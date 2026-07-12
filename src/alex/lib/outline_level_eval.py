from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from alex.lib.markdown_structure import infer_chapter_level
from alex.lib.outline_level_annotation import (
    CHAPTER_LABELS,
    ChapterLabel,
    OutlineLevelEvalError,
    parse_outline_level_output,
)
from alex.lib.outline_level_corpus import (
    PreparedOutlineCorpus,
    load_trusted_outline_corpus,
    prepare_outline_level_corpus,
)

__all__ = [
    "CHAPTER_LABELS",
    "CaseStatus",
    "ChapterLabel",
    "OutlineLevelCaseResult",
    "OutlineLevelEvalError",
    "OutlineLevelRunResult",
    "PreparedOutlineCorpus",
    "evaluate_outline_level",
    "prepare_outline_level_corpus",
    "validate_outline_level_run_id",
]

type CaseStatus = Literal["correct", "incorrect", "pending"]


@dataclass(frozen=True, slots=True)
class OutlineLevelCaseResult:
    case_id: str
    predicted: ChapterLabel
    expected: ChapterLabel | None
    status: CaseStatus


@dataclass(frozen=True, slots=True)
class OutlineLevelRunResult:
    run_id: str
    run_path: Path
    cases: tuple[OutlineLevelCaseResult, ...]
    accuracy: float | None
    annotated_count: int
    pending_count: int
    corpus_sha256: str = ""


def evaluate_outline_level(
    *,
    evals_dir: Path,
    run_id: str,
) -> OutlineLevelRunResult:
    validate_outline_level_run_id(evals_dir=evals_dir, run_id=run_id)
    corpus = load_trusted_outline_corpus(evals_dir)

    results = tuple(
        _evaluate_case(corpus.cases_root / manifest_case.id)
        for manifest_case in corpus.cases
    )
    annotated = tuple(case for case in results if case.expected is not None)
    correct_count = sum(case.status == "correct" for case in annotated)
    accuracy = correct_count / len(annotated) if annotated else None
    pending_count = sum(case.status == "pending" for case in results)
    runs_root = evals_dir / "outline_level" / "runs"
    if runs_root.is_symlink():
        raise OutlineLevelEvalError(runs_root, "runs directory cannot be a symlink")
    run_dir = runs_root / run_id
    if run_dir.exists():
        raise OutlineLevelEvalError(run_dir, "run already exists")
    run_dir.mkdir(parents=True)
    run_path = run_dir / "run.json"
    artifact = {
        "run_id": run_id,
        "accuracy": accuracy,
        "annotated_count": len(annotated),
        "pending_count": pending_count,
        "corpus_sha256": corpus.sha256,
        "cases": [asdict(case) for case in results],
    }
    run_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return OutlineLevelRunResult(
        run_id=run_id,
        run_path=run_path,
        cases=results,
        accuracy=accuracy,
        annotated_count=len(annotated),
        pending_count=pending_count,
        corpus_sha256=corpus.sha256,
    )


def validate_outline_level_run_id(*, evals_dir: Path, run_id: str) -> None:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", run_id) is None:
        path = evals_dir / "outline_level" / "runs" / run_id
        raise OutlineLevelEvalError(path, "unsafe run ID")


def _evaluate_case(case_dir: Path) -> OutlineLevelCaseResult:
    input_path = case_dir / "input.md"
    output_path = case_dir / "output.md"
    input_bytes = input_path.read_bytes()
    if output_path.is_symlink():
        raise OutlineLevelEvalError(output_path, "output cannot be a symlink")
    output_bytes = output_path.read_bytes()
    annotation = parse_outline_level_output(
        output_path=output_path,
        output_bytes=output_bytes,
        input_bytes=input_bytes,
    )
    raw_expected = annotation.chapter.level
    expected: ChapterLabel | None = None
    if raw_expected != "TODO":
        expected = raw_expected
    predicted = _chapter_label(
        infer_chapter_level(headers=input_bytes.decode("utf-8"), markdown="")
    )
    if expected is None:
        status: CaseStatus = "pending"
    elif predicted == expected:
        status = "correct"
    else:
        status = "incorrect"
    return OutlineLevelCaseResult(case_dir.name, predicted, expected, status)


def _chapter_label(level: int) -> ChapterLabel:
    if not 1 <= level <= len(CHAPTER_LABELS):
        raise OutlineLevelEvalError(Path("<prediction>"), f"invalid H{level}")
    return CHAPTER_LABELS[level - 1]
