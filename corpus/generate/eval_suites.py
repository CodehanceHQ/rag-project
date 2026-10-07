"""Rebuild evaluations/*.json from the manifest, against the new corpus.

The fork shipped these suites pointing at sample-documents (HR policies). That
corpus is gone; these are the same schema, same harness, pointed at the 25
questions in corpus/manifest.yaml. backend/app/ is untouched — the two
filenames in app/evaluation.py:SUITES are preserved deliberately.

Path A is EXPECTED to fail most of these. That is the measurement: the
single_hop rows are test_baseline_succeeds, the multi_hop and long_distance
rows are test_baseline_fails.
"""
import json, pathlib, re, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
manifest = yaml.safe_load((ROOT / "corpus/manifest.yaml").read_text())
have = sorted(p.name for p in (ROOT / "corpus/documents").glob("*.pdf"))

BEHAVIOUR = {
    "single_hop": "retrieve_answer",
    "context_loss": "retrieve_answer",
    "multi_hop": "retrieve_multiple_sources",
    "long_distance": "retrieve_multiple_sources",
    "aggregation": "retrieve_multiple_sources",
    "ambiguous": "request_clarification",
    "unanswerable": "abstain",
}
SUITE_A = {"single_hop", "multi_hop", "long_distance", "context_loss", "aggregation"}


def expand(sources):
    """Resolve the manifest's prose globs to real filenames."""
    out = []
    for s in sources:
        s = str(s)
        if ".." in s:                                   # rework_2025_01.pdf .. _12.pdf
            stem = re.match(r"([\w\-]+?)_?\d+\.pdf", s.split("..")[0].strip())
            if stem:
                out += [f for f in have if f.startswith(stem.group(1))]
            continue
        if "every" in s or "*" in s:                    # "every CR-*.pdf in the corpus"
            out += [f for f in have if f.startswith("CR-")]
            continue
        out += [f for f in re.findall(r"[\w\-]+\.pdf", s) if f in have]
    return sorted(set(out))


def case(q):
    behaviour = BEHAVIOUR[q["shape"]]
    c = {"id": q["id"], "category": q["shape"], "question": " ".join(q["q"].split()),
         "expected_behavior": behaviour,
         "expected_sources": expand(q.get("expected_sources", []))}
    if q.get("answer"):
        c["expected_fact"] = " ".join(str(q["answer"]).split())[:300]
    if q.get("wrong_answer_path_a"):
        c["competing_answer"] = " ".join(str(q["wrong_answer_path_a"]).split())[:200]
    return c


def suite(name, shapes, note):
    cases = [case(q) for q in manifest["questions"] if q["shape"] in shapes]
    return {"corpus": "rag-project (corpus/documents)", "version": 1, "suite": name,
            "required_document_groups": ["corpus/documents"], "excluded_document_groups": [],
            "instructions": note, "cases": cases}


if __name__ == "__main__":
    ev = ROOT / "evaluations"
    (ev / "questions.json").write_text(json.dumps(suite(
        "baseline-shapes", SUITE_A,
        "Path A over the 25-question benchmark. single_hop rows must PASS "
        "(test_baseline_succeeds); multi_hop and long_distance rows are "
        "expected to FAIL (test_baseline_fails). A passing multi_hop row means "
        "the corpus is not hard enough — see corpus/manifest.yaml negatives."
    ), indent=2) + "\n")
    (ev / "conflict-and-noise-questions.json").write_text(json.dumps(suite(
        "ambiguous-and-unanswerable", {"ambiguous", "unanswerable"},
        "Correct behaviour is to decline, not to answer. Path A has an "
        "ambiguity detector (backend/app/ambiguity.py) and may genuinely pass "
        "these."
    ), indent=2) + "\n")
    for f in ("questions.json", "conflict-and-noise-questions.json"):
        d = json.loads((ev / f).read_text())
        print(f"{f}: {len(d['cases'])} cases")
        for c in d["cases"]:
            print(f"   {c['id']:6} {c['expected_behavior']:26} {len(c['expected_sources'])} source(s)")
