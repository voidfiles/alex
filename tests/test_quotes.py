from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from alex.commands.main import main
from alex.commands.quotes import build_quotes_command
from alex.lib.llm import DEFAULT_QUOTE_MODEL, resolve_quote_model
from alex.lib.prompt_templates import load_prompt
from alex.lib.quotes import (
    QuoteError,
    QuoteExtraction,
    QuoteSettings,
    extract_quotes,
    markdown_to_text,
    parse_selected_quotes,
    quotes_markdown,
    sha256,
)
from helpers import RecordingCompleter

SOURCE = "# A document\n\nA **patient** tutor helps you [learn](https://example.com).\n"
TEXT = "A patient tutor helps you learn."


def response(*segments: str) -> str:
    return json.dumps({"quotes": [{"segments": list(segments)}]})


def fake_extraction(source: str, settings: QuoteSettings) -> QuoteExtraction:
    return extract_quotes(
        source,
        settings,
        completer=RecordingCompleter(compression_response=response(TEXT)),
    )


def test_markdown_rendering_preserves_readable_content_and_hides_scripts() -> None:
    source = (
        SOURCE + "\n<div>HTML <em>prose</em> &amp; entities.</div>\n\n"
        "<script>hidden</script>\n"
    )
    text = markdown_to_text(source)
    assert TEXT in text
    assert "HTML prose & entities." in text
    assert "hidden" not in text
    assert "https://example.com" not in text
    assert "**patient**" not in text


def test_markdown_renderer_handles_tables_lists_and_code() -> None:
    source = (
        "- First\n- Second\n\n| Key | Value |\n| --- | --- |\n| a | b |\n\n"
        "```\n<literal>\n```\n"
    )
    text = markdown_to_text(source)
    assert all(
        word in text for word in ("First", "Second", "Key", "Value", "<literal>")
    )


def test_markdown_output_preserves_literal_markup_from_source_code() -> None:
    passage = (
        "Use *literal* [brackets], &copy;, and <script>alert(1)</script>.\n"
        "- This is literal text.\n1. This is literal text too."
    )
    source = "```text\n" + passage + "\n```\n"
    result = extract_quotes(
        source,
        completer=RecordingCompleter(compression_response=response(passage)),
    )
    output = quotes_markdown(result)
    assert "<script>" not in output
    assert markdown_to_text(output) == "Quote 1\n\n" + passage


def test_extraction_sends_full_rendered_document_and_records_source_spans() -> None:
    source = SOURCE + "\nThe closing paragraph also matters.\n"
    completer = RecordingCompleter(compression_response=response(TEXT))
    result = extract_quotes(
        source, QuoteSettings(model="fake-model", count=1), completer=completer
    )
    assert len(completer.calls) == 1
    assert "The closing paragraph also matters." in completer.calls[0].prompt
    assert TEXT in completer.calls[0].prompt
    assert completer.calls[0].model == "fake-model"
    segment = result.quotes[0].segments[0]
    assert markdown_to_text(source)[segment.char_start : segment.char_end] == TEXT
    assert result.source_sha256 == sha256(source)
    assert result.to_dict()["offset_target"] == "markdown_to_text(source_markdown)"


def test_reflowed_whitespace_is_recovered_from_source_and_gaps_are_explicit() -> None:
    source = "First line\ncontinues here.\n\nOmitted text.\n\nLast sentence."
    result = parse_selected_quotes(
        response("First line continues here.", "Last sentence."), source, count=1
    )
    assert result[0].segments[0].text == "First line\ncontinues here."
    assert result[0].text == "First line\ncontinues here.\n\n[...]\n\nLast sentence."


@pytest.mark.parametrize(
    "raw",
    [
        response("A patient tutor helps you master quantum physics."),
        response("A Patient tutor helps you learn."),
        response("A patient tutor helps you learn!"),
        response(""),
        '{"quotes":[{"text":"A patient tutor helps you learn."}]}',
        'Here are your quotes: {"quotes": []}',
        '{"quotes": [], "explanation": "extra"}',
    ],
)
def test_invalid_or_rewritten_quotes_are_rejected(raw: str) -> None:
    with pytest.raises(QuoteError):
        parse_selected_quotes(raw, TEXT, count=1)


def test_changed_numbers_and_word_fragments_are_rejected() -> None:
    for quoted in ("There were 99 tasks.", "ere were 100 tasks."):
        with pytest.raises(QuoteError, match="absent"):
            parse_selected_quotes(response(quoted), "There were 100 tasks.", count=1)


def test_reversed_segments_and_overlapping_quotes_are_rejected() -> None:
    with pytest.raises(QuoteError, match="absent"):
        parse_selected_quotes(
            response("Last sentence.", "First sentence."),
            "First sentence. Last sentence.",
            count=1,
        )
    raw = json.dumps({"quotes": [{"segments": [TEXT]}, {"segments": [TEXT]}]})
    with pytest.raises(QuoteError, match="overlapping"):
        parse_selected_quotes(raw, TEXT, count=2)
    with pytest.raises(QuoteError, match="more than"):
        parse_selected_quotes(raw, TEXT, count=1)


def test_empty_document_fails_before_model_call() -> None:
    completer = RecordingCompleter()
    with pytest.raises(QuoteError, match="no readable text"):
        extract_quotes(" \n", completer=completer)
    assert completer.calls == []


def test_empty_selection_and_json_fences_are_supported() -> None:
    assert parse_selected_quotes('{"quotes": []}', TEXT, count=1) == ()
    assert (
        parse_selected_quotes("```json\n" + response(TEXT) + "\n```", TEXT, count=1)[
            0
        ].text
        == TEXT
    )


def test_quotes_command_reads_stdin_and_writes_valid_json() -> None:
    captured: list[QuoteSettings] = []

    def fake(source: str, settings: QuoteSettings) -> QuoteExtraction:
        captured.append(settings)
        return fake_extraction(source, settings)

    result = CliRunner().invoke(
        build_quotes_command(fake),
        ["-", "--count", "1", "--model", "fake-model", "--json"],
        input=SOURCE,
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["quotes"][0]["text"] == TEXT
    assert captured[0].count == 1
    assert captured[0].model == "fake-model"


def test_quotes_command_writes_markdown_to_file(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(SOURCE)
    output = tmp_path / "quotes.md"
    result = CliRunner().invoke(
        build_quotes_command(fake_extraction), [str(source), "-o", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "> " + TEXT in output.read_text()


def test_quotes_command_does_not_overwrite_input(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(SOURCE)
    result = CliRunner().invoke(
        build_quotes_command(fake_extraction), [str(source), "-o", str(source)]
    )
    assert result.exit_code != 0
    assert "must not replace" in result.output
    assert source.read_text() == SOURCE


def test_quote_model_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALEX_QUOTE_MODEL", raising=False)
    assert resolve_quote_model() == DEFAULT_QUOTE_MODEL
    monkeypatch.setenv("ALEX_QUOTE_MODEL", "test/provider")
    assert resolve_quote_model() == "test/provider"


def test_quote_prompt_version_is_pinned_and_placeholders_are_stable() -> None:
    template = load_prompt("quote_extraction", version="v001")
    assert template.placeholders() == {"source", "count"}
    result = fake_extraction(SOURCE, QuoteSettings(prompt_version="v001"))
    assert result.prompt_version == "v001"
    assert result.prompt_sha256 == sha256(template.text)
    assert "> " + TEXT in quotes_markdown(result)


def test_quotes_commands_are_registered_and_help_is_available() -> None:
    for command in ("quotes", "eval-quotes"):
        result = CliRunner().invoke(main, [command, "--help"])
        assert result.exit_code == 0
