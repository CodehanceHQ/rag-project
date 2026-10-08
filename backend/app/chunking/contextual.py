"""Contextual chunking: say what each piece is about before embedding it.

Another strategy decides where to cut. This one then asks a language model
for one sentence that places each piece in its document, and puts that
sentence in front of the piece. A chunk reading "Set it to 230 °C" gains a
line naming the document, the product and what "it" is, so it can be found
and understood on its own.

The sentence needs a model that writes, which the embedding model cannot do.
CONTEXTUAL_PROVIDER chooses where that model runs:

    local        a model downloaded from Hugging Face and run on this machine.
                 Free and private; a few seconds per chunk.
    openrouter   a hosted model. Fast and paid: one call per chunk, with the
                 document text sent to the provider.

CONTEXTUAL_BASE_STRATEGY picks the strategy that does the cutting.
"""
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import List, Protocol

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


class Writer(Protocol):
    workers: int

    def validate(self) -> None: ...
    def write(self, prompt: str, max_tokens: int) -> str: ...


class HostedWriter:
    """A hosted model, called through OpenRouter. Paid, and fast enough to
    run several requests at once."""
    workers = 8

    def __init__(self):
        self.model = settings.contextual_model or settings.openrouter_model

    def validate(self) -> None:
        if not settings.openrouter_api_key:
            raise ValueError(
                "CONTEXTUAL_PROVIDER=openrouter needs OPENROUTER_API_KEY. "
                "Set the key, or use CONTEXTUAL_PROVIDER=local to run the model on this machine."
            )

    def write(self, prompt: str, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
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
                return response.json()["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
        raise ValueError(f"Contextual chunking could not get a sentence from the model: "
                         f"{type(last_error).__name__}")


@lru_cache(maxsize=1)
def _load_local(name: str):
    """Download (first time) and load a Hugging Face text-generation model.
    Uses the Mac's GPU when there is one, otherwise the CPU."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(
        name, dtype=torch.float16 if device == "mps" else torch.float32
    ).to(device)
    model.eval()
    return tokenizer, model, device


class LocalWriter:
    """A model from Hugging Face, run on this machine. Free and private. It
    writes one sentence at a time, so a large corpus takes a long while."""
    workers = 1
    _lock = threading.Lock()

    def __init__(self):
        self.model_name = settings.contextual_local_model

    def validate(self) -> None:
        if not self.model_name.strip():
            raise ValueError("CONTEXTUAL_PROVIDER=local needs CONTEXTUAL_LOCAL_MODEL, "
                             "the name of a Hugging Face model.")

    def write(self, prompt: str, max_tokens: int) -> str:
        import torch

        tokenizer, model, device = _load_local(self.model_name)
        messages = [{"role": "system", "content": INSTRUCTION},
                    {"role": "user", "content": prompt}]
        # enable_thinking=False asks models that can reason aloud to answer
        # directly; templates that have no such switch ignore it.
        inputs = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, enable_thinking=False,
            return_tensors="pt", return_dict=True,
        ).to(device)
        with self._lock, torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                                    pad_token_id=tokenizer.eos_token_id)
        written = output[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(written, skip_special_tokens=True)


WRITERS = {"local": LocalWriter, "openrouter": HostedWriter}
THINKING = re.compile(r"<think>.*?(</think>|$)", re.S)


class ContextualChunker:
    name = "contextual"

    def __init__(self, base: str | None = None, context_tokens: int | None = None,
                 provider: str | None = None):
        self.context_tokens = context_tokens or settings.contextual_context_tokens
        self.base_name = (base or settings.contextual_base_strategy).strip().lower()
        self.base = _base_chunker(self.base_name, token_budget() - self.context_tokens)
        self.provider = (provider or settings.contextual_provider).strip().lower()
        if self.provider not in WRITERS:
            raise ValueError(f"Unknown CONTEXTUAL_PROVIDER '{self.provider}'. "
                             f"Choose one of: {', '.join(sorted(WRITERS))}.")
        self.writer: Writer = WRITERS[self.provider]()

    def validate(self) -> None:
        self.writer.validate()

    def chunk(self, source: SourceDocument) -> List[Chunk]:
        self.validate()
        pieces = self.base.chunk(source)
        if not pieces:
            return []
        opening = "\n".join(page.page_content for page in source.pages)[:OPENING_CHARS]
        before = [""] + [piece.text[-BEFORE_CHARS:] for piece in pieces[:-1]]

        def describe(index: int) -> str:
            return self._context(source.filename, opening, before[index], pieces[index].text)

        with ThreadPoolExecutor(max_workers=self.writer.workers) as pool:
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
        written = self.writer.write(prompt, max_tokens=self.context_tokens * 2)
        # A chunk stored without its sentence would look like a contextual
        # chunk and not be one, so an empty reply fails the document.
        sentence = " ".join(THINKING.sub("", written or "").split())
        if not sentence:
            raise ValueError("Contextual chunking got an empty sentence from the model.")
        return self._fit(sentence)

    def _fit(self, context: str) -> str:
        """Keep the sentence inside its share of the token budget."""
        words = context.split()
        while words and count_tokens(" ".join(words)) > self.context_tokens:
            words.pop()
        return " ".join(words)
