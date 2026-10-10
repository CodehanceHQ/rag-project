import math
from typing import Any, Dict, Iterable, List

from sentence_transformers import CrossEncoder

from .config import settings
from .loading import load_once


def reciprocal_rank_fusion(
    result_sets: Iterable[List[Dict[str, Any]]],
    rank_constant: int = 60,
) -> List[Dict[str, Any]]:
    fused: Dict[str, Dict[str, Any]] = {}
    sets = list(result_sets)
    for results in sets:
        for rank, result in enumerate(results, start=1):
            key = str(result["_id"])
            item = fused.setdefault(key, {**result, "fused_score": 0.0, "signals": []})
            item["fused_score"] += 1.0 / (rank_constant + rank)
            item["signals"].append(result["signal"])
            score_name = f"{result['signal']}_score"
            item[score_name] = float(result.get("score", 0.0))

    maximum = len(sets) / (rank_constant + 1) if sets else 1.0
    for item in fused.values():
        item["fused_score"] = item["fused_score"] / maximum
    return sorted(fused.values(), key=lambda item: item["fused_score"], reverse=True)


@load_once()
def get_reranker() -> CrossEncoder:
    return CrossEncoder(settings.reranker_model, max_length=settings.reranker_max_tokens)


def rerank(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    logits = get_reranker().predict(
        [(query, item["content"]) for item in candidates],
        batch_size=settings.reranker_batch_size,
    )
    for item, raw_score in zip(candidates, logits):
        raw = float(raw_score)
        item["reranker_score"] = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, raw))))
    return sorted(candidates, key=lambda item: item["reranker_score"], reverse=True)


def candidate_outcomes(
    reranked: List[Dict[str, Any]],
    accepted: List[Dict[str, Any]],
    minimum_score: float,
) -> Dict[str, str]:
    """What became of each reranked candidate. A candidate missing from the
    result was fused but never reached the reranker."""
    returned = {str(item["_id"]) for item in accepted}
    outcomes: Dict[str, str] = {}
    for item in reranked:
        key = str(item["_id"])
        if key in returned:
            outcomes[key] = "returned"
        elif item["reranker_score"] >= minimum_score:
            outcomes[key] = "beyond_limit"
        else:
            outcomes[key] = "below_threshold"
    return outcomes
