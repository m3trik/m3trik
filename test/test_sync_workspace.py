#!/usr/bin/python
# coding=utf-8
"""Tests for sync_workspace.py -- the workspace manifest and what restates it.

``m3trik/workspace.json`` is the one declaration of the cascade, the registry set
and every unit's domain line. These tests pin that the real manifest validates and
that every restatement agrees with it (the same checks as ``--check``), and the
semantics on fixture manifests: what the registry set is, what the Dispatch table
looks like, and that a drifted CI loop or a missing charter is reported.
"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_workspace as sw  # noqa: E402

FIXTURE = {
    "cascade": ["core", "ui"],
    "units": [
        {"path": "core", "release": "cascade", "domain": "Core"},
        {"path": "extra", "release": "standalone", "domain": "Extra"},
        {"path": "ui", "release": "cascade", "domain": "UI"},
        {"path": "notes", "release": "none", "domain": "Notes"},
    ],
}


class TestRealManifest(unittest.TestCase):
    def test_the_manifest_validates(self):
        self.assertEqual(sw.validate(sw.load()), [])

    def test_the_ci_sibling_loops_list_the_registry_set(self):
        self.assertEqual(sw.workflow_drift(), [])

    def test_every_declared_unit_on_disk_carries_its_charter(self):
        self.assertEqual(sw.missing_charters(), [])

    def test_the_root_dispatch_table_is_current(self):
        if not sw.ROOT_CLAUDE.is_file():
            self.skipTest("no workspace root checkout (a CI runner clones repos only)")
        self.assertIsNone(sw.dispatch_drift())


class TestSemantics(unittest.TestCase):
    def test_the_registry_set_is_the_cascade_then_the_standalones(self):
        self.assertEqual(sw.ecosystem_packages(FIXTURE), ("core", "ui", "extra"))

    def test_validate_names_every_problem(self):
        broken = {
            "cascade": ["core"],
            "units": [
                {"path": "core", "release": "cascade", "domain": "Core"},
                {"path": "core", "release": "sometimes", "domain": ""},
            ],
        }
        problems = " | ".join(sw.validate(broken))
        for fragment in ("duplicate unit paths", "release must be", "no domain line"):
            self.assertIn(fragment, problems)

    def test_the_cascade_must_name_exactly_the_cascade_units(self):
        drifted = dict(FIXTURE, cascade=["core"])
        self.assertTrue(any("cascade" in p for p in sw.validate(drifted)))

    def test_a_manifest_without_a_cascade_is_malformed(self):
        # push.ps1 reads the cascade raw: an empty or missing one would release
        # nothing in order and validate nothing strictly, so the gate refuses it.
        units = [dict(u, release="none") for u in FIXTURE["units"]]
        for manifest in ({"units": units}, {"cascade": [], "units": units}, {}):
            with self.subTest(manifest=manifest):
                self.assertIn("no cascade declared", sw.validate(manifest))

    def test_the_dispatch_table_links_each_charter_in_manifest_order(self):
        table = sw.render_dispatch(FIXTURE).splitlines()
        self.assertEqual(table[:2], ["| Unit | Domain |", "|:---|:---|"])
        self.assertEqual(table[2], "| [`core/`](core/CLAUDE.md) | Core |")
        self.assertEqual(len(table), 2 + len(FIXTURE["units"]))

    def test_splice_replaces_only_the_table_under_the_heading(self):
        text = "# Title\n\n## Dispatch\n\n| a |\n| b |\n\n## Next\n| keep |\n"
        spliced = sw.splice_dispatch(text, "| new |")
        self.assertEqual(
            spliced, "# Title\n\n## Dispatch\n\n| new |\n\n## Next\n| keep |\n"
        )

    def test_splice_refuses_a_file_without_the_heading_or_its_table(self):
        with self.assertRaises(ValueError):
            sw.splice_dispatch("# Title\n| a |\n", "| new |")
        with self.assertRaises(ValueError):
            sw.splice_dispatch("## Dispatch\n\n## Next\n| a |\n", "| new |")

    def test_a_drifted_ci_loop_is_reported_and_an_unrelated_loop_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            wanted = " ".join(sw.ecosystem_packages())
            (Path(tmp) / "ok.yml").write_text(f"for repo in {wanted}; do\n")
            (Path(tmp) / "other.yml").write_text("for repo in alpha beta; do\n")
            (Path(tmp) / "bad.yml").write_text("for repo in pythontk uitk; do\n")
            drift = sw.workflow_drift(Path(tmp))
        self.assertEqual(len(drift), 1)
        self.assertTrue(drift[0].startswith("bad.yml:1:"))


if __name__ == "__main__":
    unittest.main()
