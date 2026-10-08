"""Structural chunking: one chunk per section.

Cuts at the document's own headings and nowhere else, so a chunk is a unit
the author intended. Unlike the other strategies it applies no size limit: a
long section stays whole, which means the embedding model may only read the
start of it. That weakness is what the hybrid strategy addresses.
"""
from typing import List

from .base import Chunk, SourceDocument
from .sections import detect_sections


class StructuralChunker:
    name = "structural"

    def chunk(self, source: SourceDocument) -> List[Chunk]:
        return [
            Chunk(
                text=f"{section.title}\n{section.text}" if section.title else section.text,
                page=section.page_start,
                section=section.title,
            )
            for section in detect_sections(source)
            if section.text.strip()
        ]
