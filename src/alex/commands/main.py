import click

from alex.commands.dump_env import dump_env
from alex.commands.eval_summary import eval_summary
from alex.commands.improve_prompt import improve_prompt_command
from alex.commands.pdf_samples import pdf_samples
from alex.commands.process_doc import process_doc
from alex.commands.process_vault import process_vault
from alex.commands.summary import summary
from alex.commands.to_asset import to_asset
from alex.commands.version import version
from alex.lib.env import load_source_dotenv


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Alex command line tools."""
    load_source_dotenv()


main.add_command(to_asset)
main.add_command(process_doc)
main.add_command(process_vault)
main.add_command(summary)
main.add_command(eval_summary)
main.add_command(improve_prompt_command)
main.add_command(pdf_samples)
main.add_command(dump_env)
main.add_command(version)
