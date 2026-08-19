#!/usr/bin/python
# coding=utf-8
"""Tests for scripts/check_temp_artifacts.py -- the temp-leak drift gate.

A gate needs its own tests more than most code: when it silently stops detecting,
every run reports OK and that reads as proof of compliance. The alias cases below
are not hypothetical -- the first version of the script matched only a literal
``tempfile.mkdtemp`` attribute and passed a file that leaked through
``from tempfile import mkdtemp``.
"""

import os
import sys
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import check_temp_artifacts as gate  # noqa: E402


class _ScanCase(unittest.TestCase):
    """Scan a synthetic package tree instead of the real repo."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="tempgate_test_")
        self.pkg = os.path.join(self.root, "fakepkg")
        os.makedirs(self.pkg)
        self._orig_repo = gate.REPO
        self._orig_pkgs = dict(gate.PACKAGES)
        gate.REPO = self.root
        gate.PACKAGES.clear()
        gate.PACKAGES["fakepkg"] = "fakepkg"

    def tearDown(self):
        gate.REPO = self._orig_repo
        gate.PACKAGES.clear()
        gate.PACKAGES.update(self._orig_pkgs)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, body):
        path = os.path.join(self.pkg, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def scan(self):
        return gate.scan(["fakepkg"])


class DetectionTest(_ScanCase):
    def test_plain_attribute_call_is_flagged(self):
        self.write(
            "a.py", "import tempfile\n\ndef f():\n    return tempfile.mkdtemp()\n"
        )
        self.assertEqual(len(self.scan()), 1, self.scan())

    def test_from_import_is_flagged(self):
        """``from tempfile import mkdtemp`` -- the spelling that defeated v1."""
        self.write(
            "b.py", "from tempfile import mkdtemp\n\ndef f():\n    return mkdtemp()\n"
        )
        found = self.scan()
        self.assertEqual(len(found), 1, found)
        self.assertIn("mkdtemp", found[0])

    def test_aliased_module_is_flagged(self):
        self.write(
            "c.py", "import tempfile as tf\n\ndef f():\n    return tf.mkstemp()\n"
        )
        found = self.scan()
        self.assertEqual(len(found), 1, found)

    def test_aliased_function_is_flagged(self):
        self.write(
            "d.py",
            "from tempfile import mkdtemp as md\n\ndef f():\n    return md()\n",
        )
        self.assertEqual(len(self.scan()), 1, self.scan())

    def test_enclosing_function_is_reported(self):
        self.write(
            "e.py", "import tempfile\n\ndef outer():\n    return tempfile.mkdtemp()\n"
        )
        self.assertIn("outer()", self.scan()[0])


class SelfCleaningFormsTest(_ScanCase):
    """Forms that already guarantee reclamation must NOT be flagged -- a gate that
    cries wolf on correct code gets suppressed."""

    def test_temporary_directory_is_not_flagged(self):
        self.write(
            "a.py",
            "import tempfile\n\ndef f():\n"
            "    with tempfile.TemporaryDirectory() as d:\n        return d\n",
        )
        self.assertEqual(self.scan(), [])

    def test_named_temporary_file_default_is_not_flagged(self):
        self.write(
            "b.py",
            "import tempfile\n\ndef f():\n"
            "    with tempfile.NamedTemporaryFile() as fh:\n        return fh.name\n",
        )
        self.assertEqual(self.scan(), [])

    def test_named_temporary_file_delete_false_IS_flagged(self):
        """delete=False opts out of the auto-delete this gate exists to require."""
        self.write(
            "c.py",
            "import tempfile\n\ndef f():\n"
            "    return tempfile.NamedTemporaryFile(delete=False)\n",
        )
        found = self.scan()
        self.assertEqual(len(found), 1, found)
        self.assertIn("delete=False", found[0])

    def test_gettempdir_is_not_flagged(self):
        """Naming a durable location is not allocating an untracked artifact."""
        self.write(
            "d.py",
            "import os, tempfile\n\ndef f():\n"
            '    return os.path.join(tempfile.gettempdir(), "my_output_dir")\n',
        )
        self.assertEqual(self.scan(), [])


class ScopeTest(_ScanCase):
    def test_test_directories_are_skipped(self):
        self.write(
            "test/test_thing.py",
            "import tempfile\n\ndef f():\n    return tempfile.mkdtemp()\n",
        )
        self.assertEqual(self.scan(), [])

    def test_allowlist_suppresses_a_named_function(self):
        self.write(
            "g.py", "import tempfile\n\ndef ok():\n    return tempfile.mkdtemp()\n"
        )
        self.assertEqual(len(self.scan()), 1)
        gate.ALLOWLIST["fakepkg/g.py::ok"] = "test"
        try:
            self.assertEqual(self.scan(), [])
        finally:
            gate.ALLOWLIST.pop("fakepkg/g.py::ok", None)

    def test_unparsable_file_does_not_abort_the_scan(self):
        """Rendered templates carry __TOKEN__ placeholders and may not parse."""
        self.write("broken.py", "def f(:\n")
        self.write(
            "h.py", "import tempfile\n\ndef f():\n    return tempfile.mkdtemp()\n"
        )
        self.assertEqual(len(self.scan()), 1)


class StrayArtifactTest(_ScanCase):
    """The filesystem half: files nothing loads, ships, or excuses.

    Declaration is read from BOTH sites on purpose. An earlier draft read only
    ``[tool.setuptools.package-data]`` and flagged all 154 of uitk's icons, which
    are declared solely in its ``MANIFEST.in`` -- a gate that noisy gets ignored.
    """

    def declare(self, pyproject="", manifest=""):
        for name, body in (("pyproject.toml", pyproject), ("MANIFEST.in", manifest)):
            if body:
                with open(os.path.join(self.root, name), "w", encoding="utf-8") as fh:
                    fh.write(body)

    def strays(self):
        return gate.scan_strays(["fakepkg"])

    def test_undeclared_file_in_the_package_is_flagged(self):
        self.declare(manifest="recursive-include fakepkg *.ui")
        self.write("prof", "profile dump")
        self.assertEqual(len(self.strays()), 1, self.strays())

    def test_package_data_declaration_passes(self):
        self.declare(
            pyproject="""
