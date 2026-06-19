from pathlib import Path

import pytest

from alex.lib.prompt_templates import (
    PromptTemplate,
    PromptTemplateError,
    active_version,
    in_source_checkout,
    list_versions,
    load_prompt,
    writable_prompt_dir,
)
from alex.lib.summarize import SUMMARY_PROMPT_NAMES, SummarizationError, SummaryPrompts


def write_prompt_version(
    root: Path,
    name: str,
    version: str,
    text: str,
    *,
    active: str | None = None,
) -> None:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{version}.md").write_text(text, encoding="utf-8")
    if active is not None:
        (directory / "active.txt").write_text(f"{active}\n", encoding="utf-8")


def test_load_prompt_resolves_active_version(tmp_path: Path) -> None:
    write_prompt_version(tmp_path, "greeting", "v001", "Hello {{name}}.")
    write_prompt_version(tmp_path, "greeting", "v002", "Hi {{name}}!", active="v002")

    template = load_prompt("greeting", root=tmp_path)

    assert template == PromptTemplate(
        name="greeting", version="v002", text="Hi {{name}}!"
    )


def test_load_prompt_with_explicit_version_ignores_active(tmp_path: Path) -> None:
    write_prompt_version(tmp_path, "greeting", "v001", "Hello {{name}}.")
    write_prompt_version(tmp_path, "greeting", "v002", "Hi {{name}}!", active="v002")

    template = load_prompt("greeting", version="v001", root=tmp_path)

    assert template.version == "v001"
    assert template.text == "Hello {{name}}."


def test_load_prompt_rejects_unknown_name_and_version(tmp_path: Path) -> None:
    write_prompt_version(tmp_path, "greeting", "v001", "Hello.", active="v001")

    with pytest.raises(PromptTemplateError, match="Unknown prompt: missing"):
        load_prompt("missing", root=tmp_path)
    with pytest.raises(PromptTemplateError, match="no version v009"):
        load_prompt("greeting", version="v009", root=tmp_path)


def test_active_version_requires_marker_pointing_at_real_version(
    tmp_path: Path,
) -> None:
    write_prompt_version(tmp_path, "greeting", "v001", "Hello.")

    with pytest.raises(PromptTemplateError, match=r"active\.txt"):
        active_version("greeting", root=tmp_path)

    (tmp_path / "greeting" / "active.txt").write_text("v404\n", encoding="utf-8")

    with pytest.raises(PromptTemplateError, match="v404"):
        active_version("greeting", root=tmp_path)


def test_list_versions_orders_numerically(tmp_path: Path) -> None:
    for version in ("v010", "v002", "v001"):
        write_prompt_version(tmp_path, "greeting", version, "Hello.")
    (tmp_path / "greeting" / "notes.md").write_text("not a version", encoding="utf-8")

    assert list_versions("greeting", root=tmp_path) == ("v001", "v002", "v010")


def test_list_versions_requires_at_least_one_version(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    with pytest.raises(PromptTemplateError, match="no versions"):
        list_versions("empty", root=tmp_path)


def test_render_substitutes_all_placeholders() -> None:
    template = PromptTemplate(
        name="greeting",
        version="v001",
        text="Hello {{name}}, today is {{day}}. Bye {{name}}.",
    )

    assert template.placeholders() == frozenset({"name", "day"})
    assert (
        template.render(name="Ada", day="Tuesday")
        == "Hello Ada, today is Tuesday. Bye Ada."
    )


def test_render_keeps_replacement_values_verbatim() -> None:
    template = PromptTemplate(name="t", version="v001", text="X {{value}} Y")

    rendered = template.render(value=r"back\slash {curly} {{nested}}")

    assert rendered == r"X back\slash {curly} {{nested}} Y"


def test_render_rejects_missing_and_unknown_values() -> None:
    template = PromptTemplate(name="t", version="v001", text="Hello {{name}}.")

    with pytest.raises(PromptTemplateError, match=r"missing values.*name"):
        template.render()
    with pytest.raises(PromptTemplateError, match="no placeholders named: extra"):
        template.render(name="Ada", extra="nope")


def test_writable_prompt_dir_returns_source_checkout_path() -> None:
    directory = writable_prompt_dir("chunk_summary")

    assert directory.is_dir()
    assert (directory / "v001.md").is_file()


def test_in_source_checkout_distinguishes_repo_from_site_packages(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "repo" / "src" / "alex" / "prompts" / "chunk_summary"
    checkout.mkdir(parents=True)
    (tmp_path / "repo" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    installed = (
        tmp_path / "venv" / "site-packages" / "alex" / "prompts" / "chunk_summary"
    )
    installed.mkdir(parents=True)

    assert in_source_checkout(checkout)
    assert not in_source_checkout(installed)


def test_packaged_summary_prompts_ship_v001_as_active() -> None:
    for name in SUMMARY_PROMPT_NAMES:
        assert active_version(name) == "v001"
        assert "v001" in list_versions(name)


def test_summary_prompts_load_uses_active_versions() -> None:
    prompts = SummaryPrompts.load()

    assert prompts.chunk_summary.placeholders() == frozenset(
        {"title", "authors", "headers", "chunk"}
    )
    assert prompts.chunk_summary_with_graph.placeholders() == frozenset(
        {"title", "authors", "headers", "chunk", "selected_chunk_graph"}
    )
    assert prompts.compression_summary.placeholders() == frozenset(
        {"title", "authors", "content"}
    )
    assert prompts.final_summary.placeholders() == frozenset(
        {"title", "authors", "section_summaries", "chunk_reference_list"}
    )


def test_summary_prompts_load_accepts_known_overrides_only() -> None:
    prompts = SummaryPrompts.load(overrides={"chunk_summary": "v001"})

    assert prompts.chunk_summary.version == "v001"

    with pytest.raises(SummarizationError, match=r"Unknown summary prompts.*nope"):
        SummaryPrompts.load(overrides={"nope": "v001"})
