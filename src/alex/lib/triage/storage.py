"""Atomic writes and YAML persistence for triage state files."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def read_yaml_model[T: BaseModel](path: Path, model_type: type[T]) -> T | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return model_type.model_validate(yaml.safe_load(raw))
    except (yaml.YAMLError, ValidationError):
        # Corrupt or stale cache files are rebuilt, never fatal.
        return None


def write_yaml_model(path: Path, model: BaseModel) -> None:
    dumped = yaml.safe_dump(
        model.model_dump(mode="json"), sort_keys=False, allow_unicode=True
    )
    atomic_write_text(path, dumped)
