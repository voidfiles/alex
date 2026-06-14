import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from alex.lib.llm import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_FAST_SUMMARY_MODEL,
    DEFAULT_FINAL_SUMMARY_MODEL,
    DEFAULT_TRANSCRIPTION_MODEL,
    EMBEDDING_MODEL_ENV,
    FAST_SUMMARY_MODEL_ENV,
    FINAL_SUMMARY_MODEL_ENV,
    TRANSCRIPTION_MODEL_ENV,
    AudioTranscript,
    LiteLlmCompleter,
    LiteLlmEmbedder,
    LiteLlmTranscriber,
    LlmError,
    TranscriptSegment,
    complete_all,
    resolve_embedding_model,
    resolve_fast_summary_model,
    resolve_final_summary_model,
    resolve_transcription_model,
)


def install_fake_litellm(
    monkeypatch: pytest.MonkeyPatch,
    completion: Callable[..., Any],
) -> None:
    litellm_module: Any = ModuleType("litellm")
    litellm_module.completion = completion
    litellm_module.suppress_debug_info = False
    monkeypatch.setitem(sys.modules, "litellm", litellm_module)


def completion_response(content: object) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_litellm_completer_returns_text_and_passes_request_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: list[dict[str, Any]] = []

    def fake_completion(**kwargs: Any) -> SimpleNamespace:
        captured_kwargs.append(kwargs)
        return completion_response("A summary.")

    install_fake_litellm(monkeypatch, fake_completion)

    result = LiteLlmCompleter(timeout_seconds=12.5, num_retries=3).complete(
        prompt="Summarize this.",
        model="anthropic/claude-haiku-4-5",
        max_tokens=1_000,
    )

    assert result == "A summary."
    assert captured_kwargs == [
        {
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "Summarize this."}],
            "max_tokens": 1_000,
            "timeout": 12.5,
            "num_retries": 3,
        }
    ]


def test_litellm_completer_wraps_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_completion(**kwargs: Any) -> SimpleNamespace:
        raise RuntimeError("rate limited")

    install_fake_litellm(monkeypatch, failing_completion)

    with pytest.raises(LlmError, match=r"openai/gpt-5.*rate limited"):
        LiteLlmCompleter().complete(
            prompt="Summarize this.",
            model="openai/gpt-5",
            max_tokens=100,
        )


@pytest.mark.parametrize("content", [None, "", "   "])
def test_litellm_completer_rejects_empty_completions(
    monkeypatch: pytest.MonkeyPatch,
    content: object,
) -> None:
    install_fake_litellm(monkeypatch, lambda **kwargs: completion_response(content))

    with pytest.raises(LlmError, match="empty completion"):
        LiteLlmCompleter().complete(
            prompt="Summarize this.",
            model="anthropic/claude-haiku-4-5",
            max_tokens=100,
        )


class SlowFirstCompleter:
    """Delays the first prompt so out-of-order completion would be visible."""

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        if prompt == "first":
            time.sleep(0.05)
        return f"response:{prompt}"


def test_complete_all_preserves_prompt_order_with_parallel_workers() -> None:
    results = complete_all(
        completer=SlowFirstCompleter(),
        prompts=("first", "second", "third"),
        model="test-model",
        max_tokens=100,
        max_workers=3,
    )

    assert results == ("response:first", "response:second", "response:third")


def test_complete_all_returns_empty_for_no_prompts() -> None:
    results = complete_all(
        completer=SlowFirstCompleter(),
        prompts=(),
        model="test-model",
        max_tokens=100,
        max_workers=4,
    )

    assert results == ()


def install_fake_litellm_embedding(
    monkeypatch: pytest.MonkeyPatch,
    embedding: Callable[..., Any],
) -> None:
    litellm_module: Any = ModuleType("litellm")
    litellm_module.embedding = embedding
    litellm_module.suppress_debug_info = False
    monkeypatch.setitem(sys.modules, "litellm", litellm_module)


def install_fake_litellm_transcription(
    monkeypatch: pytest.MonkeyPatch,
    transcription: Callable[..., Any],
) -> None:
    litellm_module: Any = ModuleType("litellm")
    litellm_module.transcription = transcription
    litellm_module.suppress_debug_info = False
    monkeypatch.setitem(sys.modules, "litellm", litellm_module)


def embedding_response(vectors: list[list[float]]) -> SimpleNamespace:
    # Reversed on purpose: the embedder must reorder by each item's index.
    data = [
        {"index": index, "embedding": vector}
        for index, vector in reversed(list(enumerate(vectors)))
    ]
    return SimpleNamespace(data=data)


def test_litellm_embedder_batches_inputs_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: list[dict[str, Any]] = []

    def fake_embedding(**kwargs: Any) -> SimpleNamespace:
        captured_kwargs.append(kwargs)
        batch_number = float(len(captured_kwargs))
        return embedding_response(
            [[batch_number, float(index)] for index in range(len(kwargs["input"]))]
        )

    install_fake_litellm_embedding(monkeypatch, fake_embedding)
    texts = [f"text {index}" for index in range(100)]

    result = LiteLlmEmbedder(timeout_seconds=5.0, num_retries=2).embed(
        texts=texts,
        model="openai/text-embedding-3-small",
    )

    assert [len(call["input"]) for call in captured_kwargs] == [96, 4]
    assert captured_kwargs[0]["model"] == "openai/text-embedding-3-small"
    assert captured_kwargs[0]["timeout"] == 5.0
    assert captured_kwargs[0]["num_retries"] == 2
    assert len(result) == 100
    assert result[0] == (1.0, 0.0)
    assert result[95] == (1.0, 95.0)
    assert result[96] == (2.0, 0.0)
    assert result[99] == (2.0, 3.0)


