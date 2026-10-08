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
from ..embeddings import count_tokens, get_embeddings, token_budget
from .base import Chunk, SourceDocument
from .recursive import RecursiveChunker

# A sentence ends at ., ! or ? followed by space, or at a blank line. A bare
# number and a full stop ("3. Oven temperature bands") is a heading or list
# number, not the end of a sentence. The separator is captured so the pieces
# can be put back together the way they were laid out.
SENTENCE_END = re.compile(r"((?<=[.!?])(?<!\s\d\.)(?<!\s\d\d\.)\s+|\n{2,})")


def _tidy(text: str) -> str:
    """Collapse runs of spaces but keep line breaks, so a table row stays a row."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


class SemanticChunker:
    name = "semantic"

    def __init__(self, breakpoint_percentile: float | None = None,
                 max_tokens: int | None = None, min_tokens: int = 50):
        self.breakpoint_percentile = (
            settings.semantic_breakpoint_percentile
            if breakpoint_percentile is None else breakpoint_percentile
        )
        self.max_tokens = max_tokens or token_budget()
        self.min_tokens = min_tokens
        self.splitter = RecursiveChunker(chunk_tokens=self.max_tokens, overlap_tokens=0)

    def chunk(self, source: SourceDocument) -> List[Chunk]:
        sentences = self._sentences(source)
        if not sentences:
            return []
        if len(sentences) == 1:
            return [Chunk(text=sentences[0][0], page=sentences[0][1])]

        # Vectors are normalised, so the dot product of neighbours is their
        # cosine similarity.
        vectors = np.array(get_embeddings().embed_documents([text for text, _, _ in sentences]))
        similarity = np.sum(vectors[:-1] * vectors[1:], axis=1)
        # A break is a similarity low enough to fall outside the usual range
        # for this document: with a percentile of 90, the lowest 10%.
        threshold = np.percentile(similarity, 100 - self.breakpoint_percentile)

        chunks: List[Chunk] = []
        current = sentences[0][0]
        page = sentences[0][1]
        for index, (text, sentence_page, joiner) in enumerate(sentences[1:]):
            topic_changed = (similarity[index] < threshold
                             and count_tokens(current) >= self.min_tokens)
            too_long = count_tokens(current + joiner + text) > self.max_tokens
            if topic_changed or too_long:
                chunks.append(Chunk(text=current, page=page))
                current, page = text, sentence_page
            else:
                current += joiner + text
        chunks.append(Chunk(text=current, page=page))
        return chunks

    def _sentences(self, source: SourceDocument) -> List[Tuple[str, Optional[int], str]]:
        """Every sentence as (text, page, joiner), where the joiner is what
        goes between it and the sentence before: a line break if they were on
        separate lines, otherwise a space."""
        out: List[Tuple[str, Optional[int], str]] = []
        for page in source.pages:
            number = page.metadata.get("page")
            parts = SENTENCE_END.split(page.page_content)
            joiner = "\n"                        # a new page starts on a new line
            for position in range(0, len(parts), 2):
                # A block with no full stop, such as a table, can be longer
                # than the model reads. Cut it between rows where possible.
                for sentence in self.splitter.split_text(_tidy(parts[position])):
                    out.append((sentence.strip(), number, joiner))
                    joiner = "\n"
                separator = parts[position + 1] if position + 1 < len(parts) else ""
                joiner = "\n" if "\n" in separator else " "
        return out
