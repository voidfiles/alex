from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from alex.lib.markdown_structure import parse_toc_header_levels
from alex.lib.outline_level_annotation import (
    OutlineLevelEvalError,
    render_pending_outline_level_output,
)


@dataclass(frozen=True, slots=True)
class PreparedOutlineCorpus:
    manifest_path: Path
    case_dirs: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class OutlineCandidate:
    relative_source: str
    content: bytes
    entry_count: int


class ManifestCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    source: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def require_relative_source(self) -> ManifestCase:
        source = PurePosixPath(self.source)
        if source.is_absolute() or ".." in source.parts or self.source.endswith("/"):
            raise ValueError("source must be a relative POSIX path")
        return self


class OutlineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal[1]
    cases: tuple[ManifestCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_cases(self) -> OutlineManifest:
        ids = tuple(case.id for case in self.cases)
        if len(set(ids)) != len(ids):
            raise ValueError("case IDs must be unique")
        return self


@dataclass(frozen=True, slots=True)
class TrustedOutlineCorpus:
    cases_root: Path
    cases: tuple[ManifestCase, ...]
    sha256: str


def prepare_outline_level_corpus(
    *,
    asset_root: Path,
    evals_dir: Path,
    count: int,
) -> PreparedOutlineCorpus:
    corpus_root = evals_dir / "outline_level"
    if count <= 0:
        raise OutlineLevelEvalError(corpus_root, "count must be positive")
    if corpus_root.exists():
        raise OutlineLevelEvalError(corpus_root, "eval corpus already exists")

    candidates = _load_candidates(asset_root)
    if len(candidates) < count:
        raise OutlineLevelEvalError(
            asset_root,
            f"found {len(candidates)} nonempty headers.md files; need {count}",
        )
    selected = _sample_distribution(candidates, count)
    identified = tuple(
        (
            candidate,
            _stable_case_id(
                candidate.relative_source,
                hashlib.sha256(candidate.content).hexdigest(),
            ),
        )
        for candidate in selected
    )
    ids = tuple(case_id for _, case_id in identified)
    if len(set(ids)) != len(ids):
        raise OutlineLevelEvalError(corpus_root, "generated duplicate case IDs")

    evals_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".outline-level-", dir=evals_dir
    ) as stage_name:
        stage_root = Path(stage_name)
        _write_corpus(stage_root, identified)
        stage_root.rename(corpus_root)

    case_dirs = tuple(corpus_root / "cases" / case_id for case_id in ids)
    return PreparedOutlineCorpus(corpus_root / "manifest.json", case_dirs)


def load_trusted_outline_corpus(evals_dir: Path) -> TrustedOutlineCorpus:
    corpus_root = evals_dir / "outline_level"
    manifest_path = corpus_root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = OutlineManifest.model_validate_json(manifest_bytes)
    except ValidationError as error:
        message = "manifest version 1 with valid, unique cases is required"
        raise OutlineLevelEvalError(manifest_path, message) from error

    cases_root = corpus_root / "cases"
    actual_ids = {
        path.name
        for path in cases_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    }
    expected_ids = {case.id for case in manifest.cases}
    if actual_ids != expected_ids:
        raise OutlineLevelEvalError(
            cases_root, "case directory set differs from manifest"
        )

    for case in manifest.cases:
        case_dir = cases_root / case.id
        if case_dir.is_symlink():
            raise OutlineLevelEvalError(case_dir, "case directory cannot be a symlink")
        input_path = case_dir / "input.md"
        if input_path.is_symlink():
            raise OutlineLevelEvalError(input_path, "input cannot be a symlink")
        input_bytes = input_path.read_bytes()
        if hashlib.sha256(input_bytes).hexdigest() != case.sha256:
            raise OutlineLevelEvalError(input_path, "SHA-256 mismatch with manifest")
        if len(input_bytes) != case.size_bytes:
            raise OutlineLevelEvalError(input_path, "size differs from manifest")

    return TrustedOutlineCorpus(
        cases_root=cases_root,
        cases=manifest.cases,
        sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def _write_corpus(
    stage_root: Path,
    identified: tuple[tuple[OutlineCandidate, str], ...],
) -> None:
    cases_root = stage_root / "cases"
    cases_root.mkdir()
    manifest_cases: list[dict[str, str | int]] = []
    for candidate, case_id in identified:
        digest = hashlib.sha256(candidate.content).hexdigest()
        case_dir = cases_root / case_id
        case_dir.mkdir()
        (case_dir / "input.md").write_bytes(candidate.content)
        (case_dir / "output.md").write_bytes(
            render_pending_outline_level_output(candidate.content)
        )
        manifest_cases.append(
            {
                "id": case_id,
                "source": candidate.relative_source,
                "sha256": digest,
                "entry_count": candidate.entry_count,
                "size_bytes": len(candidate.content),
            }
        )
    (stage_root / "manifest.json").write_text(
        json.dumps({"version": 1, "cases": manifest_cases}, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_candidates(asset_root: Path) -> tuple[OutlineCandidate, ...]:
    candidates: list[OutlineCandidate] = []
    for source in asset_root.rglob("headers.md"):
        content = source.read_bytes()
        if not content.strip():
            continue
        levels = parse_toc_header_levels(content.decode("utf-8"))
        if not levels:
            continue
        candidates.append(
            OutlineCandidate(
                relative_source=source.relative_to(asset_root).as_posix(),
                content=content,
                entry_count=len(levels),
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.entry_count,
                len(item.content),
                item.relative_source,
            ),
        )
    )


def _sample_distribution(
    candidates: tuple[OutlineCandidate, ...], count: int
) -> tuple[OutlineCandidate, ...]:
    if count == 1:
        return (candidates[len(candidates) // 2],)
    last_index = len(candidates) - 1
    return tuple(
        candidates[(sample_index * last_index) // (count - 1)]
        for sample_index in range(count)
    )


def _stable_case_id(relative_source: str, digest: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", relative_source.lower()).strip("-")
    slug = (slug or "outline")[:48].rstrip("-")
    source_digest = hashlib.sha256(relative_source.encode()).hexdigest()[:12]
    return f"{slug}-{source_digest}-{digest[:12]}"
