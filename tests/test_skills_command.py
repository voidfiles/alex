from collections.abc import Sequence

from click.testing import CliRunner

from alex.commands.skills import build_skills_command


def test_skills_command_forwards_to_npx_skills() -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command: Sequence[str]) -> int:
        commands.append(tuple(command))
        return 0

    result = CliRunner().invoke(
        build_skills_command(fake_run),
        [
            "add",
            "shadcn/improve",
            "--skill",
            "improve",
            "--all",
        ],
    )

    assert result.exit_code == 0
    assert commands == [
        (
            "npx",
            "skills",
            "add",
            "shadcn/improve",
            "--skill",
            "improve",
            "--all",
        )
    ]


def test_skills_command_forwards_help_to_npx_skills() -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command: Sequence[str]) -> int:
        commands.append(tuple(command))
        return 0

    result = CliRunner().invoke(build_skills_command(fake_run), ["--help"])

    assert result.exit_code == 0
    assert commands == [("npx", "skills", "--help")]


def test_skills_command_returns_npx_exit_code() -> None:
    result = CliRunner().invoke(
        build_skills_command(lambda command: 7),
        ["list"],
    )

    assert result.exit_code == 7


def test_skills_command_rejects_copy_installs() -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command: Sequence[str]) -> int:
        commands.append(tuple(command))
        return 0

    result = CliRunner().invoke(
        build_skills_command(fake_run),
        ["add", "shadcn/improve", "--copy"],
    )

    assert result.exit_code == 1
    assert "alex skills installs by symlinking" in result.output
    assert commands == []


def test_skills_command_reports_missing_npx() -> None:
    def missing_npx(command: Sequence[str]) -> int:
        raise FileNotFoundError("npx")

    result = CliRunner().invoke(build_skills_command(missing_npx), ["list"])

    assert result.exit_code == 1
    assert "Could not find npx" in result.output
