"""Shared test doubles for the summarize pipeline."""

import json
import re
from collections.abc import Sequence
from typing import NamedTuple


class BagOfWordsEmbedder:
    """Deterministic, offline stand-in for a real embedder.

    Each text becomes a term-frequency vector over the vocabulary of the batch,
    so cosine similarity reduces to word overlap. Real embeddings would catch
    paraphrases this misses, but tests only need similar texts to score high and
    dissimilar ones to score low, deterministically and without a network call.
    """

    def embed(
        self, *, texts: Sequence[str], model: str
    ) -> tuple[tuple[float, ...], ...]:
        tokenized = [re.findall(r"[a-z]+", text.lower()) for text in texts]
        vocab = sorted({word for tokens in tokenized for word in tokens})
        position = {word: index for index, word in enumerate(vocab)}
        vectors: list[tuple[float, ...]] = []
        for tokens in tokenized:
            counts = [0.0] * len(vocab)
            for word in tokens:
                counts[position[word]] += 1.0
            vectors.append(tuple(counts))
        return tuple(vectors)


class CompletionCall(NamedTuple):
    prompt: str
    model: str
    max_tokens: int


class RecordingCompleter:
    """Routes canned responses by prompt shape, mirroring the real pipeline.

    Tests pin summary_max_workers=1 so chunk responses pop in chunk order.
    """

    def __init__(
        self,
        *,
        chunk_responses: list[str] | None = None,
        compression_response: str = "Compressed summary.",
        final_response: str = "Final synthesis.",
    ) -> None:
        self.chunk_responses = chunk_responses
        self.compression_response = compression_response
        self.final_response = final_response
        self.calls: list[CompletionCall] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append(CompletionCall(prompt, model, max_tokens))
        if "<section_content>" in prompt:
            if self.chunk_responses is None:
                return f"Summary for chunk {len(self.calls)}."
            return self.chunk_responses.pop(0)
        if "<section_summaries>" in prompt:
            return self.final_response
        if "source-grounded items" in prompt:
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": "The document preserves important claims.",
                            "evidence": "The document states important claims.",
                        }
                    ],
                    "concepts": [
                        {
                            "concept": "Summary graph",
                            "definition": "A graph that preserves important claims.",
                            "evidence": "The document states important claims.",
                        }
                    ],
                    "key_passages": [
                        {
                            "passage": "The document states important claims.",
                            "why_it_matters": (
                                "It anchors the summary in source wording."
                            ),
                        }
                    ],
                }
            )
        if "Use the selected summary graph as the only source of truth" in prompt:
            return "Graph-grounded summary."
        if "merging two independently generated summaries" in prompt:
            return f"Merged summary from {self.final_response}"
        if "revising a merged summary" in prompt:
            return f"Repaired {self.final_response}"
        if "extracting factual claims from a summary" in prompt:
            return json.dumps({"claims": ["Merged summary is supported."]})
        if "verifying summary claims against the source document" in prompt:
            return json.dumps(
                {
                    "verdicts": [
                        {"supported": True, "evidence": "document support"}
                        for _ in range(numbered_item_count(prompt))
                    ]
                }
            )
        if "filtering a merged summary for source faithfulness" in prompt:
            return f"Faithful {self.final_response}"
        return self.compression_response

    def chunk_calls(self) -> list[CompletionCall]:
        return [call for call in self.calls if "<section_content>" in call.prompt]

    def compression_calls(self) -> list[CompletionCall]:
        return [call for call in self.calls if "Consolidated summary:" in call.prompt]

    def final_calls(self) -> list[CompletionCall]:
        return [call for call in self.calls if "<section_summaries>" in call.prompt]


def numbered_item_count(prompt: str) -> int:
    return sum(
        1 for line in prompt.splitlines() if line[:1].isdigit() and ". " in line[:5]
    )
