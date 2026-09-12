import unittest
import json
from unittest.mock import Mock, patch

from app.ambiguity import detect_ambiguity
from app.config import settings
from app.extractors import _extract_csv
from app.evaluation import assess_case
from app.retrieval import reciprocal_rank_fusion
from app.source_metadata import extract_source_metadata


class SourceMetadataTests(unittest.TestCase):
    def test_extracts_policy_headers(self):
        metadata = extract_source_metadata([
            "Policy ID: HR-LEAVE-2024-03\nStatus: Superseded\nEffective date: 1 January 2024"
        ])

        self.assertEqual(metadata["record_id"], "HR-LEAVE-2024-03")
        self.assertEqual(metadata["source_status"], "superseded")
        self.assertEqual(metadata["effective_date"].date().isoformat(), "2024-01-01")

    def test_defaults_unstructured_sources_to_current(self):
        self.assertEqual(extract_source_metadata(["ordinary text"]), {"source_status": "current"})


class CsvExtractionTests(unittest.TestCase):
    def test_repeats_column_names_for_each_row(self):
        documents = _extract_csv("rates.csv", b"city,currency,hotel_cap\nValencia,EUR,145\n")

        self.assertEqual(len(documents), 1)
        self.assertEqual(
            documents[0].page_content,
            "city: Valencia; currency: EUR; hotel_cap: 145",
        )
        self.assertEqual(documents[0].metadata["section"], "CSV row 2")


class RankFusionTests(unittest.TestCase):
    def test_rewards_candidates_returned_by_both_retrievers(self):
        vector = [
            {"_id": "a", "content": "A", "score": 0.8, "signal": "vector"},
            {"_id": "b", "content": "B", "score": 0.7, "signal": "vector"},
        ]
        text = [
            {"_id": "b", "content": "B", "score": 4.2, "signal": "text"},
            {"_id": "c", "content": "C", "score": 3.1, "signal": "text"},
        ]

        output = reciprocal_rank_fusion([vector, text])

        self.assertEqual(output[0]["_id"], "b")
        self.assertEqual(output[0]["signals"], ["vector", "text"])
        self.assertEqual(output[0]["vector_score"], 0.7)
        self.assertEqual(output[0]["text_score"], 4.2)


class EvaluationTests(unittest.TestCase):
    def test_does_not_count_ambiguous_results_as_clarification(self):
        case = {
            "expected_behavior": "request_clarification",
            "expected_sources": ["rates.csv", "facilities.md"],
        }
        response = {
            "abstained": False,
            "decision": "answer",
            "pipeline": {"ambiguity_status": "not_configured"},
            "results": [{"filename": "rates.csv"}, {"filename": "facilities.md"}],
        }

        passed, detail = assess_case(case, response)

        self.assertFalse(passed)
        self.assertIn("not requested", detail)


class AmbiguityTests(unittest.TestCase):
    @patch("app.ambiguity.httpx.post")
    def test_returns_evidence_backed_clarification(self, post):
        old_key = settings.openrouter_api_key
        settings.openrouter_api_key = "test-key"
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "decision": "clarify",
                "reason": "Two different allowances are supported.",
                "clarification_question": "Which Valencia allowance do you mean?",
                "options": [
                    {"label": "Hotel cap", "refined_query": "What is the Valencia hotel cap?", "evidence_ids": ["a"]},
                    {"label": "Bicycle allowance", "refined_query": "What is the Valencia bicycle allowance?", "evidence_ids": ["b"]},
                ],
            })}}],
        }
        post.return_value = response
        candidates = [
            {"_id": "a", "filename": "rates.csv", "section": "row", "reranker_score": 0.99, "content": "hotel cap"},
            {"_id": "b", "filename": "office.md", "section": None, "reranker_score": 0.98, "content": "bicycle allowance"},
        ]
        try:
            result = detect_ambiguity("What is the Valencia allowance?", candidates)
        finally:
            settings.openrouter_api_key = old_key

        self.assertEqual(result["decision"], "clarify")
        self.assertEqual(len(result["options"]), 2)
        self.assertEqual(result["options"][0]["evidence_ids"], ["a"])


if __name__ == "__main__":
    unittest.main()
