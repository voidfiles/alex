"""Production prompt registry for the summarization pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources.abc import Traversable

from alex.lib.prompt_templates import PromptTemplate, load_prompt

SUMMARY_PROMPT_NAMES = (
    "chunk_summary",
    "chunk_summary_with_graph",
    "compression_summary",
    "final_summary",
)
GRAPH_PROMPT_NAMES = (
    "source_claim_extraction",
    "graph_guided_summary",
)
MERGE_PROMPT_NAMES = (
    "merged_summary",
    "merged_summary_repair",
    "merged_summary_faithfulness_filter",
)
PRODUCTION_PROMPT_NAMES = (
    *SUMMARY_PROMPT_NAMES,
    *GRAPH_PROMPT_NAMES,
    *MERGE_PROMPT_NAMES,
)
FIXED_EVAL_PROMPT_NAMES = (
    "fact_extraction",
    "fact_coverage_judge",
    "claim_extraction",
    "claim_verification",
    "rubric_judge",
    "prompt_critic",
)

PRODUCTION_PROMPT_ROLES = {
    "chunk_summary": "Summarizes one source chunk without graph context.",
    "chunk_summary_with_graph": (
        "Summarizes one source chunk with its selected claim graph."
    ),
    "compression_summary": "Consolidates many chunk summaries into context budget.",
    "final_summary": "Synthesizes consolidated section summaries into final output.",
    "source_claim_extraction": "Extracts source-grounded graph items from sections.",
    "graph_guided_summary": "Creates a graph-only summary from selected graph items.",
    "merged_summary": "Merges standard and graph-guided summary drafts.",
    "merged_summary_repair": "Restores graph-supported facts lost during merging.",
    "merged_summary_faithfulness_filter": (
        "Removes or rewrites unsupported claims before final scoring."
    ),
}


@dataclass(frozen=True)
class MergePrompts:
    merged_summary: PromptTemplate
    merged_summary_repair: PromptTemplate
    merged_summary_faithfulness_filter: PromptTemplate

    @classmethod
    def load(
        cls,
        overrides: Mapping[str, str] | None = None,
        *,
        root: Traversable | None = None,
    ) -> MergePrompts:
        versions = dict(overrides or {})
        return cls(
            merged_summary=load_prompt(
                "merged_summary", version=versions.get("merged_summary"), root=root
            ),
            merged_summary_repair=load_prompt(
                "merged_summary_repair",
                version=versions.get("merged_summary_repair"),
                root=root,
            ),
            merged_summary_faithfulness_filter=load_prompt(
                "merged_summary_faithfulness_filter",
                version=versions.get("merged_summary_faithfulness_filter"),
                root=root,
            ),
        )


def unknown_production_overrides(overrides: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(sorted(set(overrides) - set(PRODUCTION_PROMPT_NAMES)))


def production_prompt_versions(
    prompts: Mapping[str, PromptTemplate],
) -> dict[str, str]:
    return {
        name: prompts[name].version
        for name in PRODUCTION_PROMPT_NAMES
        if name in prompts
    }


def load_production_prompt_map(
    overrides: Mapping[str, str] | None = None,
    *,
    root: Traversable | None = None,
) -> dict[str, PromptTemplate]:
    versions = dict(overrides or {})
    unknown = unknown_production_overrides(versions)
    if unknown:
        raise ValueError(f"Unknown production prompts: {', '.join(unknown)}")
    return {
        name: load_prompt(name, version=versions.get(name), root=root)
        for name in PRODUCTION_PROMPT_NAMES
    }
