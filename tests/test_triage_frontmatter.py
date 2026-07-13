"""Tests for surgical frontmatter editing used by the triage pipeline."""

from alex.lib.triage.frontmatter import (
    assemble_frontmatter,
    read_frontmatter,
    read_triage_block,
    replace_top_level_key,
    set_frontmatter_list,
    split_frontmatter,
    write_triage_block,
)
from alex.lib.triage.models import TriageBlock

NOTE = (
    "---\n"
    "type: article\n"
    "created: 2026-01-05\n"
    "# reviewed by hand, do not touch\n"
    "tags:\n"
    "  - learning\n"
    "  - spaced-repetition\n"
    "workflow:\n"
    "  highlighted: true\n"
    "---\n"
    "\n"
    "Body with **bold** and ==highlight== marks.\n"
)


def test_split_frontmatter_returns_yaml_and_body() -> None:
    yaml_text, body = split_frontmatter("---\ntype: note\n---\nBody\n")

    assert yaml_text == "type: note"
    assert body == "Body\n"


def test_split_frontmatter_handles_missing_block() -> None:
    assert split_frontmatter("Just text\n") == (None, "Just text\n")


def test_split_frontmatter_handles_fence_at_end_of_file() -> None:
    yaml_text, body = split_frontmatter("---\ntype: note\n---")

    assert yaml_text == "type: note"
    assert body == ""


def test_split_frontmatter_ignores_unclosed_fence() -> None:
    text = "---\ntype: note\nno closing fence\n"

    assert split_frontmatter(text) == (None, text)


def test_assemble_frontmatter_round_trips_split() -> None:
    yaml_text, body = split_frontmatter(NOTE)

    assert yaml_text is not None
    assert assemble_frontmatter(yaml_text, body) == NOTE


def test_read_frontmatter_parses_nested_keys() -> None:
    frontmatter = read_frontmatter(NOTE)

    assert frontmatter["type"] == "article"
    assert frontmatter["workflow"] == {"highlighted": True}
    assert frontmatter["tags"] == ["learning", "spaced-repetition"]


def test_read_frontmatter_returns_empty_dict_for_invalid_yaml() -> None:
    assert read_frontmatter("---\n{unclosed: [\n---\nBody\n") == {}


def test_read_frontmatter_returns_empty_dict_for_non_mapping() -> None:
    assert read_frontmatter("---\n- just\n- a list\n---\nBody\n") == {}


def test_replace_top_level_key_appends_block_keeping_other_lines_byte_identical() -> (
    None
):
    result = replace_top_level_key(NOTE, "triage", "triage:\n  decision: area")

    original_yaml, original_body = split_frontmatter(NOTE)
    new_yaml, new_body = split_frontmatter(result)
    assert new_body == original_body
    assert new_yaml is not None
    assert new_yaml == f"{original_yaml}\ntriage:\n  decision: area"
    assert "# reviewed by hand, do not touch" in result


def test_replace_top_level_key_removes_old_entry_with_nested_lines() -> None:
    text = (
        "---\n"
        "title: T\n"
        "triage:\n"
        "  decision: area\n"
        "  target: old-target\n"
        "status: keep-me\n"
        "---\n"
        "Body\n"
    )

    result = replace_top_level_key(text, "triage", "triage:\n  decision: trash")

    assert "old-target" not in result
    assert "status: keep-me" in result
    assert result.index("status: keep-me") < result.index("triage:")


def test_replace_top_level_key_with_none_deletes_entry() -> None:
    text = "---\ntitle: T\ntriage:\n  decision: area\n---\nBody\n"

    result = replace_top_level_key(text, "triage", None)

    assert result == "---\ntitle: T\n---\nBody\n"


def test_replace_top_level_key_removes_column_zero_list_items() -> None:
    text = "---\ntags:\n- one\n- two\ntitle: T\n---\nBody\n"

    result = replace_top_level_key(text, "tags", None)

    assert result == "---\ntitle: T\n---\nBody\n"


def test_replace_top_level_key_leaves_similarly_prefixed_keys_alone() -> None:
    text = "---\ntriage-notes: keep\n---\nBody\n"

    result = replace_top_level_key(text, "triage", "triage:\n  promising: true")

    assert "triage-notes: keep" in result


