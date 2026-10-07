"""Find a document's sections.

For a PDF, headings are detected from typography: a heading is a bold line set
larger than the body text and smaller than the title. Nothing is read from a
side file, so this behaves on an unseen PDF the way it does on the corpus.

Other formats have no layout to read, so each unit the extractor produced
(a slide, a sheet, the whole text file) is treated as one section.
"""
import collections
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import pymupdf

from .base import SourceDocument

FRONT_MATTER = "(front matter)"


@dataclass
class Section:
    title: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    text: str


def detect_sections(source: SourceDocument) -> List[Section]:
    if Path(source.filename).suffix.lower() == ".pdf":
        found = _pdf_sections(source.data)
        if found:
            return found
    return [
        Section(
            title=page.metadata.get("section"),
            page_start=page.metadata.get("page"),
            page_end=page.metadata.get("page"),
            text=page.page_content,
        )
        for page in source.pages
        if page.page_content.strip()
    ]


def _pdf_sections(data: bytes) -> List[Section]:
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        sizes: collections.Counter = collections.Counter()
        for page in pdf:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if span["text"].strip():
                            sizes[round(span["size"], 1)] += len(span["text"])
        if not sizes:
            return []
        body = sizes.most_common(1)[0][0]      # the size most of the text is set in
        title = max(sizes)                     # the largest size is the document title

        found = [{"title": FRONT_MATTER, "page_start": 1, "page_end": 1, "lines": []}]
        for page_number, page in enumerate(pdf, start=1):
            for text, size, bold in _rows(page, body):
                if bold and body < size < title:
                    previous = found[-1]
                    if (not previous["lines"] and previous["title"] != FRONT_MATTER
                            and previous["page_start"] == page_number):
                        previous["title"] += " " + text      # a heading wrapped onto two lines
                        continue
                    found.append({"title": text, "page_start": page_number,
                                  "page_end": page_number, "lines": []})
                    continue
                found[-1]["lines"].append(text)
                found[-1]["page_end"] = page_number

    return [
        Section(title=s["title"], page_start=s["page_start"],
                page_end=max(s["page_end"], s["page_start"]), text="\n".join(s["lines"]))
        for s in found
        if s["lines"] or s["title"] != FRONT_MATTER
    ]


def _rows(page, body: float) -> List[Tuple[str, float, bool]]:
    """A page as rows of (text, font size, bold). Extraction yields one line
    per table cell; cells sharing a baseline are joined with ' | ' so a table
    row reads as a row, and a cell that wrapped onto a second line is folded
    back into the cell above it. Running headers and footers, which are set
    smaller than the body, drop out."""
    items = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            size = round(max(s["size"] for s in spans), 1)
            if size < body - 1:
                continue
            items.append({
                "y": round(line["bbox"][1]), "x": line["bbox"][0],
                "text": " ".join(s["text"].strip() for s in spans), "size": size,
                "bold": all("Bold" in s["font"] or s["flags"] & 16 for s in spans),
            })
    items.sort(key=lambda item: (item["y"], item["x"]))

    lines: List[list] = []
    for item in items:
        if lines and abs(lines[-1][0]["y"] - item["y"]) <= 2:
            lines[-1].append(item)
        else:
            lines.append([item])

    rows: List[Tuple[str, float, bool]] = []
    previous = None                     # cells of the last table row, for wrapped cells
    for cells in lines:
        cells.sort(key=lambda cell: cell["x"])
        if (previous and len(previous) > 1 and cells[0]["x"] > previous[0]["x"] + 5
                and cells[0]["y"] - previous[0]["y"] < 2.2 * cells[0]["size"]):
            for cell in cells:
                home = max((p for p in previous if p["x"] <= cell["x"] + 2),
                           key=lambda p: p["x"], default=previous[-1])
                home["text"] += " " + cell["text"]
            rows[-1] = (" | ".join(p["text"] for p in previous), rows[-1][1], rows[-1][2])
            continue
        rows.append((" | ".join(cell["text"] for cell in cells),
                     max(cell["size"] for cell in cells),
                     all(cell["bold"] for cell in cells)))
        previous = cells
    return rows
