"""Markdown -> PDF, with a ground-truth sections sidecar.

Rules (see corpus/document-spec.yaml, decision 1):
  #   document title          renders in the title block on page 1
  ##  numbered section        starts a new page, except the first
  <!--page-break-->           forces a break
  | a | b |                   markdown table
Everything else flows. Page ranges are recorded from the ACTUAL layout, never
authored — the sidecar is true by construction.
"""
import json, pathlib, re, sys, yaml
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as canvasmod
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC, OUT, SECT = ROOT/"corpus/source", ROOT/"corpus/documents", ROOT/"corpus/sections"

BODY = ParagraphStyle("body", fontName="Times-Roman", fontSize=10.5, leading=14.5,
                      spaceAfter=7, alignment=TA_LEFT)
H2   = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                      spaceAfter=9, spaceBefore=0)
RECORD = ParagraphStyle("record", fontName="Helvetica", fontSize=9, leading=12.5,
                        textColor=colors.HexColor("#333333"), spaceAfter=1)
TITLE= ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=3)
SUB  = ParagraphStyle("sub", fontName="Helvetica", fontSize=9, leading=12,
                      textColor=colors.HexColor("#444444"), spaceAfter=14)


class SectionMark(Flowable):
    """Zero-height flowable that records the page it lands on."""
    def __init__(self, title, sink):
        super().__init__(); self.title, self.sink = title, sink
        self.width = self.height = 0
    def draw(self):
        self.sink.append((self.title, self.canv.getPageNumber()))


class NumberedCanvas(canvasmod.Canvas):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw); self._saved = []; self.meta = kw.pop("meta", {})
    def showPage(self):
        self._saved.append(dict(self.__dict__)); self._startPage()
    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state); self._furniture(total); super().showPage()
        super().save()
    def _furniture(self, total):
        m = getattr(self, "docmeta", {})
        w, h = A4
        self.setFont("Helvetica", 7.5); self.setFillColor(colors.HexColor("#555555"))
        # `header` overrides what is PRINTED on each page. It matters: page
        # furniture is extracted into every page's text, so a header carrying
        # an edition year would put that year in every chunk and defeat
        # cl-03, whose whole point is that the raw chunk is anonymous and only
        # the title-prefix fix rescues it. `title` stays full for metadata.
        self.drawString(20*mm, h-12*mm, f"{m.get('header') or m.get('title','')}")
        self.drawRightString(w-20*mm, h-12*mm, f"{m.get('header_right', m.get('revision','')) or ''}")
        self.setStrokeColor(colors.HexColor("#bbbbbb")); self.setLineWidth(0.4)
        self.line(20*mm, h-14*mm, w-20*mm, h-14*mm)
        self.line(20*mm, 16*mm, w-20*mm, 16*mm)
        self.drawString(20*mm, 12*mm, f"{m.get('doc_id','')}")
        self.drawRightString(w-20*mm, 12*mm, f"Page {self.getPageNumber()} of {total}")


def inline(t):
    """Escape for reportlab, then convert **bold** and `code`."""
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", t)
    return t


