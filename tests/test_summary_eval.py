import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from alex.lib.summarize import SummaryPrompts, SummarySettings
from alex.lib.summary_eval import (
    DocScore,
    EvalConfig,
    EvalError,
    EvalJudgeError,
    EvalPrompts,
    EvalSettings,
    FactVerdict,
    PipelineSummaryEvaluator,
    bool_list,
    claim_verdicts,
    corpus_docs,
    density_score,
    eval_config_for,
    fact_cache_path,
    fact_sections,
    fact_verdicts,
    judge_fact_coverage,
    mean_blended,
    parse_json_payload,
    rubric_grade,
    string_list,
    strip_code_fence,
    verify_claims,
)

GUIDE_MD = (
    "# Field Guide\n"
    "\n"
    "By Pat Author\n"
    "\n"
    "## Habitat\n"
    "\n"
    "Owls live in cavities.\n"
    "\n"
    "## Diet\n"
    "\n"
    "Owls eat voles.\n"
)

FACTS = [
    "Owls live in cavities.",
    "Owls eat voles.",
    "The guide is by Pat Author.",
    "The guide covers habitat and diet.",
]


@dataclass
class ScriptedCompleter:
    """Returns canned responses keyed by a marker substring of the prompt."""

    responses: list[tuple[str, str]]
    calls: list[str] = field(default_factory=list)

    def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
        self.calls.append(prompt)
        for marker, response in self.responses:
            if marker in prompt:
                return response
        raise AssertionError(f"Unexpected prompt: {prompt[:80]!r}")


class NullEmbedder:
    def embed(
        self,
        *,
        texts: Sequence[str],
        model: str,
    ) -> tuple[tuple[float, ...], ...]:
        raise AssertionError("small eval docs should never be embedded")


def judge_responses() -> list[tuple[str, str]]:
    return [
        (
            "source-grounded claims",
            json.dumps(
                {
                    "claims": [
                        {
                            "claim": "The guide explains owl habitat.",
                            "evidence": "Owls live in cavities.",
                        },
                        {
                            "claim": "The guide explains owl diet.",
                            "evidence": "Owls eat voles.",
                        },
                    ]
                }
            ),
        ),
        ("graph-guided abstractive summary", "The graph covers owl habitat and diet."),
        (
            "merging two independently generated summaries",
            "The guide explains owl habitat and diet.",
        ),
        (
            "filtering a merged summary for source faithfulness",
            "The guide explains owl habitat and diet.",
        ),
        ('"facts"', json.dumps({"facts": FACTS})),
        (
            '"covered"',
            json.dumps(
                {
                    "verdicts": [
                        {"covered": True, "evidence": "habitat"},
                        {"covered": True, "evidence": "diet"},
                        {"covered": True, "evidence": "author"},
                        {"covered": False, "evidence": "missing coverage scope"},
                    ]
                }
            ),
        ),
        ('"claims"', json.dumps({"claims": ["Claim habitat.", "Claim diet."]})),
        (
            '"supported"',
            json.dumps(
                {
                    "verdicts": [
                        {"supported": True, "evidence": "document says habitat"},
                        {"supported": False, "evidence": "document does not say diet"},
                    ]
                }
            ),
        ),
        (
            '"coherence"',
            json.dumps(
                {
                    "coherence": 5,
                    "organization": 4,
                    "readability": 3,
                    "notes": "Could be tighter.",
                }
            ),
        ),
        ("<section_content>", "Chunk synopsis."),
        ("<section_summaries>", "The guide explains owl habitat and diet."),
    ]


def eval_config(tmp_path: Path) -> EvalConfig:
    evals_dir = tmp_path / "evals"
    config = EvalConfig(
        corpus_dir=evals_dir / "corpus",
        facts_dir=evals_dir / "facts",
        runs_dir=evals_dir / "runs",
        # Tiny density target so density saturates at 1.0 and the blended
        # score stays independent of the summary scaffolding's word count.
        # Models pinned so tests ignore any ALEX_* env in the shell.
        settings=EvalSettings(
            target_facts_per_100_words=0.01,
            judge_model="test-judge",
            fact_extractor_model="test/extractor-1",
        ),
        summary=SummarySettings(max_workers=1),
    )
    config.corpus_dir.mkdir(parents=True)
    (config.corpus_dir / "guide.md").write_text(GUIDE_MD, encoding="utf-8")
    return config


def guide_cache_path(config: EvalConfig) -> Path:
    return fact_cache_path(
        facts_dir=config.facts_dir,
        doc_text=GUIDE_MD,
        extractor_model="test/extractor-1",
        extractor_version="v002",
    )


