"""Surgical YAML frontmatter editing that preserves every untouched byte.

Vault notes carry state from several pipelines (workflow blocks, tags,
comments, hand-written keys). Editing the triage block must never reformat
or reorder anything else, so edits are line-based splices instead of a
parse/re-dump roundtrip.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import yaml

from alex.lib.triage.models import TriageBlock


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter yaml without fences, body after the closing fence)."""
    if not text.startswith("---\n"):
        return None, text
    close = text.find("\n---\n", 3)
    if close >= 0:
        return text[4:close], text[close + 5 :]
    if text.endswith("\n---"):
        return text[4:-4], ""
    return None, text


def assemble_frontmatter(yaml_text: str, body: str) -> str:
    stripped = yaml_text.rstrip("\n")
    return f"---\n{stripped}\n---\n{body}"


def read_frontmatter(text: str) -> dict[str, Any]:
    yaml_text, _ = split_frontmatter(text)
    if yaml_text is None:
        return {}
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def replace_top_level_key(text: str, key: str, yaml_block: str | None) -> str:
    """Remove the top-level `key:` entry, then append yaml_block at the end.

    yaml_block is the full entry starting with f"{key}:", 2-space indented,
    no trailing newline; None deletes the key. Every other line survives
    byte-identical, comments included. Creates a frontmatter block when the
    file has none.
    """
    yaml_text, body = split_frontmatter(text)
    if yaml_text is None:
        if yaml_block is None:
            return text
        return assemble_frontmatter(yaml_block, text)
    kept: list[str] = []
    in_entry = False
    for line in yaml_text.split("\n"):
        if in_entry and _is_entry_continuation(line):
            continue
        in_entry = False
        if line.startswith(f"{key}:"):
            in_entry = True
            continue
        kept.append(line)
    if yaml_block is not None:
        kept.append(yaml_block)
    return assemble_frontmatter("\n".join(kept), body)


def _is_entry_continuation(line: str) -> bool:
    return bool(line) and (line[0] in " \t" or line.startswith("- "))


def read_triage_block(text: str) -> TriageBlock | None:
    frontmatter = read_frontmatter(text)
    if "triage" not in frontmatter:
        return None
    raw = frontmatter["triage"]
    if raw is None:
        # A bare `triage:` line (hand edit, or a stray data-free block)
        # parses as YAML null; treat it as an all-default block.
        return TriageBlock()
    if isinstance(raw, dict):
        # yaml parses bare dates like `decided: 2026-07-12` into date
        # objects; the model stores plain strings.
        raw = {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in raw.items()
        }
    return TriageBlock.model_validate(raw)


def write_triage_block(text: str, block: TriageBlock) -> str:
    lines = ["triage:"]
    if block.decision is not None:
        lines.append(f"  decision: {block.decision}")
    if block.target:
        lines.append(f"  target: {block.target}")
    if block.promising:
        lines.append("  promising: true")
    if block.status is not None:
        lines.append(f"  status: {block.status}")
    if block.decided:
        lines.append(f"  decided: {block.decided}")
    if block.applied:
        lines.append(f"  applied: {block.applied}")
    if len(lines) == 1:
        # An all-default block would serialize as a bare `triage:` key
        # (YAML null); delete the key instead of writing a data-free block.
        return replace_top_level_key(text, "triage", None)
    return replace_top_level_key(text, "triage", "\n".join(lines))


def set_frontmatter_list(text: str, key: str, values: list[str]) -> str:
    if not values:
        return replace_top_level_key(text, key, f"{key}: []")
    lines = [f"{key}:"]
    lines.extend(f"  - {json.dumps(value)}" for value in values)
    return replace_top_level_key(text, key, "\n".join(lines))