def test_replace_top_level_key_creates_frontmatter_when_missing() -> None:
    result = replace_top_level_key(
        "Plain body\n", "triage", "triage:\n  promising: true"
    )

    assert result == "---\ntriage:\n  promising: true\n---\nPlain body\n"


def test_replace_top_level_key_delete_without_frontmatter_is_a_noop() -> None:
    assert replace_top_level_key("Plain body\n", "triage", None) == "Plain body\n"


def test_write_triage_block_then_read_round_trips() -> None:
    block = TriageBlock(
        decision="area",
        target="learning-science",
        status="decided",
        decided="2026-07-12",
    )

    result = write_triage_block(NOTE, block)

    assert read_triage_block(result) == block
    assert "Body with **bold** and ==highlight== marks." in result


def test_write_triage_block_keeps_body_and_other_keys_byte_identical() -> None:
    original_yaml, original_body = split_frontmatter(NOTE)

    result = write_triage_block(NOTE, TriageBlock(decision="area", target="x"))

    new_yaml, new_body = split_frontmatter(result)
    assert new_body == original_body
    assert original_yaml is not None
    assert new_yaml is not None
    assert new_yaml.startswith(original_yaml)


def test_write_triage_block_emits_only_non_default_fields() -> None:
    result = write_triage_block(
        "---\ntitle: T\n---\nBody\n", TriageBlock(promising=True)
    )

    yaml_text, _ = split_frontmatter(result)
    assert yaml_text == "title: T\ntriage:\n  promising: true"


def test_write_triage_block_replaces_previous_block() -> None:
    first = write_triage_block(NOTE, TriageBlock(promising=True))

    second = write_triage_block(
        first, TriageBlock(decision="trash", status="decided", decided="2026-07-12")
    )

    expected = TriageBlock(decision="trash", status="decided", decided="2026-07-12")
    assert read_triage_block(second) == expected
    assert second.count("triage:") == 1
    assert "promising" not in second


def test_write_triage_block_creates_frontmatter_on_bare_note() -> None:
    result = write_triage_block("Just a body\n", TriageBlock(promising=True))

    assert result == "---\ntriage:\n  promising: true\n---\nJust a body\n"


def test_write_triage_block_with_all_defaults_deletes_the_key() -> None:
    with_block = write_triage_block(NOTE, TriageBlock(promising=True))

    result = write_triage_block(with_block, TriageBlock())

    assert result == NOTE
    assert read_triage_block(result) is None


def test_read_triage_block_returns_none_without_triage_key() -> None:
    assert read_triage_block(NOTE) is None


def test_read_triage_block_treats_null_triage_value_as_defaults() -> None:
    text = "---\ntitle: T\ntriage:\n---\nBody\n"

    assert read_triage_block(text) == TriageBlock()


def test_read_triage_block_accepts_hand_edited_unquoted_dates() -> None:
    text = (
        "---\n"
        "triage:\n"
        "  decision: archive\n"
        "  status: applied\n"
        "  decided: 2026-07-01\n"
        "  applied: 2026-07-12\n"
        "---\n"
        "Body\n"
    )

    block = read_triage_block(text)

    assert block is not None
    assert block.decided == "2026-07-01"
    assert block.applied == "2026-07-12"


def test_set_frontmatter_list_renders_quoted_wikilinks() -> None:
    values = [
        "[[resources/permanent-notes/Spacing beats cramming]]",
        "[[resources/permanent-notes/Testing is learning]]",
    ]

    result = set_frontmatter_list(NOTE, "permanent_notes", values)

    assert read_frontmatter(result)["permanent_notes"] == values
    yaml_text, _ = split_frontmatter(result)
    assert yaml_text is not None
    assert '  - "[[resources/permanent-notes/Spacing beats cramming]]"' in yaml_text


def test_set_frontmatter_list_with_empty_values_writes_empty_list() -> None:
    result = set_frontmatter_list(NOTE, "permanent_notes", [])

    assert read_frontmatter(result)["permanent_notes"] == []
