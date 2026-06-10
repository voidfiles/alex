from pathlib import Path

from alex.lib.env import SOURCE_DOTENV_PATH, load_source_dotenv


def test_source_dotenv_path_points_to_repository_root() -> None:
    assert SOURCE_DOTENV_PATH == Path(__file__).resolve().parents[1] / ".env"


def test_load_source_dotenv_sets_missing_values_from_dotenv(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "# local CLI configuration",
                "DATALAB_API_KEY=from-dotenv",
                'export QUOTED_VALUE="quoted value"',
                "EMPTY_VALUE=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    environ: dict[str, str] = {}

    load_source_dotenv(dotenv_path=dotenv_path, environ=environ)

    assert environ == {
        "DATALAB_API_KEY": "from-dotenv",
        "QUOTED_VALUE": "quoted value",
        "EMPTY_VALUE": "",
    }


def test_load_source_dotenv_keeps_existing_environment_values(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("DATALAB_API_KEY=from-dotenv\n", encoding="utf-8")
    environ = {"DATALAB_API_KEY": "from-env"}

    load_source_dotenv(dotenv_path=dotenv_path, environ=environ)

    assert environ == {"DATALAB_API_KEY": "from-env"}


def test_load_source_dotenv_ignores_missing_file(tmp_path: Path) -> None:
    environ = {"DATALAB_API_KEY": "from-env"}

    load_source_dotenv(dotenv_path=tmp_path / ".env", environ=environ)

    assert environ == {"DATALAB_API_KEY": "from-env"}
