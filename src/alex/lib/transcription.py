from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from alex.lib.llm import (
    AudioTranscript,
    LiteLlmTranscriber,
    Transcriber,
    TranscriptSegment,
)

DEFAULT_TRANSCRIBER = LiteLlmTranscriber()


@dataclass(frozen=True)
class TranscriptionConfig:
    source: Path
    output_path: Path
    model: str
    force: bool


@dataclass(frozen=True)
class TranscriptionOutput:
    output_dir: Path
    transcript_path: Path
    json_path: Path


def transcribe_audio(
    config: TranscriptionConfig,
    *,
    transcriber: Transcriber = DEFAULT_TRANSCRIBER,
) -> TranscriptionOutput:
    output_dir = config.output_path / config.source.stem
    if output_dir.exists():
        if not config.force:
            raise FileExistsError(
                f"{output_dir} already exists. Pass --force to replace it."
            )
        _remove_existing_output(output_dir)
    output_dir.mkdir(parents=True)

    transcript = transcriber.transcribe(audio_path=config.source, model=config.model)
    transcript_path = output_dir / "transcript.txt"
    json_path = output_dir / "transcript.json"
    transcript_path.write_text(format_diarized_text(transcript), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            transcript_to_jsonable(
                source=config.source,
                model=config.model,
                transcript=transcript,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return TranscriptionOutput(
        output_dir=output_dir,
        transcript_path=transcript_path,
        json_path=json_path,
    )


def format_diarized_text(transcript: AudioTranscript) -> str:
    segments = transcript.segments or (
        TranscriptSegment(
            text=transcript.text,
            speaker=None,
            start_seconds=None,
            end_seconds=None,
        ),
    )
    lines = [_format_segment(segment) for segment in segments]
    return "\n".join(lines) + "\n"


def transcript_to_jsonable(
    *,
    source: Path,
    model: str,
    transcript: AudioTranscript,
) -> dict[str, object]:
    return {
        "source": str(source),
        "model": model,
        "text": transcript.text,
        "language": transcript.language,
        "duration_seconds": transcript.duration_seconds,
        "segments": [
            {
                "speaker": segment.speaker,
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }


def _format_segment(segment: TranscriptSegment) -> str:
    speaker = segment.speaker or "Speaker 1"
    timestamp = _format_time_range(segment.start_seconds, segment.end_seconds)
    if timestamp is None:
        return f"{speaker}: {segment.text}"
    return f"[{timestamp}] {speaker}: {segment.text}"


def _format_time_range(
    start_seconds: float | None,
    end_seconds: float | None,
) -> str | None:
    if start_seconds is None or end_seconds is None:
        return None
    return f"{_format_timestamp(start_seconds)} - {_format_timestamp(end_seconds)}"


def _format_timestamp(seconds: float) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    total_seconds, milliseconds = divmod(total_milliseconds, 1000)
    minutes, seconds_part = divmod(total_seconds, 60)
    hours, minutes_part = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes_part:02d}:{seconds_part:02d}.{milliseconds:03d}"
    return f"{minutes_part:02d}:{seconds_part:02d}.{milliseconds:03d}"


def _remove_existing_output(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()
