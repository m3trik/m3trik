#!/usr/bin/python
# coding=utf-8
"""Tests for sync_scene_records.py -- what derives from ``ptk.SceneRecords``.

The declaration is pythontk's; the owner doc's records table and unitytk's
importer channel list are derived from it. These tests pin that the doc region
exists and is current, that the Unity channels match the records declared for
Unity and accept their declared versions (the same checks as ``--check``),
and that the splice refuses a doc
without its markers instead of guessing where the table goes.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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
        self.assertEqual(
            s.unity_mismatch(), {"undeclared": [], "unread": [], "version": []}
        )

    def test_a_version_the_unity_importer_does_not_accept_is_reported(self):
        """A record bumped without its importer: Unity would refuse the payload."""
        bumped = [
            SimpleNamespace(
                key=spec.key,
                consumers=spec.consumers,
                version=spec.version + (spec.key == "shadow_metadata"),
            )
            for spec in s._records().deliverable()
        ]
        mismatch = s.unity_mismatch(SimpleNamespace(deliverable=lambda: bumped))
        self.assertEqual(len(mismatch["version"]), 1, mismatch)
        self.assertIn("ShadowPlaneController", mismatch["version"][0])

    def test_the_two_dcc_producer_tables_agree_modulo_the_ledger(self):
        self.assertEqual(s.producer_parity(), [])

    def test_every_producer_names_a_declared_record(self):
        from pythontk import RecordSpec

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


def _text(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


class TestGeneratedTypes(unittest.TestCase):
    """What the other languages read is generated from the declaration and
    held to it (the same checks as ``--check``)."""

    def test_the_web_records_module_is_current(self):
        self.assertEqual(
            _text(s.WEB_RECORDS),
            s.render_records_js(),
            "stale kernel/records.js -- run m3trik/scripts/sync_scene_records.py",
        )

    def test_every_web_projected_record_is_in_it(self):
        text = s.render_records_js()
        for spec in s._records().web_projected():
            self.assertIn(f"key: '{spec.key}'", text)
            self.assertIn(f"webKey: '{spec.web.key}'", text)

    def test_the_csharp_record_types_are_current(self):
        targets = s.record_cs_targets()
        self.assertTrue(targets, "no record declares a shape Unity reads")
        for spec, shape, path in targets:
            with self.subTest(record=spec.key):
                self.assertEqual(_text(path), s.render_record_cs(spec, shape))
                meta = path.with_name(path.name + ".meta")
                self.assertEqual(_text(meta), s.record_cs_meta(spec))
                # Beside the importer that reads it, in its feature folder.
                self.assertEqual(path.parent.name, "ArticulatedRig")

    def test_a_record_types_guid_is_its_records_alone(self):
        records = s._records()
        a = s.record_cs_meta(records.ARTICULATION)
        self.assertEqual(a, s.record_cs_meta(records.ARTICULATION))
        self.assertNotEqual(a, s.record_cs_meta(records.SHADOWS))

    def test_jsdoc_types_of_the_schema_shapes(self):
        number_or_null = {"anyOf": [{"type": "number"}, {"type": "null"}]}
        self.assertEqual(s.jsdoc_type(number_or_null), "number|null")
        self.assertEqual(
            s.jsdoc_type({"type": "array", "prefixItems": [{"type": "number"}] * 3}),
            "[number, number, number]",
        )
        self.assertEqual(
            s.jsdoc_type({"type": "string", "enum": ["a", "b"]}), "'a'|'b'"
        )
        self.assertEqual(
            s.jsdoc_type({"type": "array", "items": {"$ref": "#/$defs/Joint"}}),
            "Joint[]",
        )

    def test_a_csharp_class_drops_its_family_prefix(self):
        self.assertEqual(
            s._cs_name("ArticulationRecord", "ArticulationRecord"), "Payload"
        )
        self.assertEqual(s._cs_name("ArticulationJoint", "ArticulationRecord"), "Joint")
        self.assertEqual(s._cs_name("Other", "ArticulationRecord"), "Other")


if __name__ == "__main__":
    unittest.main()
