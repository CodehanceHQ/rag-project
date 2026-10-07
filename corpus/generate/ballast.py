"""Ballast tier: 49 documents, template plus seeded tables. No model.

negatives.ballast_vocabulary: ballast varies WORDING, never VOCABULARY.

The co-occurrence trap is designed out structurally rather than checked for.
Every ballast document has a SCOPE: it is either plant-scoped (may name
plants, never names a part) or part-scoped (may name parts, never names a
plant). No ballast document can therefore put BV-12 next to Bamberg, which is
the single invention that would collapse mh-01 and take pages 03, 06 and 07
with it.
"""
import pathlib, random

SRC = pathlib.Path(__file__).resolve().parents[1] / "source"
PLANTS = ["Plant X (Bamberg)", "Plant Y (Kassel)", "Plant Z (Ingolstadt)"]
SUPPLIERS = ["Alpha Dichtungen GmbH", "Beta Valve Co.", "Gamma Sealing Systems"]
PARTS = ["BV-12", "BV-13"]
GENERIC = ["valve body", "housing", "cover plate", "spindle", "seat ring", "retainer",
           "spacer", "gland", "bush", "washer set", "fastener kit", "spring", "guide",
           "plug", "bracket", "dowel", "shim", "clip", "insert", "bearing"]

KINDS = [
    ("Calibration Log",          "CAL", "plant", ["1. Instruments", "2. Calibration record", "3. Overdue items"]),
    ("Goods Receipt Register",   "GRR", "part",  ["1. Receipts", "2. Inspection status", "3. Discrepancies"]),
    ("Shift Handover Record",    "SHO", "plant", ["1. Shift summary", "2. Carried items", "3. Staffing"]),
    ("Maintenance Schedule",     "MTS", "plant", ["1. Planned tasks", "2. Completion record", "3. Deferred tasks"]),
    ("Training Record",          "TRN", "plant", ["1. Competences", "2. Attendance", "3. Renewals due"]),
    ("Packaging Specification",  "PKG", "part",  ["1. Pack configuration", "2. Materials", "3. Labelling"]),
    ("Shipping Manifest",        "SHP", "part",  ["1. Consignment", "2. Line items", "3. Documentation"]),
    ("Internal Audit Checklist", "AUD", "plant", ["1. Scope", "2. Checklist", "3. Findings"]),
]

FRAMING = [
    "This record is maintained by the issuing function and reissued at the interval stated in the controlling procedure.",
    "Entries are recorded as observed at the time of the activity and are not amended retrospectively.",
    "Figures are stated as booked and cover the period shown above only.",
    "Where an entry is incomplete it is carried to the following period and shown again.",
    "Queries on an entry should be directed to the issuing function, quoting the reference above.",
    "This document does not confer authority and does not record approval of any change.",
]


def rows(kind, scope, rnd, n):
    out = []
    for i in range(n):
        subject = rnd.choice(PLANTS) if scope == "plant" else rnd.choice(GENERIC)
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
author_function: {rnd.choice(['Manufacturing Operations','Quality Management System','Facilities','Procurement'])}
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
