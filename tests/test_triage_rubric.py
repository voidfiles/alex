from pathlib import Path

from alex.lib.triage.models import Rubric
from alex.lib.triage.rubric import DEFAULT_RUBRIC_TEXT, load_rubric, save_rubric


def test_load_rubric_seeds_and_writes_default_when_file_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projects" / "vault-triage" / "rubric.md"

    rubric = load_rubric(path)

    assert rubric == Rubric(version=1, text=DEFAULT_RUBRIC_TEXT)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\nversion: 1\n---\n")
    assert "## Triage rules" in content
    assert "## Atomic note rules" in content
    assert load_rubric(path) == rubric


def test_load_rubric_parses_version_from_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "rubric.md"
    body = "## Triage rules\n\n1. Hand-edited rule.\n"
    path.write_text(f"---\nversion: 7\n---\n{body}", encoding="utf-8")

    rubric = load_rubric(path)

    assert rubric.version == 7
    assert rubric.text == body


def test_load_rubric_defaults_version_when_frontmatter_is_absent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rubric.md"
    path.write_text("## Triage rules\n\n1. No frontmatter here.\n", encoding="utf-8")

    rubric = load_rubric(path)

    assert rubric.version == 1
    assert rubric.text == "## Triage rules\n\n1. No frontmatter here.\n"


def test_save_rubric_writes_atomically_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "rubric.md"
    rubric = Rubric(version=3, text="## Triage rules\n\n1. Updated.\n")

    save_rubric(path, rubric)

    assert path.read_text(encoding="utf-8") == (
        "---\nversion: 3\n---\n## Triage rules\n\n1. Updated.\n"
    )
    assert not list(tmp_path.glob("*.tmp"))
    assert load_rubric(path) == rubric