def parse(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    fm, body = (yaml.safe_load(m.group(1)), m.group(2)) if m else ({}, text)
    blocks, buf, tbl = [], [], []
    def flush_p():
        if buf: blocks.append(("p", " ".join(buf))); buf.clear()
    def flush_t():
        if tbl: blocks.append(("table", list(tbl))); tbl.clear()
    for line in body.split("\n"):
        st = line.strip()
        if st.startswith("|"):
            flush_p()
            cells = [c.strip() for c in st.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells): tbl.append(cells)
            continue
        flush_t()
        if st.startswith("## "): flush_p(); blocks.append(("h2", st[3:]))
        elif st == "<!--page-break-->": flush_p(); blocks.append(("break", None))
        elif not st: flush_p()
        else: buf.append(st)
    flush_p(); flush_t()
    return fm, blocks


def build(md_path):
    fm, blocks = parse(md_path.read_text())
    OUT.mkdir(parents=True, exist_ok=True); SECT.mkdir(parents=True, exist_ok=True)
    pdf_path = OUT / fm["file"]
    marks = []

    story = [Paragraph(inline(fm["title"]), TITLE),
             Paragraph(f"{fm['author_function']} · {fm['date']} · {fm.get('revision','')}", SUB)]

    # Line-anchored record header, emitted only when the front matter declares
    # a status or an effective date. backend/app/source_metadata.py reads these
    # with ^Key:\s*(.+)$ under re.MULTILINE, so each must be its own line and
    # must land inside the first 8000 characters. Putting this in a table —
    # which is what the first cut did — means it is never matched and every
    # document ingests as `current`, so the supersession filter does nothing.
    if fm.get("status") or fm.get("effective_date"):
        for label, key in (("Document ID", "doc_id"), ("Owner", "author_function"),
                           ("Status", "status"), ("Effective date", "effective_date"),
                           ("Superseded date", "superseded_date")):
            val = fm.get(key)
            if val:
                story.append(Paragraph(f"{label}: {val}", RECORD))
        story.append(Spacer(1, 8))
    first = True
    for kind, val in blocks:
        if kind == "h2":
            if not first: story.append(PageBreak())
            first = False
            story += [SectionMark(val, marks), Paragraph(inline(val), H2)]
        elif kind == "break": story.append(PageBreak())
        elif kind == "p": story.append(Paragraph(inline(val), BODY))
        elif kind == "table":
            data = [[Paragraph(inline(c), BODY) for c in row] for row in val]
            ncol = max(len(r) for r in val)
            avail = 160*mm
            widths = [55*mm, 105*mm] if ncol == 2 else [avail/ncol]*ncol
            data = [row + [""]*(ncol-len(row)) for row in data]
            t = Table(data, hAlign="LEFT", colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#999999")),
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eeeeee")),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
                ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
            story += [Spacer(1, 3), t, Spacer(1, 9)]

    doc = BaseDocTemplate(str(pdf_path), pagesize=A4,
                          leftMargin=20*mm, rightMargin=20*mm,
                          topMargin=20*mm, bottomMargin=22*mm, title=fm["title"])
    doc.addPageTemplates([PageTemplate(id="main", frames=[
        # leftPadding=0 matters: reportlab's default 6pt inset makes pymupdf
        # emit every body line with a leading space, which breaks the
        # ^Key:\s*(.+)$ anchors in backend/app/source_metadata.py and silently
        # ingests every document as `current`.
        Frame(20*mm, 22*mm, A4[0]-40*mm, A4[1]-44*mm, id="f",
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)])])

    def mk(*a, **kw):
        c = NumberedCanvas(*a, **kw); c.docmeta = fm; return c
    doc.build(story, canvasmaker=mk)

    total = _page_count(pdf_path)
    sections = []
    for i, (title, start) in enumerate(marks):
        end = marks[i+1][1]-1 if i+1 < len(marks) else total
        sections.append({"section": title, "page_start": start, "page_end": end,
                         "pages": f"{start}-{end}" if start != end else str(start)})
    sidecar = {"file": fm["file"], "doc_id": fm.get("doc_id"), "date": str(fm.get("date")),
               "pages_total": total, "sections": sections}
    (SECT / (pdf_path.stem + ".sections.json")).write_text(json.dumps(sidecar, indent=2))
    return pdf_path, sidecar


def _page_count(path):
    import pymupdf
    with pymupdf.open(path) as d: return d.page_count


if __name__ == "__main__":
    targets = sys.argv[1:] or [p.name for p in sorted(SRC.glob("*.md"))]
    for name in targets:
        p, side = build(SRC / name)
        print(f"{p.relative_to(ROOT)}  {side['pages_total']} pages")
        for s in side["sections"]:
            print(f"    p{s['pages']:<6} {s['section']}")
