#!/usr/bin/env python
"""Answer-level grading for any system under test.

The retrieval benchmark (/evaluations/run) grades which DOCUMENTS came back.
This grades the SENTENCE: did it state the right fact, did it decline when it
should have, and is every named claim supported by a passage it actually
cited. "Got the right answer" and "got the right
answer from the right evidence" are different results.

    .venv/bin/python evaluations/answer_eval/run.py --system path-a
    .venv/bin/python evaluations/answer_eval/run.py --only mh-01 --runs 3
    .venv/bin/python evaluations/answer_eval/run.py --no-judge
"""
import argparse, json, pathlib, sys, time
import yaml

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

from systems import SYSTEMS                     # noqa: E402
from checks import (entities_from, mentioned, salient_terms, check_expected,      # noqa: E402
                    check_not_wrong, check_declined, check_citation_support)
from judge import judge_answer, DEFAULT_JUDGE   # noqa: E402

REFUSAL_SHAPES = {"ambiguous", "unanswerable"}
# shapes whose expected answer is prose, so a string match cannot grade them
JUDGED_SHAPES = {"long_distance", "aggregation", "multi_hop", "context_loss"}


def load_manifest():
    return yaml.safe_load((ROOT / "corpus/manifest.yaml").read_text())


def grade(q, result, vocab, api_key, judge_model, use_judge):
    answer = result.get("answer") or ""
    shape = q["shape"]
    expected_text = " ".join(str(q.get("answer", "")).split())
    checks = []

    if shape in REFUSAL_SHAPES:
        checks.append(check_declined(answer, result.get("abstained"), result.get("decision")))
    else:
        expected_terms = salient_terms(expected_text, vocab)
        wrong_text = " ".join(str(q.get(k, "")) for k in ("wrong_answer_path_a", "wrong_answer_naive"))
        wrong_terms = salient_terms(wrong_text, vocab)
        checks.append(check_expected(answer, expected_terms))
        checks.append(check_not_wrong(answer, wrong_terms))

    checks.append(check_citation_support(answer, result.get("cited", []),
                                         result.get("passages", {}), vocab))

    verdict = None
    if use_judge and shape in JUDGED_SHAPES and expected_text and answer:
        verdict = judge_answer(q["q"], expected_text, answer, api_key, judge_model)
        checks.append({"name": "covers_expected (judge)", "passed": verdict["covered"],
                       "detail": verdict["why"]})

    scored = [c for c in checks if c["passed"] is not None]
    return {"passed": all(c["passed"] for c in scored) if scored else None,
            "checks": checks, "judge": verdict}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="path-a", choices=sorted(SYSTEMS))
    ap.add_argument("--only", default="", help="comma-separated question ids")
    ap.add_argument("--runs", type=int, default=1, help="repeat each question, for variance")
    ap.add_argument("--judge", default=DEFAULT_JUDGE)
    ap.add_argument("--no-judge", action="store_true", help="deterministic checks only, no API cost")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    manifest = load_manifest()
    vocab = entities_from(manifest)
    api_key = ""
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            api_key = line.split("=", 1)[1].strip()
    use_judge = not args.no_judge and bool(api_key)

    wanted = {x.strip() for x in args.only.split(",") if x.strip()}
    questions = [q for q in manifest["questions"] if not wanted or q["id"] in wanted]
    system = SYSTEMS[args.system]

    print(f"system={args.system}  questions={len(questions)}  runs={args.runs}  "
          f"judge={'off' if not use_judge else args.judge}\n")

    rows, t0 = [], time.time()
    for q in questions:
        for run_n in range(1, args.runs + 1):
            try:
                result = system(q["q"])
            except Exception as exc:
                result = {"answer": None, "cited": [], "passages": {},
                          "error": f"{type(exc).__name__}: {exc}"}
            g = grade(q, result, vocab, api_key, args.judge, use_judge)
            mark = {True: "PASS", False: "fail", None: " -- "}[g["passed"]]
            suffix = f" (run {run_n})" if args.runs > 1 else ""
            print(f"[{mark}] {q['id']:6} {q['shape']:14}{suffix}")
            for c in g["checks"]:
                sym = {True: "ok ", False: "XX ", None: "-- "}[c["passed"]]
                print(f"         {sym}{c['name']:26} {c['detail'][:88]}")
            rows.append({"id": q["id"], "shape": q["shape"], "run": run_n,
                         "passed": g["passed"], "checks": g["checks"],
                         "judge": g["judge"], "answer": result.get("answer"),
                         **({"error": result["error"]} if "error" in result else {})})
            print()

    by_shape = {}
    for r in rows:
        by_shape.setdefault(r["shape"], []).append(r)
    print("=" * 66)
    for shape, rs in sorted(by_shape.items()):
        p = sum(1 for r in rs if r["passed"])
        print(f"  {shape:16} {p}/{len(rs)}")
    total = sum(1 for r in rows if r["passed"])
    print(f"  {'TOTAL':16} {total}/{len(rows)}   {time.time()-t0:.0f}s")

    out = pathlib.Path(args.out) if args.out else \
        ROOT / f"evaluations/results/answers_{args.system}_{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"system": args.system, "judge": args.judge if use_judge else None,
                               "rows": rows}, indent=2))
    print(f"\n  -> {out.resolve().relative_to(ROOT)}")


if __name__ == "__main__":
    main()
