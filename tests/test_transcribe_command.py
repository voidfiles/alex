from pathlib import Path

import pytest
from click.testing import CliRunner

from alex.commands.transcribe import build_transcribe_command
from alex.lib.transcription import TranscriptionConfig, TranscriptionOutput


def test_transcribe_command_passes_audio_config_to_processor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"audio")
    output_path = tmp_path / "transcripts"
    captured_configs: list[TranscriptionConfig] = []

    def fake_processor(config: TranscriptionConfig) -> TranscriptionOutput:
        captured_configs.append(config)
        output_dir = config.output_path / config.source.stem
        return TranscriptionOutput(
            output_dir=output_dir,
            transcript_path=output_dir / "transcript.txt",
            json_path=output_dir / "transcript.json",
        )

    result = CliRunner().invoke(
        build_transcribe_command(fake_processor),
        [
            str(source),
            str(output_path),
            "--model",
            "groq/whisper-large-v3",
            "--force",
        ],
    )

    output_dir = output_path / "meeting"
    assert result.exit_code == 0
    assert result.output == (
        f"Wrote {output_dir}\n"
        f"Transcript: {output_dir / 'transcript.txt'}\n"
        f"JSON: {output_dir / 'transcript.json'}\n"
    )
    assert captured_configs == [
        TranscriptionConfig(
            source=source,
            output_path=output_path,
            model="groq/whisper-large-v3",
            force=True,
        )
    ]


def test_transcribe_command_uses_model_environment_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"audio")
    captured_models: list[str] = []
    monkeypatch.setenv("ALEX_TRANSCRIPTION_MODEL", "openai/whisper-1")

    def fake_processor(config: TranscriptionConfig) -> TranscriptionOutput:
        captured_models.append(config.model)
        output_dir = config.output_path / config.source.stem
        return TranscriptionOutput(
            output_dir=output_dir,
            transcript_path=output_dir / "transcript.txt",
            json_path=output_dir / "transcript.json",
        )

    result = CliRunner().invoke(
        build_transcribe_command(fake_processor),
        [str(source), str(tmp_path / "transcripts")],
    )

    assert result.exit_code == 0
    assert captured_models == ["openai/whisper-1"]


def test_transcribe_help_describes_model_and_force_options() -> None:
    result = CliRunner().invoke(build_transcribe_command(), ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "AUDIO" in result.output
    assert "OUTPUT_PATH" in result.output
    assert "--model" in result.output
    assert "--force" in result.output
