"""LLM access for the CLI.

All model choices live here. Each role (fast summaries, final synthesis,
asset naming) has a default and an environment override, and any LiteLLM
model string works: "anthropic/claude-opus-4-8", "openai/gpt-5",
"gemini/gemini-2.5-pro", and so on.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeGuard

DEFAULT_FAST_SUMMARY_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_FINAL_SUMMARY_MODEL = "anthropic/claude-opus-4-8"
DEFAULT_ASSET_NAMING_MODEL = "anthropic/claude-sonnet-4-6"
# Anthropic has no embeddings endpoint, so the embedding default needs a
# non-Anthropic key. Swap providers via ALEX_EMBEDDING_MODEL.
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_EVAL_JUDGE_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_FACT_EXTRACTOR_MODEL = "anthropic/claude-sonnet-4-6"
DEFAULT_PROMPT_CRITIC_MODEL = "anthropic/claude-opus-4-8"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
FAST_SUMMARY_MODEL_ENV = "ALEX_FAST_SUMMARY_MODEL"
FINAL_SUMMARY_MODEL_ENV = "ALEX_FINAL_SUMMARY_MODEL"
ASSET_NAMING_MODEL_ENV = "ALEX_NAMING_MODEL"
EMBEDDING_MODEL_ENV = "ALEX_EMBEDDING_MODEL"
EVAL_JUDGE_MODEL_ENV = "ALEX_EVAL_JUDGE_MODEL"
FACT_EXTRACTOR_MODEL_ENV = "ALEX_FACT_EXTRACTOR_MODEL"
PROMPT_CRITIC_MODEL_ENV = "ALEX_PROMPT_CRITIC_MODEL"
TRANSCRIPTION_MODEL_ENV = "ALEX_TRANSCRIPTION_MODEL"
DEFAULT_LLM_TIMEOUT_SECONDS = 900.0
DEFAULT_LLM_RETRIES = 6
EMBEDDING_BATCH_SIZE = 96


def resolve_fast_summary_model() -> str:
    return os.getenv(FAST_SUMMARY_MODEL_ENV) or DEFAULT_FAST_SUMMARY_MODEL


def resolve_final_summary_model() -> str:
    return os.getenv(FINAL_SUMMARY_MODEL_ENV) or DEFAULT_FINAL_SUMMARY_MODEL


def resolve_asset_naming_model() -> str:
    return os.getenv(ASSET_NAMING_MODEL_ENV) or DEFAULT_ASSET_NAMING_MODEL


def resolve_embedding_model() -> str:
    return os.getenv(EMBEDDING_MODEL_ENV) or DEFAULT_EMBEDDING_MODEL


def resolve_eval_judge_model() -> str:
    return os.getenv(EVAL_JUDGE_MODEL_ENV) or DEFAULT_EVAL_JUDGE_MODEL


def resolve_fact_extractor_model() -> str:
    return os.getenv(FACT_EXTRACTOR_MODEL_ENV) or DEFAULT_FACT_EXTRACTOR_MODEL


def resolve_prompt_critic_model() -> str:
    return os.getenv(PROMPT_CRITIC_MODEL_ENV) or DEFAULT_PROMPT_CRITIC_MODEL


def resolve_transcription_model() -> str:
    return os.getenv(TRANSCRIPTION_MODEL_ENV) or DEFAULT_TRANSCRIPTION_MODEL


class LlmError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    speaker: str | None
    start_seconds: float | None
    end_seconds: float | None


@dataclass(frozen=True)
class AudioTranscript:
    text: str
    language: str | None
    duration_seconds: float | None
    segments: tuple[TranscriptSegment, ...]


class Completer(Protocol):
    def complete(
        self,
        *,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> str: ...


@dataclass(frozen=True)
class LiteLlmCompleter:
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    num_retries: int = DEFAULT_LLM_RETRIES

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        # Imported lazily: litellm drags in a large dependency tree and the
        # CLI only needs it once a command actually calls a model.
        import litellm

        litellm.suppress_debug_info = True
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                timeout=self.timeout_seconds,
                num_retries=self.num_retries,
            )
        except Exception as error:
            raise LlmError(f"LLM request failed for model {model}: {error}") from error

        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise LlmError(f"Model {model} returned an empty completion.")
        return content


class Transcriber(Protocol):
    def transcribe(
        self,
        *,
        audio_path: Path,
        model: str,
    ) -> AudioTranscript: ...


@dataclass(frozen=True)
class LiteLlmTranscriber:
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    num_retries: int = DEFAULT_LLM_RETRIES

    def transcribe(
        self,
        *,
        audio_path: Path,
        model: str,
    ) -> AudioTranscript:
        # Imported lazily: litellm drags in a large dependency tree and the
        # CLI only needs it once a command actually calls a model.
        import litellm

        litellm.suppress_debug_info = True
        try:
            with audio_path.open("rb") as audio_file:
                response = litellm.transcription(
                    model=model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    timeout=self.timeout_seconds,
                    num_retries=self.num_retries,
                )
        except Exception as error:
            raise LlmError(
                f"Transcription request failed for model {model}: {error}"
            ) from error

        return parse_transcription_response(response, model=model)


class Embedder(Protocol):
    def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
    ) -> tuple[tuple[float, ...], ...]: ...


@dataclass(frozen=True)
class LiteLlmEmbedder:
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    num_retries: int = DEFAULT_LLM_RETRIES

    def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
    ) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        # Imported lazily: litellm drags in a large dependency tree and the
        # CLI only needs it once a command actually calls a model.
        import litellm

        litellm.suppress_debug_info = True
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = list(texts[start : start + EMBEDDING_BATCH_SIZE])
            try:
                response = litellm.embedding(
                    model=model,
                    input=batch,
                    timeout=self.timeout_seconds,
                    num_retries=self.num_retries,
                )
            except Exception as error:
                raise LlmError(
                    f"Embedding request failed for model {model}: {error}"
                ) from error
            vectors.extend(
                parse_embedding_response(response, model=model, expected=len(batch))
            )
        return tuple(vectors)


def parse_embedding_response(
    response: Any,
    *,
    model: str,
    expected: int,
) -> tuple[tuple[float, ...], ...]:
    try:
        items = sorted(response.data, key=lambda item: int(item["index"]))
        vectors = tuple(
            tuple(float(value) for value in item["embedding"]) for item in items
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise LlmError(
            f"Model {model} returned a malformed embedding response: {error}"
        ) from error
    if len(vectors) != expected:
        raise LlmError(
            f"Model {model} returned {len(vectors)} embeddings for {expected} inputs."
        )
    return vectors


def parse_transcription_response(
    response: object,
    *,
    model: str,
) -> AudioTranscript:
    segments = _parse_transcript_segments(response)
    response_text = _optional_str(response if isinstance(response, str) else None)
    if response_text is None:
        response_text = _optional_str(_response_field(response, "text"))
    if response_text is None and segments:
        response_text = " ".join(segment.text for segment in segments)
    if response_text is None:
        raise LlmError(f"Model {model} returned an empty transcription.")

    if not segments:
        segments = (
            TranscriptSegment(
                text=response_text,
                speaker=None,
                start_seconds=None,
                end_seconds=None,
            ),
        )

    return AudioTranscript(
        text=response_text,
        language=_optional_str(_response_field(response, "language")),
        duration_seconds=_optional_float(_response_field(response, "duration")),
        segments=segments,
    )


def _parse_transcript_segments(response: object) -> tuple[TranscriptSegment, ...]:
    value = _response_field(response, "segments")
    if not _is_object_sequence(value):
        return ()

    segments: list[TranscriptSegment] = []
    for item in value:
        text = _optional_str(_response_field(item, "text"))
        if text is None:
            continue
        segments.append(
            TranscriptSegment(
                text=text,
                speaker=_optional_str(_response_field(item, "speaker")),
                start_seconds=_optional_float(_response_field(item, "start")),
                end_seconds=_optional_float(_response_field(item, "end")),
            )
        )
    return tuple(segments)


def _response_field(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        mapping: Mapping[object, object] = value
        return mapping.get(name)
    return getattr(value, name, None)


def _is_object_sequence(value: object | None) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(
        value,
        str | bytes | bytearray,
    )


def _optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _optional_float(value: object | None) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def complete_all(
    *,
    completer: Completer,
    prompts: Sequence[str],
    model: str,
    max_tokens: int,
    max_workers: int,
) -> tuple[str, ...]:
    if not prompts:
        return ()

    def run(prompt: str) -> str:
        return completer.complete(prompt=prompt, model=model, max_tokens=max_tokens)

    worker_count = min(max(1, max_workers), len(prompts))
    if worker_count == 1:
        return tuple(run(prompt) for prompt in prompts)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return tuple(executor.map(run, prompts))