[tool.setuptools.package-data]
"*" = ["*.json"]
"""
        )
        self.write("config.json", "{}")
        self.assertEqual(self.strays(), [])

    def test_manifest_only_declaration_passes(self):
        """uitk's icons ship via the manifest alone -- reading pyproject only lies."""
        self.declare(manifest="recursive-include fakepkg *.svg")
        self.write("icons/add.svg", "<svg/>")
        self.assertEqual(self.strays(), [])

    def test_manifest_subtree_does_not_whitelist_the_whole_package(self):
        self.declare(manifest="recursive-include fakepkg/icons *.svg")
        self.write("icons/ok.svg", "<svg/>")
        self.write("elsewhere/stray.svg", "<svg/>")
        found = self.strays()
        self.assertEqual(len(found), 1, found)
        self.assertIn("elsewhere/stray.svg", found[0])

    def test_python_files_are_never_strays(self):
        self.declare(manifest="recursive-include fakepkg *.ui")
        self.write("module.py", "x = 1")
        self.write("module.pyi", "x: int")
        self.write("py.typed", "")
        self.assertEqual(self.strays(), [])

    def test_package_declaring_nothing_is_skipped(self):
        """No contract to check against; inventing one produces noise."""
        self.write("prof", "profile dump")
        self.assertEqual(self.strays(), [])

    def test_skipped_directories_are_not_swept(self):
        self.declare(manifest="recursive-include fakepkg *.ui")
        self.write("__pycache__/module.cpython-311.pyc", "bytecode")
        self.write("test/fixture.bin", "fixture")
        self.assertEqual(self.strays(), [])

    def test_extensionless_file_at_the_repo_root_is_flagged(self):
        """`python -m cProfile -o p` run one directory up lands exactly here."""
        self.declare(manifest="recursive-include fakepkg *.ui")
        with open(os.path.join(self.root, "p"), "w", encoding="utf-8") as fh:
            fh.write("profile dump")
        found = self.strays()
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("p "), found[0])

    def test_root_sentinel_is_not_flagged(self):
        self.declare(manifest="recursive-include fakepkg *.ui")
        with open(os.path.join(self.root, "LICENSE"), "w", encoding="utf-8") as fh:
            fh.write("MIT")
        self.assertEqual(self.strays(), [])

    def test_stray_allowlist_suppresses(self):
        self.declare(manifest="recursive-include fakepkg *.ui")
        self.write("prof", "profile dump")
        self.assertEqual(len(self.strays()), 1)
        gate.STRAY_ALLOWLIST["fakepkg/prof"] = "test"
        try:
            self.assertEqual(self.strays(), [])
        finally:
            gate.STRAY_ALLOWLIST.pop("fakepkg/prof", None)


class RealRepoTest(unittest.TestCase):
    def test_the_repo_is_currently_clean(self):
        """The gate must pass on the tree that ships."""
        self.assertEqual(gate.scan(list(gate.PACKAGES)), [])

    def test_the_repo_has_no_stray_artifacts(self):
        self.assertEqual(gate.scan_strays(list(gate.PACKAGES)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
