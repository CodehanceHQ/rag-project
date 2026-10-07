"""The seam. Every system under test is a callable of one shape:

    f(question: str) -> {"answer": str|None, "sources": [...], "cited": [int]}

Path A, the single-pass RAG pipeline, is the only entry. Another system can
be added to SYSTEMS without changing anything else in the harness, so every
system is scored by the same instrument.
"""
from typing import Any, Callable, Dict

import httpx

API = "http://localhost:18001"


def path_a(question: str, limit: int = 5) -> Dict[str, Any]:
    """Single-pass RAG: retrieve top-k, generate from what came back."""
    r = httpx.post(f"{API}/answer", json={"query": question, "limit": limit}, timeout=300.0)
    r.raise_for_status()
    d = r.json()
    gen = d.get("generation") or {}
    return {
        "answer": d.get("answer"),
        "abstained": d.get("abstained", False),
        "decision": d.get("decision"),
        "sources": gen.get("sources", []),
        "cited": gen.get("cited", []),
        # passage text comes from results[], not from generation.sources[] —
        # the citation check needs the actual content, not just the filename
        "passages": {
            s["n"]: {**s, "content": (d.get("results") or [{}] * s["n"])[s["n"] - 1].get("content", "")}
            for s in gen.get("sources", [])
        },
    }


SYSTEMS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "path-a": path_a,
}
