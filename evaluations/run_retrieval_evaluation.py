#!/usr/bin/env python3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation import assess_case, load_cases  # noqa: E402
from app.main import SearchRequest, search  # noqa: E402


def main() -> int:
    failures = 0
    total = 0
    for _, case in load_cases():
        total += 1
        response = search(SearchRequest(
            query=case["question"],
            limit=8,
            mode="hybrid",
            include_superseded=case["expected_behavior"] == "retrieve_historical_answer",
        ))
        passed, detail = assess_case(case, response)
        failures += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {case['id']}: {detail}")
    print(f"\n{total - failures}/{total} behavioural checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
