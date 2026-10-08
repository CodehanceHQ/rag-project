"""The two documents whose job is to defeat text extraction. Built as PDFs
directly — there is no Markdown source, because there is no text layer to
author. See document-spec.yaml, tier: special."""
import json, pathlib
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as canvasmod

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT, SECT = ROOT/"corpus/documents", ROOT/"corpus/sections"
TMP = ROOT/"corpus/render/_tmp"; TMP.mkdir(parents=True, exist_ok=True)


def scanned_cert():
    """Image-only. No text layer at all — this is the point, and it is why
    backend/app/extractors.py:_extract_pdf currently RAISES on it."""
    lines = [
        ("DELIVERY INSPECTION CERTIFICATE", 30), ("Certificate no.  IC-2025-0884", 20),
        ("", 10), ("Issued by       Goods Inwards", 18),
        ("Date            2025-04-18", 18), ("Delivery ref.   DN-2025-0907", 18),
        ("", 10), ("CHARACTERISTIC            SPECIFIED      MEASURED     RESULT", 16),
        ("Sack weight               within order    conforming   PASS", 16),
        ("Sack seal                 intact          conforming   PASS", 16),
        ("Moisture                  within limit    conforming   PASS", 16),
        ("Visual, external          free of damage  conforming   PASS", 16),
        ("Identification            legible         conforming   PASS", 16),
        ("", 10), ("Sample size     30", 18), ("Accepted        30", 18),
        ("Rejected         0", 18), ("", 14),
        ("Inspected by    ......................................", 16),
        ("Countersigned   ......................................", 16),
    ]
    W, H = 1654, 2339                      # A4 at 200 dpi
    for page in range(1, 5):
        img = Image.new("L", (W, H), 246)
        d = ImageDraw.Draw(img)
        d.rectangle([90, 90, W-90, H-90], outline=140, width=3)
        y = 190
        for text, size in lines:
            try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New.ttf", size*2)
            except Exception: f = ImageFont.load_default()
            d.text((150, y), text, fill=55, font=f)
            y += size*2 + 22
        d.text((150, H-220), f"Page {page} of 4", fill=90)
        for x in range(0, W, 7):           # scan noise
            img.putpixel((x, (x*13) % H), 205)
        img = img.rotate(0.35, fillcolor=246, resample=Image.BICUBIC)
        img.save(TMP/f"cert_{page}.png")

    path = OUT/"inspection_cert_scanned.pdf"
    c = canvasmod.Canvas(str(path), pagesize=A4)
    for page in range(1, 5):
        c.drawImage(str(TMP/f"cert_{page}.png"), 0, 0, width=A4[0], height=A4[1])
        c.showPage()
    c.save()
    return path, 4


def floor_layout():
    """Callouts positioned around a drawing. The numbers mean nothing without
    the picture, which is the parsing challenge."""
    path = OUT/"bakery_floor_layout_diagram.pdf"
    c = canvasmod.Canvas(str(path), pagesize=A4)
    W, H = A4
    for page, title in enumerate(["Sheet 1 — Floor layout", "Sheet 2 — Callout index"], 1):
        c.setFont("Helvetica-Bold", 11); c.drawString(20*mm, H-20*mm, title)
        c.setLineWidth(0.8)
        if page == 1:
            ys = [H-60*mm - i*22*mm for i in range(6)]
            for i, y in enumerate(ys, 1):
                c.rect(70*mm, y, 60*mm, 14*mm)
                c.line(70*mm, y+7*mm, 45*mm, y+7*mm)
                c.setFont("Helvetica", 9); c.drawRightString(43*mm, y+5*mm, str(i))
                c.line(130*mm, y+7*mm, 155*mm, y+7*mm)
                c.drawString(157*mm, y+5*mm, str(i+6))
        else:
            c.setFont("Helvetica", 9)
            for i in range(1, 13):
                c.drawString(25*mm, H-40*mm - i*8*mm, str(i))
                c.line(32*mm, H-40*mm - i*8*mm + 1*mm, 60*mm, H-40*mm - i*8*mm + 1*mm)
        c.setFont("Helvetica", 7.5); c.drawRightString(W-20*mm, 12*mm, f"Page {page} of 2")
        c.showPage()
    c.save()
    return path, 2


if __name__ == "__main__":
    for fn, pages in (scanned_cert(), floor_layout()):
        (SECT/f"{fn.stem}.sections.json").write_text(json.dumps(
            {"file": fn.name, "pages_total": pages, "sections": [],
             "note": "PDF-native, no authored sections"}, indent=2))
        print(f"{fn.name}  {pages} pages")
