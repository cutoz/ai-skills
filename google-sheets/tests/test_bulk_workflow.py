from __future__ import annotations

import unittest

from google_sheets_skill.rich_text import apply_replace_chunks


class BulkWorkflowTests(unittest.TestCase):
    def test_multi_cell_chunk_replacements_preserve_cell_local_formatting(self) -> None:
        cells = [
            (
                "HELLO",
                [
                    {"startIndex": 1, "format": {"bold": True, "foregroundColor": {"blue": 0.9}}},
                    {"startIndex": 4, "format": {}},
                ],
                ["c2", "c3", "c4"],
                [{"text": "12"}],
                "H12O",
                {"bold": True, "foregroundColor": {"blue": 0.9}},
            ),
            (
                "WORLD",
                [
                    {"startIndex": 0, "format": {"bold": True, "foregroundColor": {"red": 0.8}}},
                    {"startIndex": 2, "format": {}},
                ],
                ["c1", "c2"],
                [{"text": "GO"}],
                "GORLD",
                {"bold": True, "foregroundColor": {"red": 0.8}},
            ),
            (
                "A🧭B",
                [
                    {"startIndex": 1, "format": {"bold": True, "foregroundColor": {"green": 0.7}}},
                    {"startIndex": 3, "format": {}},
                ],
                ["c2"],
                [{"text": "🚦"}],
                "A🚦B",
                {"bold": True, "foregroundColor": {"green": 0.7}},
            ),
        ]

        for text, runs, chunk_ids, replacement_chunks, expected_text, expected_format in cells:
            with self.subTest(text=text):
                rebuilt_text, _, rebuilt_chunks, _ = apply_replace_chunks(
                    text=text,
                    text_format_runs=runs,
                    chunk_ids=chunk_ids,
                    replacement_chunks=replacement_chunks,
                )
                self.assertEqual(rebuilt_text, expected_text)
                replaced_index = min(int(chunk_id[1:]) for chunk_id in chunk_ids) - 1
                self.assertEqual(rebuilt_chunks[replaced_index].format, expected_format)


if __name__ == "__main__":
    unittest.main()
