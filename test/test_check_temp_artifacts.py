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
        self.write("a.py", "import tempfile\n\ndef f():\n    return tempfile.mkdtemp()\n")
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
        self.write("g.py", "import tempfile\n\ndef ok():\n    return tempfile.mkdtemp()\n")
        self.assertEqual(len(self.scan()), 1)
        gate.ALLOWLIST["fakepkg/g.py::ok"] = "test"
        try:
            self.assertEqual(self.scan(), [])
        finally:
            gate.ALLOWLIST.pop("fakepkg/g.py::ok", None)

    def test_unparsable_file_does_not_abort_the_scan(self):
        """Rendered templates carry __TOKEN__ placeholders and may not parse."""
        self.write("broken.py", "def f(:\n")
        self.write("h.py", "import tempfile\n\ndef f():\n    return tempfile.mkdtemp()\n")
        self.assertEqual(len(self.scan()), 1)


class RealRepoTest(unittest.TestCase):
    def test_the_repo_is_currently_clean(self):
        """The gate must pass on the tree that ships."""
        self.assertEqual(gate.scan(list(gate.PACKAGES)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
