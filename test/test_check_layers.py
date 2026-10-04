#!/usr/bin/python
# coding=utf-8
"""Tests for check_layers.py -- declared layer order and declared dependencies.

The real workspace must hold against the frozen baseline (the same check as
``--check``); fixture packages prove each rule fires: an undeclared ecosystem
import, an upward import, a peer import, and a subpackage in no declared part.
"""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_layers as cl  # noqa: E402


def _package(root: Path, files: dict) -> Path:
    repo = root / "pkg"
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
    return repo


class TestRealWorkspace(unittest.TestCase):
    def test_no_new_violation_beyond_the_baseline(self):
        violations, problems = cl.scan()
        self.assertEqual(problems, [])
        baseline = cl.load_baseline()
        new = {
            pkg: [v for v in found if v not in set(baseline.get(pkg, []))]
            for pkg, found in violations.items()
        }
        self.assertEqual({k: v for k, v in new.items() if v}, {})


class TestRules(unittest.TestCase):
    FILES = {
        "pkg/__init__.py": "",
        "pkg/core/__init__.py": "",
        "pkg/core/base.py": "from pkg.top import tool\n",  # upward
        "pkg/top/__init__.py": "",
        "pkg/top/tool.py": "import pkg.core.base\nimport uitk\n",
        "pkg/core/typed.py": (  # upward, but type-only: not counted
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    import pkg.top.tool\n"
        ),
        "pkg/peer/__init__.py": "",
        "pkg/peer/x.py": "def f():\n    from pkg.side import y\n",  # peer, deferred
        "pkg/side/__init__.py": "",
        "pkg/side/y.py": "",
        "pkg/templates/t.py": "import mayatk\n",  # exec-template: exempt
    }
    ORDER = [["top"], ["peer", "side"], ["core"]]

    def test_upward_and_peer_imports_are_violations_type_only_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _package(Path(tmp), self.FILES)
            found = cl.layer_violations(repo, "pkg", self.ORDER)
        self.assertEqual(
            found, {"core/base.py -> pkg.top.tool", "peer/x.py -> pkg.side.y"}
        )

    def test_an_undeclared_ecosystem_import_is_a_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _package(Path(tmp), self.FILES)
            (repo / "pyproject.toml").write_text(
                '[project]\ndependencies = ["pythontk>=1"]\n'
                '[project.optional-dependencies]\nx = ["unitytk"]\n'
            )
            found = cl.chain_violations(repo, "pkg", ("pythontk", "uitk", "mayatk"))
        self.assertEqual(found, {"top/tool.py -> uitk"})

    def test_an_uncovered_subpackage_is_a_declaration_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _package(Path(tmp), self.FILES)
            problems = cl.order_problems(repo, "pkg", [["top"], ["core"], ["gone"]])
        joined = " | ".join(problems)
        self.assertIn("'gone' does not exist", joined)
        self.assertIn("'peer' is in no declared part", joined)

    def test_the_longest_prefix_wins(self):
        self.assertEqual(
            cl.part_of("core/engines/x", ["core", "core/engines"]), "core/engines"
        )
        self.assertIsNone(cl.part_of("corex/y", ["core"]))


class TestWebRuntime(unittest.TestCase):
    """The same declaration over a served ES-module runtime: its relative
    imports point down the order, and a ``<folder>/*`` part makes each feature
    a peer of the others."""

    FILES = {
        "pkg/__init__.py": "",
        "pkg/web/__init__.py": "",
        "pkg/web/kernel/math.js": "export const add = (a, b) => a + b;\n",
        "pkg/web/kernel/main.js": (
            "import * as THREE from 'three';\n"  # bare: names no part
            "import { add } from './math.js';\n"
            "import { spin } from '../features/spin.js';\n"  # upward
        ),
        "pkg/web/features/spin.js": (
            "/* an app can import { add } from '../kernel/nowhere.js' */\n"  # comment
            "import {\n  add,\n} from '../kernel/math.js';\n"  # down, multi-line
            "export const spin = 1;\n"
        ),
        "pkg/web/features/rig/rig.js": (
            "export { spin } from '../spin.js';\n"  # peer feature
            "import './model.js';\n"  # its own folder
        ),
        "pkg/web/features/rig/model.js": "",
    }
    ORDER = [["web/features/*"], ["web/kernel"], ["web"]]

    def test_upward_and_peer_imports_are_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _package(Path(tmp), self.FILES)
            found = cl.layer_violations(repo, "pkg", self.ORDER)
        self.assertEqual(
            found,
            {
                "web/kernel/main.js -> web/features/spin.js",
                "web/features/rig/rig.js -> web/features/spin.js",
            },
        )

    def test_a_wildcard_part_is_each_child_a_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _package(Path(tmp), self.FILES)
            order = cl.expand_order(repo / "pkg", self.ORDER)
            problems = cl.order_problems(repo, "pkg", self.ORDER)
        self.assertEqual(order[0], ["web/features/rig", "web/features/spin"])
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
