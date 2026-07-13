"""Filesystem layout for triage state inside and outside the vault."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TriagePaths:
    vault_root: Path

    @property
    def state_dir(self) -> Path:
        return self.vault_root / ".claude" / "triage"

    @property
    def inventory_path(self) -> Path:
        return self.state_dir / "inventory.yaml"

    @property
    def cluster_map_path(self) -> Path:
        return self.state_dir / "cluster-map.yaml"

    @property
    def catalog_path(self) -> Path:
        return self.state_dir / "catalog.yaml"

    @property
    def embeddings_cache_path(self) -> Path:
        return self.state_dir / "embeddings.jsonl"

    @property
    def proposals_dir(self) -> Path:
        return self.state_dir / "proposals"

    @property
    def session_path(self) -> Path:
        return self.state_dir / "session.yaml"

    @property
    def pending_areas_path(self) -> Path:
        return self.state_dir / "pending-areas.yaml"

    @property
    def project_dir(self) -> Path:
        return self.vault_root / "projects" / "vault-triage"

    @property
    def ledger_path(self) -> Path:
        return self.project_dir / "ledger.jsonl"

    @property
    def rubric_path(self) -> Path:
        return self.project_dir / "rubric.md"

    @property
    def processing_log_path(self) -> Path:
        return self.vault_root / "_meta" / "processing-log.md"

    @property
    def lock_path(self) -> Path:
        key = str(self.vault_root.resolve()).encode()
        digest = hashlib.sha256(key).hexdigest()[:12]
        return Path.home() / ".cache" / "alex" / f"triage-{digest}.lock"

    def proposals_path(self, batch_id: int, rubric_version: int) -> Path:
        return self.proposals_dir / (
            f"batch-{batch_id:03d}.rubric-v{rubric_version:02d}.yaml"
        )
