"""Grounded close/far idea generation and strict local judging."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from xml.sax.saxutils import escape

from alex.lib.brain import BrainIndex, KnowledgePage, SearchHit
from alex.lib.llm import (
    Completer,
    Embedder,
    LiteLlmCompleter,
    preflight_completion_cost,
)
from alex.lib.prompt_templates import load_prompt

JUDGE_BATCH_SIZE = 100
SOURCE_LIMIT = 4_000


class CollisionError(ValueError):
    """A collision response did not meet its output contract."""


@dataclass(frozen=True)
class JudgePolicy:
    threshold: float
    weights: tuple[tuple[str, float], ...] = (
        ("originality", 0.30),
        ("defensibility", 0.25),
        ("thesis_density", 0.20),
        ("concrete_grounding", 0.25),
    )
    obviousness_ceiling: float | None = None


@dataclass(frozen=True)
class ColliderProfile:
    name: str
    close_count: int
    far_count: int
    ideas_per_cross: int
    temperature: float
    voice: str
    inversion_instruction: str
    requires_inversion: bool
    prefer_stale: bool
    save_by_default: bool
    judge: JudgePolicy


BRAINSTORM_PROFILE = ColliderProfile(
    "brainstorm",
    4,
    6,
    3,
    0.7,
    "Write as a rigorous, playful research collaborator.",
    "Do not add an axiom inversion.",
    False,
    False,
    True,
    JudgePolicy(4.0),
)
LSD_PROFILE = ColliderProfile(
    "lsd",
    2,
    12,
    4,
    0.95,
    "Write as a lucid, provocative systems thinker; stay concrete.",
    "For each idea include distinct original_axiom and inverted_axiom strings.",
    True,
    True,
    False,
    JudgePolicy(3.5, obviousness_ceiling=4.5),
)


def profile_for_mode(mode: str) -> ColliderProfile:
    try:
        return {"brainstorm": BRAINSTORM_PROFILE, "lsd": LSD_PROFILE}[mode]
    except KeyError as error:
        raise CollisionError(f"Unknown collision mode: {mode}") from error


@dataclass(frozen=True)
class CollisionCandidate:
    idea: str
    inversion: str | None
    close: SearchHit
    far: SearchHit
    original_axiom: str | None = None
    pair_index: int = 0
    score: float | None = None
    judge_notes: str | None = None
    novelty: float | None = None
    axes: dict[str, float] = field(default_factory=dict)
    obviousness: float | None = None
    passes: bool = False
    rejection_reason: str | None = None


@dataclass(frozen=True)
class CollisionResult:
    close: tuple[SearchHit, ...]
    far: tuple[SearchHit, ...]
    candidates: tuple[CollisionCandidate, ...]
    rejected: tuple[CollisionCandidate, ...] = ()
    profile: ColliderProfile = BRAINSTORM_PROFILE
    run_id: str = ""
    warnings: tuple[str, ...] = ()
    estimated_cost: float = 0.0
    observed_cost: float = 0.0
    checkpoint_status: str = "not_requested"

    @property
    def passing(self) -> tuple[CollisionCandidate, ...]:
        return self.candidates


def run_collisions(
    *,
    index: BrainIndex,
    question: str,
    mode: str,
    limit: int | None,
    completer: Completer,
    model: str,
    judge_model: str,
    embedder: Embedder | None = None,
    calibration_tags: tuple[str, ...] = (),
    max_cost: float = 5.0,
) -> CollisionResult:
    """Generate pairs concurrently; provenance is always supplied by code."""
    profile = profile_for_mode(mode)
    if max_cost < 0:
        raise CollisionError("max_cost must be non-negative.")
    estimated_cost = (
        _preflight_cost(question, profile, model, judge_model, limit)
        if isinstance(completer, LiteLlmCompleter)
        else 0.0
    )
    if estimated_cost > max_cost:
        raise CollisionError(
            f"Estimated collision cost ${estimated_cost:.2f} exceeds "
            f"--max-cost ${max_cost:.2f}."
        )
    close, far = _retrieve_pairs(index, question, profile, limit, embedder)
    run_id = _run_id(question, profile, close, far)
    if not far:
        return CollisionResult(
            close,
            (),
            (),
            (),
            profile,
            run_id,
            (
                "No distant eligible vault pages were found; "
                "index more notes and retry.",
            ),
            estimated_cost=estimated_cost,
        )
    pairs = [
        (number, near, distant)
        for number, (near, distant) in enumerate(
            pair for near in close for pair in ((near, distant) for distant in far)
        )
    ]
    with ThreadPoolExecutor(max_workers=min(4, len(pairs))) as executor:
        generated = executor.map(
            lambda pair: _generate_pair(
                question,
                profile,
                pair[0],
                pair[1],
                pair[2],
                completer,
                model,
            ),
            pairs,
        )
        unjudged = [candidate for group in generated for candidate in group]
    judged = _judge(unjudged, profile, completer, judge_model, calibration_tags)
    return CollisionResult(
        close,
        far,
        tuple(item for item in judged if item.passes),
        tuple(item for item in judged if not item.passes),
        profile,
        run_id,
        estimated_cost=estimated_cost,
    )


def _preflight_cost(
    question: str,
    profile: ColliderProfile,
    model: str,
    judge_model: str,
    limit: int | None,
) -> float:
    """Fail closed for unknown remote model prices before any retrieval/model call."""
    generator_prompt = _generation_prompt(
        question,
        profile,
        SearchHit("preflight-close", "Preflight", "x" * SOURCE_LIMIT, 1, 1, 0.0),
        SearchHit("preflight-far", "Preflight", "x" * SOURCE_LIMIT, 1, 1, 0.0),
    )
    generator = preflight_completion_cost(
        prompt=generator_prompt,
        model=model,
        max_tokens=max(700, profile.ideas_per_cross * 280),
    )
    judge = preflight_completion_cost(
        prompt=_judge_prompt([], (), include_system=True),
        model=judge_model,
        max_tokens=min(
            16_000,
            160
            * profile.close_count
            * (limit if limit is not None else profile.far_count),
        ),
    )
    far_count = limit if limit is not None else profile.far_count
    return profile.close_count * far_count * generator + judge


def _retrieve_pairs(
    index: BrainIndex,
    question: str,
    profile: ColliderProfile,
    limit: int | None,
    embedder: Embedder | None,
) -> tuple[tuple[SearchHit, ...], tuple[SearchHit, ...]]:
    """Use the newer page API when available, retaining fake-index compatibility."""
    page_search = getattr(index, "search_diverse_pages", None)
    page_far = getattr(index, "far_pages", None)
    hydrate = getattr(index, "hydrate_page", None)
    embed_question = getattr(index, "embed_question", None)
    far_count = limit if limit is not None else profile.far_count
    if not callable(page_search) or not callable(page_far) or not callable(hydrate):
        close = index.search_diverse_hybrid(
            question, embedder=embedder, limit=profile.close_count
        )
        close = close or (_synthetic_close(question),)
        return close, index.far_notes(close, limit=far_count)
    query_embedding = None
    if embedder is not None and callable(embed_question):
        try:
            query_embedding = embed_question(question, embedder)
        except Exception:
            query_embedding = None
    pages: tuple[KnowledgePage, ...] = page_search(
        question,
        embedder=embedder,
        limit=profile.close_count,
        query_embedding=query_embedding,
    )
    hydrated_close = tuple(hydrate(page) for page in pages)
    close = tuple(_hit_from_page(page) for page in hydrated_close)
    if not close:
        return (_synthetic_close(question),), ()
    far_pages: tuple[KnowledgePage, ...] = page_far(
        hydrated_close,
        limit=far_count,
        mode=profile.name,
        question_embedding=query_embedding,
    )
    return close, tuple(_hit_from_page(hydrate(page)) for page in far_pages)


def _hit_from_page(page: KnowledgePage) -> SearchHit:
    return SearchHit(
        page.path, page.title, page.text, page.line_start, page.line_end, page.score
    )


def _synthetic_close(question: str) -> SearchHit:
    return SearchHit("__question__.md", "Question", question, 1, 1, 0.0)


def _generate_pair(
    question: str,
    profile: ColliderProfile,
    pair_index: int,
    close: SearchHit,
    far: SearchHit,
    completer: Completer,
    model: str,
) -> tuple[CollisionCandidate, ...]:
    try:
        response = completer.complete(
            prompt=_generation_prompt(question, profile, close, far),
            model=model,
            max_tokens=max(700, profile.ideas_per_cross * 280),
        )
    except Exception:
        return ()
    result: list[CollisionCandidate] = []
    for item in _json_list(response):
        idea = item.get("idea")
        original = item.get("original_axiom")
        inverted = item.get("inverted_axiom", item.get("inversion"))
        if not isinstance(idea, str) or not idea.strip():
            continue
        if profile.requires_inversion and (
            not isinstance(original, str)
            or not isinstance(inverted, str)
            or _normalized(original) == _normalized(inverted)
        ):
            continue
        result.append(
            CollisionCandidate(
                idea.strip(),
                inverted.strip() if isinstance(inverted, str) else None,
                close,
                far,
                original.strip() if isinstance(original, str) else None,
                pair_index,
            )
        )
    return tuple(result[: profile.ideas_per_cross])


def _generation_prompt(
    question: str, profile: ColliderProfile, close: SearchHit, far: SearchHit
) -> str:
    values = {
        "question": _sanitize(question),
        "voice": profile.voice,
        "inversion_instruction": profile.inversion_instruction,
        "idea_count": str(profile.ideas_per_cross),
        "close_source": _source_data("close", close),
        "far_source": _source_data("far", far),
    }
    try:
        return load_prompt("collision_generator").render(**values)
    except Exception:
        return "\n".join(
            (
                f"Question: {values['question']}",
                profile.voice,
                profile.inversion_instruction,
                values["close_source"],
                values["far_source"],
                f"Return exactly {profile.ideas_per_cross} ideas as a bare JSON array.",
            )
        )


def _source_data(arm: str, hit: SearchHit) -> str:
    return (
        f'<source-data arm="{arm}" path="{escape(hit.path)}" '
        f'lines="{hit.line_start}-{hit.line_end}">{_sanitize(hit.text)[:SOURCE_LIMIT]}</source-data>'
    )


def _sanitize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = "".join(
        c
        for c in text
        if c != "\x00"
        and not 0x202A <= ord(c) <= 0x202E
        and not 0x2066 <= ord(c) <= 0x2069
    )
    return escape(text, {'"': "&quot;", "'": "&apos;"})


def _judge(
    candidates: list[CollisionCandidate],
    profile: ColliderProfile,
    completer: Completer,
    model: str,
    calibration_tags: tuple[str, ...],
) -> tuple[CollisionCandidate, ...]:
    records: dict[int, dict[str, object]] = {}
    judge_completer: Completer = completer
    judge_system = _judge_system(calibration_tags)
    if isinstance(completer, LiteLlmCompleter):
        judge_completer = replace(completer, system_prompt=judge_system)
    for start in range(0, len(candidates), JUDGE_BATCH_SIZE):
        batch = candidates[start : start + JUDGE_BATCH_SIZE]
        payload: list[dict[str, object]] = [
            {
                "index": number,
                "idea": item.idea,
                "original_axiom": item.original_axiom,
                "inverted_axiom": item.inversion,
                "close": {
                    "path": item.close.path,
                    "lines": [item.close.line_start, item.close.line_end],
                    "text": _sanitize(item.close.text)[:SOURCE_LIMIT],
                },
                "far": {
                    "path": item.far.path,
                    "lines": [item.far.line_start, item.far.line_end],
                    "text": _sanitize(item.far.text)[:SOURCE_LIMIT],
                },
            }
            for number, item in enumerate(batch, start)
        ]
        response = judge_completer.complete(
            prompt=_judge_prompt(
                payload,
                calibration_tags,
                include_system=not isinstance(completer, LiteLlmCompleter),
            ),
            model=model,
            max_tokens=min(16_000, 160 * len(batch)),
        )
        parsed = _judge_json_list(response)
        expected = set(range(start, start + len(batch)))
        received = [item.get("index") for item in parsed]
        if set(received) != expected or len(received) != len(set(received)):
            raise CollisionError(
                "Judge response is incomplete or contains duplicate indexes."
            )
        for record in parsed:
            number = record["index"]
            if not isinstance(number, int):
                raise CollisionError("Judge response has an invalid index.")
            _validate_judge_record(record, profile)
            records[number] = record
    return tuple(
        _scored(item, records[number], profile)
        for number, item in enumerate(candidates)
    )


def _judge_prompt(
    payload: list[dict[str, object]],
    calibration_tags: tuple[str, ...],
    *,
    include_system: bool,
) -> str:
    system = _judge_system(calibration_tags)
    data = json.dumps(payload, ensure_ascii=False)
    return f"{system}\n{data}" if include_system else data


def _judge_system(calibration_tags: tuple[str, ...]) -> str:
    tags = ", ".join(calibration_tags) or "none (cold start)"
    try:
        return load_prompt("collision_judge").render(calibration_tags=tags)
    except Exception:
        return "Return a bare JSON score array with requested axes and source booleans."


def _validate_judge_record(record: dict[str, object], profile: ColliderProfile) -> None:
    score_keys = (
        "originality",
        "defensibility",
        "thesis_density",
        "concrete_grounding",
        "cognitive_load",
        "obviousness",
    )
    required: tuple[str, ...] = (*score_keys, "both_sources_material")
    if profile.requires_inversion:
        required += ("substantive_inversion",)
    missing = [key for key in required if key not in record]
    if missing:
        raise CollisionError(f"Judge response is missing fields: {', '.join(missing)}.")
    for key in score_keys:
        value = record[key]
        if not isinstance(value, int | float) or not 1 <= float(value) <= 5:
            raise CollisionError(f"Judge score {key} must be between 1 and 5.")
    if not isinstance(record["both_sources_material"], bool):
        raise CollisionError("Judge both_sources_material must be a boolean.")
    if profile.requires_inversion and not isinstance(
        record["substantive_inversion"], bool
    ):
        raise CollisionError("Judge substantive_inversion must be a boolean.")


def _scored(
    candidate: CollisionCandidate, record: dict[str, object], profile: ColliderProfile
) -> CollisionCandidate:
    axes = {
        key: _score_float(record[key])
        for key in (
            "originality",
            "defensibility",
            "thesis_density",
            "concrete_grounding",
            "cognitive_load",
        )
    }
    score = sum(axes[key] * weight for key, weight in profile.judge.weights)
    obviousness = _score_float(record["obviousness"])
    reasons: list[str] = []
    if score < profile.judge.threshold:
        reasons.append("weighted score below threshold")
    if not bool(record["both_sources_material"]):
        reasons.append("both sources do not materially contribute")
    if profile.requires_inversion and not bool(record["substantive_inversion"]):
        reasons.append("inversion is not substantive")
    if (
        profile.judge.obviousness_ceiling is not None
        and obviousness > profile.judge.obviousness_ceiling
    ):
        reasons.append("obviousness exceeds ceiling")
    notes = record.get("notes")
    return CollisionCandidate(
        candidate.idea,
        candidate.inversion,
        candidate.close,
        candidate.far,
        candidate.original_axiom,
        candidate.pair_index,
        score,
        notes if isinstance(notes, str) else None,
        axes["originality"],
        axes,
        obviousness,
        not reasons,
        "; ".join(reasons) or None,
    )


def _score_float(value: object) -> float:
    if not isinstance(value, int | float):
        raise CollisionError("Judge score must be numeric.")
    return float(value)


def _json_list(text: str) -> list[dict[str, object]]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return []
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _judge_json_list(text: str) -> list[dict[str, object]]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise CollisionError("Judge returned invalid JSON.") from error
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CollisionError("Judge response must be a JSON array of objects.")
    return value


def _run_id(
    question: str,
    profile: ColliderProfile,
    close: tuple[SearchHit, ...],
    far: tuple[SearchHit, ...],
) -> str:
    payload = json.dumps(
        {
            "question": question,
            "profile": asdict(profile),
            "close": [x.path for x in close],
            "far": [x.path for x in far],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())
