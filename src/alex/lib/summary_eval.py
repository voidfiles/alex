"""Blended scoring of summary quality over a small eval corpus.

Each document runs through the same pipeline as ``alex summary``, then the
resulting summary is graded four ways:

    coverage      did the summary include the document's salient facts?
    faithfulness  is every claim in the summary supported by the source?
    density       covered facts per hundred words of summary
    rubric        LLM-judged coherence / organization / readability

Salient facts are extracted once per (document, extractor prompt version)
and cached on disk, so paired evals of two prompt candidates always grade
against the same answer key.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Protocol

from alex.lib.chunking import ChunkSettings
from alex.lib.llm import (
    Completer,
    Embedder,
    LlmError,
    ordered_parallel_map,
    resolve_eval_judge_model,
    resolve_fact_extractor_model,
    resolve_summary_max_workers,
)
from alex.lib.markdown_structure import (
    MarkdownHeader,
    MarkdownStructureError,
    infer_chapter_level,
    parse_markdown_headers,
    split_chapters,
)
from alex.lib.production_prompts import MergePrompts
from alex.lib.prompt_templates import PromptTemplate, load_prompt
from alex.lib.summarize import SummaryPrompts, SummarySettings
from alex.lib.summary_assets import SummaryAssetConfig, process_summary_asset

EVAL_PROMPT_NAMES = (
    "fact_extraction",
    "fact_coverage_judge",
    "claim_extraction",
    "claim_verification",
    "rubric_judge",
)
JUDGE_BATCH_SIZE = 10

# A sink for human-readable progress lines. Scoring one document is a handful
# of sequential LLM calls, so callers inject a reporter to watch the work
# stream by instead of staring at a silent terminal.
Progress = Callable[[str], None]


def no_progress(_: str) -> None:
    pass


class EvalError(ValueError):
    pass


class EvalJudgeError(EvalError):
    pass


@dataclass(frozen=True)
class EvalSettings:
    judge_model: str = field(default_factory=resolve_eval_judge_model)
    fact_extractor_model: str = field(default_factory=resolve_fact_extractor_model)
    judge_max_tokens: int = 8_192
    extractor_max_tokens: int = 8_192
    coverage_weight: float = 0.45
    faithfulness_weight: float = 0.35
    density_weight: float = 0.10
    rubric_weight: float = 0.10
    # A detailed, information-dense summary lands around one salient fact
    # per hundred words; density saturates at this rate.
    target_facts_per_100_words: float = 1.0
    max_workers: int = field(default_factory=resolve_summary_max_workers)


@dataclass(frozen=True)
class EvalConfig:
    corpus_dir: Path
    facts_dir: Path
    runs_dir: Path
    settings: EvalSettings = field(default_factory=EvalSettings)
    summary: SummarySettings = field(default_factory=SummarySettings)
    chunking: ChunkSettings = field(default_factory=ChunkSettings)


def eval_config_for(evals_dir: Path) -> EvalConfig:
    return EvalConfig(
        corpus_dir=evals_dir / "corpus",
        facts_dir=evals_dir / "facts",
        runs_dir=evals_dir / "runs",
    )


@dataclass(frozen=True)
class EvalPrompts:
    fact_extraction: PromptTemplate
    fact_coverage_judge: PromptTemplate
    claim_extraction: PromptTemplate
    claim_verification: PromptTemplate
    rubric_judge: PromptTemplate

    @classmethod
    def load(cls) -> EvalPrompts:
        return cls(
            fact_extraction=load_prompt("fact_extraction"),
            fact_coverage_judge=load_prompt("fact_coverage_judge"),
            claim_extraction=load_prompt("claim_extraction"),
            claim_verification=load_prompt("claim_verification"),
            rubric_judge=load_prompt("rubric_judge"),
        )


@dataclass(frozen=True)
class RubricResult:
    coherence: int
    organization: int
    readability: int
    notes: str

    def normalized(self) -> float:
        mean = (self.coherence + self.organization + self.readability) / 3
        return (mean - 1) / 4


@dataclass(frozen=True)
class FactVerdict:
    fact: str
    covered: bool
    evidence: str


@dataclass(frozen=True)
class ClaimVerdict:
    claim: str
    supported: bool
    evidence: str
    status: Literal[
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "CONTRADICTED",
        "NOT_IN_SOURCE",
        "AMBIGUOUS",
    ] = "SUPPORTED"
    issue_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChunkGraphArtifact:
    chunk: str
    graph_json: str
    selected_subgraph_json: str
    selected_subgraph_markdown: str


@dataclass(frozen=True)
class SummaryGraphArtifacts:
    artifact_dir: str
    chunk_graphs_markdown: str
    chunk_graphs: tuple[ChunkGraphArtifact, ...]


@dataclass(frozen=True)
class GeneratedSummary:
    doc_name: str
    doc_text: str
    summary: str
    graph_artifacts: SummaryGraphArtifacts | None = None
    error: str | None = None


@dataclass(frozen=True)
class SummaryGeneration:
    text: str
    graph_artifacts: SummaryGraphArtifacts | None = None


@dataclass(frozen=True)
class DocScore:
    doc_name: str
    coverage: float
    faithfulness: float
    density: float
    rubric: float
    blended: float
    missed_facts: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    rubric_notes: str
    summary: str
    fact_verdicts: tuple[FactVerdict, ...] = ()
    claim_verdicts: tuple[ClaimVerdict, ...] = ()
    error: str | None = None


def doc_score_line(score: DocScore) -> str:
    if score.error is not None:
        return f"{score.doc_name}: FAILED ({score.error})"
    return (
        f"{score.doc_name}: blended={score.blended:.3f} "
        f"coverage={score.coverage:.2f} faithfulness={score.faithfulness:.2f} "
        f"density={score.density:.2f} rubric={score.rubric:.2f}"
    )


@dataclass(frozen=True)
class EvalRun:
    run_id: str
    prompt_versions: dict[str, str]
    judge_model: str
    fact_extractor_model: str
    summary_fast_model: str
    summary_final_model: str
    doc_scores: tuple[DocScore, ...]
    mean_blended: float
    generated_summaries: tuple[GeneratedSummary, ...] = ()


class SummaryEvaluator(Protocol):
    def evaluate(
        self, *, prompts: SummaryPrompts, run_id: str, progress: Progress = no_progress
    ) -> EvalRun: ...

    def rescore(
        self,
        *,
        summaries: Sequence[GeneratedSummary],
        prompt_versions: dict[str, str],
        run_id: str,
        progress: Progress = no_progress,
    ) -> EvalRun: ...


@dataclass(frozen=True)
class PipelineSummaryEvaluator:
    config: EvalConfig
    completer: Completer
    embedder: Embedder
    doc_names: tuple[str, ...] | None = None

    def evaluate(
        self, *, prompts: SummaryPrompts, run_id: str, progress: Progress = no_progress
    ) -> EvalRun:
        docs = corpus_docs(self.config.corpus_dir, self.doc_names)
        progress(f"loaded {len(docs)} eval document(s) from {self.config.corpus_dir}")
        summaries: list[GeneratedSummary] = []
        graph_artifacts_root = self.config.runs_dir / run_id / "graphs"
        for index, doc_path in enumerate(docs, 1):
            progress(f"summarizing ({index}/{len(docs)}) {doc_path.name}")
            try:
                progress(f"  reading source: {doc_path}")
                doc_text = doc_path.read_text(encoding="utf-8")
                progress(
                    f"  source size: {len(doc_text.split())} words, "
                    f"{len(doc_text)} chars"
                )
                progress("  running summary pipeline")
                summary = generate_summary(
                    doc_path=doc_path,
                    prompts=prompts,
                    config=self.config,
                    completer=self.completer,
                    embedder=self.embedder,
                    graph_output_dir=graph_artifacts_root / doc_path.stem,
                )
                if summary.graph_artifacts is not None:
                    progress(
                        "  chunk graphs: "
                        f"{len(summary.graph_artifacts.chunk_graphs)} persisted to "
                        f"{summary.graph_artifacts.chunk_graphs_markdown}"
                    )
                progress(f"  summary complete: {len(summary.text.split())} words")
                summaries.append(
                    GeneratedSummary(
                        doc_name=doc_path.name,
                        doc_text=doc_text,
                        summary=summary.text,
                        graph_artifacts=summary.graph_artifacts,
                    )
                )
            except (LlmError, OSError, ValueError) as error:
                progress(f"  summarizing failed: {error}")
                summaries.append(
                    GeneratedSummary(
                        doc_name=doc_path.name,
                        doc_text="",
                        summary="",
                        error=str(error),
                    )
                )
        return self.rescore(
            summaries=tuple(summaries),
            prompt_versions=summary_prompt_versions(
                prompts=prompts,
                overrides=self.config.summary.prompt_overrides,
            ),
            run_id=run_id,
            progress=progress,
        )

    def rescore(
        self,
        *,
        summaries: Sequence[GeneratedSummary],
        prompt_versions: dict[str, str],
        run_id: str,
        progress: Progress = no_progress,
    ) -> EvalRun:
        eval_prompts = EvalPrompts.load()
        scores: list[DocScore] = []
        for index, summary in enumerate(summaries, 1):
            progress(f"scoring ({index}/{len(summaries)}) {summary.doc_name}")
            if summary.error is not None:
                score = failed_doc_score(
                    doc_name=summary.doc_name,
                    error=EvalError(summary.error),
                )
            elif not summary.doc_text or not summary.summary:
                score = failed_doc_score(
                    doc_name=summary.doc_name,
                    error=EvalError("Pipeline produced no summary for this document."),
                )
            else:
                score = score_generated_summary(
                    generated=summary,
                    config=self.config,
                    eval_prompts=eval_prompts,
                    completer=self.completer,
                    progress=progress,
                )
            progress(doc_score_line(score))
            scores.append(score)
        run = EvalRun(
            run_id=run_id,
            prompt_versions=prompt_versions,
            judge_model=self.config.settings.judge_model,
            fact_extractor_model=self.config.settings.fact_extractor_model,
            summary_fast_model=self.config.summary.fast_model,
            summary_final_model=self.config.summary.final_model,
            doc_scores=tuple(scores),
            mean_blended=mean_blended(scores),
            generated_summaries=tuple(summaries),
        )
        write_run_artifact(run, runs_dir=self.config.runs_dir)
        return run


def corpus_docs(
    corpus_dir: Path,
    doc_names: Sequence[str] | None,
) -> tuple[Path, ...]:
    if not corpus_dir.is_dir():
        raise EvalError(f"Eval corpus directory not found: {corpus_dir}")
    if doc_names:
        paths = tuple(corpus_dir / name for name in doc_names)
        missing = [path.name for path in paths if not path.is_file()]
        if missing:
            raise EvalError(f"Corpus documents not found: {', '.join(missing)}")
        return paths
    paths = tuple(sorted(corpus_dir.glob("*.md")))
    if not paths:
        raise EvalError(f"No markdown documents in eval corpus: {corpus_dir}")
    return paths


def score_doc(
    *,
    doc_path: Path,
    prompts: SummaryPrompts,
    config: EvalConfig,
    eval_prompts: EvalPrompts,
    completer: Completer,
    embedder: Embedder,
) -> DocScore:
    try:
        doc_text = doc_path.read_text(encoding="utf-8")
        summary = generate_summary(
            doc_path=doc_path,
            prompts=prompts,
            config=config,
            completer=completer,
            embedder=embedder,
        ).text
    except (LlmError, OSError, ValueError) as error:
        return failed_doc_score(doc_name=doc_path.name, error=error)

    return score_generated_summary(
        generated=GeneratedSummary(
            doc_name=doc_path.name,
            doc_text=doc_text,
            summary=summary,
        ),
        config=config,
        eval_prompts=eval_prompts,
        completer=completer,
    )


def score_generated_summary(
    *,
    generated: GeneratedSummary,
    config: EvalConfig,
    eval_prompts: EvalPrompts,
    completer: Completer,
    progress: Progress = no_progress,
) -> DocScore:
    settings = config.settings
    try:
        doc_text = generated.doc_text
        summary = generated.summary
        progress("  facts: loading or extracting reference facts")
        facts = facts_for_doc(
            doc_text=doc_text,
            facts_dir=config.facts_dir,
            template=eval_prompts.fact_extraction,
            completer=completer,
            settings=settings,
            progress=progress,
        )
        progress(f"  facts: {len(facts)} reference facts")
        progress("  coverage: judging summary against reference facts")
        fact_verdicts = judge_fact_coverage(
            facts=facts,
            summary=summary,
            template=eval_prompts.fact_coverage_judge,
            completer=completer,
            settings=settings,
        )
        progress(
            "  coverage: "
            f"{sum(verdict.covered for verdict in fact_verdicts)}/{len(facts)} "
            "facts covered"
        )
        progress("  faithfulness: extracting summary claims")
        claims = extract_claims(
            summary=summary,
            template=eval_prompts.claim_extraction,
            completer=completer,
            settings=settings,
        )
        progress(f"  faithfulness: verifying {len(claims)} summary claims")
        claim_verdicts = verify_claims(
            doc_text=doc_text,
            claims=claims,
            template=eval_prompts.claim_verification,
            completer=completer,
            settings=settings,
        )
        progress(
            "  faithfulness: "
            f"{sum(verdict.supported for verdict in claim_verdicts)}/{len(claims)} "
            "claims supported"
        )
        progress("  rubric: judging coherence, organization, and readability")
        rubric = judge_rubric(
            summary=summary,
            template=eval_prompts.rubric_judge,
            completer=completer,
            settings=settings,
        )
        progress(
            "  rubric: "
            f"coherence={rubric.coherence}/5 "
            f"organization={rubric.organization}/5 "
            f"readability={rubric.readability}/5"
        )
    except (LlmError, OSError, ValueError) as error:
        progress(f"  scoring failed: {error}")
        return failed_doc_score(doc_name=generated.doc_name, error=error)

    covered_count = sum(verdict.covered for verdict in fact_verdicts)
    coverage = covered_count / len(facts)
    faithfulness = sum(verdict.supported for verdict in claim_verdicts) / len(claims)
    density = density_score(
        covered_count=covered_count,
        summary_word_count=len(summary.split()),
        settings=settings,
    )
    rubric_score = rubric.normalized()
    return DocScore(
        doc_name=generated.doc_name,
        coverage=coverage,
        faithfulness=faithfulness,
        density=density,
        rubric=rubric_score,
        blended=blended_score(
            coverage=coverage,
            faithfulness=faithfulness,
            density=density,
            rubric=rubric_score,
            settings=settings,
        ),
        missed_facts=tuple(
            verdict.fact for verdict in fact_verdicts if not verdict.covered
        ),
        unsupported_claims=tuple(
            verdict.claim for verdict in claim_verdicts if not verdict.supported
        ),
        rubric_notes=rubric.notes,
        summary=summary,
        fact_verdicts=fact_verdicts,
        claim_verdicts=claim_verdicts,
    )


def failed_doc_score(*, doc_name: str, error: Exception) -> DocScore:
    return DocScore(
        doc_name=doc_name,
        coverage=0.0,
        faithfulness=0.0,
        density=0.0,
        rubric=0.0,
        blended=0.0,
        missed_facts=(),
        unsupported_claims=(),
        rubric_notes="",
        summary="",
        error=str(error),
    )


def generate_summary(
    *,
    doc_path: Path,
    prompts: SummaryPrompts,
    config: EvalConfig,
    completer: Completer,
    embedder: Embedder,
    graph_output_dir: Path | None = None,
) -> SummaryGeneration:
    with tempfile.TemporaryDirectory(prefix="alex-eval-") as workspace:
        output = process_summary_asset(
            SummaryAssetConfig(
                source=doc_path,
                output_path=Path(workspace),
                force=True,
                summary=replace(config.summary, prompts=prompts, force=True),
                chunking=config.chunking,
            ),
            completer=completer,
            embedder=embedder,
        )
        if output.summary_path is None:
            raise EvalError("Pipeline produced no summary for this document.")
        graph_artifacts = persist_summary_graph_artifacts(
            source_dir=output.graph_artifact_dir,
            output_dir=graph_output_dir,
        )
        return SummaryGeneration(
            text=output.summary_path.read_text(encoding="utf-8"),
            graph_artifacts=graph_artifacts,
        )


def persist_summary_graph_artifacts(
    *,
    source_dir: Path | None,
    output_dir: Path | None,
) -> SummaryGraphArtifacts | None:
    if source_dir is None or output_dir is None or not source_dir.is_dir():
        return None
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, output_dir)
    return write_chunk_graphs_index(output_dir)


def write_chunk_graphs_index(artifact_dir: Path) -> SummaryGraphArtifacts:
    chunks_dir = artifact_dir / "chunks"
    chunk_graphs: list[ChunkGraphArtifact] = []
    sections = ["# Chunk Graphs", ""]
    if chunks_dir.is_dir():
        for chunk_dir in sorted(path for path in chunks_dir.iterdir() if path.is_dir()):
            selected_markdown = chunk_dir / "selected_subgraph.md"
            graph_json = chunk_dir / "graph.json"
            selected_json = chunk_dir / "selected_subgraph.json"
            chunk_graphs.append(
                ChunkGraphArtifact(
                    chunk=chunk_dir.name,
                    graph_json=str(graph_json),
                    selected_subgraph_json=str(selected_json),
                    selected_subgraph_markdown=str(selected_markdown),
                )
            )
            sections.extend(
                [
                    f"## {chunk_dir.name}",
                    "",
                    f"- Graph JSON: `{graph_json}`",
                    f"- Selected subgraph JSON: `{selected_json}`",
                    f"- Selected subgraph Markdown: `{selected_markdown}`",
                    "",
                ]
            )
            if selected_markdown.is_file():
                sections.extend(
                    [
                        selected_markdown.read_text(encoding="utf-8").strip(),
                        "",
                    ]
                )
    if not chunk_graphs:
        sections.extend(["No chunk graph artifacts were produced.", ""])

    index_path = artifact_dir / "chunk_graphs.md"
    index_path.write_text("\n".join(sections).strip() + "\n", encoding="utf-8")
    return SummaryGraphArtifacts(
        artifact_dir=str(artifact_dir),
        chunk_graphs_markdown=str(index_path),
        chunk_graphs=tuple(chunk_graphs),
    )


def fact_cache_path(
    *,
    facts_dir: Path,
    doc_text: str,
    extractor_model: str,
    extractor_version: str,
) -> Path:
    digest = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()[:12]
    model_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", extractor_model)
    return facts_dir / f"{digest}.{model_slug}.{extractor_version}.json"


def facts_for_doc(
    *,
    doc_text: str,
    facts_dir: Path,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
    progress: Progress = no_progress,
) -> tuple[str, ...]:
    cache_path = fact_cache_path(
        facts_dir=facts_dir,
        doc_text=doc_text,
        extractor_model=settings.fact_extractor_model,
        extractor_version=template.version,
    )
    cached = read_facts_cache(cache_path)
    if cached is not None:
        progress(f"  facts cache hit: {cache_path}")
        return cached

    progress(f"  facts cache miss: {cache_path}")
    facts = extract_facts(
        doc_text=doc_text,
        template=template,
        completer=completer,
        settings=settings,
    )
    facts_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"facts": list(facts)}, indent=2) + "\n",
        encoding="utf-8",
    )
    progress(f"  facts cache wrote: {cache_path}")
    return facts


def read_facts_cache(cache_path: Path) -> tuple[str, ...] | None:
    """Return cached facts, or None when absent or corrupt (re-extract)."""
    if not cache_path.is_file():
        return None
    try:
        payload = parse_json_payload(
            cache_path.read_text(encoding="utf-8"), step="Facts cache"
        )
        facts = string_list(payload, key="facts")
    except EvalJudgeError:
        return None
    return facts or None


def extract_facts(
    *,
    doc_text: str,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
) -> tuple[str, ...]:
    sections = fact_sections(doc_text)

    def run(section: FactSection) -> tuple[str, ...]:
        return extract_section_facts(
            section=section,
            template=template,
            completer=completer,
            settings=settings,
        )

    facts = dedupe_facts(
        round_robin_facts(
            ordered_parallel_map(sections, run, max_workers=settings.max_workers),
            limit=40,
        )
    )
    if not facts:
        raise EvalJudgeError("Fact extraction returned no facts.")
    return facts


@dataclass(frozen=True)
class FactSection:
    title: str
    text: str


def fact_sections(doc_text: str) -> tuple[FactSection, ...]:
    headers = parse_markdown_headers(doc_text)
    if not headers:
        return (FactSection(title="Full document", text=doc_text),)
    try:
        chapter_level = infer_chapter_level(headers="", markdown=doc_text)
        chapters = split_chapters(
            lines=doc_text.splitlines(),
            chapter_level=chapter_level,
        )
    except MarkdownStructureError:
        return (FactSection(title="Full document", text=doc_text),)
    if not chapters:
        return (FactSection(title="Full document", text=doc_text),)

    sections: list[FactSection] = []
    first_chapter_start = chapters[0].start_index
    preamble = "\n".join(doc_text.splitlines()[:first_chapter_start]).strip()
    if preamble:
        sections.append(FactSection(title="Document Preamble", text=preamble))

    header_by_line = {header.line_index: header for header in headers}
    for chapter in chapters:
        title = section_title(
            headers=headers,
            header=header_by_line.get(chapter.start_index),
        )
        sections.append(FactSection(title=title, text="\n".join(chapter.lines)))
    return tuple(sections)


def section_title(
    *,
    headers: tuple[MarkdownHeader, ...],
    header: MarkdownHeader | None,
) -> str:
    if header is None:
        return "Untitled section"
    parents = [
        candidate.title
        for candidate in headers
        if candidate.line_index < header.line_index and candidate.level < header.level
    ]
    if parents:
        return " > ".join((*parents, header.title))
    return header.title


def extract_section_facts(
    *,
    section: FactSection,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
) -> tuple[str, ...]:
    values = {
        "document": section.text,
        "section_title": section.title,
        "section_text": section.text,
    }
    payload = parse_json_payload(
        completer.complete(
            prompt=render_prompt_subset(template, values),
            model=settings.fact_extractor_model,
            max_tokens=settings.extractor_max_tokens,
        ),
        step="Fact extraction",
    )
    return string_list(payload, key="facts")


def round_robin_facts(
    fact_groups: Sequence[Sequence[str]],
    *,
    limit: int,
) -> tuple[str, ...]:
    selected: list[str] = []
    max_length = max((len(group) for group in fact_groups), default=0)
    for index in range(max_length):
        for group in fact_groups:
            if index < len(group):
                selected.append(group[index])
                if len(selected) >= limit:
                    return tuple(selected)
    return tuple(selected)


def summary_prompt_versions(
    *,
    prompts: SummaryPrompts,
    overrides: Mapping[str, str],
) -> dict[str, str]:
    from alex.lib.claim_graph import GraphPrompts

    graph_prompts = GraphPrompts.load(overrides=overrides)
    merge_prompts = MergePrompts.load(overrides=overrides)
    return {
        "chunk_summary": prompts.chunk_summary.version,
        "chunk_summary_with_graph": prompts.chunk_summary_with_graph.version,
        "compression_summary": prompts.compression_summary.version,
        "final_summary": prompts.final_summary.version,
        "source_claim_extraction": graph_prompts.source_claim_extraction.version,
        "graph_guided_summary": graph_prompts.graph_guided_summary.version,
        "merged_summary": merge_prompts.merged_summary.version,
        "merged_summary_repair": merge_prompts.merged_summary_repair.version,
        "merged_summary_faithfulness_filter": (
            merge_prompts.merged_summary_faithfulness_filter.version
        ),
    }


def dedupe_facts(facts: Sequence[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        normalized = normalize_fact(fact)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(fact.strip())
    return tuple(deduped)


def normalize_fact(fact: str) -> str:
    return re.sub(r"\s+", " ", fact.strip().casefold())


def render_prompt_subset(template: PromptTemplate, values: Mapping[str, str]) -> str:
    return template.render(
        **{name: values[name] for name in template.placeholders() if name in values}
    )


def judge_fact_coverage(
    *,
    facts: tuple[str, ...],
    summary: str,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
) -> tuple[FactVerdict, ...]:
    if len(facts) > JUDGE_BATCH_SIZE:
        batches = chunks(facts, JUDGE_BATCH_SIZE)

        def run(batch: tuple[str, ...]) -> tuple[FactVerdict, ...]:
            return judge_fact_coverage(
                facts=batch,
                summary=summary,
                template=template,
                completer=completer,
                settings=settings,
            )

        return tuple(
            verdict
            for batch_verdicts in ordered_parallel_map(
                batches,
                run,
                max_workers=settings.max_workers,
            )
            for verdict in batch_verdicts
        )

    payload = parse_json_payload(
        completer.complete(
            prompt=template.render(facts=numbered(facts), summary=summary),
            model=settings.judge_model,
            max_tokens=settings.judge_max_tokens,
        ),
        step="Fact coverage judge",
    )
    return fact_verdicts(payload, facts=facts)


def extract_claims(
    *,
    summary: str,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
) -> tuple[str, ...]:
    payload = parse_json_payload(
        completer.complete(
            prompt=template.render(summary=summary),
            model=settings.judge_model,
            max_tokens=settings.judge_max_tokens,
        ),
        step="Claim extraction",
    )
    claims = string_list(payload, key="claims")
    if not claims:
        raise EvalJudgeError("Claim extraction returned no claims.")
    return claims


def verify_claims(
    *,
    doc_text: str,
    claims: tuple[str, ...],
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
) -> tuple[ClaimVerdict, ...]:
    if len(claims) > JUDGE_BATCH_SIZE:
        batches = chunks(claims, JUDGE_BATCH_SIZE)

        def run(batch: tuple[str, ...]) -> tuple[ClaimVerdict, ...]:
            return verify_claims(
                doc_text=doc_text,
                claims=batch,
                template=template,
                completer=completer,
                settings=settings,
            )

        return tuple(
            verdict
            for batch_verdicts in ordered_parallel_map(
                batches,
                run,
                max_workers=settings.max_workers,
            )
            for verdict in batch_verdicts
        )

    payload = parse_json_payload(
        completer.complete(
            prompt=template.render(document=doc_text, claims=numbered(claims)),
            model=settings.judge_model,
            max_tokens=settings.judge_max_tokens,
        ),
        step="Claim verification",
    )
    return claim_verdicts(payload, claims=claims)


def chunks[T](items: Sequence[T], size: int) -> tuple[tuple[T, ...], ...]:
    return tuple(
        tuple(items[index : index + size]) for index in range(0, len(items), size)
    )


def judge_rubric(
    *,
    summary: str,
    template: PromptTemplate,
    completer: Completer,
    settings: EvalSettings,
) -> RubricResult:
    payload = parse_json_payload(
        completer.complete(
            prompt=template.render(summary=summary),
            model=settings.judge_model,
            max_tokens=settings.judge_max_tokens,
        ),
        step="Rubric judge",
    )
    if not isinstance(payload, dict):
        raise EvalJudgeError("Rubric judge did not return a JSON object.")
    notes = payload.get("notes", "")
    if not isinstance(notes, str):
        raise EvalJudgeError("Rubric notes must be a string.")
    return RubricResult(
        coherence=rubric_grade(payload, key="coherence"),
        organization=rubric_grade(payload, key="organization"),
        readability=rubric_grade(payload, key="readability"),
        notes=notes,
    )


def rubric_grade(payload: dict[str, Any], *, key: str) -> int:
    grade = payload.get(key)
    if isinstance(grade, bool) or not isinstance(grade, int) or not 1 <= grade <= 5:
        raise EvalJudgeError(f"Rubric grade {key!r} must be an integer from 1 to 5.")
    return grade


def density_score(
    *,
    covered_count: int,
    summary_word_count: int,
    settings: EvalSettings,
) -> float:
    facts_per_100_words = covered_count / max(summary_word_count, 1) * 100
    return min(1.0, facts_per_100_words / settings.target_facts_per_100_words)


def blended_score(
    *,
    coverage: float,
    faithfulness: float,
    density: float,
    rubric: float,
    settings: EvalSettings,
) -> float:
    return (
        settings.coverage_weight * coverage
        + settings.faithfulness_weight * faithfulness
        + settings.density_weight * density
        + settings.rubric_weight * rubric
    )


def mean_blended(scores: Sequence[DocScore]) -> float:
    scored = [score.blended for score in scores if score.error is None]
    if not scored:
        return 0.0
    return sum(scored) / len(scored)


def numbered(items: Sequence[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        lines = lines[1:-1]
    else:
        lines = lines[1:]
    return "\n".join(lines).strip()


def parse_json_payload(text: str, *, step: str) -> Any:
    cleaned = strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Models sometimes wrap the JSON in prose despite instructions; salvage
    # the outermost object before giving up.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise EvalJudgeError(f"{step} returned invalid JSON: {cleaned[:120]!r}")


def string_list(payload: Any, *, key: str) -> tuple[str, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise EvalJudgeError(f"Expected a JSON object with a {key!r} list.")
    items = payload[key]
    if not all(isinstance(item, str) for item in items):
        raise EvalJudgeError(f"Expected {key!r} to be a list of strings.")
    return tuple(items)


def bool_list(payload: Any, *, key: str, expected_length: int) -> tuple[bool, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise EvalJudgeError(f"Expected a JSON object with a {key!r} list.")
    items = payload[key]
    if not all(isinstance(item, bool) for item in items):
        raise EvalJudgeError(f"Expected {key!r} to be a list of booleans.")
    if len(items) != expected_length:
        raise EvalJudgeError(
            f"Expected {expected_length} {key!r} verdicts, got {len(items)}."
        )
    return tuple(items)


def fact_verdicts(payload: Any, *, facts: Sequence[str]) -> tuple[FactVerdict, ...]:
    verdicts = verdict_payloads(
        payload,
        expected_length=len(facts),
        verdict_key="covered",
    )
    return tuple(
        FactVerdict(
            fact=fact,
            covered=verdict["verdict"],
            evidence=verdict["evidence"],
        )
        for fact, verdict in zip(facts, verdicts, strict=True)
    )


def claim_verdicts(payload: Any, *, claims: Sequence[str]) -> tuple[ClaimVerdict, ...]:
    verdicts = verdict_payloads(
        payload,
        expected_length=len(claims),
        verdict_key="supported",
    )
    return tuple(
        ClaimVerdict(
            claim=claim,
            supported=verdict["verdict"],
            evidence=verdict["evidence"],
            status=claim_verdict_status(verdict, supported=verdict["verdict"]),
            issue_categories=issue_categories(verdict),
        )
        for claim, verdict in zip(claims, verdicts, strict=True)
    )


def claim_verdict_status(
    verdict: Mapping[str, Any],
    *,
    supported: bool,
) -> Literal[
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "NOT_IN_SOURCE",
    "AMBIGUOUS",
]:
    raw = verdict.get("status")
    allowed = {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "CONTRADICTED",
        "NOT_IN_SOURCE",
        "AMBIGUOUS",
    }
    if isinstance(raw, str) and raw in allowed:
        return raw  # type: ignore[return-value]
    return "SUPPORTED" if supported else "NOT_IN_SOURCE"


def issue_categories(verdict: Mapping[str, Any]) -> tuple[str, ...]:
    raw = verdict.get("issue_categories")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, str) and item.strip())


def verdict_payloads(
    payload: Any,
    *,
    expected_length: int,
    verdict_key: str,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("verdicts"), list):
        raise EvalJudgeError("Expected a JSON object with a 'verdicts' list.")
    items = payload["verdicts"]
    if len(items) != expected_length:
        raise EvalJudgeError(f"Expected {expected_length} verdicts, got {len(items)}.")
    verdicts: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise EvalJudgeError("Each verdict must be a JSON object.")
        verdict = item.get(verdict_key)
        evidence = item.get("evidence")
        if not isinstance(verdict, bool):
            raise EvalJudgeError(f"Verdict field {verdict_key!r} must be a boolean.")
        if not isinstance(evidence, str) or not evidence.strip():
            raise EvalJudgeError("Verdict evidence must be a non-empty string.")
        parsed = {"verdict": verdict, "evidence": evidence.strip()}
        status = item.get("status")
        if isinstance(status, str):
            parsed["status"] = status
        issue_values = item.get("issue_categories")
        if isinstance(issue_values, list):
            parsed["issue_categories"] = issue_values
        verdicts.append(parsed)
    return tuple(verdicts)


def write_run_artifact(run: EvalRun, *, runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = runs_dir / f"{run.run_id}.json"
    payload = {
        "run_id": run.run_id,
        "prompt_versions": run.prompt_versions,
        "judge_model": run.judge_model,
        "fact_extractor_model": run.fact_extractor_model,
        "summary_fast_model": run.summary_fast_model,
        "summary_final_model": run.summary_final_model,
        "mean_blended": run.mean_blended,
        "docs": [
            doc_score_payload(
                score,
                generated=(
                    run.generated_summaries[index]
                    if index < len(run.generated_summaries)
                    else None
                ),
            )
            for index, score in enumerate(run.doc_scores)
        ],
    }
    artifact_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact_path


def doc_score_payload(
    score: DocScore,
    *,
    generated: GeneratedSummary | None,
) -> dict[str, Any]:
    return {
        "doc_name": score.doc_name,
        "coverage": score.coverage,
        "faithfulness": score.faithfulness,
        "density": score.density,
        "rubric": score.rubric,
        "blended": score.blended,
        "missed_facts": list(score.missed_facts),
        "unsupported_claims": list(score.unsupported_claims),
        "fact_verdicts": [
            {
                "fact": verdict.fact,
                "covered": verdict.covered,
                "evidence": verdict.evidence,
            }
            for verdict in score.fact_verdicts
        ],
        "claim_verdicts": [
            {
                "claim": verdict.claim,
                "supported": verdict.supported,
                "status": verdict.status,
                "evidence": verdict.evidence,
                "issue_categories": list(verdict.issue_categories),
            }
            for verdict in score.claim_verdicts
        ],
        "rubric_notes": score.rubric_notes,
        "summary": score.summary,
        "error": score.error,
        "chunk_graphs": graph_artifacts_payload(
            generated.graph_artifacts if generated is not None else None
        ),
    }


def graph_artifacts_payload(
    artifacts: SummaryGraphArtifacts | None,
) -> dict[str, Any] | None:
    if artifacts is None:
        return None
    return {
        "artifact_dir": artifacts.artifact_dir,
        "chunk_graphs_markdown": artifacts.chunk_graphs_markdown,
        "chunks": [
            {
                "chunk": chunk.chunk,
                "graph_json": chunk.graph_json,
                "selected_subgraph_json": chunk.selected_subgraph_json,
                "selected_subgraph_markdown": chunk.selected_subgraph_markdown,
            }
            for chunk in artifacts.chunk_graphs
        ],
    }
