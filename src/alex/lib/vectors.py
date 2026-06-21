"""Small, dependency-free vector helpers shared across the codebase.

Both semantic chunking and the claim graph reason over embedding vectors, so
the cosine/mean primitives live here instead of being duplicated or imported
across feature modules.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def mean_vector(vectors: Sequence[tuple[float, ...]]) -> tuple[float, ...]:
    count = len(vectors)
    return tuple(sum(values) / count for values in zip(*vectors, strict=True))


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
