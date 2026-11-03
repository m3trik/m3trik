#!/usr/bin/python
# coding=utf-8
"""Tests for sync_operation_contract.py -- unitytk's C# copy of pythontk's operation payloads.

The payloads are pythontk's (``OpRequest``, ``Outcome`` and its parts, the
catalog's entry and document); the Unity kernel reads and writes them through
generated types. These tests pin that the committed files are current (the
same check as ``--check``), that every field and every choice a payload
declares is spelled in its type, that each ``.meta`` GUID is fixed by its
type's name, and the null rule (a typed field refuses null, an untyped one
admits it).
"""

import re
import sys
import unittest
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_operation_contract as c  # noqa: E402


class TestOperationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = c._payloads()

    def test_the_generated_files_are_current(self):
        for path, text in c.targets():
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"missing {path}: run sync_operation_contract.py")
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    text,
                    f"stale {path.name}: run m3trik/scripts/sync_operation_contract.py",
                )

    def test_every_field_and_choice_is_spelled(self):
        for name, payload in self.payloads.items():
            schema = payload.json_schema()
            text = c.render_type(name, payload, self.payloads)
            for key, prop in schema.get("properties", {}).items():
                with self.subTest(payload=name, field=key):
                    self.assertRegex(text, rf"public [^;]+ @?{key};")
                    self.assertIn(f'Wire.Put(o, "{key}"', text)
                    for choice in prop.get("enum") or ():
                        self.assertIn(f'"{choice}"', text)

    def test_the_effects_include_code(self):
        """``code`` (runs code: no plan, applied only) is one of the entry's effects."""
        text = c.render_type("OperationEntry", self.payloads["OperationEntry"], self.payloads)
        choice = re.search(r'Wire\.Choice\(o, "effect", ([^)]*)\);', text).group(1)
        self.assertEqual(choice, '"read", "state", "files", "code"')

    def test_null_is_refused_only_where_the_payload_refuses_it(self):
        text = c.render_type("Outcome", self.payloads["Outcome"], self.payloads)
        refused = re.search(r'Wire\.NotNull\(o, "Outcome", ([^)]*)\);', text).group(1)
        self.assertIn('"status"', refused)
        self.assertNotIn('"result"', refused, "an untyped result admits null")
        # Typed but optional: left out when unset (pythontk writes no None), never null.
        self.assertIn('"error"', refused)

    def test_each_meta_guid_is_fixed_by_its_name(self):
        guids = {}
        for path, text in c.targets():
            if path.suffix != ".meta":
                continue
            name = path.name.split(".")[0]
            guid = re.search(r"guid: ([0-9a-f]{32})", text).group(1)
            self.assertEqual(guid, uuid.uuid5(uuid.NAMESPACE_URL, c.GUID_NAMESPACE + name).hex)
            guids[guid] = name
        self.assertEqual(len(guids), len(self.payloads) + 1, "one GUID per type and Wire")


if __name__ == "__main__":
    unittest.main()
