from pathlib import Path

import click

from alex.lib.env import SOURCE_DOTENV_PATH


def build_dump_env_command(dotenv_path: Path = SOURCE_DOTENV_PATH) -> click.Command:
    @click.command("dump-env")
    def command() -> None:
        """Print the selected .env file."""
        if not dotenv_path.exists():
            raise click.ClickException(
                f"Selected .env file does not exist: {dotenv_path}"
            )

        click.echo(dotenv_path.read_text(encoding="utf-8"), nl=False)

    return command


dump_env = build_dump_env_command()
