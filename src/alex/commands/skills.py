from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

import click

RunCommand = Callable[[Sequence[str]], int]


def run_command(command: Sequence[str]) -> int:
    completed = subprocess.run(command, check=False)
    return completed.returncode


def build_skills_command(run: RunCommand = run_command) -> click.Command:
    @click.command(
        "skills",
        add_help_option=False,
        context_settings={
            "allow_extra_args": True,
            "ignore_unknown_options": True,
        },
    )
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    @click.pass_context
    def command(ctx: click.Context, args: tuple[str, ...]) -> None:
        """Manage agent skills with npx skills."""
        if _copy_install_requested(args):
            raise click.ClickException(
                "alex skills installs by symlinking. Remove --copy, or run "
                "npx skills directly if you intentionally need copied files."
            )

        try:
            exit_code = run(("npx", "skills", *args))
        except FileNotFoundError as error:
            raise click.ClickException(
                "Could not find npx. Install Node.js/npm to use alex skills."
            ) from error

        ctx.exit(exit_code)

    return command


def _copy_install_requested(args: Sequence[str]) -> bool:
    if len(args) < 2:
        return False

    command = args[0]
    return command in {"add", "a"} and "--copy" in args[1:]


skills = build_skills_command()
