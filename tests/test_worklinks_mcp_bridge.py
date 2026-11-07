import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import worklinks_mcp_bridge as b

GOOD = {
    "id": "mcp-official-test-0001",
    "title": "Official supported startup intake",
    "url": "https://www.bizinfo.go.kr/foo",
    "source_url": "https://www.bizinfo.go.kr/foo",
    "deadline": "2026-11-13",
    "verified": True,
    "category": "general",
}
INDEX = 'var pendingSupportCandidates=[{"id":"existing","url":"https://www.bizinfo.go.kr/old"}];\nvar jobs=[];'


class TestWorkLinksMCPBridge(unittest.TestCase):
    def test_import_and_duplicate(self):
        text, count = b.apply(INDEX, [GOOD], date(2026, 11, 7))
        self.assertEqual(count, 1)
        text, count = b.apply(text, [GOOD], date(2026, 11, 7))
        self.assertEqual(count, 0)
        self.assertIn("mcp-official-test-0001", text)

    def test_fail_closed(self):
        for bad in (
            {**GOOD, "verified": False},
            {**GOOD, "url": "https://evil.example.com"},
            {**GOOD, "deadline": "2026-10-01"},
            {**GOOD, "title": "<script>x</script>"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                b.apply(INDEX, [bad], date(2026, 11, 7))

    def test_exported_batch_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "batch.json"
            file_path.write_text(json.dumps({
                "schema": b.SCHEMA, "checkpoint": 7, "candidates": [GOOD],
            }), encoding="utf-8")
            self.assertEqual(b.batch_from_file(file_path), (7, [GOOD]))
            file_path.write_text('{"schema":"invalid","candidates":[]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                b.batch_from_file(file_path)

    def test_sqlite_checkpoint_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE checkpoints(id INTEGER,project TEXT,summary TEXT)")
                db.execute("INSERT INTO checkpoints VALUES(1,?,?)", (
                    "worklinks", json.dumps({"schema": b.SCHEMA, "candidates": [GOOD]})
                ))
            self.assertEqual(b.latest_batch(path)[1], [GOOD])


if __name__ == "__main__":
    unittest.main()
