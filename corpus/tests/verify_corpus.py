"""The verification suite, run against EXTRACTED PDF TEXT and the real chunker.

Source-level checks (check_source.py, check_ballast.py) run on Markdown and
catch most things. These cannot: extraction rewraps text, tables come out in
an order nobody authored, and page furniture lands in every page's text. The
chunk-boundary assertions are only true or false here.
"""
import json, pathlib, re, sys, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.extractors import extract_documents
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHUNK_SIZE, CHUNK_OVERLAP = 1000, 180     # the fixed-width split the boundary cases are designed against
DOCS = ROOT / "corpus/documents"
manifest = yaml.safe_load((ROOT / "corpus/manifest.yaml").read_text())

results = []
def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))

print("extracting 100 PDFs with backend/app/extractors.py ...")
text, chunks, skipped = {}, {}, []
splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
                                          add_start_index=True)
for pdf in sorted(DOCS.glob("*.pdf")):
    try:
        pages = extract_documents(pdf.name, pdf.read_bytes())
    except ValueError as e:
        skipped.append((pdf.name, str(e)[:48])); continue
    text[pdf.name] = "\n".join(p.page_content for p in pages)
    chunks[pdf.name] = [c.page_content for c in splitter.split_documents(pages)]
corpus = "\n".join(text.values())
print(f"extracted {len(text)} documents, {sum(len(v) for v in chunks.values())} chunks"
      f"{f', SKIPPED {len(skipped)}' if skipped else ''}\n")
for n, why in skipped:
    print(f"  ! {n}: {why}")

print("\n--- test_negatives_hold : asserted co-occurrences do not occur ---")
for key, block in manifest["negatives"].items():
    if not isinstance(block, dict): continue
    for pair in block.get("assert_no_cooccurrence", []) or []:
        a, b = str(pair[0]), str(pair[1])
        bad = [f for f, t in text.items() if a in t and b in t]
        check(f"{key}: {a!r} + {b!r} never co-occur", not bad, f"in {bad[:2]}" if bad else "")

print("\n--- test_forbidden_words : unwritten abstractions stay unwritten ---")
for key, block in manifest["negatives"].items():
    if not isinstance(block, dict): continue
    words, applies = block.get("forbidden_words_in_fragments"), block.get("applies_to")
    if not words or not applies: continue
    carve = block.get("forbidden_except", {}) or {}
    for f in applies:
        t = text.get(f, "")
        hits = [w for w in words if re.search(rf"\b{re.escape(str(w))}\b", t, re.I)]
        check(f"{key}: {f} free of {words}", not hits, f"found {hits}" if hits else "")

print("\n--- test_flour_undiscoverable ---")
FLOUR = "Heritage Stoneground"
bad_title = [f for f, t in text.items() if FLOUR in t.split("\n")[0]]
check(f"{FLOUR} in no page-header line", not bad_title, f"{bad_title[:3]}" if bad_title else "")
for f in ("withdrawal_W-2025-014.pdf", "launch_plan_sourdough.pdf"):
    check(f"{FLOUR} absent from {f}", FLOUR not in text.get(f, ""))
holders = sorted(f for f, t in text.items() if FLOUR in t)
check(f"{FLOUR} held only where the manifest allows",
      holders == ["RC-88_flour_change.pdf", "allergen_retest_certificate.pdf", "product_specifications_2025.pdf"],
      f"{holders}")

print("\n--- test_no_single_chunk : multi-hop stays multi-hop ---")
MULTIHOP = {"mh-01": ["SD-12", "High Street"], "mh-01b": ["W-2025-014", "Birch Lane"],
            "mh-05": ["Golden Field", "Heritage Stoneground"]}
for qid, ents in MULTIHOP.items():
    bad = [(f, i) for f, cs in chunks.items() for i, c in enumerate(cs)
           if all(e in c for e in ents)]
    check(f"{qid}: no single chunk holds {ents}", not bad, f"{bad[:2]}" if bad else "")

print("\n--- test_chunking : the boundary assertions (cl-01, cl-02, cl-04) ---")
wi = chunks.get("baking_instruction_rev_D.pdf", [])
hit = [c for c in wi if "230 °C" in c and "deck oven" not in c.lower()]
check("oven_referent: a chunk has '230 °C' without 'deck oven'", bool(hit),
      f"{len(hit)} such chunk(s)")
tt = chunks.get("tolerance_tables.pdf", [])
hit = [c for c in tt if "SD-12 baked weight" in c and "Class A" not in c]
check("cl02_table_header: baked weight row orphaned from its header", bool(hit),
      f"{len(hit)} such chunk(s)")
pr = chunks.get("recipe_change_approval_procedure.pdf", [])
hit = [c for c in pr if "Level 3 approval is required" in c and "allergen-critical" not in c.lower()]
check("cl04_scope_orphaned: Level 3 rule stranded from its scope", bool(hit),
      f"{len(hit)} such chunk(s)")
b24 = chunks.get("product_specifications_2024.pdf", [])
hit = [c for c in b24 if "Golden Field" in c and "2024" not in c]
check("cl03_edition_orphaned: 'Golden Field' chunk with no edition identifier", bool(hit),
      f"{len(hit)} such chunk(s)")
temps = [f for f, t in text.items() if "230 °C" in t and "210 °C" in t]
check("am02: no document holds both oven temperatures", not temps, f"{temps[:3]}" if temps else "")

print("\n--- test_single_answer : mh-01 has one answer, mh-02 can be reached ---")
G = "Cedar"                                # cells wrap, so match the first word
for f in ("product_specifications_2024.pdf", "product_specifications_2025.pdf"):
    t = text.get(f, "")
    a, b, c, d = (t.find(h) for h in ("2. Classic Sourdough (SD-12)\n", "3. Country Sourdough (SD-13)\n",
                                      "4. Common ingredients\n", "5. Approved supplier index\n"))
    ok = -1 < a < b < c < d and G not in t[a:b] and G not in t[c:d] and G in t[b:c]
    check(f"cedar_not_sd12: {f} sources SD-13 only from Cedar Valley", ok)
rc88 = text.get("RC-88_flour_change.pdf", "")
check("rc88_class_recorded: RC-88 records Class A, and no level",
      "Class A" in rc88 and not re.search(r"\bLevel [123]\b", rc88))
levels = [f for f, t in text.items() if f.startswith("RC-") and re.search(r"\bLevel [123]\b", t)]
check("ag02: no recipe change states an approval level", not levels, f"{levels[:3]}" if levels else "")

print("\n--- test_unanswerable : the corpus really does not say ---")
for word in ("Market Square", "calorie", "calories"):
    bad = [f for f, t in text.items() if re.search(rf"\b{word}\b", t, re.I)]
    check(f"{word!r} appears nowhere", not bad, f"in {bad[:3]}" if bad else "")

print("\n--- test_sources_exist : every expected_sources filename resolves ---")
have = {p.name for p in DOCS.glob("*.pdf")}
missing = []
for q in manifest["questions"]:
    for src in q.get("expected_sources", []):
        if re.search(r"\.\.|every |\*", str(src)): continue
        for f in re.findall(r"[\w\-]+\.pdf", str(src)):
            if f not in have: missing.append(f"{q['id']}->{f}")
check("all expected_sources resolve", not missing, f"{missing[:4]}" if missing else "")

n_fail = sum(1 for _, ok, _ in results if not ok)
print(f"\n{'='*64}\n{len(results)} checks, {n_fail} failure(s)")
print("CORPUS VERIFIED" if not n_fail else "CORPUS HAS FAILURES")
sys.exit(1 if n_fail else 0)
