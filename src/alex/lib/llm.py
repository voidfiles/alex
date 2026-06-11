"""LLM access for the CLI.

All model choices live here. Each role (fast summaries, final synthesis,
asset naming) has a default and an environment override, and any LiteLLM
model string works: "anthropic/claude-opus-4-8", "openai/gpt-5",
"gemini/gemini-2.5-pro", and so on.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

DEFAULT_FAST_SUMMARY_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_FINAL_SUMMARY_MODEL = "anthropic/claude-opus-4-8"
DEFAULT_ASSET_NAMING_MODEL = "anthropic/claude-sonnet-4-6"
FAST_SUMMARY_MODEL_ENV = "ALEX_FAST_SUMMARY_MODEL"
FINAL_SUMMARY_MODEL_ENV = "ALEX_FINAL_SUMMARY_MODEL"
ASSET_NAMING_MODEL_ENV = "ALEX_NAMING_MODEL"
DEFAULT_LLM_TIMEOUT_SECONDS = 900.0
DEFAULT_LLM_RETRIES = 6


def resolve_fast_summary_model() -> str:
    return os.getenv(FAST_SUMMARY_MODEL_ENV) or DEFAULT_FAST_SUMMARY_MODEL


def resolve_final_summary_model() -> str:
    return os.getenv(FINAL_SUMMARY_MODEL_ENV) or DEFAULT_FINAL_SUMMARY_MODEL


def resolve_asset_naming_model() -> str:
    return os.getenv(ASSET_NAMING_MODEL_ENV) or DEFAULT_ASSET_NAMING_MODEL


class LlmError(RuntimeError):
    pass


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
