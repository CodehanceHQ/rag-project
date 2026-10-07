"""What every chunking strategy shares: its input, its output, and its shape.

A strategy takes one extracted document and returns the pieces that will be
embedded and stored. Nothing else in ingestion depends on how it decided
where to cut.
"""
from dataclasses import dataclass
from typing import List, Optional, Protocol

from langchain_core.documents import Document


@dataclass
class SourceDocument:
    """One uploaded file, as the extractor left it. `data` is the original
    bytes, kept because finding headings needs the layout, not just the text."""
    filename: str
    data: bytes
    pages: List[Document]


@dataclass
class Chunk:
    text: str                           # what gets embedded and stored
    page: Optional[int] = None
    section: Optional[str] = None
    start_index: Optional[int] = None


class Chunker(Protocol):
    name: str

    def chunk(self, source: SourceDocument) -> List[Chunk]: ...
