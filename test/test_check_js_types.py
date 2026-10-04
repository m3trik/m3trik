#!/usr/bin/python
# coding=utf-8
"""Tests for check_js_types.py -- ``tsc --checkJs`` over the served JavaScript.

The compiler is resolved in a declared order (``$TSC`` first); a project with a
type error fails, the workspace's own projects pass. The two that run the
compiler skip only when no compiler can be found at all -- which the gate
itself reports as exit 2, never as a pass.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_js_types as cj  # noqa: E402

FOUND = cj.compiler()


class TestCompiler(unittest.TestCase):
    def test_tsc_from_the_environment_wins(self):
        with mock.patch.dict(os.environ, {"TSC": "npx --yes -p typescript@5 tsc"}):
            name, argv = cj.compiler()
        self.assertEqual(name, "$TSC")
        self.assertEqual(argv, ["npx", "--yes", "-p", "typescript@5", "tsc"])

    def test_no_compiler_is_exit_2_never_a_pass(self):
        with mock.patch.object(cj, "compiler", return_value=None):
            self.assertEqual(cj.main([]), 2)


@unittest.skipIf(FOUND is None, "no TypeScript compiler on this machine")
class TestCheck(unittest.TestCase):
    def test_a_type_error_fails_its_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "jsconfig.json").write_text(
                '{"compilerOptions": {"allowJs": true, "checkJs": true, "noEmit": true,'
                ' "module": "ESNext", "target": "ES2022", "types": []},'
                ' "include": ["*.js"]}',
                encoding="utf-8",
            )
            (root / "a.js").write_text(
                "export const add = (a, b) => a + b;\n", encoding="utf-8"
            )
            (root / "b.js").write_text(
                "import { sum } from './a.js';\nexport const x = sum;\n",
                encoding="utf-8",
            )
            code, output = cj.check(root / "jsconfig.json", FOUND)
        self.assertNotEqual(code, 0)
        self.assertIn("sum", output)

    def test_the_workspace_projects_are_clean(self):
        for project in cj.PROJECTS:
            if not project.is_file():
                continue  # a partial checkout
            with self.subTest(project=project.name):
                code, output = cj.check(project, FOUND)
                self.assertEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main()
