import datetime as dt
import unittest
from unittest.mock import patch
from scripts import worklinks_global_accelerators as monitor


class OfficialAcceleratorTests(unittest.TestCase):
    def test_yc_batch_and_deadline_timezone(self):
        text = ("We are accepting applications for the Winter 2027 Batch. "
                "The deadline to apply on-time is November 2 at 8pm PT.")
        parsed = monitor.parse_yc(text)
        self.assertEqual(parsed[:2], ("Winter", 2027))
        self.assertEqual(parsed[2], "2026-11-03T13:00+09:00")
        self.assertTrue(parsed[3])

    def test_no_made_up_deadline(self):
        self.assertIsNone(monitor.parse_yc("YC has a program."))

    def test_error_is_visible(self):
        with patch.object(monitor, "OFFICIAL_COLLECTORS", (
            ("Y Combinator 공식 모집", lambda: (_ for _ in ()).throw(ValueError("blocked"))),
        )):
            rows, status = monitor.scan_global()
        self.assertEqual(rows, [])
        self.assertEqual(status[0]["status"], "error")
        self.assertIn("blocked", status[0]["error"])

    def test_techstars_unknown_deadline(self):
        self.assertIsNone(monitor.parse_techstars_deadline("Final Deadline coming soon"))

    def test_ef_deadline(self):
        self.assertEqual(monitor.parse_ef_deadline("Apply by 31 December 2026"), "2026-12-31")


if __name__ == "__main__":
    unittest.main()
