#!/usr/bin/python
# coding=utf-8
"""Tests for ledger_drift.py -- has the code a ledger entry names moved?

Held against the real workspace (the anchors resolve through affected_tests'
index of it): which names an entry anchors, that a recorded hash of today's
code reads as no drift, and that a different or vanished definition reads as
drift -- the signal that sends an entry back to be re-measured.
"""

import ast
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ledger_drift as ld  # noqa: E402

ENTRY = (
    "## 2026-10-20 | pythontk | S2 | ready | `StatusBadge.gate` refuses something\n"
    "- Where: pythontk `core_utils/status_badge.py` `ptk.StatusBadge.discover_module_names`, "
    "the `is_import_standin` check, and `NoSuchThingAnywhere`\n"
    "- Symptom: a probe\n"
)


class TestAnchoring(unittest.TestCase):
    def test_names_come_from_the_heading_and_where_line_with_aliases_stripped(self):
        names = ld.candidate_names(ENTRY)
        self.assertIn("StatusBadge.gate", names)
        self.assertIn("StatusBadge.discover_module_names", names)  # ptk. stripped
        self.assertIn("is_import_standin", names)
        self.assertNotIn("probe", names)  # the Symptom line anchors nothing

    def test_a_stamp_anchors_only_what_resolves(self):
        line = ld.stamp_line(ENTRY)
        self.assertTrue(line.startswith("- Anchors: "), line)
        anchored = dict(pair.split("@") for pair in line[len("- Anchors: "):].split())
        self.assertIn("StatusBadge.gate", anchored)
        self.assertIn("is_import_standin", anchored)  # a bare method resolves
        self.assertNotIn("NoSuchThingAnywhere", anchored)

    def test_todays_hash_is_no_drift(self):
        entry = ENTRY + ld.stamp_line(ENTRY) + "\n"
        self.assertEqual(ld.drift(entry), [])

    def test_a_changed_and_a_vanished_definition_both_drift(self):
        entry = ENTRY + "- Anchors: StatusBadge.gate@00000000 NoSuchThingAnywhere@12345678\n"
        moved = {name: now for name, _recorded, now in ld.drift(entry)}
        self.assertEqual(set(moved), {"StatusBadge.gate", "NoSuchThingAnywhere"})
        self.assertIsNone(moved["NoSuchThingAnywhere"])  # GONE
        self.assertIsNotNone(moved["StatusBadge.gate"])

    def test_the_test_harness_anchors_too(self):
        """Entries about the runners name harness code (mayatk's suite driver)."""
        entry = "## 2026-10-21 | mayatk | S2 | ready | x\n- Where: mayatk `test/_suite_driver.py` `_module_suite`\n"
        self.assertTrue((ld.stamp_line(entry) or "").startswith("- Anchors: _module_suite@"))

    def test_an_entry_without_anchors_reports_nothing(self):
        self.assertEqual(ld.drift(ENTRY), [])

    def test_the_hash_reads_neither_of_the_interpreters_reprs(self):
        """Bug: anchors hashed ``ast.dump``, whose text changes between Python
        versions (3.12 adds ``type_params``, 3.13 omits empty fields), so under
        another interpreter every recorded anchor read as drift (measured: 5 of
        5 under 3.12, 1 genuine). ``ast.unparse`` is no cure: 3.12 re-quotes
        f-strings. Fixed: 2026-10-24"""
        before = ld.fingerprint("StatusBadge.gate", ["pythontk"])
        real_dump, real_unparse = ast.dump, ast.unparse

        def other_dump(node, *args, **kwargs):  # 3.12's repr
            return real_dump(node, *args, **kwargs).replace("decorator_list=", "type_params=[], decorator_list=")

        def other_unparse(node):  # 3.12's f-string quoting
            return real_unparse(node).replace('"', "'")

        with mock.patch.object(ast, "dump", other_dump), mock.patch.object(ast, "unparse", other_unparse):
            self.assertEqual(ld.fingerprint("StatusBadge.gate", ["pythontk"]), before)

    def test_a_format_spec_reads_the_same_with_312s_trailing_empty_string(self):
        """3.12 parses ``f"{a:<{w}}"``'s spec as ``['<', w, '']``; 3.11 as ``['<', w]``."""
        def spec_values(node):
            return node.value.values[0].format_spec.values

        node_311, node_312 = (ast.parse('f"{a:<{w}}"').body[0] for _ in range(2))
        empty = [v for v in spec_values(node_311) if isinstance(v, ast.Constant) and v.value == ""]
        for value in empty:  # whichever interpreter runs this, build both forms
            spec_values(node_311).remove(value)
        if not empty:
            spec_values(node_312).append(ast.Constant(value=""))
        self.assertNotEqual(len(spec_values(node_311)), len(spec_values(node_312)))
        self.assertEqual(ld.canonical(node_311), ld.canonical(node_312))


if __name__ == "__main__":
    unittest.main()
