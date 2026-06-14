"""Shared test doubles for the summarize pipeline."""

from typing import NamedTuple


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
        return self.compression_response

    def chunk_calls(self) -> list[CompletionCall]:
        return [call for call in self.calls if "<section_content>" in call.prompt]

    def compression_calls(self) -> list[CompletionCall]:
        return [call for call in self.calls if "Consolidated summary:" in call.prompt]

    def final_calls(self) -> list[CompletionCall]:
        return [call for call in self.calls if "<section_summaries>" in call.prompt]
