import json
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple


EVALUATION_DIRECTORY = Path(__file__).resolve().parents[2] / "evaluations"
SUITES = ("questions.json", "conflict-and-noise-questions.json")


def load_cases() -> Iterator[Tuple[str, Dict[str, Any]]]:
    for filename in SUITES:
        payload = json.loads((EVALUATION_DIRECTORY / filename).read_text())
        for case in payload["cases"]:
            yield filename.removesuffix(".json"), case


def assess_case(case: Dict[str, Any], response: Dict[str, Any]) -> Tuple[bool, str]:
    results = response["results"]
    filenames = [item["filename"] for item in results]
    expected = case.get("expected_sources", [])
    competing = case.get("competing_sources", [])
    behavior = case["expected_behavior"]

    if behavior in {"abstain", "unanswerable_with_noise"}:
        return response["abstained"], "Expected the retrieval pipeline to abstain."
    if behavior == "request_clarification":
        if response.get("decision") == "clarify":
            return True, "The ambiguity model requested clarification."
        status = response.get("pipeline", {}).get("ambiguity_status", "unknown")
        return False, f"Clarification was not requested (ambiguity status: {status})."
    if behavior == "retrieve_multiple_sources":
        missing = [name for name in expected if name not in filenames]
        if missing:
            return False, f"Missing expected sources: {', '.join(missing)}."
        return True, "All expected sources were returned."
    if behavior in {
        "prefer_current_source",
        "prefer_later_controlling_source",
        "prefer_relevant_source",
        "retrieve_historical_answer",
    }:
        top = filenames[0] if filenames else "none"
        passed = bool(filenames) and top in expected and top not in competing
        return passed, f"Top result: {top}."
    found = any(name in filenames[:3] for name in expected)
    if found and not response["abstained"]:
        return True, "An expected source appeared in the top three."
    return False, "No expected source appeared in the top three."
