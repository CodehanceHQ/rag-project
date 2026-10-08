"""Recursive chunking: cut by size, preferring natural breaks.

Tries paragraph breaks first, then lines, then sentences, then words, until
every piece fits the token budget. Consecutive pieces share a few tokens of
overlap. It knows nothing about headings or meaning, and it works page by
page, so a piece never spans two pages.

Size is counted in the embedding model's tokens, not characters. A table of
part numbers uses far more tokens per character than prose, and anything past
the model's limit would be stored but never embedded.
"""
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import settings
from ..embeddings import count_tokens, token_budget
from .base import Chunk, SourceDocument


class RecursiveChunker:
    name = "recursive"

    def __init__(self, chunk_tokens: int | None = None, overlap_tokens: int | None = None):
        self.chunk_tokens = chunk_tokens or token_budget()
        self.overlap_tokens = (
            settings.chunk_overlap_tokens if overlap_tokens is None else overlap_tokens
        )

    def _splitter(self, reserve: int = 0) -> RecursiveCharacterTextSplitter:
        size = max(self.chunk_tokens - reserve, 32)
        return RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=min(self.overlap_tokens, size // 2),
            length_function=count_tokens,
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
            for item in self._splitter().split_documents(source.pages)
            if item.page_content.strip()
        ]

    def split_text(self, text: str, reserve: int = 0) -> List[str]:
        """Split one block of text, leaving `reserve` tokens free in each
        piece. Used by strategies that cut by structure or meaning first and
        only need this for what is still too long."""
        return [piece for piece in self._splitter(reserve).split_text(text) if piece.strip()]