def test_evaluate_scores_a_doc_and_writes_run_artifact(tmp_path: Path) -> None:
    config = eval_config(tmp_path)
    completer = ScriptedCompleter(responses=judge_responses())

    run = PipelineSummaryEvaluator(
        config=config,
        completer=completer,
        embedder=NullEmbedder(),
    ).evaluate(prompts=SummaryPrompts.load(), run_id="testrun")

    assert set(run.prompt_versions) == {
        "chunk_summary",
        "compression_summary",
        "final_summary",
    }
    assert len(run.doc_scores) == 1
    score = run.doc_scores[0]
    assert score.error is None
    assert score.doc_name == "guide.md"
    assert score.coverage == pytest.approx(0.75)
    assert score.faithfulness == pytest.approx(0.5)
    assert score.density == pytest.approx(1.0)
    assert score.rubric == pytest.approx(0.75)
    assert score.blended == pytest.approx(0.6875)
    assert run.mean_blended == pytest.approx(0.6875)
    assert score.missed_facts == ("The guide covers habitat and diet.",)
    assert score.unsupported_claims == ("Claim diet.",)
    assert score.rubric_notes == "Could be tighter."
    assert score.fact_verdicts[-1] == FactVerdict(
        fact="The guide covers habitat and diet.",
        covered=False,
        evidence="missing coverage scope",
    )
    assert "The guide explains owl habitat and diet." in score.summary

    artifact = json.loads(
        (config.runs_dir / "testrun.json").read_text(encoding="utf-8")
    )
    assert artifact["run_id"] == "testrun"
    assert artifact["mean_blended"] == pytest.approx(0.6875)
    assert set(artifact["prompt_versions"]) == {
        "chunk_summary",
        "compression_summary",
        "final_summary",
    }
    assert artifact["judge_model"] == "test-judge"
    assert artifact["fact_extractor_model"] == "test/extractor-1"
    assert artifact["summary_fast_model"] == config.summary.fast_model
    assert artifact["summary_final_model"] == config.summary.final_model
    assert artifact["docs"][0]["doc_name"] == "guide.md"
    assert artifact["docs"][0]["missed_facts"] == ["The guide covers habitat and diet."]
    assert artifact["docs"][0]["fact_verdicts"][-1] == {
        "fact": "The guide covers habitat and diet.",
        "covered": False,
        "evidence": "missing coverage scope",
    }

    cache_path = guide_cache_path(config)
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {"facts": FACTS}


def test_evaluate_streams_per_document_progress(tmp_path: Path) -> None:
    config = eval_config(tmp_path)
    lines: list[str] = []

    PipelineSummaryEvaluator(
        config=config,
        completer=ScriptedCompleter(responses=judge_responses()),
        embedder=NullEmbedder(),
    ).evaluate(
        prompts=SummaryPrompts.load(),
        run_id="progress",
        progress=lines.append,
    )

    assert "scoring (1/1) guide.md" in lines
    assert any(line.startswith("guide.md: blended=") for line in lines)


def test_evaluate_reuses_cached_facts_without_calling_the_extractor(
    tmp_path: Path,
) -> None:
    config = eval_config(tmp_path)
    cache_path = guide_cache_path(config)
    config.facts_dir.mkdir(parents=True)
    cache_path.write_text(json.dumps({"facts": ["Cached fact."]}), encoding="utf-8")
    # No fact-extraction response scripted: an extractor call would raise.
    responses = [pair for pair in judge_responses() if pair[0] != '"facts"']
    responses = [
        (
            marker,
            json.dumps({"verdicts": [{"covered": True, "evidence": "cached"}]}),
        )
        if marker == '"covered"'
        else (marker, response)
        for marker, response in responses
    ]

    run = PipelineSummaryEvaluator(
        config=config,
        completer=ScriptedCompleter(responses=responses),
        embedder=NullEmbedder(),
    ).evaluate(prompts=SummaryPrompts.load(), run_id="cached")

    score = run.doc_scores[0]
    assert score.error is None
    assert score.coverage == pytest.approx(1.0)
    assert score.missed_facts == ()


def test_fact_cache_key_includes_doc_hash_model_and_extractor_version() -> None:
    path = fact_cache_path(
        facts_dir=Path("facts"),
        doc_text=GUIDE_MD,
        extractor_model="anthropic/claude-sonnet-4-6",
        extractor_version="v003",
    )

    digest = hashlib.sha256(GUIDE_MD.encode("utf-8")).hexdigest()[:12]
    assert path == Path(f"facts/{digest}.anthropic-claude-sonnet-4-6.v003.json")


