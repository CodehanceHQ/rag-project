"""The last step of Path A: paste the retrieved passages into a prompt and ask
the model to answer from them.

Deliberately naive. This is the baseline, not a good system: one call, no
second lookup, no way for the model to ask for anything it was not given.
Nothing here tries to compensate for that.
"""
import json
import re
from typing import Any, Dict, List

import httpx

from .config import settings
from .local_llm import THINKING, write_local

SYSTEM_PROMPT = """You answer questions about a document corpus.

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


def answer_model() -> str:
    """The model the answer step is set to use."""
    if settings.answer_provider.strip().lower() == "local":
        return settings.answer_local_model
    return settings.openrouter_model


def _write_hosted(prompt: str) -> str:
    payload = {
        "model": settings.openrouter_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }
    response = httpx.post(
        f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
        headers=headers, json=payload, timeout=settings.openrouter_timeout_seconds * 2,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _write_local(prompt: str) -> str:
    written = write_local(settings.answer_local_model, SYSTEM_PROMPT, prompt,
                          settings.answer_max_tokens)
    return THINKING.sub("", written)


def generate_answer(query: str, passages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One model call over the retrieved passages. Returns the answer and the
    sources it was given — not the sources it actually used, which is a
    distinction the benchmark cares about.

    ANSWER_PROVIDER chooses where the model runs: "openrouter" (hosted, paid)
    or "local" (a Hugging Face model on this machine, free and slower)."""
    provider = settings.answer_provider.strip().lower()
    told = {"provider": provider, "model": answer_model()}
    if provider not in ("local", "openrouter"):
        return {"status": "error", "answer": None, "cited": [], "sources": [], **told,
                "detail": f"Unknown ANSWER_PROVIDER '{provider}'. Choose local or openrouter."}
    if provider == "openrouter" and not settings.openrouter_api_key:
        return {"status": "not_configured", "answer": None, "cited": [], "sources": [], **told}
    if not passages:
        return {"status": "no_passages", "answer": None, "cited": [], "sources": [], **told}

    prompt = build_prompt(query, passages)
    try:
        text = (_write_local(prompt) if provider == "local" else _write_hosted(prompt)).strip()
    except (httpx.HTTPError, KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
        return {"status": "error", "answer": None, "cited": [],
                "sources": [], **told, "detail": f"{type(exc).__name__}"}

    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)
                    if 0 < int(n) <= len(passages)})
    return {
        "status": "generated",
        **told,
        "answer": text,
        "cited": cited,
        "sources": [
            {"n": n, "filename": p["filename"], "page": p.get("page"),
             "score": p.get("score"), "used": n in cited}
            for n, p in enumerate(passages, 1)
        ],
    }
