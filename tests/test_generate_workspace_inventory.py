#!/usr/bin/python
# coding=utf-8
"""Tests for generate_workspace_inventory.py -- the workspace repo inventory.

The inventory's Domain column is the one declared fact in an otherwise measured
report: what each repo is FOR. It comes from ``m3trik/workspace.json`` through
``sync_workspace``, not from parsing a markdown table -- the parser it replaced
silently read a retired file and reported every repo Unclassified (2026-09-27).
"""

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_workspace_inventory as inv  # noqa: E402
import sync_workspace  # noqa: E402


class TestDomains(unittest.TestCase):
    def test_domains_are_the_manifest_declaration(self):
        self.assertEqual(inv._declared_domains(), sync_workspace.domains())

    def test_every_registry_package_has_a_domain(self):
        domains = inv._declared_domains()
        for package in sync_workspace.ecosystem_packages():
            with self.subTest(package=package):
                self.assertTrue(domains.get(package))


class TestNoMachinePath(unittest.TestCase):
    def test_the_inventory_names_its_workspace_relative_to_itself(self):
        """The inventory is published with m3trik: it named the workspace's
        absolute root (a drive layout, CODE_STANDARD section 11). It now
        names it from the inventory's own folder. Fixed: 2026-11-08"""
        import json
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td).resolve()
            repo = ws / "demo"
            (repo / "demo").mkdir(parents=True)
            (repo / "demo" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
            git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
            for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
                subprocess.run(git + args, check=True, capture_output=True)
            # A hidden folder holding a repo (``.claude``'s ledger history) is
            # tooling state: never a row of the inventory.
            (ws / ".claude" / ".git").mkdir(parents=True)
            md_path, json_path = inv.generate_inventory(ws, ws / "m3trik" / "docs")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            text = md_path.read_text(encoding="utf-8") + json_path.read_text(encoding="utf-8")
        self.assertNotIn(".claude", text)
        self.assertEqual(data["workspace_root"], "../..")
        for form in (ws.as_posix(), str(ws)):
            self.assertNotIn(form, text)


if __name__ == "__main__":
    unittest.main()
