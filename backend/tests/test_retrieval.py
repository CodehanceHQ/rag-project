import unittest
import json
from unittest.mock import Mock, patch

from app.ambiguity import detect_ambiguity
from app.config import settings
from app.extractors import _extract_csv
from app.evaluation import assess_case
from app.generation import generate_answer
from app.retrieval import candidate_outcomes, reciprocal_rank_fusion
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

    def test_names_what_became_of_each_reranked_candidate(self):
        reranked = [
            {"_id": "a", "reranker_score": 0.9},
            {"_id": "b", "reranker_score": 0.4},
            {"_id": "c", "reranker_score": 0.01},
        ]

        outcomes = candidate_outcomes(reranked, accepted=reranked[:1], minimum_score=0.15)

        self.assertEqual(outcomes, {"a": "returned", "b": "beyond_limit", "c": "below_threshold"})
        self.assertNotIn("d", outcomes)


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

    @patch("app.ambiguity.httpx.post")
    def test_keeps_a_decision_whose_reason_runs_long(self, post):
        old_key = settings.openrouter_api_key
        settings.openrouter_api_key = "test-key"
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "decision": "clarify",
                "reason": "Two oven temperatures are supported by the evidence. " * 12,
                "clarification_question": "Which sourdough do you mean?",
                "options": [
                    {"label": "Classic Sourdough", "refined_query": "Oven temperature for the Classic Sourdough?", "evidence_ids": ["a"]},
                    {"label": "Country Sourdough", "refined_query": "Oven temperature for the Country Sourdough?", "evidence_ids": ["b"]},
                ],
            })}}],
        }
        post.return_value = response
        candidates = [
            {"_id": "a", "filename": "rev_D.pdf", "section": "4. Baking", "reranker_score": 0.84, "content": "230"},
            {"_id": "b", "filename": "country.pdf", "section": "4. Baking", "reranker_score": 0.84, "content": "210"},
        ]
        try:
            result = detect_ambiguity("What temperature for the sourdough?", candidates)
        finally:
            settings.openrouter_api_key = old_key

        self.assertEqual(result["status"], "checked")
        self.assertEqual(result["decision"], "clarify")
        self.assertLessEqual(len(result["reason"]), 300)
        self.assertTrue(result["reason"].endswith("…"))


class ModelLoadingTests(unittest.TestCase):
    def test_loads_one_model_at_a_time_and_keeps_it(self):
        import threading
        import time
        from app.loading import load_once

        busy, overlaps, calls = [], [], []

        def loader(name):
            calls.append(name)
            overlaps.append(len(busy))
            busy.append(name)
            time.sleep(0.05)
            busy.pop()
            return name.upper()

        first, second = load_once()(loader), load_once()(loader)
        threads = [threading.Thread(target=fn, args=(name,))
                   for fn, name in ((first, "a"), (second, "b"), (first, "a"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(overlaps, [0, 0])
        self.assertEqual(sorted(calls), ["a", "b"])
        self.assertEqual(first("a"), "A")


class LocalAnswerTests(unittest.TestCase):
    PASSAGES = [
        {"filename": "country.pdf", "page": 4, "content": "Set it to 210 °C.", "score": 0.9},
        {"filename": "rev_D.pdf", "page": 4, "content": "Set it to 230 °C.", "score": 0.6},
    ]

    def test_answers_with_the_local_model_and_no_key(self):
        old = settings.answer_provider, settings.openrouter_api_key
        settings.answer_provider, settings.openrouter_api_key = "local", ""
        try:
            with patch("app.generation.write_local",
                       return_value="<think>Which oven?</think>It is 230 °C [2].") as write:
                result = generate_answer("What temperature?", self.PASSAGES)
        finally:
            settings.answer_provider, settings.openrouter_api_key = old

        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["answer"], "It is 230 °C [2].")
        self.assertEqual(result["cited"], [2])
        self.assertEqual(result["provider"], "local")
        self.assertEqual(write.call_args.args[0], settings.answer_local_model)


if __name__ == "__main__":
    unittest.main()
