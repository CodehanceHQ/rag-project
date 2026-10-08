"""Hybrid chunking: structure first, size second.

Cuts at headings like the structural strategy, then splits any section that
is still too long for the embedding model with the recursive splitter, so no
piece crosses a heading.
Every piece starts with a line naming its document and section, so a piece
from the middle of a section still says where it came from.
"""
from typing import List

from ..embeddings import count_tokens
from .base import Chunk, SourceDocument
from .recursive import RecursiveChunker
from .sections import detect_sections


class HybridChunker:
    name = "hybrid"

    def __init__(self, inner: RecursiveChunker | None = None):
        self.inner = inner or RecursiveChunker()

    def chunk(self, source: SourceDocument) -> List[Chunk]:
        chunks: List[Chunk] = []
        for section in detect_sections(source):
            if not section.text.strip():
                continue
            heading = " › ".join(part for part in (source.filename, section.title) if part)
            # The heading line is embedded too, so it comes out of the budget.
            reserve = count_tokens(heading + "\n")
            for piece in self.inner.split_text(section.text, reserve=reserve):
                chunks.append(Chunk(text=f"{heading}\n{piece}", page=section.page_start,
                                    section=section.title))
        return chunks
