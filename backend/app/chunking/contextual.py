"""Contextual chunking: say what each piece is about before embedding it.

Another strategy decides where to cut. This one then asks a language model
for one sentence that places each piece in its document, and puts that
sentence in front of the piece. A chunk reading "Set it to 230 °C" gains a
line naming the document, the product and what "it" is, so it can be found
and understood on its own.

Unlike the other strategies this one is not free and not local: it makes one
model call per chunk through OpenRouter, and the text of each document is sent
there. CONTEXTUAL_BASE_STRATEGY picks the strategy that does the cutting.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import List

import httpx

from ..config import settings
from ..embeddings import count_tokens, token_budget
from .base import Chunk, Chunker, SourceDocument
from .hybrid import HybridChunker
from .recursive import RecursiveChunker
from .semantic import SemanticChunker
from .structural import StructuralChunker

INSTRUCTION = """You write one sentence that places a passage within its document, so the passage can be found and understood on its own.

Name the document, the product or subject it concerns, and the section if it is clear. If the passage uses a word such as "it" or "this" for something named earlier, say what that is. Use only the text supplied; do not add facts. Reply with the single sentence and nothing else."""

OPENING_CHARS = 1500      # the start of the document: its title and scope
BEFORE_CHARS = 2000       # the text just before the passage: what "it" points at


def _base_chunker(name: str, budget: int) -> Chunker:
    """The strategy that does the cutting, with room left for the sentence."""
    name = name.strip().lower()
    if name == "recursive":
        return RecursiveChunker(chunk_tokens=budget)
    if name == "hybrid":
        return HybridChunker(RecursiveChunker(chunk_tokens=budget))
    if name == "semantic":
        return SemanticChunker(max_tokens=budget)
    if name == "structural":
        return StructuralChunker()
    raise ValueError(
        f"Unknown CONTEXTUAL_BASE_STRATEGY '{name}'. "
        "Choose one of: hybrid, recursive, semantic, structural."
    )


class ContextualChunker:
    name = "contextual"

    def __init__(self, base: str | None = None, context_tokens: int | None = None,
                 workers: int = 8):
        self.context_tokens = context_tokens or settings.contextual_context_tokens
        self.base_name = (base or settings.contextual_base_strategy).strip().lower()
        self.base = _base_chunker(self.base_name, token_budget() - self.context_tokens)
        self.model = settings.contextual_model or settings.openrouter_model
        self.workers = workers

    def validate(self) -> None:
        if not settings.openrouter_api_key:
            raise ValueError(
                "CHUNKING_STRATEGY=contextual needs OPENROUTER_API_KEY: it asks a language "
                "model for one sentence of context per chunk."
            )

    def chunk(self, source: SourceDocument) -> List[Chunk]:
        self.validate()
        pieces = self.base.chunk(source)
        if not pieces:
            return []
        opening = "\n".join(page.page_content for page in source.pages)[:OPENING_CHARS]
        before = [""] + [piece.text[-BEFORE_CHARS:] for piece in pieces[:-1]]

        def describe(index: int) -> str:
            return self._context(source.filename, opening, before[index], pieces[index].text)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            contexts = list(pool.map(describe, range(len(pieces))))

        return [
            Chunk(text=f"{context}\n{piece.text}", page=piece.page, section=piece.section,
                  start_index=piece.start_index)
            for context, piece in zip(contexts, pieces)
        ]

    def _context(self, filename: str, opening: str, before: str, passage: str) -> str:
        prompt = (
            f"Document: {filename}\n\n"
            f"How the document opens:\n{opening}\n\n"
            f"Text just before the passage:\n{before or '(the passage is the start of the document)'}\n\n"
            f"Passage:\n{passage}"
        )
        return self._fit(self._ask(prompt))

    def _ask(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.context_tokens * 2,
            "messages": [
                {"role": "system", "content": INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.openrouter_site_url,
            "X-Title": settings.openrouter_app_name,
        }
        last_error: Exception | None = None
        for _ in range(3):
            try:
                response = httpx.post(
                    f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers=headers, json=payload, timeout=settings.openrouter_timeout_seconds * 2,
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
                return " ".join(text.split())
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
        # A chunk stored without its sentence would look like a contextual
        # chunk and not be one, so the document fails instead.
        raise ValueError(f"Contextual chunking could not get a sentence from the model: "
                         f"{type(last_error).__name__}")

    def _fit(self, context: str) -> str:
        """Keep the sentence inside its share of the token budget."""
        words = context.split()
        while words and count_tokens(" ".join(words)) > self.context_tokens:
            words.pop()
        return " ".join(words)
