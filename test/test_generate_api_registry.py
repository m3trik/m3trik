"""Tests for generate_api_registry.py — focused on the logic added in the
context-budget pass: shadow-report parity bucketing and JSON reconstruction of
non-walked packages (so a partial run still produces a complete shadow report)."""

import ast
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

SCRIPTS = Path(r"O:\Cloud\Code\_scripts\m3trik\scripts")
sys.path.insert(0, str(SCRIPTS))

import generate_api_registry as g  # noqa: E402


def _cls(name: str) -> "g.ClassEntry":
    return g.ClassEntry(name=name, summary="", line=1, bases=["object"], members=[])


def _mod(relpath: str, classes: list) -> "g.ModuleEntry":
    return g.ModuleEntry(relpath=relpath, summary="", functions=[], classes=classes)


def _pkg(name: str, modules: list) -> "g.PackageData":
    return g.PackageData(name=name, source_root=f"{name}/{name}", generated_at="2026-06-21", modules=modules)


class TestShadowBucketing(unittest.TestCase):
    def test_parity_vs_genuine_split(self):
        # Bevel: mayatk + blendertk only -> intentional port parity.
        # CoreUtils: pythontk + mayatk    -> genuine cross-layer collision.
        mayatk = _pkg("mayatk", [_mod("edit_utils/_edit_utils.py", [_cls("Bevel"), _cls("CoreUtils")])])
        blendertk = _pkg("blendertk", [_mod("edit_utils/_edit_utils.py", [_cls("Bevel")])])
        pythontk = _pkg("pythontk", [_mod("core_utils/_core_utils.py", [_cls("CoreUtils")])])

        md = g.emit_shadow_report([pythontk, mayatk, blendertk])
        self.assertIn("Intentional mayatk", md, "parity bucket header missing")
        genuine, parity = md.split("Intentional mayatk", 1)

        self.assertIn("CoreUtils", genuine, "genuine cross-layer collision should be in the top section")
        self.assertNotIn("Bevel", genuine, "intentional parity must NOT pollute the genuine section")
        self.assertIn("Bevel", parity, "mayatk<->blendertk parity should be bucketed separately")

    def test_no_collisions_message(self):
        md = g.emit_shadow_report([_pkg("pythontk", [_mod("m.py", [_cls("Solo")])])])
        self.assertIn("No cross-package name collisions", md)


class TestJsonReconstruction(unittest.TestCase):
    def test_roundtrip_preserves_symbols(self):
        pkg = _pkg("pythontk", [_mod("m.py", [_cls("CoreUtils")])])
        rebuilt = g._package_data_from_json(asdict(pkg))
        self.assertEqual(rebuilt.name, "pythontk")
        names = [c.name for mod in rebuilt.modules for c in mod.classes]
        self.assertIn("CoreUtils", names)

    def test_reconstructed_package_feeds_shadow_report(self):
        # A package reconstructed from JSON must collide like a walked one.
        walked = _pkg("mayatk", [_mod("m.py", [_cls("CoreUtils")])])
        from_json = g._package_data_from_json(asdict(_pkg("pythontk", [_mod("m.py", [_cls("CoreUtils")])])))
        md = g.emit_shadow_report([walked, from_json])
        self.assertIn("CoreUtils", md)
        self.assertIn("pythontk", md)


class TestPropertyAccessorSkip(unittest.TestCase):
    """A property setter/deleter must not be emitted as a phantom member (it
    re-defines the property already emitted by its getter; recording it
    double-lists the property and mislabels the setter as a plain method)."""

    @staticmethod
    def _func(src: str):
        return ast.parse(src).body[0]

    def test_setter_is_accessor(self):
        self.assertTrue(g._is_property_accessor(self._func("@x.setter\ndef x(self, v): ...")))

    def test_deleter_is_accessor(self):
        self.assertTrue(g._is_property_accessor(self._func("@x.deleter\ndef x(self): ...")))

    def test_getter_is_not_accessor(self):
        self.assertFalse(g._is_property_accessor(self._func("@property\ndef x(self): ...")))

    def test_plain_method_is_not_accessor(self):
        self.assertFalse(g._is_property_accessor(self._func("def x(self): ...")))

    def test_walk_module_emits_property_once(self):
        src = (
            "class C:\n"
            "    @property\n"
            "    def val(self): return self._v\n"
            "    @val.setter\n"
            "    def val(self, v): self._v = v\n"
            "    def plain(self): pass\n"
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "m.py"
            f.write_text(src, encoding="utf-8")
            mod = g._walk_module(f, root)
            members = {(m.name, m.kind) for m in mod.classes[0].members}
            self.assertIn(("val", "property"), members)
            self.assertIn(("plain", "method"), members)
            # the setter must NOT appear as a separate (phantom) member
            self.assertNotIn(("val", "method"), members)
            self.assertEqual(sum(1 for n, _ in members if n == "val"), 1)


if __name__ == "__main__":
    unittest.main()
