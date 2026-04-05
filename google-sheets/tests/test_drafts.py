from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google_sheets_skill import drafts


class DraftTests(unittest.TestCase):
    def test_add_or_replace_operation_keeps_latest_by_key(self) -> None:
        draft = {"operations": [{"key": "content:Sheet1:A1", "value": "old"}]}
        drafts.add_or_replace_operation(draft, {"key": "content:Sheet1:A1", "value": "new"})
        self.assertEqual(draft["operations"], [{"key": "content:Sheet1:A1", "value": "new"}])

    def test_remove_operations_keeps_conflicts_staged(self) -> None:
        draft = {
            "operations": [
                {"key": "content:Sheet1:A1"},
                {"key": "content:Sheet1:A2"},
                {"key": "format:Sheet1:A1"},
            ]
        }
        drafts.remove_operations(draft, {"content:Sheet1:A1", "format:Sheet1:A1"})
        self.assertEqual(draft["operations"], [{"key": "content:Sheet1:A2"}])

    def test_create_and_persist_active_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "drafts.json"
            with patch("google_sheets_skill.paths.DRAFTS_PATH", path), patch("google_sheets_skill.drafts.DRAFTS_PATH", path):
                created = drafts.create_draft("roadmap", "sheet-123", "Sheet1")
                active = drafts.get_active_draft()
                self.assertEqual(active["id"], created["id"])
                self.assertEqual(active["name"], "roadmap")
                self.assertEqual(active["spreadsheet_id"], "sheet-123")
                self.assertEqual(active["tab"], "Sheet1")


if __name__ == "__main__":
    unittest.main()
