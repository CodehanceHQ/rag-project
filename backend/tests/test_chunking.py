import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.chunking import CHUNKERS, SourceDocument, get_chunker
from app.chunking.sections import detect_sections
from app.embeddings import count_tokens, token_budget
from app.extractors import extract_documents

DOCUMENTS = Path(__file__).resolve().parents[2] / "corpus" / "documents"


def load(name: str) -> SourceDocument:
    data = (DOCUMENTS / name).read_bytes()
    return SourceDocument(filename=name, data=data, pages=extract_documents(name, data))


class RegistryTests(unittest.TestCase):
    def test_every_strategy_is_registered_under_its_own_name(self):
        for name in ("recursive", "structural", "hybrid", "semantic", "contextual"):
            self.assertEqual(get_chunker(name).name, name)
        self.assertEqual(set(CHUNKERS), {"recursive", "structural", "hybrid", "semantic", "contextual"})

    def test_unknown_strategy_names_the_choices(self):
        with self.assertRaises(ValueError) as raised:
            get_chunker("nonsense")
        self.assertIn("recursive", str(raised.exception))


class BakingInstructionTests(unittest.TestCase):
    """baking_instruction_rev_D.pdf names the deck oven at the start of
    section 4 and gives the temperature a few paragraphs later: "Set it to
    230 °C"."""

    @classmethod
    def setUpClass(cls):
        cls.source = load("baking_instruction_rev_D.pdf")

    def test_sections_are_found_from_the_headings(self):
        titles = [section.title for section in detect_sections(self.source)]
        self.assertEqual(titles[-5:], ["1. Scope", "2. Equipment", "3. Shaping and proving",
                                       "4. Baking", "5. Inspection"])

    def test_recursive_separates_the_temperature_from_its_oven(self):
        chunks = [c for c in get_chunker("recursive").chunk(self.source) if "230 °C" in c.text]
        self.assertTrue(chunks)
        self.assertTrue(all("deck oven" not in c.text.lower() for c in chunks))

    def test_structural_keeps_the_section_whole(self):
        chunks = [c for c in get_chunker("structural").chunk(self.source) if "230 °C" in c.text]
        self.assertEqual(len(chunks), 1)
        self.assertIn("deck oven", chunks[0].text)
        self.assertEqual(chunks[0].section, "4. Baking")

    def test_hybrid_pieces_carry_their_heading_and_fit_the_size_limit(self):
        chunks = get_chunker("hybrid").chunk(self.source)
        for chunk in chunks:
            self.assertTrue(chunk.text.startswith("baking_instruction_rev_D.pdf"))
            self.assertLessEqual(count_tokens(chunk.text), token_budget())
        temperature = [c for c in chunks if "230 °C" in c.text]
        self.assertTrue(all("4. Baking" in c.text for c in temperature))


class TokenLimitTests(unittest.TestCase):
    """tolerance_tables.pdf is mostly numbers, which use many tokens per
    character: a chunk can be short in characters and still too long to embed."""

    def test_size_limited_strategies_never_exceed_what_the_model_reads(self):
        source = load("tolerance_tables.pdf")
        for name in ("recursive", "hybrid", "semantic"):
            for chunk in get_chunker(name).chunk(source):
                self.assertLessEqual(count_tokens(chunk.text), token_budget(), name)

    def test_structural_does_not_limit_size(self):
        chunks = get_chunker("structural").chunk(load("tolerance_tables.pdf"))
        self.assertTrue(any(count_tokens(chunk.text) > token_budget() for chunk in chunks))


