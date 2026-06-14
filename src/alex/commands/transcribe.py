from __future__ import annotations

from pathlib import Path
from typing import Protocol

import click

from alex.lib.llm import (
    DEFAULT_TRANSCRIPTION_MODEL,
    TRANSCRIPTION_MODEL_ENV,
    resolve_transcription_model,
)
from alex.lib.transcription import (
    TranscriptionConfig,
    TranscriptionOutput,
    transcribe_audio,
)


class TranscriptionProcessor(Protocol):
    def __call__(self, config: TranscriptionConfig) -> TranscriptionOutput: ...


def build_transcribe_command(
    processor: TranscriptionProcessor = transcribe_audio,
) -> click.Command:
    @click.command("transcribe")
    @click.argument(
        "source",
        metavar="AUDIO",
        type=click.Path(
            exists=True,
            dir_okay=False,
            readable=True,
            path_type=Path,
        ),
    )
    @click.argument(
        "output_path",
        metavar="OUTPUT_PATH",
        type=click.Path(file_okay=False, path_type=Path),
    )
    @click.option(
        "--model",
        help=(
            f"LiteLLM transcription model. Defaults to ${TRANSCRIPTION_MODEL_ENV} "
            f"or {DEFAULT_TRANSCRIPTION_MODEL}."
        ),
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Replace an existing transcription directory with the same source name.",
    )
    def command(
        source: Path,
        output_path: Path,
        model: str | None,
        force: bool,
    ) -> None:
        """Transcribe an audio file into speaker-labelled text."""
        selected_model = model or resolve_transcription_model()
        try:
            result = processor(
                TranscriptionConfig(
                    source=source,
                    output_path=output_path,
                    model=selected_model,
                    force=force,
                )
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Wrote {result.output_dir}")
        click.echo(f"Transcript: {result.transcript_path}")
        click.echo(f"JSON: {result.json_path}")

    return command


transcribe = build_transcribe_command()
