"""Tests for verify_runtime_surface.py — the runtime-vs-static API drift gate.

Pure-logic tests for the diff, plus an in-process integration check that
pythontk's live HelpMixin surface matches its committed static registry (the
canonical zero-drift case)."""

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(r"O:\Cloud\Code\_scripts\m3trik\scripts")
sys.path.insert(0, str(SCRIPTS))
# pythontk source on path for the integration test (no install required).
sys.path.insert(0, r"O:\Cloud\Code\_scripts\pythontk")

import verify_runtime_surface as v  # noqa: E402


class TestComputeDrift(unittest.TestCase):
    def test_no_drift_when_equal(self):
        static = {"C": {"a": "method", "b": "property"}}
        runtime = {"C": {"a": "method", "b": "property"}}
        self.assertEqual(v.compute_drift(static, runtime), {})

    def test_missing_flagged(self):
        # Registry promises C.gone; runtime lacks the NAME entirely -> FAIL.
        static = {"C": {"a": "method", "gone": "method"}}
        runtime = {"C": {"a": "method"}}
        report = v.compute_drift(static, runtime)
        self.assertEqual(report["C"]["missing"], ["gone"])
        self.assertEqual(report["C"]["added"], [])
        self.assertEqual(report["C"]["kind_changed"], [])

    def test_added_flagged(self):
        # Metaclass/mixin-injected member the AST walker can't see.
        static = {"C": {"a": "method"}}
        runtime = {"C": {"a": "method", "injected": "method"}}
        report = v.compute_drift(static, runtime)
        self.assertEqual(report["C"]["added"], ["injected"])
        self.assertEqual(report["C"]["missing"], [])

    def test_kind_change_is_not_missing(self):
        # A wrapping decorator over @staticmethod yields a runtime 'method': the
        # member EXISTS, so it must be kind_changed, never missing.
        static = {"C": {"a": "staticmethod"}}
        runtime = {"C": {"a": "method"}}
        report = v.compute_drift(static, runtime)
        self.assertEqual(report["C"]["kind_changed"], [("a", "staticmethod", "method")])
        self.assertEqual(report["C"]["missing"], [])
        self.assertEqual(report["C"]["added"], [])

    def test_only_intersection_of_classes_compared(self):
        # A class on just one side is out of scope (not comparable) -> no report.
        static = {"OnlyStatic": {"a": "method"}}
        runtime = {"OnlyRuntime": {"b": "method"}}
        self.assertEqual(v.compute_drift(static, runtime), {})

    def test_member_kinds_extracts_name_kind(self):
        surface = {"C": [{"name": "a", "kind": "method", "signature": "()"}]}
        self.assertEqual(v._member_kinds(surface), {"C": {"a": "method"}})


class TestPythontkIntegration(unittest.TestCase):
    def test_pythontk_runtime_matches_static(self):
        """The canonical zero-drift case: pythontk has no metaclass magic, so its
        live surface must equal its committed registry."""
        self.assertEqual(v.main(["verify", "pythontk"]), 0)

    def test_runtime_surface_nonempty(self):
        surface = v.runtime_surface_from_package("pythontk")
        self.assertIn("CoreUtils", surface)
        self.assertTrue(any(m["name"] == "listify" for m in surface["CoreUtils"]))

    def test_verify_missing_artifact_skips(self):
        """A missing --runtime artifact -> exit 2 (skip), never a crash: a failed
        DCC dump must not read as drift."""
        self.assertEqual(
            v.main(["verify", "pythontk", "--runtime", "does_not_exist_xyz.json"]), 2
        )


if __name__ == "__main__":
    unittest.main()
