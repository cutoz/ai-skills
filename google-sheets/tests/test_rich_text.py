from __future__ import annotations

import unittest

from google_sheets_skill.rich_text import apply_replace_chunks, grapheme_chunks, revision_hash


class RichTextTests(unittest.TestCase):
    def test_replace_chunks_preserves_unaffected_formatting(self) -> None:
        text = "HELLO"
        runs = [
            {"startIndex": 1, "format": {"bold": True, "foregroundColor": {"red": 0.2, "green": 0.4, "blue": 0.9}}},
            {"startIndex": 4, "format": {}},
        ]

        rebuilt_text, rebuilt_runs, rebuilt_chunks, changed_chunk_ids = apply_replace_chunks(
            text=text,
            text_format_runs=runs,
            chunk_ids=["c2", "c3", "c4"],
            replacement_chunks=[{"text": "12"}],
        )

        self.assertEqual(rebuilt_text, "H12O")
        self.assertEqual(changed_chunk_ids, ["c2", "c3", "c4"])
        self.assertEqual(rebuilt_chunks[0].format, {})
        self.assertTrue(rebuilt_chunks[1].format["bold"])
        self.assertTrue(rebuilt_chunks[2].format["bold"])
        self.assertEqual(rebuilt_chunks[3].format, {})
        self.assertEqual(rebuilt_runs[0]["startIndex"], 1)
        self.assertTrue(rebuilt_runs[0]["format"]["bold"])
        self.assertEqual(rebuilt_runs[1], {"startIndex": 3, "format": {}})

    def test_replace_chunks_handles_emoji_graphemes(self) -> None:
        text = "A🧭B"
        runs = [
            {"startIndex": 1, "format": {"bold": True, "foregroundColor": {"green": 0.7}}},
            {"startIndex": 3, "format": {}},
        ]

        rebuilt_text, rebuilt_runs, rebuilt_chunks, _ = apply_replace_chunks(
            text=text,
            text_format_runs=runs,
            chunk_ids=["c2"],
            replacement_chunks=[{"text": "🚦"}],
        )

        self.assertEqual(rebuilt_text, "A🚦B")
        self.assertEqual(len(rebuilt_chunks), 3)
        self.assertEqual(rebuilt_chunks[1].text, "🚦")
        self.assertTrue(rebuilt_chunks[1].format["bold"])
        self.assertEqual(rebuilt_chunks[2].format, {})
        self.assertEqual(rebuilt_runs[0]["startIndex"], 1)
        self.assertEqual(rebuilt_runs[1], {"startIndex": 3, "format": {}})

    def test_revision_hash_changes_when_text_changes(self) -> None:
        original_chunks = grapheme_chunks("ABC", [])
        changed_chunks = grapheme_chunks("ABD", [])
        self.assertNotEqual(
            revision_hash("ABC", original_chunks),
            revision_hash("ABD", changed_chunks),
        )

    def test_replace_chunks_requires_contiguous_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "contiguous"):
            apply_replace_chunks(
                text="ABCDE",
                text_format_runs=[],
                chunk_ids=["c1", "c3"],
                replacement_chunks=[{"text": "Z"}],
            )


if __name__ == "__main__":
    unittest.main()
