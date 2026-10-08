"""Chunking strategies. CHUNKING_STRATEGY in .env picks one by name.

    recursive    cut by size at natural breaks (the default)
    structural   one chunk per section, cut at headings
    hybrid       cut at headings, then by size inside long sections
    semantic     cut where the topic changes
    contextual   cut with another strategy, then add a model-written sentence
                 saying what each piece is about (paid: one call per chunk)
"""
from typing import Callable, Dict

from .base import Chunk, Chunker, SourceDocument
from .contextual import ContextualChunker
from .hybrid import HybridChunker
from .recursive import RecursiveChunker
from .semantic import SemanticChunker
from .structural import StructuralChunker

CHUNKERS: Dict[str, Callable[[], Chunker]] = {
    RecursiveChunker.name: RecursiveChunker,
    StructuralChunker.name: StructuralChunker,
    HybridChunker.name: HybridChunker,
    SemanticChunker.name: SemanticChunker,
    ContextualChunker.name: ContextualChunker,
}


def get_chunker(name: str) -> Chunker:
    try:
        return CHUNKERS[name.strip().lower()]()
    except KeyError:
        raise ValueError(
            f"Unknown CHUNKING_STRATEGY '{name}'. Choose one of: {', '.join(sorted(CHUNKERS))}."
        ) from None


__all__ = ["Chunk", "Chunker", "SourceDocument", "CHUNKERS", "get_chunker"]