def test_litellm_embedder_makes_no_calls_for_empty_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_embedding(**kwargs: Any) -> SimpleNamespace:
        raise AssertionError("embedding should not be called")

    install_fake_litellm_embedding(monkeypatch, fail_embedding)

    assert LiteLlmEmbedder().embed(texts=[], model="openai/x") == ()


def test_litellm_embedder_wraps_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_embedding(**kwargs: Any) -> SimpleNamespace:
        raise RuntimeError("quota exceeded")

    install_fake_litellm_embedding(monkeypatch, failing_embedding)

    with pytest.raises(LlmError, match=r"openai/x.*quota exceeded"):
        LiteLlmEmbedder().embed(texts=["one"], model="openai/x")


def test_litellm_embedder_rejects_vector_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_litellm_embedding(
        monkeypatch,
        lambda **kwargs: embedding_response([[1.0, 0.0]]),
    )

    with pytest.raises(LlmError, match="1 embeddings for 2 inputs"):
        LiteLlmEmbedder().embed(texts=["one", "two"], model="openai/x")


def test_litellm_embedder_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_litellm_embedding(
        monkeypatch,
        lambda **kwargs: SimpleNamespace(data=[{"index": 0}]),
    )

    with pytest.raises(LlmError, match="malformed embedding response"):
        LiteLlmEmbedder().embed(texts=["one"], model="openai/x")


def test_embedding_model_defaults_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(EMBEDDING_MODEL_ENV, raising=False)
    assert resolve_embedding_model() == DEFAULT_EMBEDDING_MODEL

    monkeypatch.setenv(EMBEDDING_MODEL_ENV, "voyage/voyage-3.5-lite")
    assert resolve_embedding_model() == "voyage/voyage-3.5-lite"


def test_summary_models_default_to_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(FAST_SUMMARY_MODEL_ENV, raising=False)
    monkeypatch.delenv(FINAL_SUMMARY_MODEL_ENV, raising=False)

    assert resolve_fast_summary_model() == DEFAULT_FAST_SUMMARY_MODEL
    assert resolve_final_summary_model() == DEFAULT_FINAL_SUMMARY_MODEL


def test_summary_models_can_be_swapped_via_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(FAST_SUMMARY_MODEL_ENV, "gemini/gemini-2.5-flash")
    monkeypatch.setenv(FINAL_SUMMARY_MODEL_ENV, "openai/gpt-5")

    assert resolve_fast_summary_model() == "gemini/gemini-2.5-flash"
    assert resolve_final_summary_model() == "openai/gpt-5"


def test_transcription_model_defaults_to_openai_whisper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TRANSCRIPTION_MODEL_ENV, raising=False)
    assert resolve_transcription_model() == DEFAULT_TRANSCRIPTION_MODEL
    assert resolve_transcription_model() == "whisper-1"

    monkeypatch.setenv(TRANSCRIPTION_MODEL_ENV, "groq/whisper-large-v3")
    assert resolve_transcription_model() == "groq/whisper-large-v3"


def test_litellm_transcriber_requests_verbose_json_segments_and_parses_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"audio bytes")
    captured_kwargs: list[dict[str, Any]] = []

    def fake_transcription(**kwargs: Any) -> SimpleNamespace:
        captured_kwargs.append(kwargs)
        assert kwargs["file"].read() == b"audio bytes"
        return SimpleNamespace(
            text="Hello there.",
            language="en",
            duration=1.2,
            segments=[
                {
                    "speaker": "Speaker A",
                    "start": 0.0,
                    "end": 1.2,
                    "text": "Hello there.",
                }
            ],
        )

    install_fake_litellm_transcription(monkeypatch, fake_transcription)

    result = LiteLlmTranscriber(timeout_seconds=12.5, num_retries=3).transcribe(
        audio_path=audio_path,
        model="whisper-1",
    )

    assert result == AudioTranscript(
        text="Hello there.",
        language="en",
        duration_seconds=1.2,
        segments=(
            TranscriptSegment(
                text="Hello there.",
                speaker="Speaker A",
                start_seconds=0.0,
                end_seconds=1.2,
            ),
        ),
    )
    assert captured_kwargs[0]["model"] == "whisper-1"
    assert captured_kwargs[0]["response_format"] == "verbose_json"
    assert captured_kwargs[0]["timestamp_granularities"] == ["segment"]
    assert captured_kwargs[0]["timeout"] == 12.5
    assert captured_kwargs[0]["num_retries"] == 3


def test_litellm_transcriber_wraps_provider_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"audio bytes")

    def failing_transcription(**kwargs: Any) -> SimpleNamespace:
        raise RuntimeError("bad audio")

    install_fake_litellm_transcription(monkeypatch, failing_transcription)

    with pytest.raises(LlmError, match=r"whisper-1.*bad audio"):
        LiteLlmTranscriber().transcribe(audio_path=audio_path, model="whisper-1")
