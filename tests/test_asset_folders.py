from pathlib import Path

from alex.lib.asset_folders import (
    AssetName,
    AssetNameInput,
    LlmAssetNamer,
)


class RecordingCompleter:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        return self.response


def test_llm_asset_namer_extracts_metadata_and_canonical_name() -> None:
    completer = RecordingCompleter(
        'Sure, here it is: {"title": "Deep Work", "authors": "Cal Newport"}'
    )
    namer = LlmAssetNamer(completer=completer, model="test-model")

    result = namer(
        AssetNameInput(
            source=Path("deep-work.pdf"),
            markdown="# Deep Work\n\nBy Cal Newport\n\nBody.\n",
            headers=(
                "# Document Structure\n\n"
                "Table of Contents:\n\n"
                "- Deep Work (H1, line 1, 5 lines)\n"
            ),
        )
    )

    assert result == AssetName(
        title="Deep Work",
        authors=("Cal Newport",),
        canonical_name="deep_work_cal_newport",
    )
    assert len(completer.calls) == 1
    call = completer.calls[0]
    assert call["model"] == "test-model"
    assert call["max_tokens"] == 200
    assert "Extract the canonical title and primary author" in str(call["prompt"])
    assert "# Deep Work" in str(call["prompt"])
    assert "- Deep Work (H1, line 1, 5 lines)" in str(call["prompt"])
