"""Constrained tier: 12 rework monthlies + 6 change requests.

Seeded. The answers to ag-01, ag-02 and ag-03 are DESIGNED here and asserted
before anything is written — see negatives.aggregation_needs_all,
ag02_no_register and ag03_pivot_discovered.
"""
import pathlib, random

SRC = pathlib.Path(__file__).resolve().parents[1] / "source"
MONTHS = ["January","February","March","April","May","June",
          "July","August","September","October","November","December"]
PLANTS = ["Plant X (Bamberg)", "Plant Y (Kassel)", "Plant Z (Ingolstadt)"]
PIVOT = 6                       # CR-91, 2025-06 -> months 1-5 before, 7-12 after

# ---- designed, then verified -------------------------------------------------
# The shape is the constraint. Ingolstadt must win on the TOTAL while never
# being the worst in any single month, or one report answers ag-01 and
# negatives.aggregation_needs_all fails. So Ingolstadt runs high and steady,
# and the other two alternate spikes above it — each spiking site accumulates
# less over the year than Ingolstadt's steady rate.
random.seed(20250928)
BAM, KAS, ING = PLANTS
counts = {p: [] for p in PLANTS}
for m in range(12):
    counts[ING].append(max(0, round(215 - 4.0*m + random.gauss(0, 6))))
    spiker = BAM if m % 2 == 0 else KAS
    for p in (BAM, KAS):
        base = (258 - 5.0*m) if p is spiker else (108 - 1.5*m)
        counts[p].append(max(0, round(base + random.gauss(0, 6))))

totals = {p: sum(v) for p, v in counts.items()}
winner = max(totals, key=totals.get)
assert winner == ING, totals
assert winner != BAM, "the ag-01 winner must not be Bamberg — it carries ld-02"
for m in range(12):                                     # no month reveals the winner
    assert max(PLANTS, key=lambda p: counts[p][m]) != winner, \
        f"month {m+1} reveals the annual winner"
for p in PLANTS:                                        # ag-01 trend is unambiguous
    assert sum(counts[p][6:]) < sum(counts[p][:6]), p
before = sum(counts[BAM][:PIVOT-1]) / (PIVOT-1)         # ag-03, four+ months either side
after  = sum(counts[BAM][PIVOT:]) / (12-PIVOT)
assert PIVOT-1 >= 4 and 12-PIVOT >= 4
assert after < before, "ag-03 has no clear direction"

CHANGE_REQUESTS = [        # (id, subject, class, level) — ag-02's answer is designed
    ("CR-84", "Fastener finish, BV series housing bolts", "Class B", 2),
    ("CR-86", "Label revision, assembly nameplate", "Class D", 1),
    ("CR-89", "Packaging specification, crated assemblies", "Class C", 2),
    ("CR-93", "Drawing note correction, cover plate", "Class D", 1),
    ("CR-95", "Bush material, guide assembly", "Class A", 3),
    ("CR-97", "Document reference correction, tooling list", "Class D", 1),
]
# CR-88 (Class A, Level 3) and CR-91 (Class C, Level 2) are authored separately.
ALL_CR_LEVELS = [3, 2] + [lvl for *_, lvl in CHANGE_REQUESTS]
AG02_TOTAL, AG02_LEVEL3 = len(ALL_CR_LEVELS), sum(1 for l in ALL_CR_LEVELS if l == 3)
assert (AG02_TOTAL, AG02_LEVEL3) == (8, 2), (AG02_TOTAL, AG02_LEVEL3)


def rework(i):
    m, month = i, MONTHS[i]
    rows = "\n".join(f"| {p} | {counts[p][m]} | {round(counts[p][m]*0.38):d} | {round(counts[p][m]*0.62):d} |"
                     for p in PLANTS)
    return f"""---
file: rework_2025_{i+1:02d}.pdf
title: Monthly Rework Return
header: Monthly Rework Return
header_right: Manufacturing Operations
doc_id: MRR-2025-{i+1:02d}
revision: Issue 1
author_function: Manufacturing Operations
date: 2025-{i+1:02d}
tier: constrained
---

## 1. Rework counts by plant

Rework recorded for {month} 2025, by site. Counts are units entering the
rework cell in the period and are taken from the rework booking record.

| Site | Units reworked | In-process | Returned from field |
| --- | --- | --- | --- |
{rows}

Counts are stated as booked. Units entering rework in the period and not
closed by the period end are carried and appear again in the following
period's in-process column.

## 2. Notes

The return is prepared by Manufacturing Operations from the rework booking
record and is issued within five working days of the period end.

Figures in this return cover the period stated above only. Comparison across
periods is not made in this return and is performed at the quarterly review.

Queries on a figure should be directed to the site recording it, quoting the
return reference above.
"""


def change_request(cr_id, subject, cls, n):
    return f"""---
file: {cr_id}_{subject.split(',')[0].lower().replace(' ','_')}.pdf
title: Engineering Change Request {cr_id} — {subject.split(',')[0]}
header: Engineering Change Request {cr_id}
header_right: Issue 1
doc_id: {cr_id}
revision: Issue 1
author_function: Engineering Change Board
date: 2025-{(n%12)+1:02d}
tier: constrained
---

## 1. Change description

This change request records the change described below against the BV series.

| Field | Entry |
| --- | --- |
| Change request | {cr_id} |
| Subject | {subject} |
| Category | {cls} |
| Originating function | Engineering Change Board |
| Status | Implemented |

The change is limited to the item described. No other characteristic is
altered and no other assembly in the series is affected.

## 2. Procedure reference

This change request was raised and processed under the Material Change
Approval Procedure, revision 3.

| Reference | Entry |
| --- | --- |
| Governing procedure | Material Change Approval Procedure |
| Procedure revision | Revision 3 |
| Classification | {cls} |
| Record retained | This change request |

The authority under which a change of this classification is approved is
determined by the governing procedure and the delegation of authority in
force on the date this request was raised. It is not reproduced here.
"""


if __name__ == "__main__":
    for i in range(12):
        (SRC / f"rework_2025_{i+1:02d}.md").write_text(rework(i))
    for n, (cr_id, subject, cls, _lvl) in enumerate(CHANGE_REQUESTS):
        fn = f"{cr_id}_{subject.split(',')[0].lower().replace(' ','_')}.md"
        (SRC / fn).write_text(change_request(cr_id, subject, cls, n))
    print(f"12 rework + {len(CHANGE_REQUESTS)} change requests written\n")
    print("DESIGNED ANSWERS, asserted above:")
    print(f"  ag-01 winner : {winner}  (totals {totals})")
    print(f"  ag-01 trend  : improving at every site")
    print(f"  ag-02        : {AG02_TOTAL} change requests, {AG02_LEVEL3} required Level 3")
    print(f"  ag-03 Bamberg: {before:.0f}/month before CR-91, {after:.0f}/month after")
