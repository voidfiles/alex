from pathlib import Path

from click.testing import CliRunner

from alex.commands.dump_env import build_dump_env_command


def test_dump_env_prints_selected_dotenv_file(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_contents = "DATALAB_API_KEY=test-key\nEMPTY_VALUE=\n"
    dotenv_path.write_text(dotenv_contents, encoding="utf-8")

    result = CliRunner().invoke(build_dump_env_command(dotenv_path), [])

    assert result.exit_code == 0
    assert result.output == dotenv_contents


def test_dump_env_fails_when_selected_dotenv_file_is_missing(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"

    result = CliRunner().invoke(build_dump_env_command(dotenv_path), [])

    assert result.exit_code == 1
    assert f"Selected .env file does not exist: {dotenv_path}" in result.output
