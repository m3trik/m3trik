#!/usr/bin/python
# coding=utf-8
"""Tests for check_layers.py -- declared layer order and declared dependencies.

The real workspace must hold against the frozen baseline (the same check as
``--check``); fixture packages prove each rule fires: an undeclared ecosystem
import, an upward import, a peer import, and a subpackage in no declared part.
"""

import contextlib
import io
import json
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
        violations, problems, strict = cl.scan()
        self.assertEqual(problems, [])
        self.assertEqual({k: v for k, v in strict.items() if v}, {})
        baseline = cl.load_baseline()
        new = {
            pkg: [v for v in found if v not in set(baseline.get(pkg, []))]
            for pkg, found in violations.items()
        }
        self.assertEqual({k: v for k, v in new.items() if v}, {})


class TestWorkspaceBaseline(unittest.TestCase):
    """A baseline describes the workspace it was frozen from, so ``--workspace``
    reads and rewrites that workspace's own copy, never this one's."""

    def setUp(self):
        real = self.real = cl.BASELINE.read_bytes()
        # A regression would rewrite the real baseline before failing: put it back.
        self.addCleanup(
            lambda: cl.BASELINE.read_bytes() == real or cl.BASELINE.write_bytes(real)
        )

    def test_a_workspace_is_judged_against_its_own_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pythontk" / "pythontk").mkdir(parents=True)
            (root / "pythontk" / "pythontk" / "__init__.py").write_text("")
            (root / "pythontk" / "pyproject.toml").write_text(
                '[project]\nname = "pythontk"\n'
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cl.main(["--workspace", str(root), "pythontk"]), 0)
                self.assertEqual(cl.main(["--update", "--workspace", str(root)]), 0)
            self.assertNotIn("[PAID]", out.getvalue())  # this workspace's entries
            self.assertTrue(cl.baseline_file(root).is_file())
            self.assertEqual(cl.BASELINE.read_bytes(), self.real)

    def test_an_update_keeps_the_packages_it_could_not_scan(self):
        """A partial checkout, or a pyproject that does not parse, is not a
        package paid off: its frozen entries stay."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pythontk").mkdir()
            (root / "pythontk" / "pyproject.toml").write_text("[project\n")
            frozen = cl.baseline_file(root)
            frozen.parent.mkdir(parents=True)
            cl.write_baseline({"mayatk": ["a.py -> b"], "pythontk": ["c.py -> d"]}, frozen)
            with contextlib.redirect_stdout(io.StringIO()):
                cl.main(["--update", "--workspace", str(root)])
            self.assertEqual(
                cl.load_baseline(frozen),
                {"mayatk": ["a.py -> b"], "pythontk": ["c.py -> d"]},
            )
        self.assertEqual(cl.BASELINE.read_bytes(), self.real)


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

    def test_an_unreadable_pyproject_is_a_declaration_problem_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = _package(root, self.FILES)
            (repo / "pyproject.toml").write_text(
                "[project]\n<<<<<<< HEAD\nname = 'a'\n=======\n", encoding="utf-8"
            )
            renamed = root / "pythontk"
            repo.rename(renamed)
            (renamed / "pkg").rename(renamed / "pythontk")
            violations, problems, strict = cl.scan(root, ["pythontk"])
        self.assertEqual(violations, {})
        self.assertEqual(len(problems), 1)
        self.assertIn("pythontk: pyproject.toml does not parse", problems[0])

    def test_the_longest_prefix_wins(self):
        self.assertEqual(
            cl.part_of("core/engines/x", ["core", "core/engines"]), "core/engines"
        )
        self.assertIsNone(cl.part_of("corex/y", ["core"]))


class TestProductAndRoles(unittest.TestCase):
    """The rules strict from their first file: no other package imports the
    product, and each part of a tool imports only what its role allows."""

    FILES = {
        "pkg/__init__.py": "",
        "pkg/tools/__init__.py": "",
        "pkg/tools/spin/__init__.py": "",
        "pkg/tools/spin/model/__init__.py": "",
        "pkg/tools/spin/model/plan.py": (
            "import pythontk\n"
            "def f():\n    import maya.cmds\n"  # a host, deferred: still counted
        ),
        "pkg/tools/spin/maya.py": "import maya.cmds\nimport mayatk\nimport bpy\n",
        "pkg/tools/spin/blender.py": "import bpy\nimport blendertk\n",
        "pkg/ui/__init__.py": "",
        "pkg/ui/panels/__init__.py": "",
        "pkg/ui/panels/spin/__init__.py": "",
        "pkg/ui/panels/spin/slots.py": (
            "import uitk\nfrom pkg.tools.spin import model\n"
            "from pkg.tools.spin import maya\n"  # a host half in disguise
        ),
        "pkg/slots/__init__.py": "",
        "pkg/slots/normals.py": "import mayatk\n",  # composed: holds
        "pkg/slots/maya/__init__.py": "",
        "pkg/slots/maya/legacy.py": "import maya.cmds\n",  # exempt until merged
        "lib/__init__.py": "",
        "lib/core.py": "def f():\n    from pkg.tools.spin import model\n",
    }
    ROLES = {
        "groups": {
            "maya": ["maya", "pymel", "mayatk"],
            "blender": ["bpy", "bmesh", "mathutils", "blendertk"],
            "halves": ["pkg.tools.*.maya", "pkg.tools.*.blender"],
            "qt": ["qtpy", "uitk"],
        },
        "forbid": {
            "tools/*/model": ["maya", "blender", "halves", "qt"],
            "tools/*/maya": ["blender", "qt"],
            "tools/*/blender": ["maya", "qt"],
            "ui/panels": ["maya", "blender", "halves"],
            "slots": ["maya", "blender", "halves"],
            "slots/maya": [],
        },
    }

    def test_no_other_package_imports_the_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _package(Path(tmp), self.FILES)
            self.assertEqual(
                cl.product_violations(repo, "lib", {"pkg"}),
                {"core.py -> pkg.tools.spin.model"},
            )
            self.assertEqual(cl.product_violations(repo, "pkg", {"pkg"}), set())

    def test_each_part_imports_only_what_its_role_allows(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _package(Path(tmp), self.FILES)
            found = cl.role_violations(repo, "pkg", self.ROLES)
        self.assertEqual(
            found,
            {
                "tools/spin/model/plan.py -> maya.cmds (tools/*/model)",
                "tools/spin/maya.py -> bpy (tools/*/maya)",
                "ui/panels/spin/slots.py -> pkg.tools.spin.maya (ui/panels)",
                "slots/normals.py -> mayatk (slots)",
            },
        )

    def test_tentacles_slots_reach_a_host_only_through_the_toolkit(self):
        """tentacle's own table: a Slots module -- a composed category or a
        shared tool -- imports no host package and no launcher; it reaches the
        host through ``self.tk``. (tentacle has no per-host halves since the
        2026-10-29 restructure, so the halves rule this replaced has nothing
        left to hold.)"""
        pyproject = cl.WORKSPACE / "tentacle" / "pyproject.toml"
        if not pyproject.is_file():
            self.skipTest("tentacle is not checked out")
        declared = cl.roles(cl.tomllib.loads(pyproject.read_text(encoding="utf-8")))
        files = {
            "tentacle/__init__.py": "",
            "tentacle/slots/__init__.py": "",
            "tentacle/slots/normals.py": "import mayatk\n",
            "tentacle/slots/tools/__init__.py": "",
            "tentacle/slots/tools/spin.py": "import bpy\nimport tentacle.tcl_blender\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            found = cl.role_violations(_package(Path(tmp), files), "tentacle", declared)
        self.assertEqual(
            found,
            {
                "slots/normals.py -> mayatk (slots)",
                "slots/tools/spin.py -> bpy (slots)",
                "slots/tools/spin.py -> tentacle.tcl_blender (slots)",
            },
        )

    def test_a_role_naming_no_group_is_a_declaration_problem(self):
        roles = {"groups": {"qt": ["qtpy"]}, "forbid": {"core": ["qt", "hots"]}}
        self.assertEqual(
            cl.role_problems(roles), ["role 'core' forbids unknown group 'hots'"]
        )

    def test_the_most_specific_role_wins(self):
        forbid = self.ROLES["forbid"]
        self.assertEqual(cl.role_of("slots/maya/legacy", forbid), "slots/maya")
        self.assertEqual(cl.role_of("slots/normals", forbid), "slots")
        self.assertEqual(cl.role_of("tools/spin/model/plan", forbid), "tools/*/model")
        self.assertIsNone(cl.role_of("tools/spin", forbid))
        self.assertTrue(cl.dotted_match("maya.cmds", "maya"))
        self.assertFalse(cl.dotted_match("mayatk", "maya"))
        self.assertTrue(cl.dotted_match("pkg.tools.spin.maya", "pkg.tools.*.maya"))


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


def _scratch(name: str):
    """A scratch folder in the house temp home (``ptk.TempArtifacts``), gone on a
    clean exit and kept for debugging on a failure."""
    pythontk = str(SCRIPTS.parents[1] / "pythontk")
    if pythontk not in sys.path:
        sys.path.insert(0, pythontk)
    from pythontk import TempArtifacts

    return TempArtifacts.scoped(f"check_layers_{name}")


def _unity(root: Path, asmdefs: dict, files: dict = ()) -> None:
    """Write each ``{folder/Name.asmdef: fields}`` (a ``guid`` field becomes its
    ``.meta``) and each ``{path: text}`` under *root*."""
    for rel, fields in asmdefs.items():
        fields = dict(fields)
        guid = fields.pop("guid", None)
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"name": path.stem, "references": [], "autoReferenced": True}
        data.update(fields)
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        if guid:
            path.with_name(path.name + ".meta").write_text(
                f"fileFormatVersion: 2\nguid: {guid}\n", encoding="utf-8"
            )
    for rel, text in dict(files).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def _door(*refs: str, **fields) -> dict:
    door = {
        "references": list(refs),
        "autoReferenced": False,
        "defineConstraints": ["PKG_XRI"],
        "versionDefines": [
            {
                "name": "com.unity.xr.interaction.toolkit",
                "expression": "3.0.0",
                "define": "PKG_XRI",
            }
        ],
    }
    door.update(fields)
    return door


class TestTheRootPartIsTheRootAlone(unittest.TestCase):
    """2026-11-04 review: "." matched every folder, so an assembly in a folder
    no part declares took the monolith's rank and a reference up the order
    passed. "." is the root folder alone."""

    def test_an_undeclared_folder_is_in_no_part(self):
        from pythontk import TempArtifacts

        with TempArtifacts.scoped("check_layers_root_part") as tmp:
            root = Path(tmp.dir_path())
            for rel, name in (("M.asmdef", "M"), ("Core/C.asmdef", "C"), ("Kits/Foo/K.asmdef", "K")):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(json.dumps({"name": name, "references": []}), encoding="utf-8")
            layout = cl.CSharpLayout(root, {"root": ".", "order": [".", "Core"]})
        self.assertEqual(layout.part_of(""), ".")
        self.assertEqual(layout.part_of("Core"), "Core")
        self.assertIsNone(layout.part_of("Kits/Foo"))
        self.assertTrue(any("Kits/Foo/K.asmdef is in no declared C# part" in p for p in layout.problems), layout.problems)


class TestCSharpAssemblies(unittest.TestCase):
    """Rule 5: each asmdef's references point down the declared C# order, never
    across peers, and outside the package only from a door or a test assembly."""

    DECLARED = {
        "root": "Pkg",
        "order": [
            "Features/*/Tests",
            "Features/*/*",
            "Features/*/Editor",
            "Features/*/Runtime",
            "Kernel",
            "Core",
        ],
        "kernel": "Kernel",
    }

    def layout(self, root: Path, asmdefs: dict, files: dict = (), declared=None):
        _unity(root, asmdefs, files)
        return cl.CSharpLayout(root, dict(declared or self.DECLARED))

    def test_references_point_down_and_never_across_peers(self):
        asmdefs = {
            "Pkg/Core/P.Core.asmdef": {"references": ["P.Kernel"], "guid": "c0" * 16},
            "Pkg/Kernel/P.Kernel.asmdef": {"references": ["GUID:" + "C0" * 16]},
            "Pkg/Features/A/Runtime/P.A.Runtime.asmdef": {
                "references": ["P.Kernel", "P.A.Editor"]  # down; up its feature
            },
            "Pkg/Features/A/Editor/P.A.Editor.asmdef": {
                "references": ["P.A.Runtime", "P.B.Runtime"],
                "guid": "ae" * 16,
            },
            "Pkg/Features/B/Runtime/P.B.Runtime.asmdef": {
                "references": ["GUID:" + "ae" * 16]  # another feature's, by GUID
            },
        }
        with _scratch("refs") as tmp:
            layout = self.layout(Path(tmp.dir_path()), asmdefs)
            found = layout.violations()
            problems = layout.problems
        self.assertEqual(problems, [])
        self.assertEqual(
            found,
            {
                "P.Core.asmdef -> P.Kernel (up the order)",
                "P.A.Runtime.asmdef -> P.A.Editor (up the order)",
                "P.A.Editor.asmdef -> P.B.Runtime (a peer)",
                "P.B.Runtime.asmdef -> P.A.Editor (a peer)",
            },
        )

    def test_the_most_specific_pattern_wins(self):
        """``Features/*/Editor`` beats ``Features/*/*`` (the doors), and a door
        may reference its own feature's editor assembly, never another door."""
        asmdefs = {
            "Pkg/Features/A/Editor/P.A.Editor.asmdef": {},
            "Pkg/Features/A/XRI/P.A.XRI.asmdef": _door("P.A.Editor", "P.A.Timeline"),
            "Pkg/Features/A/Timeline/P.A.Timeline.asmdef": _door(),
        }
        with _scratch("specific") as tmp:
            layout = self.layout(Path(tmp.dir_path()), asmdefs)
            self.assertEqual(layout.part_of("Features/A/Editor"), "Features/*/Editor")
            self.assertEqual(layout.part_of("Features/A/XRI/Sub"), "Features/*/*")
            found = layout.violations()
        self.assertEqual(found, {"P.A.XRI.asmdef -> P.A.Timeline (a peer)"})

    def test_an_outside_reference_is_a_doors_alone(self):
        asmdefs = {
            "Pkg/Core/P.Core.asmdef": {},
            "Pkg/Features/A/Runtime/P.A.Runtime.asmdef": {
                "references": ["P.Core", "Unity.InputSystem"]
            },
            "Pkg/Features/A/XRI/P.A.XRI.asmdef": _door(
                "P.A.Runtime", "Unity.XR.Interaction.Toolkit", "GUID:" + "ab" * 16
            ),
            # An almost-door: auto-referenced, so every assembly sees it.
            "Pkg/Features/B/XRI/P.B.XRI.asmdef": _door(
                "Unity.XR.CoreUtils", autoReferenced=True
            ),
            # Its define is not one of its constraints: it compiles without XRI.
            "Pkg/Features/C/XRI/P.C.XRI.asmdef": _door(
                "Unity.XR.Interaction.Toolkit", defineConstraints=[]
            ),
        }
        with _scratch("outside") as tmp:
            found = self.layout(Path(tmp.dir_path()), asmdefs).violations()
        self.assertEqual(
            found,
            {
                "P.A.Runtime.asmdef -> Unity.InputSystem (outside the package)",
                "P.B.XRI.asmdef -> Unity.XR.CoreUtils (outside the package)",
                "P.C.XRI.asmdef -> Unity.XR.Interaction.Toolkit (outside the package)",
            },
        )

    def test_a_test_assembly_may_reference_the_test_framework(self):
        tests = {
            "references": [
                "P.A.Runtime",
                "UnityEngine.TestRunner",
                "GUID:0acc523941302664db1f4e527237feb3",
                "Unity.InputSystem",
            ],
            "overrideReferences": True,
            "precompiledReferences": ["nunit.framework.dll"],
            "defineConstraints": ["UNITY_INCLUDE_TESTS"],
        }
        asmdefs = {
            "Pkg/Features/A/Runtime/P.A.Runtime.asmdef": {
                "references": ["UnityEngine.TestRunner"],
                "precompiledReferences": ["nunit.framework.dll", "Vendor.dll"],
            },
            "Pkg/Features/A/Tests/P.A.Tests.asmdef": tests,
        }
        with _scratch("tests") as tmp:
            layout = self.layout(Path(tmp.dir_path()), asmdefs)
            found = layout.violations()
            shapes = {a.name: a.is_test for a in layout.asmdefs}
        self.assertEqual(shapes, {"P.A.Runtime": False, "P.A.Tests": True})
        framework = "(the test framework outside a test assembly)"
        self.assertEqual(
            found,
            {
                f"P.A.Runtime.asmdef -> UnityEngine.TestRunner {framework}",
                f"P.A.Runtime.asmdef -> nunit.framework.dll {framework}",
                "P.A.Runtime.asmdef -> Vendor.dll (outside the package)",
                "P.A.Tests.asmdef -> Unity.InputSystem (outside the package)",
            },
        )

    def test_the_repos_own_assembly_is_never_referenced_a_door_included(self):
        """The sandbox sits outside the package and nothing uses it; build
        copies and the folders Unity skips are never read."""
        asmdefs = {
            "DevProject/Assets/Sandbox/Sandbox.asmdef": {"guid": "5a" * 16},
            "build/lib/Pkg/Core/P.Core.asmdef": {"references": ["Nowhere"]},
            "Pkg/Core/P.Core.asmdef": {},
            "Pkg/Samples~/Demo/P.Demo.asmdef": {"references": ["Unity.Timeline"]},
            "Pkg/Features/A/XRI/P.A.XRI.asmdef": _door("GUID:" + "5a" * 16),
            "Pkg/Features/A/Runtime/P.A.Runtime.asmdef": {"references": ["Sandbox"]},
        }
        with _scratch("sandbox") as tmp:
            layout = self.layout(Path(tmp.dir_path()), asmdefs)
            found = layout.violations()
            names = sorted(a.name for a in layout.asmdefs)
        self.assertEqual(names, ["P.A.Runtime", "P.A.XRI", "P.Core"])
        self.assertEqual(
            found,
            {
                "P.A.XRI.asmdef -> Sandbox (the repo's own assembly)",
                "P.A.Runtime.asmdef -> Sandbox (the repo's own assembly)",
            },
        )

    def test_the_root_folder_is_a_part(self):
        """Today's layout: a monolith at the root, its almost-door above it."""
        declared = {
            "root": "templates",
            "order": ["Rig/XR", ".", "Kernel/Editor", "Kernel/Core"],
            "kernel": "Kernel/Editor",
        }
        asmdefs = {
            "templates/P.asmdef": {"references": ["P.Core", "Unity.InputSystem"]},
            "templates/Rig/XR/P.XR.asmdef": _door("P", autoReferenced=True),
            "templates/Kernel/Editor/P.Kernel.asmdef": {
                "references": ["P.Core"],
                "includePlatforms": ["Editor"],
            },
            "templates/Kernel/Core/P.Core.asmdef": {"references": ["P"]},
        }
        with _scratch("root") as tmp:
            layout = self.layout(Path(tmp.dir_path()), asmdefs, declared=declared)
            found = layout.violations()
            problems = layout.problems
            kernel = {a.name: layout.at_or_below_kernel(a) for a in layout.asmdefs}
        self.assertEqual(problems, [])
        self.assertEqual(
            found,
            {
                "P.asmdef -> Unity.InputSystem (outside the package)",
                "P.Core.asmdef -> P (up the order)",
            },
        )
        self.assertEqual(
            kernel, {"P": False, "P.Core": True, "P.Kernel": True, "P.XR": False}
        )

    def test_a_bad_declaration_or_asmdef_is_a_problem(self):
        declared = {
            "root": "Pkg",
            "order": ["Kernel", "Kernel", "Gone"],
            "kernel": "Core",
        }
        asmdefs = {
            "Pkg/Kernel/P.Kernel.asmdef": {},
            "Pkg/Kernel/Sub/P.Kernel.asmdef": {},
            "Pkg/Loose/P.Loose.asmdef": {},
        }
        with _scratch("problems") as tmp:
            root = Path(tmp.dir_path())
            _unity(root, {}, {"Pkg/Kernel/Bad/P.Bad.asmdef": "{ not json"})
            problems = self.layout(root, asmdefs, declared=declared).problems
            missing = cl.CSharpLayout(root, {"root": "Nowhere", "order": ["."]}).problems
        text = "\n".join(problems)
        for expected in (
            "P.Bad.asmdef does not parse",
            "C# parts declared twice: ['Kernel']",
            "declared C# part 'Gone' does not exist",
            "csharp kernel 'Core' is not a declared part",
            "two assemblies are named 'P.Kernel'",
            "Loose/P.Loose.asmdef is in no declared C# part",
        ):
            self.assertIn(expected, text)
        self.assertEqual(len(missing), 1)
        self.assertIn("csharp root 'Nowhere' is not a folder", missing[0])

    def test_the_package_rule_reads_the_declaration_and_names_each_fix(self):
        """Through ``main``: the pyproject table is read, a C# violation fails
        with its fix printed, and ``--update`` freezes it."""
        with _scratch("main") as tmp:
            root = Path(tmp.dir_path())
            repo = root / "unitytk"
            (repo / "unitytk").mkdir(parents=True)
            (repo / "unitytk" / "__init__.py").write_text("")
            (repo / "pyproject.toml").write_text(
                '[project]\nname = "unitytk"\n\n'
                "[tool.m3trik.layers.csharp]\n"
                'root = "unitytk/templates"\n'
                'order = [".", "Core"]\n',
                encoding="utf-8",
            )
            _unity(
                repo,
                {
                    "unitytk/templates/P.asmdef": {
                        "references": ["P.Core", "Unity.InputSystem"]
                    },
                    "unitytk/templates/Core/P.Core.asmdef": {},
                },
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                failed = cl.main(["--workspace", str(root), "unitytk"])
                updated = cl.main(["--update", "--workspace", str(root)])
                passed = cl.main(["--workspace", str(root), "unitytk"])
            frozen = cl.load_baseline(cl.baseline_file(root))
        self.assertEqual((failed, updated, passed), (1, 0, 0))
        self.assertIn(
            "[FAIL] unitytk: P.asmdef -> Unity.InputSystem (outside the package)"
            " -- only a door references an outside package",
            out.getvalue(),
        )
        self.assertEqual(
            frozen,
            {"unitytk": ["P.asmdef -> Unity.InputSystem (outside the package)"]},
        )


if __name__ == "__main__":
    unittest.main()