def test_corrupt_facts_cache_self_heals_by_re_extracting(tmp_path: Path) -> None:
    config = eval_config(tmp_path)
    cache_path = guide_cache_path(config)
    config.facts_dir.mkdir(parents=True)
    cache_path.write_text("{ not json", encoding="utf-8")

    run = PipelineSummaryEvaluator(
        config=config,
        completer=ScriptedCompleter(responses=judge_responses()),
        embedder=NullEmbedder(),
    ).evaluate(prompts=SummaryPrompts.load(), run_id="healed")

    assert run.doc_scores[0].error is None
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {"facts": FACTS}


def test_unreadable_corpus_doc_fails_only_that_doc(tmp_path: Path) -> None:
    config = eval_config(tmp_path)
    (config.corpus_dir / "broken.md").write_bytes(b"\xff\xfe invalid utf8")

    run = PipelineSummaryEvaluator(
        config=config,
        completer=ScriptedCompleter(responses=judge_responses()),
        embedder=NullEmbedder(),
    ).evaluate(prompts=SummaryPrompts.load(), run_id="partial")

    by_name = {score.doc_name: score for score in run.doc_scores}
    assert by_name["broken.md"].error is not None
    assert by_name["guide.md"].error is None
    assert run.mean_blended == pytest.approx(0.6875)


def test_evaluate_records_malformed_judge_output_as_failed_doc(
    tmp_path: Path,
) -> None:
    config = eval_config(tmp_path)
    responses = judge_responses()
    responses = [
        (marker, "this is not json") if marker == '"covered"' else (marker, response)
        for marker, response in responses
    ]

    run = PipelineSummaryEvaluator(
        config=config,
        completer=ScriptedCompleter(responses=responses),
        embedder=NullEmbedder(),
    ).evaluate(prompts=SummaryPrompts.load(), run_id="broken")

    score = run.doc_scores[0]
    assert score.error is not None
    assert "invalid JSON" in score.error
    assert score.blended == 0.0
    assert run.mean_blended == 0.0

    artifact = json.loads((config.runs_dir / "broken.json").read_text(encoding="utf-8"))
    assert "invalid JSON" in artifact["docs"][0]["error"]


