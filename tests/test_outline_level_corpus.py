import hashlib
import json
from pathlib import Path

import pytest

from alex.lib.outline_level_eval import (
    OutlineLevelEvalError,
    prepare_outline_level_corpus,
)


def _write_headers(asset_root: Path, name: str, levels: tuple[int, ...]) -> bytes:
    asset_dir = asset_root / name
    asset_dir.mkdir(parents=True)
    content = "\n".join(
        f"Section {index} (H{level}, line {index * 10})"
        for index, level in enumerate(levels, 1)
    ).encode()
    (asset_dir / "headers.md").write_bytes(content)
    return content


def test_prepare_outline_level_corpus_is_deterministic_and_spans_distribution(
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "assets"
    outlines = {
        f"book-{index}": _write_headers(
            asset_root,
            f"book-{index}",
            tuple([1, *([2] * index)]),
        )
        for index in range(1, 7)
    }
    first_evals = tmp_path / "first-evals"
    second_evals = tmp_path / "second-evals"

    first = prepare_outline_level_corpus(
        asset_root=asset_root,
        evals_dir=first_evals,
        count=3,
    )
    second = prepare_outline_level_corpus(
        asset_root=asset_root,
        evals_dir=second_evals,
        count=3,
    )

    assert len(first.case_dirs) == 3
    assert tuple(path.name for path in first.case_dirs) == tuple(
        path.name for path in second.case_dirs
    )
    first_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
    assert first_manifest == second_manifest
    selected_sources = [case["source"] for case in first_manifest["cases"]]
    assert "book-1/headers.md" in selected_sources
    assert "book-6/headers.md" in selected_sources
    for case in first_manifest["cases"]:
        source = case["source"]
        case_dir = first_evals / "outline_level" / "cases" / case["id"]
        source_bytes = outlines[source.split("/", 1)[0]]
        assert (case_dir / "input.md").read_bytes() == source_bytes
        assert case["sha256"] == hashlib.sha256(source_bytes).hexdigest()
        assert (case_dir / "output.md").read_bytes().endswith(source_bytes)


def test_prepare_outline_level_corpus_rejects_existing_corpus(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    _write_headers(asset_root, "book", (1, 2, 2))
    evals_dir = tmp_path / "evals"
    prepare_outline_level_corpus(
        asset_root=asset_root,
        evals_dir=evals_dir,
        count=1,
    )

    with pytest.raises(OutlineLevelEvalError, match="already exists"):
        prepare_outline_level_corpus(
            asset_root=asset_root,
            evals_dir=evals_dir,
            count=1,
        )


def test_prepare_outline_level_corpus_rejects_nonpositive_count(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    evals_dir = tmp_path / "evals"

    with pytest.raises(OutlineLevelEvalError, match="count must be positive") as error:
        prepare_outline_level_corpus(
            asset_root=asset_root,
            evals_dir=evals_dir,
            count=0,
        )
    assert error.value.path == evals_dir / "outline_level"


def test_prepare_outline_level_corpus_uses_full_relative_source_for_case_ids(
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "assets"
    _write_headers(asset_root, "one/book", (1, 2, 2))
    _write_headers(asset_root, "two/book", (1, 2, 2))

    prepared = prepare_outline_level_corpus(
        asset_root=asset_root,
        evals_dir=tmp_path / "evals",
        count=2,
    )

    assert len({case_dir.name for case_dir in prepared.case_dirs}) == 2


def test_prepare_outline_level_corpus_cleans_staging_after_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_root = tmp_path / "assets"
    _write_headers(asset_root, "book", (1, 2, 2))
    evals_dir = tmp_path / "evals"
    original_write_bytes = Path.write_bytes

    def fail_output_write(path: Path, data: bytes) -> int:
        if path.name == "output.md":
            raise OSError("injected output write failure")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_output_write)

    with pytest.raises(OSError, match="injected output write failure"):
        prepare_outline_level_corpus(
            asset_root=asset_root,
            evals_dir=evals_dir,
            count=1,
        )
    assert not (evals_dir / "outline_level").exists()
    assert not tuple(evals_dir.glob(".outline-level-*"))
