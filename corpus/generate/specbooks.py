"""The two editions of the Product Specification Book, 2024 and 2025.

These are the long documents in the corpus, and they carry facts several
questions depend on, so they are built from a seed rather than typed out. The
two editions share one layout and differ in exactly the places the manifest
says they must:

  edition  status       flour for SD-12             must never mention
  2024     superseded   Golden Field flour          Heritage Stoneground, RC-88
  2025     current      Heritage Stoneground flour  Golden Field, "formerly"

Rules built in here, each checked by corpus/tests/verify_corpus.py:
  - the page header carries no year, so a chunk from the middle of either
    edition cannot say which edition it came from (cl03_edition_orphaned)
  - Cedar Valley Mill sources Country Sourdough (SD-13) lines only, never a
    Classic Sourdough (SD-12) line or a common ingredient (cedar_not_sd12)
  - the two products sit in the same table layout, told apart only by name
    and code (mh03_identity)
  - no site is named anywhere (multihop_supplier)
"""
import pathlib, random

SRC = pathlib.Path(__file__).resolve().parents[1] / "source"
ALDER, BIRCH, CEDAR = "Alder Mill", "Birch Lane Mill", "Cedar Valley Mill"
PER_PAGE = 22

LINE_ITEMS = ["flour, sack", "flour, bulk", "wholemeal flour", "rye flour", "fine salt",
              "coarse salt", "starter feed flour", "dusting flour", "semolina", "malt flour",
              "bread bag, paper", "bread bag, window", "closure tag", "ingredient label",
              "date label", "tray liner", "crate liner", "proving cloth", "baking parchment",
              "scoring blade", "cooling tray card", "allergen card"]
COMMON_ITEMS = ["fine salt", "coarse salt", "water treatment filter", "starter culture feed",
                "dusting semolina", "baking parchment", "tray liner", "crate liner",
                "closure tag", "date label", "cleaning-down sanitiser", "proving cloth"]

EDITIONS = {
    2024: dict(doc_id="PSB-E4", edition="Edition 4", flour="Golden Field flour", seed=2024,
               pages=(15, 14, 8),
               front="status: Superseded\neffective_date: 1 January 2024\nsuperseded_date: 1 January 2025\n"),
    2025: dict(doc_id="PSB-E5", edition="Edition 5", flour="Heritage Stoneground flour", seed=2025,
               pages=(18, 17, 9), front=""),
}


def table(header, rows):
    out = [f"| {' | '.join(header)} |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def spec_table(name, code, shelf_life, flour, weight, sources):
    return table(["Field", "Value"], [
        ["Product", name], ["Product code", code], ["Shelf life", shelf_life],
        ["Flour", flour], ["Baked weight", weight], ["Approved flour sources", "; ".join(sources)],
    ])


def line_tables(prefix, items, sources, pages, rnd):
    rows = []
    for i in range(pages * PER_PAGE):
        rows.append([f"{prefix}-{i+1:04d}", f"{prefix}-{rnd.randint(10000, 99999)}",
                     rnd.choice(items), rnd.choice(sources),
                     rnd.choice(["each", "kg", "pack of 50", "roll", "sack"])])
    parts = []
    for i in range(0, len(rows), PER_PAGE):
        parts.append(table(["Item", "Line reference", "Description", "Source", "Unit"],
                           rows[i:i + PER_PAGE]))
    return "\n\n<!--page-break-->\n\n".join(parts)


def build(year):
    e = EDITIONS[year]
    rnd = random.Random(e["seed"])
    classic, country, common = e["pages"]
    return f"""---
file: product_specifications_{year}.pdf
title: Product Specification Book — Sourdough Range
header: Product Specification Book
header_right: Sourdough Range
doc_id: {e['doc_id']}
revision: {e['edition']}
author_function: Product Development
date: {year}-01
{e['front']}tier: authored
---

## 1. Introduction and revision history

This book states the specification of each product in the sourdough range and
lists the ingredient and packaging lines used to make it. It is the reference
for purchasing, production and labelling.

| Field | Entry |
| --- | --- |
| Book | Product Specification Book, Sourdough Range |
| Edition | {e['edition']} |
| Issued | {year}-01 |
| Issued by | Product Development |

Each product has one specification table followed by its line items. Where two
products appear similar, the product name and product code in the
specification table are the only reliable way to tell them apart.

Line items are listed in the order they were raised. A line item names the
source approved for that line. Site approvals are not recorded in this book.

## 2. Classic Sourdough (SD-12)

{spec_table("Classic Sourdough", "SD-12", "4 days", e['flour'], "800 g", [ALDER, BIRCH])}

The lines below are those raised against this product.

{line_tables("C12", LINE_ITEMS, [ALDER, BIRCH], classic, rnd)}

## 3. Country Sourdough (SD-13)

{spec_table("Country Sourdough", "SD-13", "6 days", "Wholemeal Country flour", "900 g", [ALDER, CEDAR])}

The lines below are those raised against this product.

{line_tables("C13", LINE_ITEMS, [ALDER, CEDAR], country, rnd)}

## 4. Common ingredients

Lines in this section are used by more than one product in the range and are
not raised against either product alone.

{line_tables("CMN", COMMON_ITEMS, [ALDER, BIRCH], common, rnd)}

## 5. Approved supplier index

The index lists each approved source and the sections of this book in which it
appears.

{table(["Source", "Classic Sourdough lines", "Country Sourdough lines", "Common ingredients"], [
    [ALDER, "Yes", "Yes", "Yes"],
    [BIRCH, "Yes", "No", "Yes"],
    [CEDAR, "No", "Yes", "No"],
])}

A source appears against a section only where a line in that section names it.
The index is rebuilt from the line items at each edition and is not maintained
separately.
"""


if __name__ == "__main__":
    for year in EDITIONS:
        (SRC / f"product_specifications_{year}.md").write_text(build(year))
        print(f"product_specifications_{year}.md written")