def test_corpus_docs_selects_and_validates_documents(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"

    with pytest.raises(EvalError, match="not found"):
        corpus_docs(corpus, None)

    corpus.mkdir()
    with pytest.raises(EvalError, match="No markdown documents"):
        corpus_docs(corpus, None)

    (corpus / "b.md").write_text("b", encoding="utf-8")
    (corpus / "a.md").write_text("a", encoding="utf-8")
    assert tuple(path.name for path in corpus_docs(corpus, None)) == ("a.md", "b.md")
    assert tuple(path.name for path in corpus_docs(corpus, ("b.md",))) == ("b.md",)

    with pytest.raises(EvalError, match=r"missing\.md"):
        corpus_docs(corpus, ("missing.md",))


def test_eval_config_for_lays_out_the_evals_directory() -> None:
    config = eval_config_for(Path("evals"))

    assert config.corpus_dir == Path("evals/corpus")
    assert config.facts_dir == Path("evals/facts")
    assert config.runs_dir == Path("evals/runs")


def test_strip_code_fence_handles_fenced_and_plain_payloads() -> None:
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'
    assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fence('```\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fence('```json\n{"a": 1}') == '{"a": 1}'


def test_parse_json_payload_salvages_json_wrapped_in_prose() -> None:
    response = 'Here are the verdicts:\n{"covered": [true, false]}\nHope that helps!'

    assert parse_json_payload(response, step="Judge") == {"covered": [True, False]}


def test_parse_json_payload_raises_judge_error_on_invalid_json() -> None:
    with pytest.raises(EvalJudgeError, match="Judge returned invalid JSON"):
        parse_json_payload("nope", step="Judge")


def test_string_list_validates_payload_shape() -> None:
    assert string_list({"facts": ["a", "b"]}, key="facts") == ("a", "b")

    with pytest.raises(EvalJudgeError, match="'facts' list"):
        string_list(["a"], key="facts")
    with pytest.raises(EvalJudgeError, match="list of strings"):
        string_list({"facts": ["a", 2]}, key="facts")


def test_bool_list_validates_values_and_length() -> None:
    payload = {"covered": [True, False]}
    assert bool_list(payload, key="covered", expected_length=2) == (True, False)

    with pytest.raises(EvalJudgeError, match="list of booleans"):
        bool_list({"covered": [True, 1]}, key="covered", expected_length=2)
    with pytest.raises(EvalJudgeError, match="Expected 3 'covered' verdicts"):
        bool_list(payload, key="covered", expected_length=3)


def test_fact_verdicts_require_evidence_and_match_fact_order() -> None:
    payload = {
        "verdicts": [
            {"covered": True, "evidence": "summary says a"},
            {"covered": False, "evidence": "missing b"},
        ]
    }

    assert fact_verdicts(payload, facts=("Fact A.", "Fact B.")) == (
        FactVerdict(fact="Fact A.", covered=True, evidence="summary says a"),
        FactVerdict(fact="Fact B.", covered=False, evidence="missing b"),
    )

    with pytest.raises(EvalJudgeError, match="non-empty string"):
        fact_verdicts(
            {"verdicts": [{"covered": True, "evidence": ""}]},
            facts=("Fact A.",),
        )


def test_claim_verdicts_require_supported_booleans() -> None:
    payload = {"verdicts": [{"supported": False, "evidence": "not in doc"}]}

    assert claim_verdicts(payload, claims=("Claim A.",))[0].supported is False

    with pytest.raises(EvalJudgeError, match="'supported' must be a boolean"):
        claim_verdicts(
            {"verdicts": [{"supported": "false", "evidence": "not in doc"}]},
            claims=("Claim A.",),
        )


def test_judges_batch_large_fact_and_claim_lists() -> None:
    class CountingCompleter:
        calls: list[str]

        def __init__(self) -> None:
            self.calls = []

        def complete(self, *, prompt: str, model: str, max_tokens: int) -> str:
            self.calls.append(prompt)
            if '"covered"' in prompt:
                return json.dumps(
                    {
                        "verdicts": [
                            {"covered": True, "evidence": "covered"}
                            for _ in range(numbered_item_count(prompt))
                        ]
                    }
                )
            return json.dumps(
                {
                    "verdicts": [
                        {"supported": True, "evidence": "supported"}
                        for _ in range(numbered_item_count(prompt))
                    ]
                }
            )

    def numbered_item_count(prompt: str) -> int:
        return sum(
            1 for line in prompt.splitlines() if line[:1].isdigit() and ". " in line[:5]
        )

    completer = CountingCompleter()
    settings = EvalSettings(judge_model="judge", fact_extractor_model="extractor")
    prompts = EvalPrompts.load()

    facts = tuple(f"Fact {index}." for index in range(45))
    fact_results = judge_fact_coverage(
        facts=facts,
        summary="A summary.",
        template=prompts.fact_coverage_judge,
        completer=completer,
        settings=settings,
    )

    claims = tuple(f"Claim {index}." for index in range(45))
    claim_results = verify_claims(
        doc_text="A document.",
        claims=claims,
        template=prompts.claim_verification,
        completer=completer,
        settings=settings,
    )

    assert len(fact_results) == 45
    assert len(claim_results) == 45
    assert len(completer.calls) == 10


def test_fact_sections_use_inferred_chapters_and_preamble() -> None:
    sections = fact_sections(GUIDE_MD)

    assert tuple(section.title for section in sections) == (
        "Document Preamble",
        "Field Guide > Habitat",
        "Field Guide > Diet",
    )
    assert "By Pat Author" in sections[0].text


def test_rubric_grade_requires_integers_between_one_and_five() -> None:
    assert rubric_grade({"coherence": 4}, key="coherence") == 4

    for bad in (True, 0, 6, "3", None):
        with pytest.raises(EvalJudgeError, match="integer from 1 to 5"):
            rubric_grade({"coherence": bad}, key="coherence")


def test_density_score_normalizes_against_the_target_rate() -> None:
    settings = EvalSettings(target_facts_per_100_words=1.0)

    assert density_score(
        covered_count=5, summary_word_count=500, settings=settings
    ) == pytest.approx(1.0)
    assert density_score(
        covered_count=2, summary_word_count=400, settings=settings
    ) == pytest.approx(0.5)
    assert density_score(
        covered_count=50, summary_word_count=100, settings=settings
    ) == pytest.approx(1.0)
    assert density_score(
        covered_count=0, summary_word_count=0, settings=settings
    ) == pytest.approx(0.0)


def test_mean_blended_skips_failed_docs() -> None:
    ok = DocScore(
        doc_name="ok.md",
        coverage=1.0,
        faithfulness=1.0,
        density=1.0,
        rubric=1.0,
        blended=0.8,
        missed_facts=(),
        unsupported_claims=(),
        rubric_notes="",
        summary="s",
    )
    failed = DocScore(
        doc_name="bad.md",
        coverage=0.0,
        faithfulness=0.0,
        density=0.0,
        rubric=0.0,
        blended=0.0,
        missed_facts=(),
        unsupported_claims=(),
        rubric_notes="",
        summary="",
        error="boom",
    )

    assert mean_blended([ok, failed]) == pytest.approx(0.8)
    assert mean_blended([failed]) == 0.0
    assert mean_blended([]) == 0.0
