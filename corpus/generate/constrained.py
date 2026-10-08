"""Constrained tier: 12 monthly waste returns + 6 routine recipe changes.

Seeded. The answers to ag-01, ag-02 and ag-03 are DESIGNED here and asserted
before anything is written — see negatives.aggregation_needs_all,
ag02_no_register and ag03_pivot_discovered.
"""
import pathlib, random

SRC = pathlib.Path(__file__).resolve().parents[1] / "source"
MONTHS = ["January","February","March","April","May","June",
          "July","August","September","October","November","December"]
SITES = ["High Street bakery", "Riverside bakery", "Station Road bakery"]
PIVOT = 6                       # RC-91, 2025-06 -> months 1-5 before, 7-12 after

# ---- designed, then verified -------------------------------------------------
# The shape is the constraint. Station Road must win on the TOTAL while never
# being the worst in any single month, or one report answers ag-01 and
# negatives.aggregation_needs_all fails. So Station Road runs high and steady,
# and the other two alternate spikes above it — each spiking site accumulates
# less over the year than Station Road's steady rate.
random.seed(20250928)
HIGH, RIV, STA = SITES
counts = {s: [] for s in SITES}
for m in range(12):
    counts[STA].append(max(0, round(215 - 4.0*m + random.gauss(0, 6))))
    spiker = HIGH if m % 2 == 0 else RIV
    for s in (HIGH, RIV):
        base = (258 - 5.0*m) if s is spiker else (108 - 1.5*m)
        counts[s].append(max(0, round(base + random.gauss(0, 6))))

totals = {s: sum(v) for s, v in counts.items()}
winner = max(totals, key=totals.get)
assert winner == STA, totals
assert winner != HIGH, "the ag-01 winner must not be High Street — it carries ld-02"
for m in range(12):                                     # no month reveals the winner
    assert max(SITES, key=lambda s: counts[s][m]) != winner, \
        f"month {m+1} reveals the annual winner"
for s in SITES:                                         # ag-01 trend is unambiguous
    assert sum(counts[s][6:]) < sum(counts[s][:6]), s
before = sum(counts[HIGH][:PIVOT-1]) / (PIVOT-1)        # ag-03, four+ months either side
after  = sum(counts[HIGH][PIVOT:]) / (12-PIVOT)
assert PIVOT-1 >= 4 and 12-PIVOT >= 4
assert after < before, "ag-03 has no clear direction"

RECIPE_CHANGES = [         # (id, subject, class, level) — ag-02's answer is designed
    ("RC-84", "Salt pack size, bread doughs", "Class B", 2),
    ("RC-86", "Label wording, bag closure tag", "Class D", 1),
    ("RC-89", "Packaging specification, paper bread bags", "Class C", 2),
    ("RC-93", "Recipe card correction, baguette", "Class D", 1),
    ("RC-95", "Butter grade, croissant dough", "Class A", 3),
    ("RC-97", "Document reference correction, cleaning list", "Class D", 1),
]
# RC-88 (Class A, Level 3) and RC-91 (Class C, Level 2) are authored separately.
ALL_RC_LEVELS = [3, 2] + [lvl for *_, lvl in RECIPE_CHANGES]
AG02_TOTAL, AG02_LEVEL3 = len(ALL_RC_LEVELS), sum(1 for l in ALL_RC_LEVELS if l == 3)
assert (AG02_TOTAL, AG02_LEVEL3) == (8, 2), (AG02_TOTAL, AG02_LEVEL3)


def waste(i):
    m, month = i, MONTHS[i]
    rows = "\n".join(f"| {s} | {counts[s][m]} | {round(counts[s][m]*0.38):d} | {round(counts[s][m]*0.62):d} |"
                     for s in SITES)
    return f"""---
file: waste_2025_{i+1:02d}.pdf
title: Monthly Waste Return
header: Monthly Waste Return
header_right: Bakery Operations
doc_id: MWR-2025-{i+1:02d}
revision: Issue 1
author_function: Bakery Operations
date: 2025-{i+1:02d}
tier: constrained
---

## 1. Waste counts by site

Waste recorded for {month} 2025, by site. Counts are loaves written off in the
period and are taken from the waste booking record.

| Site | Loaves wasted | Unsold at close | Rejected at bake |
| --- | --- | --- | --- |
{rows}

Counts are stated as booked. Loaves set aside in the period and not written
off by the period end are carried and appear in the following period's return.

## 2. Notes

The return is prepared by Bakery Operations from the waste booking record and
is issued within five working days of the period end.

Figures in this return cover the period stated above only. Comparison across
periods is not made in this return and is performed at the quarterly review.

Queries on a figure should be directed to the site recording it, quoting the
return reference above.
"""


def filename(rc_id, subject):
    return f"{rc_id}_{subject.split(',')[0].lower().replace(' ', '_')}"


def recipe_change(rc_id, subject, cls, n):
    return f"""---
file: {filename(rc_id, subject)}.pdf
title: Recipe Change {rc_id} — {subject.split(',')[0]}
header: Recipe Change {rc_id}
header_right: Issue 1
doc_id: {rc_id}
revision: Issue 1
author_function: Recipe Change Board
date: 2025-{(n%12)+1:02d}
tier: constrained
---

## 1. Change description

This recipe change records the change described below.

| Field | Entry |
| --- | --- |
| Recipe change | {rc_id} |
| Subject | {subject} |
| Category | {cls} |
| Originating function | Recipe Change Board |
| Status | Implemented |

The change is limited to the item described. No other characteristic is
altered and no other product in the range is affected.

## 2. Procedure reference

This recipe change was raised and processed under the Recipe Change Approval
Procedure, revision 3.

| Reference | Entry |
| --- | --- |
| Governing procedure | Recipe Change Approval Procedure |
| Procedure revision | Revision 3 |
| Classification | {cls} |
| Record retained | This recipe change |

The authority under which a change of this classification is approved is
determined by the governing procedure and the approval matrix in force on the
date this change was raised. It is not reproduced here.
"""


if __name__ == "__main__":
    for i in range(12):
        (SRC / f"waste_2025_{i+1:02d}.md").write_text(waste(i))
    for n, (rc_id, subject, cls, _lvl) in enumerate(RECIPE_CHANGES):
        (SRC / f"{filename(rc_id, subject)}.md").write_text(recipe_change(rc_id, subject, cls, n))
    print(f"12 waste returns + {len(RECIPE_CHANGES)} recipe changes written\n")
    print("DESIGNED ANSWERS, asserted above:")
    print(f"  ag-01 winner : {winner}  (totals {totals})")
    print(f"  ag-01 trend  : improving at every site")
    print(f"  ag-02        : {AG02_TOTAL} recipe changes, {AG02_LEVEL3} required Level 3")
    print(f"  ag-03 High Street: {before:.0f}/month before RC-91, {after:.0f}/month after")
