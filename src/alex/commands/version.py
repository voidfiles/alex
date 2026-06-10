import click

from alex.lib.metadata import package_version


@click.command()
def version() -> None:
    """Print the installed alex version."""
    click.echo(f"alex {package_version()}")
