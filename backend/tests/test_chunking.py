import unittest
from pathlib import Path

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
        for name in ("recursive", "structural", "hybrid", "semantic"):
            self.assertEqual(get_chunker(name).name, name)
        self.assertEqual(set(CHUNKERS), {"recursive", "structural", "hybrid", "semantic"})

    def test_unknown_strategy_names_the_choices(self):
        with self.assertRaises(ValueError) as raised:
            get_chunker("nonsense")
        self.assertIn("recursive", str(raised.exception))


class WorkInstructionTests(unittest.TestCase):
    """work_instruction_rev_D.pdf states the torque in section 4, a few
    sentences after naming the bolt it applies to."""

    @classmethod
    def setUpClass(cls):
        cls.source = load("work_instruction_rev_D.pdf")

    def test_sections_are_found_from_the_headings(self):
        titles = [section.title for section in detect_sections(self.source)]
        self.assertEqual(titles[-5:], ["1. Scope", "2. Tooling", "3. Sub-assembly",
                                       "4. Housing assembly", "5. Inspection"])

    def test_recursive_separates_the_torque_from_its_bolt(self):
        torque = [c for c in get_chunker("recursive").chunk(self.source) if "40 Nm" in c.text]
        self.assertTrue(torque)
        self.assertTrue(all("M8" not in c.text for c in torque))

    def test_structural_keeps_the_section_whole(self):
        torque = [c for c in get_chunker("structural").chunk(self.source) if "40 Nm" in c.text]
        self.assertEqual(len(torque), 1)
        self.assertIn("M8", torque[0].text)
        self.assertEqual(torque[0].section, "4. Housing assembly")

    def test_hybrid_pieces_carry_their_heading_and_fit_the_size_limit(self):
        chunks = get_chunker("hybrid").chunk(self.source)
        for chunk in chunks:
            self.assertTrue(chunk.text.startswith("work_instruction_rev_D.pdf"))
            self.assertLessEqual(count_tokens(chunk.text), token_budget())
        torque = [c for c in chunks if "40 Nm" in c.text]
        self.assertTrue(all("4. Housing assembly" in c.text for c in torque))


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


class SemanticSentenceTests(unittest.TestCase):
    def sentences(self, text):
        from langchain_core.documents import Document

        source = SourceDocument("notes.txt", b"", [Document(page_content=text, metadata={"page": 1})])
        return [s for s, _, _ in get_chunker("semantic")._sentences(source)]

    def test_a_heading_number_does_not_end_a_sentence(self):
        found = self.sentences("Class B applies.\n\n3. Fastener torque bands\n\nTorque bands state the range.")
        self.assertEqual(found, ["Class B applies.", "3. Fastener torque bands", "Torque bands state the range."])

    def test_table_rows_keep_their_line_breaks(self):
        found = self.sentences("Feature   Class A   Class B\nPort face   0.02   0.04\nBore land   0.02   0.03")
        self.assertEqual(found, ["Feature Class A Class B\nPort face 0.02 0.04\nBore land 0.02 0.03"])


if __name__ == "__main__":
    unittest.main()
