import subprocess
import sys
import textwrap

import pytest
from click.testing import CliRunner

from alex.commands.main import main


def test_cli_help_lists_available_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "Alex command line tools." in result.output
    assert "dump-env" in result.output
    assert "process-doc" in result.output
    assert "summary" in result.output
    assert "to-asset" in result.output
    assert "to-markdown" not in result.output
    assert "version" in result.output


def test_version_command_prints_package_version() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["version"])

    assert result.exit_code == 0
    assert result.output == "alex 0.1.0\n"


def test_cli_help_does_not_import_pdf_converter_dependencies() -> None:
    code = textwrap.dedent(
        """
        import builtins

        original_import = builtins.__import__

        def rejecting_import(name, *args, **kwargs):
            blocked_prefixes = ("pymupdf4llm", "marker")
            if name.startswith(blocked_prefixes):
                raise RuntimeError(f"{name} should not be imported for help")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = rejecting_import

        from click.testing import CliRunner
        from alex.commands.main import main

        result = CliRunner().invoke(main, ["--help"])
        if result.exit_code != 0:
            raise SystemExit(result.output)

        print(result.output)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "process-doc" in result.stdout
    assert "summary" in result.stdout
    assert "to-asset" in result.stdout
    assert "to-markdown" not in result.stdout


def test_running_a_command_loads_the_source_dotenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "alex.commands.main.load_source_dotenv",
        lambda: calls.append("loaded"),
    )

    result = CliRunner().invoke(main, ["version"])

    assert result.exit_code == 0
    assert calls == ["loaded"]
