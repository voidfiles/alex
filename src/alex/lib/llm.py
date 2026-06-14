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
from typing import Any, Protocol

DEFAULT_FAST_SUMMARY_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_FINAL_SUMMARY_MODEL = "anthropic/claude-opus-4-8"
DEFAULT_ASSET_NAMING_MODEL = "anthropic/claude-sonnet-4-6"
# Anthropic has no embeddings endpoint, so the embedding default needs a
# non-Anthropic key. Swap providers via ALEX_EMBEDDING_MODEL.
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_EVAL_JUDGE_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_FACT_EXTRACTOR_MODEL = "anthropic/claude-sonnet-4-6"
DEFAULT_PROMPT_CRITIC_MODEL = "anthropic/claude-opus-4-8"
FAST_SUMMARY_MODEL_ENV = "ALEX_FAST_SUMMARY_MODEL"
FINAL_SUMMARY_MODEL_ENV = "ALEX_FINAL_SUMMARY_MODEL"
ASSET_NAMING_MODEL_ENV = "ALEX_NAMING_MODEL"
EMBEDDING_MODEL_ENV = "ALEX_EMBEDDING_MODEL"
EVAL_JUDGE_MODEL_ENV = "ALEX_EVAL_JUDGE_MODEL"
FACT_EXTRACTOR_MODEL_ENV = "ALEX_FACT_EXTRACTOR_MODEL"
PROMPT_CRITIC_MODEL_ENV = "ALEX_PROMPT_CRITIC_MODEL"
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
