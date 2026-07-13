"""Pydantic models for the vault triage pipeline state."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Population = Literal["root", "clippings", "meetings", "weekly"]
ProposalDecision = Literal["area", "resource", "archive", "trash", "skip"]
FilingDecision = Literal["area", "resource", "archive", "trash"]
Confidence = Literal["high", "medium", "low"]
LedgerEventKind = Literal[
    "approve", "reject", "edit", "repropose", "atomic_approve", "atomic_revise"
]


class NoteEvidence(BaseModel):
    path: str  # vault-relative posix path
    title: str
    population: Population
    tags: list[str] = Field(default_factory=list)
    wikilinks: list[str] = Field(default_factory=list)
    snippet: str = ""
    has_highlights: bool = False
    mtime: float = 0.0
    word_count: int = 0


class Inventory(BaseModel):
    generated: str  # ISO timestamp
    notes: list[NoteEvidence] = Field(default_factory=list)


class Cluster(BaseModel):
    cluster_id: int
    label: str = ""
    note_paths: list[str] = Field(default_factory=list)


class Batch(BaseModel):
    batch_id: int
    label: str = ""  # label of the dominant cluster; "misc" for pooled singletons
    note_paths: list[str] = Field(default_factory=list)


class ClusterMap(BaseModel):
    generated: str
    clusters: list[Cluster] = Field(default_factory=list)
    batches: list[Batch] = Field(default_factory=list)


class NewAreaProposal(BaseModel):
    slug: str
    name: str
    description: str


class Proposal(BaseModel):
    note_path: str
    decision: ProposalDecision
    target: str = ""  # area slug | resource topic | archives subfolder
    confidence: Confidence = "low"
    why: str = ""
    alternatives: list[str] = Field(default_factory=list)
    new_area: NewAreaProposal | None = None
    needs_manual: bool = False


class BatchProposals(BaseModel):
    batch_id: int
    rubric_version: int
    proposals: list[Proposal] = Field(default_factory=list)


class TriageBlock(BaseModel):
    decision: FilingDecision | None = None
    target: str = ""
    promising: bool = False
    status: Literal["decided", "applied"] | None = None
    decided: str = ""  # YYYY-MM-DD
    applied: str = ""


class LedgerEvent(BaseModel):
    ts: str
    note: str
    batch: int
    rubric_version: int
    event: LedgerEventKind
    proposal: dict[str, Any] = Field(default_factory=dict)
    correction: dict[str, Any] | None = None
    reason: str = ""


class Rubric(BaseModel):
    version: int
    text: str  # full markdown body below the frontmatter


class CatalogEntry(BaseModel):
    slug: str
    name: str
    description: str = ""
    evidence: list[str] = Field(default_factory=list)


class Catalog(BaseModel):
    areas: list[CatalogEntry] = Field(default_factory=list)
    resource_topics: list[str] = Field(default_factory=list)
    source_mtimes: dict[str, float] = Field(default_factory=dict)


class AtomicDraft(BaseModel):
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)  # existing note paths, no [[]]
    source_path: str


class PlannedMove(BaseModel):
    note_path: str
    destination: str  # vault-relative posix
    decision: FilingDecision
    target: str


class ApplyPlan(BaseModel):
    moves: list[PlannedMove] = Field(default_factory=list)
    new_areas: list[NewAreaProposal] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)  # human-readable reasons


class MoveResult(BaseModel):
    note_path: str
    destination: str
    status: Literal["moved", "collision_renamed", "failed", "dry_run"]
    links_rewritten: int = 0
    error: str = ""


class ApplyReport(BaseModel):
    results: list[MoveResult] = Field(default_factory=list)
    areas_created: list[str] = Field(default_factory=list)


class PendingDecision(BaseModel):
    proposal: Proposal
    action: LedgerEventKind
    promising: bool = False
    reason: str = ""


class SessionState(BaseModel):
    batch_id: int
    pending: dict[str, PendingDecision] = Field(default_factory=dict)
    corrections: list[str] = Field(default_factory=list)
    extra_events: list[LedgerEvent] = Field(default_factory=list)


class PendingAreas(BaseModel):
    areas: list[NewAreaProposal] = Field(default_factory=list)
