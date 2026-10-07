"""negatives.ballast_vocabulary, enforced over every generated ballast file."""
import pathlib, re, sys, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
m = yaml.safe_load((ROOT/"corpus/manifest.yaml").read_text())
PLANTS = [p["name"] for p in m["entities"]["plants"]]
SUPPLIERS = [s["name"] for s in m["entities"]["suppliers"]]
PARTS = [p["id"] for p in m["entities"]["parts"]]

PAIRS = []
for block in m["negatives"].values():
    if isinstance(block, dict):
        for pair in block.get("assert_no_cooccurrence", []) or []:
            PAIRS.append([str(x) for x in pair])

fails = 0
files = sorted((ROOT/"corpus/source").glob("ballast_*.md"))
for f in files:
    t = f.read_text()
    for a, b in PAIRS:
        if a in t and b in t:
            print(f"FAIL {f.name}: co-occurrence {a!r} + {b!r}"); fails += 1
    for bad in ["Regensburg", "warranty", "recall", "R-2025-014"]:
        if re.search(rf"\b{bad}\b", t, re.I):
            print(f"FAIL {f.name}: forbidden {bad!r}"); fails += 1
    named_plants = [p for p in PLANTS if p in t]
    named_parts  = [p for p in PARTS if re.search(rf"\b{re.escape(p)}\b", t)]
    if named_plants and named_parts:
        print(f"FAIL {f.name}: names a plant AND a part ({named_plants[:1]}, {named_parts[:1]})"); fails += 1
print(f"\n{len(files)} ballast files, {len(PAIRS)} co-occurrence rules checked")
print("ALL BALLAST CHECKS PASS" if not fails else f"{fails} FAILURE(S)")
sys.exit(1 if fails else 0)
