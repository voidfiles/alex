from pathlib import Path

from click.testing import CliRunner

from alex.commands.prepare_outline_level_eval import (
    build_prepare_outline_level_eval_command,
)
from alex.lib.outline_level_eval import PreparedOutlineCorpus


def test_prepare_command_uses_default_paths_and_count() -> None:
    # Given
    calls: list[tuple[Path, Path, int]] = []

    def fake_prepare(
        *, asset_root: Path, evals_dir: Path, count: int
    ) -> PreparedOutlineCorpus:
        calls.append((asset_root, evals_dir, count))
        return PreparedOutlineCorpus(evals_dir / "manifest.json", ())

    # When
    result = CliRunner().invoke(
        build_prepare_outline_level_eval_command(fake_prepare),
        [],
    )

    # Then
    assert result.exit_code == 0
    assert calls == [(Path("~/Documents/Alex3/assets").expanduser(), Path("evals"), 25)]


def test_prepare_command_reports_existing_corpus_error(tmp_path: Path) -> None:
    # Given
    def failing_prepare(
        *, asset_root: Path, evals_dir: Path, count: int
    ) -> PreparedOutlineCorpus:
        raise ValueError(f"{evals_dir / 'outline_level'} already exists")

    # When
    result = CliRunner().invoke(
        build_prepare_outline_level_eval_command(failing_prepare),
        ["--evals-dir", str(tmp_path)],
    )

    # Then
    assert result.exit_code != 0
    assert "already exists" in result.output
