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


if __name__ == "__main__":
    unittest.main()
