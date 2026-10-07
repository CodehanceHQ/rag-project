"""Semantic chunking: cut where the topic changes.

Splits the document into sentences, embeds each one, and measures how similar
each sentence is to the next. A sharp drop in similarity is a change of
subject, and that is where a chunk ends. No headings are needed, at the price
of embedding every sentence once before the chunks themselves are embedded.
"""
import re
from typing import List, Optional, Tuple

import numpy as np

from ..config import settings
from ..embeddings import get_embeddings
from .base import Chunk, SourceDocument

SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n{2,}")


class SemanticChunker:
    name = "semantic"

    def __init__(self, breakpoint_percentile: float | None = None,
                 max_chars: int | None = None, min_chars: int = 200):
        self.breakpoint_percentile = (
            settings.semantic_breakpoint_percentile
            if breakpoint_percentile is None else breakpoint_percentile
        )
        self.max_chars = max_chars or settings.chunk_size
        self.min_chars = min_chars

    def chunk(self, source: SourceDocument) -> List[Chunk]:
        sentences = self._sentences(source)
        if not sentences:
            return []
        if len(sentences) == 1:
            return [Chunk(text=sentences[0][0], page=sentences[0][1])]

        # Vectors are normalised, so the dot product of neighbours is their
        # cosine similarity.
        vectors = np.array(get_embeddings().embed_documents([text for text, _ in sentences]))
        similarity = np.sum(vectors[:-1] * vectors[1:], axis=1)
        # A break is a similarity low enough to fall outside the usual range
        # for this document: with a percentile of 90, the lowest 10%.
        threshold = np.percentile(similarity, 100 - self.breakpoint_percentile)

        chunks: List[Chunk] = []
        current: List[str] = [sentences[0][0]]
        page = sentences[0][1]
        for index, (text, sentence_page) in enumerate(sentences[1:]):
            length = sum(len(s) for s in current) + len(current)
            topic_changed = similarity[index] < threshold and length >= self.min_chars
            too_long = length + len(text) > self.max_chars
            if topic_changed or too_long:
                chunks.append(Chunk(text=" ".join(current), page=page))
                current, page = [], sentence_page
            current.append(text)
        chunks.append(Chunk(text=" ".join(current), page=page))
        return chunks

    def _sentences(self, source: SourceDocument) -> List[Tuple[str, Optional[int]]]:
        out: List[Tuple[str, Optional[int]]] = []
        for page in source.pages:
            for sentence in SENTENCE_END.split(page.page_content):
                sentence = " ".join(sentence.split())
                # One "sentence" with no full stop, such as a table, would
                # otherwise become a single oversized piece.
                while len(sentence) > self.max_chars:
                    cut = sentence.rfind(" ", 0, self.max_chars)
                    cut = cut if cut > 0 else self.max_chars
                    out.append((sentence[:cut], page.metadata.get("page")))
                    sentence = sentence[cut:].strip()
                if sentence:
                    out.append((sentence, page.metadata.get("page")))
        return out
