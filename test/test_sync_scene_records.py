#!/usr/bin/python
# coding=utf-8
"""Tests for sync_scene_records.py -- what derives from ``ptk.SceneRecords``.

The declaration is pythontk's; the owner doc's records table and unitytk's
importer channel list are derived from it. These tests pin that the doc region
exists and is current, that the Unity channels match the records declared for
Unity and each declares the shape its generated reader reads (the same checks
as ``--check``), and that the splice refuses a doc
without its markers instead of guessing where the table goes.
"""

import re
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
            s.unity_mismatch(), {"undeclared": [], "unread": [], "shapeless": []}
        )

    def test_a_unity_record_without_a_shape_is_reported(self):
        """A record Unity reads declares its shape: its importer reads it
        through the generated type, and the one version it reads is that
        type's (``<Shape>.CurrentVersion``). One declaring none is said under
        ``shapeless`` -- whatever else is out of step, which the test above
        reports. Added: 2026-10-20"""
        shadows = s._records().SHADOWS.key
        stripped = [
            SimpleNamespace(
                key=spec.key,
                consumers=spec.consumers,
                shape=None if spec.key == shadows else spec.shape,
            )
            for spec in s._records().deliverable()
        ]
        before = s.unity_mismatch()["shapeless"]
        after = s.unity_mismatch(SimpleNamespace(deliverable=lambda: stripped))
        self.assertEqual(
            [key for key in after["shapeless"] if key not in before], [shadows]
        )

    def test_a_channel_line_spells_its_key_once(self):
        """A carrier key's one spelling in unitytk is its ``UnitytkRecords``
        constant; the line's comment names only the importer that reads it.
        Added: 2026-10-20"""
        line = 'public const string Shadows = "shadows";  // channel → ShadowPlaneController'
        found = s._UNITY_CHANNEL.search(line)
        self.assertEqual(
            (found["key"], found["reader"]), ("shadows", "ShadowPlaneController")
        )
        unread = s._UNITY_CHANNEL.search('public const string Handoff = "handoff";')
        self.assertIsNone(unread, "a constant with no channel comment is no channel")

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
            registered = s.registered_producer_specs(s.HOSTS[dcc])
            for spec in s.producer_specs(path) | registered:
                self.assertIn(spec, declared, f"{dcc}: {spec}")

    def test_a_producer_registered_as_an_entry_point_counts_for_its_host(self):
        """A tool outside the libraries registers its producer in its own
        pyproject.toml (SceneRecords.HOOK_GROUP); read as TOML, nothing
        imported, and an undeclared key comes back as itself."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "pyproject.toml"
            project.write_text(
                '[project.entry-points."m3trik.scene_records"]\n'
                '"maya.producer.lightmaps" = "tentacle.lm.maya:LightmapRecords.export_record"\n'
                '"blender.producer.lightmaps" = "tentacle.lm.blender:LightmapRecords.export_record"\n'
                '"maya.owner.shot_store" = "tentacle.shots.maya:ShotStore"\n'
                '"maya.producer.no_such" = "tentacle.x:X.export_record"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                s.registered_producer_specs("maya", projects=(project,)),
                {"LIGHTMAPS", "no_such"},
            )
            self.assertEqual(
                s.registered_producer_specs("blender", projects=(project,)), {"LIGHTMAPS"}
            )

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

    def test_every_glb_block_is_in_it(self):
        """Each block a GLB carries -- every record's (``RecordSpec.glb``) and
        the handoff -- under its record's key, at the version the page reads,
        and every one in ``BLOCKS``. Added: 2026-10-20"""
        records, handoff = s._records(), s._handoff()
        names = s._spec_names(records)
        text = s.render_records_js()
        blocks = [
            (names[id(spec)], spec.key, spec.glb.version)
            for spec in records.glb_records()
        ]
        blocks.append(("HANDOFF", handoff.KEY, handoff.VERSION))
        for name, key, version in blocks:
            with self.subTest(block=key):
                self.assertIn(
                    f"export const {name} = Object.freeze({{ key: '{key}', "
                    f"version: {version} }});",
                    text,
                )
        self.assertIn(
            "export const BLOCKS = Object.freeze(["
            + ", ".join(name for name, _key, _version in blocks)
            + "]);",
            text,
        )
        self.assertNotIn("webKey", text)

    def test_the_retired_block_keys_are_in_it(self):
        """The root-extras keys a GLB written before the current blocks
        carries (``SceneRecords.RETIRED_BLOCKS``: the ``*_web`` blocks, the
        ``scene_sidecar`` envelope) are exported as ``RETIRED_BLOCK_KEYS``,
        so the viewer names a file holding one stale instead of loading it
        unlit and unrigged without a word. None is a current block's key.
        Added: 2026-10-24"""
        records, handoff = s._records(), s._handoff()
        retired = records.RETIRED_BLOCKS
        self.assertTrue(
            {"lightmap_web", "shadow_web", "animation_web", "articulation_web",
             "scene_sidecar"} <= set(retired)
        )
        current = {spec.key for spec in records.glb_records()} | {handoff.KEY}
        self.assertFalse(current & set(retired), "a retired key is current")
        self.assertIn(
            "export const RETIRED_BLOCK_KEYS = Object.freeze(["
            + ", ".join(f"'{key}'" for key in retired)
            + "]);",
            s.render_records_js(),
        )

    def test_the_policy_states_its_settings_alone(self):
        """The handoff's version is its shape's (``HandoffBlock.CurrentVersion``,
        generated with it), so the policy repeats no number of it.
        Added: 2026-10-20"""
        self.assertNotIn("HandoffVersion", s.render_policy_cs())

    def test_the_csharp_record_types_are_current(self):
        targets = s.record_cs_targets()
        self.assertTrue(targets, "no record declares a shape Unity reads")
        for spec, shape, path in targets:
            with self.subTest(record=spec.key):
                self.assertEqual(_text(path), s.render_record_cs(spec, shape))
                meta = path.with_name(path.name + ".meta")
                self.assertEqual(_text(meta), s.record_cs_meta(spec))

    def test_a_record_type_states_its_version_first(self):
        """Each generated record type states the version a reader reads -- its
        record's declared one -- before its shape, so no importer spells it.
        Added: 2026-10-20"""
        records = s._records()
        for spec in records.deliverable():
            shape = records.shape(spec)
            if shape is None:
                continue
            with self.subTest(record=spec.key):
                text = s.render_record_cs(spec, shape)
                body = text.split(f"public static partial class {shape.__name__}", 1)
                members = [
                    line.strip()
                    for line in body[1].splitlines()
                    if line.strip().startswith("public ")
                ]
                self.assertRegex(
                    members[0], rf"^public const int \w*Version = {spec.version};$"
                )

    def test_a_record_types_read_refuses_what_its_shape_refuses(self):
        """A generated ``Read`` throws ``FormatException`` where the declared
        shape refuses: a required key absent (``Wire.Require``), a nested
        value or a list item that is no object (``Wire.Obj`` / ``Wire.Objs``),
        a value outside its choices (``Wire.Choice``). Added: 2026-10-20"""
        for helper in ("Require", "Obj", "Objs", "Choice"):
            with self.subTest(helper=helper):
                body = re.search(
                    rf"public static [^\n]*\b{helper}\b[^\n]*\n(.*?)\n    }}",
                    s.CS_WIRE,
                    re.S,
                )
                self.assertIsNotNone(body, f"no Wire.{helper}")
                self.assertIn("throw new FormatException", body.group(1))
        self.assertNotIn(" Items(", s.CS_WIRE, "a list's items read by their spec")
        records = s._records()
        rendered = {
            spec.key: s.render_record_cs(spec, records.shape(spec))
            for spec in (records.HANDOFF, records.EMISSIVE_GROUPS)
        }
        for key, line in (
            (
                records.HANDOFF.key,
                'Wire.Require(o, "Payload", "version", "instructions", '
                '"assembly", "rendering");',
            ),
            (
                records.HANDOFF.key,
                'assembly = Wire.Objs(o, "assembly", HandoffPart.Read),',
            ),
            (
                records.HANDOFF.key,
                'extras = Wire.Obj(o, "extras", HandoffExtras.Read),',
            ),
            (
                records.EMISSIVE_GROUPS.key,
                'Wire.Choice(o, "encoding", "vertex-color", "channels");',
            ),
            (
                records.EMISSIVE_GROUPS.key,
                'Wire.Choice(o, "slot", "0", "1", "2", "3");',
            ),
        ):
            with self.subTest(record=key, line=line):
                self.assertIn(line, rendered[key])

    def test_a_value_of_another_kind_is_refused_not_read_as_null(self):
        """A present, non-null array or free object of another kind throws
        ``FormatException`` (``Wire.Elements`` under ``Nums`` / ``Strs`` /
        ``Objs``, ``Wire.Dict``) -- it read as null past ``Require`` and
        ``NotNull``, and the importer then crashed on it (``"shots": {}``: a
        NullReferenceException out of ``OnPostprocessModel``). A tuple of
        another length is refused (pythontk's validate: "expected N items"),
        and so is an integer past an int's range, which read wrapped
        (``1e12`` as 0). Added: 2026-10-24"""
        def body(helper):
            found = re.search(
                rf"public static [^\n]*\b{helper}(?:<T>)?\(.*?\n    \{{\n(.*?)\n    \}}\n",
                s.CS_WIRE,
                re.S,
            )
            self.assertIsNotNone(found, f"no Wire.{helper}")
            return found.group(1)

        elements = body("Elements")
        self.assertIn("is not an array", elements)
        self.assertIn("list.Count != length", elements)
        self.assertIn("is not an object", body("Dict"))
        self.assertIn("int.MaxValue", body("Int"))
        for helper in ("Nums", "Strs", "Objs"):
            with self.subTest(helper=helper):
                self.assertIn("Elements(o, key, length)", body(helper))
                self.assertNotIn("is IList<object> list)) return null", body(helper))

        records = s._records()
        for spec, line in (
            (records.SHOTS, 'shots = Wire.Objs(o, "shots", Shot.Read),'),
            (records.LIGHTMAPS, 'scaleOffset = Wire.Nums(o, "scaleOffset", 4),'),
            (records.LIGHTMAPS, 'hierarchy = Wire.Strs(o, "hierarchy"),'),
            (records.SHADOWS, 'canvas = Wire.Nums(o, "canvas", 4),'),
            (records.HANDOFF, 'rendering = Wire.Dict(o, "rendering", objectValues: true),'),
        ):
            with self.subTest(record=spec.key, line=line):
                self.assertIn(line, s.render_record_cs(spec, records.shape(spec)))
        for spec, shape, _path in s.record_cs_targets():
            with self.subTest(record=spec.key):
                self.assertNotRegex(
                    s.render_record_cs(spec, shape),
                    r"= Wire\.Get\([^\n]*\) as ",
                    "a member read unchecked through a cast",
                )

    def test_every_array_and_free_object_shape_reads_checked(self):
        """``_cs_member`` over the shapes no current record declares: a mixed
        tuple reads through ``Wire.Elements`` with its length, a string tuple
        through ``Wire.Strs`` with its, a free object with free values through
        ``Wire.Dict`` alone. Added: 2026-10-24"""
        cases = (
            (
                {"type": "array", "prefixItems": [{"type": "string"}, {"type": "number"}]},
                ("IList<object>", 'Wire.Elements(o, "k", 2)'),
            ),
            (
                {"type": "array", "prefixItems": [{"type": "string"}] * 2},
                ("List<string>", 'Wire.Strs(o, "k", 2)'),
            ),
            (
                {"type": "array", "items": {"type": "number"}},
                ("double[]", 'Wire.Nums(o, "k")'),
            ),
            (
                {"type": "object", "additionalProperties": {"type": "number"}},
                ("IDictionary<string, object>", 'Wire.Dict(o, "k")'),
            ),
            (
                {"anyOf": [{"type": "object"}, {"type": "null"}]},
                ("IDictionary<string, object>", 'Wire.Dict(o, "k")'),
            ),
        )
        for node, expected in cases:
            with self.subTest(node=node):
                self.assertEqual(s._cs_member("k", node, "TestRecord"), expected)

    def test_the_deliverable_format_reference_is_current(self):
        """``DELIVERABLE_FORMAT.md`` is generated whole from the declarations
        (the same check as ``--check``): a row and a section per record, each
        at the version every file states it in. Added: 2026-10-20"""
        text = s.render_format_md()
        for spec in s._records().deliverable():
            with self.subTest(record=spec.key):
                self.assertIn(f"\n## {spec.key}\n", text)
                self.assertIn(f"`data_export.{spec.key}` v{spec.version}", text)
                if spec.glb:
                    self.assertIn(f"`extras.{spec.key}` v{spec.glb.version}", text)
        self.assertEqual(
            _text(s.FORMAT_MD),
            text,
            "stale DELIVERABLE_FORMAT.md -- run m3trik/scripts/sync_scene_records.py",
        )

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
