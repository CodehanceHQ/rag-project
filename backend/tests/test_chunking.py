import unittest
from pathlib import Path

from app.chunking import CHUNKERS, SourceDocument, get_chunker
from app.chunking.sections import detect_sections
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
            heading, _, body = chunk.text.partition("\n")
            self.assertTrue(heading.startswith("work_instruction_rev_D.pdf"))
            self.assertLessEqual(len(body), 1000)
        torque = [c for c in chunks if "40 Nm" in c.text]
        self.assertTrue(all("4. Housing assembly" in c.text for c in torque))


if __name__ == "__main__":
    unittest.main()
