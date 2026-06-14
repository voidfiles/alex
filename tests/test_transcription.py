import json
from pathlib import Path

import pytest

from alex.lib.llm import AudioTranscript, TranscriptSegment
from alex.lib.transcription import (
    TranscriptionConfig,
    TranscriptionOutput,
    format_diarized_text,
    transcribe_audio,
)


class RecordingTranscriber:
    def __init__(self, transcript: AudioTranscript) -> None:
        self.transcript = transcript
        self.calls: list[tuple[Path, str]] = []

    def transcribe(self, *, audio_path: Path, model: str) -> AudioTranscript:
        self.calls.append((audio_path, model))
        return self.transcript


def test_format_diarized_text_uses_speaker_and_timestamp_metadata() -> None:
    transcript = AudioTranscript(
        text="Hello there. Hi.",
        language="en",
        duration_seconds=2.4,
        segments=(
            TranscriptSegment(
                text="Hello there.",
                speaker="Agent",
                start_seconds=0.0,
                end_seconds=1.2,
            ),
            TranscriptSegment(
                text="Hi.",
                speaker="Customer",
                start_seconds=1.2,
                end_seconds=2.4,
            ),
        ),
    )

    assert format_diarized_text(transcript) == (
        "[00:00.000 - 00:01.200] Agent: Hello there.\n"
        "[00:01.200 - 00:02.400] Customer: Hi.\n"
    )


def test_format_diarized_text_falls_back_to_single_speaker_for_whisper() -> None:
    transcript = AudioTranscript(
        text="Just one speaker.",
        language=None,
        duration_seconds=None,
        segments=(
            TranscriptSegment(
                text="Just one speaker.",
                speaker=None,
                start_seconds=None,
                end_seconds=None,
            ),
        ),
    )

    assert format_diarized_text(transcript) == "Speaker 1: Just one speaker.\n"


def test_transcribe_audio_writes_stem_named_output_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"audio")
    output_path = tmp_path / "transcripts"
    transcript = AudioTranscript(
        text="Hello there. Hi.",
        language="en",
        duration_seconds=2.4,
        segments=(
            TranscriptSegment(
                text="Hello there.",
                speaker="Agent",
                start_seconds=0.0,
                end_seconds=1.2,
            ),
            TranscriptSegment(
                text="Hi.",
                speaker="Customer",
                start_seconds=1.2,
                end_seconds=2.4,
            ),
        ),
    )
    transcriber = RecordingTranscriber(transcript)

    result = transcribe_audio(
        TranscriptionConfig(
            source=source,
            output_path=output_path,
            model="whisper-1",
            force=False,
        ),
        transcriber=transcriber,
    )

    transcript_dir = output_path / "meeting"
    assert result == TranscriptionOutput(
        output_dir=transcript_dir,
        transcript_path=transcript_dir / "transcript.txt",
        json_path=transcript_dir / "transcript.json",
    )
    assert transcriber.calls == [(source, "whisper-1")]
    assert result.transcript_path.read_text(encoding="utf-8") == (
        "[00:00.000 - 00:01.200] Agent: Hello there.\n"
        "[00:01.200 - 00:02.400] Customer: Hi.\n"
    )
    assert json.loads(result.json_path.read_text(encoding="utf-8")) == {
        "source": str(source),
        "model": "whisper-1",
        "text": "Hello there. Hi.",
        "language": "en",
        "duration_seconds": 2.4,
        "segments": [
            {
                "speaker": "Agent",
                "start_seconds": 0.0,
                "end_seconds": 1.2,
                "text": "Hello there.",
            },
            {
                "speaker": "Customer",
                "start_seconds": 1.2,
                "end_seconds": 2.4,
                "text": "Hi.",
            },
        ],
    }


def test_transcribe_audio_rejects_existing_output_without_force(
    tmp_path: Path,
) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"audio")
    output_path = tmp_path / "transcripts"
    (output_path / "meeting").mkdir(parents=True)
    transcriber = RecordingTranscriber(
        AudioTranscript(
            text="unused",
            language=None,
            duration_seconds=None,
            segments=(),
        )
    )

    with pytest.raises(FileExistsError, match="already exists"):
        transcribe_audio(
            TranscriptionConfig(
                source=source,
                output_path=output_path,
                model="whisper-1",
                force=False,
            ),
            transcriber=transcriber,
        )

    assert transcriber.calls == []


def test_transcribe_audio_replaces_existing_output_with_force(tmp_path: Path) -> None:
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"audio")
    output_path = tmp_path / "transcripts"
    stale_file = output_path / "meeting" / "old.txt"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale", encoding="utf-8")
    transcriber = RecordingTranscriber(
        AudioTranscript(
            text="Fresh.",
            language=None,
            duration_seconds=None,
            segments=(
                TranscriptSegment(
                    text="Fresh.",
                    speaker=None,
                    start_seconds=None,
                    end_seconds=None,
                ),
            ),
        )
    )

    result = transcribe_audio(
        TranscriptionConfig(
            source=source,
            output_path=output_path,
            model="whisper-1",
            force=True,
        ),
        transcriber=transcriber,
    )

    assert not stale_file.exists()
    assert result.transcript_path.read_text(encoding="utf-8") == "Speaker 1: Fresh.\n"
