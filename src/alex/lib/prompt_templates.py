"""Versioned prompt templates stored as markdown files in alex.prompts.

Each prompt lives in its own directory: the directory name is the prompt
name, every ``vNNN.md`` file is one immutable version, and ``active.txt``
names the version the pipeline uses by default. Templates use
``{{placeholder}}`` substitution so literal braces in prompt prose never
collide with formatting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

PROMPTS_PACKAGE = "alex.prompts"
ACTIVE_VERSION_FILENAME = "active.txt"
PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")
VERSION_PATTERN = re.compile(r"^v\d{3,}$")


class PromptTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    text: str

    def placeholders(self) -> frozenset[str]:
        return frozenset(PLACEHOLDER_PATTERN.findall(self.text))

    def render(self, **values: str) -> str:
        expected = self.placeholders()
        provided = frozenset(values)
        missing = sorted(expected - provided)
        if missing:
            raise PromptTemplateError(
                f"Prompt {self.name}/{self.version} is missing values for "
                f"placeholders: {', '.join(missing)}"
            )
        unknown = sorted(provided - expected)
        if unknown:
            raise PromptTemplateError(
                f"Prompt {self.name}/{self.version} has no placeholders named: "
                f"{', '.join(unknown)}"
            )
        return PLACEHOLDER_PATTERN.sub(lambda match: values[match.group(1)], self.text)


def prompts_root() -> Traversable:
    return files(PROMPTS_PACKAGE)


def prompt_dir(name: str, *, root: Traversable | None = None) -> Traversable:
    directory = (root if root is not None else prompts_root()) / name
    if not directory.is_dir():
        raise PromptTemplateError(f"Unknown prompt: {name}")
    return directory


def writable_prompt_dir(name: str, *, root: Traversable | None = None) -> Path:
    directory = prompt_dir(name, root=root)
    if not isinstance(directory, Path):
        raise PromptTemplateError(
            f"Prompt directory for {name} is not writable; new prompt versions "
            "can only be written in a source checkout."
        )
    # The packaged prompts resolve to a real Path even when installed into
    # site-packages; only a source checkout (src/alex/prompts under a repo
    # root with pyproject.toml) may be mutated.
    if root is None and not in_source_checkout(directory):
        raise PromptTemplateError(
            f"Refusing to write prompt versions outside a source checkout: {directory}"
        )
    return directory


def in_source_checkout(prompt_directory: Path) -> bool:
    # <repo>/src/alex/prompts/<name> -> the repo root is parents[3].
    parents = prompt_directory.resolve().parents
    return len(parents) >= 4 and (parents[3] / "pyproject.toml").is_file()


def list_versions(name: str, *, root: Traversable | None = None) -> tuple[str, ...]:
    directory = prompt_dir(name, root=root)
    versions = [
        entry.name.removesuffix(".md")
        for entry in directory.iterdir()
        if entry.is_file()
        and entry.name.endswith(".md")
        and VERSION_PATTERN.match(entry.name.removesuffix(".md"))
    ]
    if not versions:
        raise PromptTemplateError(f"Prompt {name} has no versions.")
    return tuple(sorted(versions, key=version_sort_key))


def version_sort_key(version: str) -> int:
    return int(version.removeprefix("v"))


def active_version(name: str, *, root: Traversable | None = None) -> str:
    directory = prompt_dir(name, root=root)
    marker = directory / ACTIVE_VERSION_FILENAME
    try:
        version = marker.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        raise PromptTemplateError(
            f"Prompt {name} has no {ACTIVE_VERSION_FILENAME}."
        ) from error
    if version not in list_versions(name, root=root):
        raise PromptTemplateError(
            f"Prompt {name} marks {version!r} active, but {version}.md is missing."
        )
    return version


def load_prompt(
    name: str,
    *,
    version: str | None = None,
    root: Traversable | None = None,
) -> PromptTemplate:
    resolved = version if version is not None else active_version(name, root=root)
    template_file = prompt_dir(name, root=root) / f"{resolved}.md"
    try:
        text = template_file.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise PromptTemplateError(
            f"Prompt {name} has no version {resolved}."
        ) from error
    return PromptTemplate(name=name, version=resolved, text=text)


def next_version(name: str, *, root: Traversable | None = None) -> str:
    latest = list_versions(name, root=root)[-1]
    return f"v{version_sort_key(latest) + 1:03d}"


def save_prompt_version(
    name: str,
    *,
    version: str,
    text: str,
    root: Traversable | None = None,
) -> Path:
    template_file = writable_prompt_dir(name, root=root) / f"{version}.md"
    if template_file.exists():
        raise PromptTemplateError(f"Prompt version already exists: {template_file}")
    template_file.write_text(text, encoding="utf-8")
    return template_file


def set_active_version(
    name: str,
    version: str,
    *,
    root: Traversable | None = None,
) -> None:
    if version not in list_versions(name, root=root):
        raise PromptTemplateError(
            f"Cannot activate {version}: prompt {name} has no such version."
        )
    marker = writable_prompt_dir(name, root=root) / ACTIVE_VERSION_FILENAME
    marker.write_text(f"{version}\n", encoding="utf-8")
