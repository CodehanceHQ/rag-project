"""Ballast tier: 49 documents, template plus seeded tables. No model.

negatives.ballast_vocabulary: ballast varies WORDING, never VOCABULARY.

The co-occurrence trap is designed out structurally rather than checked for.
Every ballast document has a SCOPE: it is either site-scoped (may name sites,
never names a product) or item-scoped (names generic items, never a site or a
product). No ballast document can therefore put SD-12 next to High Street,
which is the single invention that would collapse mh-01.
"""
import pathlib, random

SRC = pathlib.Path(__file__).resolve().parents[1] / "source"
SITES = ["High Street bakery", "Riverside bakery", "Station Road bakery"]
GENERIC = ["baking tray", "bread crate", "paper bag", "cooling rack", "dough scraper",
           "proving basket", "bench brush", "oven glove", "bread knife", "label roll",
           "cleaning cloth", "hand soap", "apron", "hair net", "flour scoop",
           "measuring jug", "mixing bowl", "till roll", "price ticket", "delivery cage"]

KINDS = [
    ("Fridge Temperature Log",   "FTL", "site", ["1. Units", "2. Temperature record", "3. Out-of-range readings"]),
    ("Goods Received Register",  "GRR", "item", ["1. Receipts", "2. Inspection status", "3. Discrepancies"]),
    ("Shift Handover Record",    "SHO", "site", ["1. Shift summary", "2. Carried items", "3. Staffing"]),
    ("Oven Maintenance Schedule","OMS", "site", ["1. Planned tasks", "2. Completion record", "3. Deferred tasks"]),
    ("Training Record",          "TRN", "site", ["1. Competences", "2. Attendance", "3. Renewals due"]),
    ("Packaging Specification",  "PKG", "item", ["1. Pack configuration", "2. Materials", "3. Labelling"]),
    ("Delivery Manifest",        "DLV", "item", ["1. Consignment", "2. Line items", "3. Documentation"]),
    ("Hygiene Audit Checklist",  "HYG", "site", ["1. Scope", "2. Checklist", "3. Findings"]),
]

FRAMING = [
    "This record is maintained by the issuing function and reissued at the interval stated in the controlling procedure.",
    "Entries are recorded as observed at the time of the activity and are not amended afterwards.",
    "Figures are stated as booked and cover the period shown above only.",
    "Where an entry is incomplete it is carried to the following period and shown there.",
    "Queries on an entry should be directed to the issuing function, quoting the reference above.",
    "This document does not confer authority and does not record approval of any change.",
]


def rows(kind, scope, rnd, n):
    out = []
    for i in range(n):
        subject = rnd.choice(SITES) if scope == "site" else rnd.choice(GENERIC)
        out.append((f"{i+1:04d}",
                    f"{kind}-{rnd.randint(1000,9999)}",
                    subject,
                    rnd.choice(["Conforming", "Complete", "Carried", "Verified", "Closed"]),
                    f"2025-{rnd.randint(1,12):02d}-{rnd.randint(1,28):02d}"))
    return out


def table(chunk, header):
    o = [f"| {' | '.join(header)} |", "| " + " | ".join("---" for _ in header) + " |"]
    o += ["| " + " | ".join(c) + " |" for c in chunk]
    return "\n".join(o)


def build(n):
    rnd = random.Random(90000 + n)
    title, code, scope, sections = KINDS[n % len(KINDS)]
    seq = n // len(KINDS) + 1
    doc_id = f"{code}-2025-{n+1:03d}"
    fname = f"ballast_{code.lower()}_{n+1:03d}"
    # sized so the corpus lands near meta.scale.pages_total (~2000). Ballast
    # carries the bulk of the page count and costs nothing to lengthen.
    per_page, pages_per_section = 22, rnd.randint(8, 13)
    header = ["Ref", "Record", "Subject", "Status", "Date"]

    parts = [f"""---
file: {fname}.pdf
title: {title} — Series {seq}
header: {title}
header_right: Series {seq}
doc_id: {doc_id}
revision: Issue {rnd.randint(1,9)}
author_function: {rnd.choice(['Bakery Operations','Food Safety','Facilities','Purchasing'])}
date: 2025-{rnd.randint(1,12):02d}
tier: ballast
---
"""]
    for sec in sections:
        parts.append(f"\n## {sec}\n\n{rnd.choice(FRAMING)}\n")
        data = rows(code, scope, rnd, per_page * pages_per_section)
        for i in range(0, len(data), per_page):
            parts.append("\n" + table(data[i:i+per_page], header) + "\n")
            if i + per_page < len(data):
                parts.append("\n<!--page-break-->\n")
        parts.append(f"\n{rnd.choice(FRAMING)}\n")
    return fname, "".join(parts)


if __name__ == "__main__":
    for n in range(49):
        fname, body = build(n)
        (SRC / f"{fname}.md").write_text(body)
    print("49 ballast documents written")
