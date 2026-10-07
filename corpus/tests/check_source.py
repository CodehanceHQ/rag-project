"""Greppable manifest checks against Markdown source. No model, no database.

Runs before rendering. Catches the failures that matter most — a missing
verbatim string, or a forbidden co-occurrence that collapses a multi-hop chain.
Chunk-boundary assertions are NOT checkable here; they need extracted PDF text.
"""
import re, sys, pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "corpus/source"

def load(p): return yaml.safe_load((ROOT / p).read_text())

def split_front_matter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    return (yaml.safe_load(m.group(1)), m.group(2)) if m else ({}, text)

def headings(body):
    return re.findall(r"^#{1,6}\s+(.*)$", body, re.M)

def check(md_path, spec_entry, manifest):
    fm, body = split_front_matter(md_path.read_text())
    title = fm.get("title", "")
    hay = body.lower()
    # verbatim strings are matched against whitespace-normalised, case-folded
    # text: PDF extraction rewraps lines, so a raw substring match is wrong.
    flat = re.sub(r"[\s*`]+", " ", body).lower()
    fails, notes = [], []

    for h in spec_entry.get("holds", []):
        if isinstance(h, dict) and "verbatim" in h:
            needle = re.sub(r"\s+", " ", h["verbatim"]).lower()
            if needle not in flat:
                fails.append(f"MISSING verbatim {h['verbatim']!r}")

    for bad in spec_entry.get("must_not_hold", []):
        if not isinstance(bad, str): continue
        if bad.startswith("any ") or "reference to" in bad:
            notes.append(f"manual check: must_not_hold {bad!r}")
            continue
        if re.search(rf"\b{re.escape(bad.lower())}\b", hay):
            fails.append(f"FORBIDDEN {bad!r} present")

    # negatives that are greppable per-document
    negs = manifest["negatives"]
    if "fkm70_undiscoverable" in spec_entry.get("negatives", []):
        if "FKM-70" in title:
            fails.append("FKM-70 in document TITLE (fkm70_undiscoverable)")
        for h in headings(body):
            if "FKM-70" in h:
                fails.append(f"FKM-70 in SECTION HEADING {h!r} (fkm70_undiscoverable)")
        if "FKM-70" in str(spec_entry["file"]):
            fails.append("FKM-70 in FILENAME (fkm70_undiscoverable)")

    if "authority_split" in spec_entry.get("negatives", []) and spec_entry["file"].startswith("CR-"):
        if re.search(r"\blevel\s*[123]\b", hay):
            fails.append("approval LEVEL stated in a change request (authority_split)")

    return fails, notes

def main():
    spec = load("corpus/document-spec.yaml")
    manifest = load("corpus/manifest.yaml")
    by_file = {d["file"]: d for d in spec["documents"]}
    total_fail = 0
    for md in sorted(SRC.glob("*.md")):
        pdf = md.stem + ".pdf"
        entry = by_file.get(pdf)
        if not entry:
            # constrained and ballast documents are covered by templates/ballast
            # in the spec, not by individual entries, and have their own checks
            # (check_ballast.py, and the assertions inside generate/constrained.py).
            fm, _ = split_front_matter(md.read_text())
            if fm.get("tier") in ("constrained", "ballast"):
                continue
            print(f"?? {md.name}: no spec entry for {pdf}"); total_fail += 1; continue
        fails, notes = check(md, entry, manifest)
        status = "FAIL" if fails else "pass"
        print(f"[{status}] {pdf}   serves={','.join(entry.get('serves', [])) or '-'}")
        for f in fails: print(f"         x {f}")
        for n in notes: print(f"         . {n}")
        total_fail += len(fails)
    print(f"\n{'ALL CHECKS PASS' if not total_fail else str(total_fail)+' FAILURE(S)'}")
    return 1 if total_fail else 0

if __name__ == "__main__":
    sys.exit(main())
