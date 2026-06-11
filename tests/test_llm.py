import sys
import time
from collections.abc import Callable
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from alex.lib.process_doc_assets import (
    DEFAULT_FAST_SUMMARY_MODEL,
    DEFAULT_FINAL_SUMMARY_MODEL,
    FAST_SUMMARY_MODEL_ENV,
    FINAL_SUMMARY_MODEL_ENV,
    LiteLlmCompleter,
    LlmError,
    complete_all,
    resolve_fast_summary_model,
    resolve_final_summary_model,
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
