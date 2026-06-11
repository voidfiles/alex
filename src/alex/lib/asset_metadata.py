"""The metadata.json contract shared by every asset-producing command."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class AssetMetadata(BaseModel):
    title: str
    authors: tuple[str, ...] = ()
    source_format: str | None = None
    source_file: str | None = None
    full_markdown: str | None = None
    headers_file: str | None = None
    chapter_level: int | None = None
    chunks_dir: str | None = None

    def write(self, path: Path) -> None:
        payload = self.model_dump(mode="json", exclude_none=True)
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
