from __future__ import annotations

import math
import re
from pathlib import PurePosixPath
from typing import Any, Iterable


def canonical_source(source: str) -> str:
    normalized = (source or "").strip().lower().replace("\\", "/")
    normalized = re.sub(r"^kb/", "", normalized)
    path = PurePosixPath(normalized)
    stem = re.sub(r"\.(md|pdf|txt)$", "", path.name)
    stem = re.sub(r"(?:_technical_analysis|_analysis|_summary|-summary)$", "", stem)
    stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    parent = re.sub(r"[^a-z0-9/]+", "_", str(path.parent)).strip("_/")
    return f"{parent}/{stem}" if parent and parent != "." else stem


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def evaluate_ranking(case: dict[str, Any], retrieved_sources: Iterable[str], k: int = 5) -> dict[str, Any]:
    relevant = {canonical_source(source) for source in case.get("relevant_sources", [])}
    retrieved = []
    for source in retrieved_sources:
        canonical = canonical_source(source)
        if canonical and canonical not in retrieved:
            retrieved.append(canonical)
    top_k = retrieved[:k]
    if not relevant:
        return {
            "recall_at_5": None,
            "reciprocal_rank": None,
            "ndcg_at_5": None,
            "relevant_found": [],
            "retrieved_canonical": retrieved,
        }

    relevant_found = [source for source in top_k if source in relevant]
    recall = len(set(relevant_found)) / len(relevant)
    first_relevant_rank = next((index for index, source in enumerate(retrieved, start=1) if source in relevant), None)
    reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    dcg = sum(1.0 / math.log2(rank + 1) for rank, source in enumerate(top_k, start=1) if source in relevant)
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return {
        "recall_at_5": recall,
        "reciprocal_rank": reciprocal_rank,
        "ndcg_at_5": dcg / ideal_dcg if ideal_dcg else 0.0,
        "relevant_found": relevant_found,
        "retrieved_canonical": retrieved,
    }


def relative_improvement(baseline: float, candidate: float) -> float:
    if baseline == 0.0:
        return 1.0 if candidate > 0.0 else 0.0
    return (candidate - baseline) / baseline
