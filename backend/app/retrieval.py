import math
from functools import lru_cache
from typing import Any, Dict, Iterable, List

from sentence_transformers import CrossEncoder

from .config import settings


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


@lru_cache
def get_reranker() -> CrossEncoder:
    return CrossEncoder(settings.reranker_model)


def rerank(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    logits = get_reranker().predict([(query, item["content"]) for item in candidates])
    for item, raw_score in zip(candidates, logits):
        raw = float(raw_score)
        item["reranker_score"] = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, raw))))
    return sorted(candidates, key=lambda item: item["reranker_score"], reverse=True)
