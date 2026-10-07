"""The last step of Path A: paste the retrieved passages into a prompt and ask
the model to answer from them.

Deliberately naive. This is the baseline, not a good system: one call, no
second lookup, no way for the model to ask for anything it was not given.
Nothing here tries to compensate for that.
"""
import json
from typing import Any, Dict, List

import httpx

from .config import settings

SYSTEM_PROMPT = """You answer questions about an engineering document corpus.

Answer using ONLY the numbered passages provided. Do not use outside
knowledge and do not infer facts the passages do not state.

Cite the passages you used by their number, like [1] or [2][3].

If the passages do not contain the answer, say so plainly and do not guess."""


def build_prompt(query: str, passages: List[Dict[str, Any]]) -> str:
    blocks = []
    for n, p in enumerate(passages, 1):
        where = p["filename"]
        if p.get("page"):
            where += f", page {p['page']}"
        if p.get("section"):
            where += f", {p['section']}"
        blocks.append(f"[{n}] ({where})\n{p['content']}")
    return f"Question: {query}\n\nPassages:\n\n" + "\n\n".join(blocks)


def generate_answer(query: str, passages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One model call over the retrieved passages. Returns the answer and the
    sources it was given — not the sources it actually used, which is a
    distinction the benchmark cares about."""
    if not settings.openrouter_api_key:
        return {"status": "not_configured", "answer": None, "cited": [], "sources": []}
    if not passages:
        return {"status": "no_passages", "answer": None, "cited": [], "sources": []}

    payload = {
        "model": settings.openrouter_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(query, passages)},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }
    try:
        response = httpx.post(
            f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers=headers, json=payload, timeout=settings.openrouter_timeout_seconds * 2,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return {"status": "error", "answer": None, "cited": [],
                "sources": [], "detail": f"{type(exc).__name__}"}

    cited = sorted({int(n) for n in __import__("re").findall(r"\[(\d+)\]", text)
                    if 0 < int(n) <= len(passages)})
    return {
        "status": "generated",
        "answer": text,
        "cited": cited,
        "sources": [
            {"n": n, "filename": p["filename"], "page": p.get("page"),
             "score": p.get("score"), "used": n in cited}
            for n, p in enumerate(passages, 1)
        ],
    }