class ContextualTests(unittest.TestCase):
    """The model is replaced with a stand-in, so these tests make no paid calls."""

    SENTENCE = ("This passage is from the baking instruction for the Classic Sourdough (SD-12), "
                "in the section on baking loaves in the deck oven.")

    def reply(self, text):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": text}}]}
        return response

    def chunks(self, text=None, **kwargs):
        from app.chunking.contextual import ContextualChunker
        from app.config import settings

        with patch.object(settings, "openrouter_api_key", "test-key"), \
             patch("app.chunking.contextual.httpx.post", return_value=self.reply(text or self.SENTENCE)) as post:
            found = ContextualChunker(provider="openrouter", **kwargs).chunk(load("baking_instruction_rev_D.pdf"))
        return found, post

    def test_every_chunk_starts_with_its_sentence_and_one_call_is_made_per_chunk(self):
        found, post = self.chunks()
        self.assertTrue(found)
        self.assertTrue(all(chunk.text.startswith(self.SENTENCE + "\n") for chunk in found))
        self.assertEqual(post.call_count, len(found))

    def test_the_sentence_gives_the_temperature_chunk_its_oven(self):
        found, _ = self.chunks()
        temperature = [chunk for chunk in found if "230 °C" in chunk.text]
        self.assertTrue(temperature)
        self.assertTrue(all("deck oven" in chunk.text for chunk in temperature))

    def test_the_model_is_shown_the_text_before_the_passage(self):
        found, post = self.chunks()
        prompts = [call.kwargs["json"]["messages"][1]["content"] for call in post.call_args_list]
        target = next(p for p in prompts if "Set it to 230 °C" in p.split("Passage:\n")[1])
        self.assertIn("baked in the deck oven", target.split("Passage:\n")[0])

    def test_sentence_and_passage_together_fit_what_the_model_reads(self):
        found, _ = self.chunks(text=" ".join(["context"] * 400))
        for chunk in found:
            self.assertLessEqual(count_tokens(chunk.text), token_budget())

    def test_the_base_strategy_can_be_changed(self):
        found, _ = self.chunks(base="hybrid")
        self.assertTrue(all("baking_instruction_rev_D.pdf › " in chunk.text for chunk in found))

    def test_the_hosted_provider_refuses_to_run_without_a_key(self):
        from app.chunking.contextual import ContextualChunker
        from app.config import settings

        with patch.object(settings, "openrouter_api_key", ""):
            with self.assertRaises(ValueError) as raised:
                ContextualChunker(provider="openrouter").chunk(load("baking_instruction_rev_D.pdf"))
        self.assertIn("OPENROUTER_API_KEY", str(raised.exception))

    def test_the_local_provider_needs_no_key_and_makes_no_network_call(self):
        from app.chunking.contextual import ContextualChunker, LocalWriter
        from app.config import settings

        with patch.object(settings, "openrouter_api_key", ""), \
             patch.object(LocalWriter, "write", return_value=self.SENTENCE) as write, \
             patch("app.chunking.contextual.httpx.post") as post:
            found = ContextualChunker(provider="local").chunk(load("baking_instruction_rev_D.pdf"))
        self.assertEqual(write.call_count, len(found))
        post.assert_not_called()
        self.assertTrue(all(chunk.text.startswith(self.SENTENCE) for chunk in found))

    def test_reasoning_a_model_writes_before_its_sentence_is_dropped(self):
        from app.chunking.contextual import ContextualChunker, LocalWriter

        with patch.object(LocalWriter, "write", return_value="<think>Let me see.</think> " + self.SENTENCE):
            found = ContextualChunker(provider="local").chunk(load("baking_instruction_rev_D.pdf"))
        self.assertTrue(all(chunk.text.startswith(self.SENTENCE) for chunk in found))

    def test_an_unknown_provider_names_the_choices(self):
        from app.chunking.contextual import ContextualChunker

        with self.assertRaises(ValueError) as raised:
            ContextualChunker(provider="cloud")
        self.assertIn("local", str(raised.exception))


class SemanticSentenceTests(unittest.TestCase):
    def sentences(self, text):
        from langchain_core.documents import Document

        source = SourceDocument("notes.txt", b"", [Document(page_content=text, metadata={"page": 1})])
        return [s for s, _, _ in get_chunker("semantic")._sentences(source)]

    def test_a_heading_number_does_not_end_a_sentence(self):
        found = self.sentences("Class B applies.\n\n3. Oven temperature bands\n\nBands state the range.")
        self.assertEqual(found, ["Class B applies.", "3. Oven temperature bands", "Bands state the range."])

    def test_table_rows_keep_their_line_breaks(self):
        found = self.sentences("Feature   Class A   Class B\nBaguette   5   10\nRye loaf   10   20")
        self.assertEqual(found, ["Feature Class A Class B\nBaguette 5 10\nRye loaf 10 20"])


if __name__ == "__main__":
    unittest.main()
