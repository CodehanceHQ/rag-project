"""Recursive chunking: cut by size, preferring natural breaks.

Tries paragraph breaks first, then lines, then sentences, then words, until
every piece fits `chunk_size`. Consecutive pieces share `chunk_overlap`
characters. It knows nothing about headings or meaning, and it works page by
page, so a piece never spans two pages.
"""
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import settings
from .base import Chunk, SourceDocument


class RecursiveChunker:
    name = "recursive"

    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size or settings.chunk_size,
            chunk_overlap=settings.chunk_overlap if chunk_overlap is None else chunk_overlap,
            add_start_index=True,
        )

    def chunk(self, source: SourceDocument) -> List[Chunk]:
        return [
            Chunk(
                text=item.page_content,
                page=item.metadata.get("page"),
                section=item.metadata.get("section"),
                start_index=item.metadata.get("start_index"),
            )
            for item in self.splitter.split_documents(source.pages)
            if item.page_content.strip()
        ]

    def split_text(self, text: str) -> List[str]:
        """Split one block of text. Used by strategies that cut by structure
        first and only need this for the pieces that are still too long."""
        return [piece for piece in self.splitter.split_text(text) if piece.strip()]
