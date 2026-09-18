#!/usr/bin/python
# coding=utf-8
"""Tests for sync_scene_records.py -- what derives from ``ptk.SceneRecords``.

The declaration is pythontk's; the owner doc's records table and unitytk's
importer channel list are derived from it. These tests pin that the doc region
exists and is current, that the Unity channels match the records declared for
Unity (the same checks as ``--check``), and that the splice refuses a doc
without its markers instead of guessing where the table goes.
"""

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_scene_records as s  # noqa: E402


class TestSceneRecordsDerivedSurfaces(unittest.TestCase):
    def test_the_doc_region_is_current(self):
        text = s.DOC.read_text(encoding="utf-8")
        self.assertEqual(
            s.splice(text, s.render_table()),
            text,
            "stale records table -- run m3trik/scripts/sync_scene_records.py",
        )

    def test_every_record_has_a_row(self):
        table = s.render_table()
        for spec in s._records().all():
            self.assertIn(f"`{spec.key}`", table, spec.key)

    def test_unity_reads_exactly_the_records_declared_for_it(self):
        self.assertEqual(s.unity_mismatch(), {"undeclared": [], "unread": []})

    def test_the_two_dcc_producer_tables_agree_modulo_the_ledger(self):
        self.assertEqual(s.producer_parity(), [])

    def test_every_producer_names_a_declared_record(self):
        from pythontk.core_utils.scene_records import RecordSpec

        declared = {
            name
            for name, value in vars(s._records()).items()
            if isinstance(value, RecordSpec)
        }
        for dcc, path in s.FBX_UTILS.items():
            for spec in s.producer_specs(path):
                self.assertIn(spec, declared, f"{dcc}: {spec}")

    def test_splice_refuses_a_doc_without_its_markers(self):
        with self.assertRaises(ValueError):
            s.splice("# no markers here\n", "| table |")

    def test_splice_is_idempotent(self):
        text = f"head\n{s.BEGIN}\nold\n{s.END}\ntail\n"
        once = s.splice(text, "new")
        self.assertEqual(s.splice(once, "new"), once)
        self.assertIn("head", once)
        self.assertIn("tail", once)


if __name__ == "__main__":
    unittest.main()
