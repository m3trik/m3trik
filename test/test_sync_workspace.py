#!/usr/bin/python
# coding=utf-8
"""Tests for sync_workspace.py -- the workspace manifest and what restates it.

``m3trik/workspace.json`` is the one declaration of the cascade, the ecosystem set
and every unit's domain line. These tests pin that the real manifest validates and
that every restatement agrees with it (the same checks as ``--check``), and the
semantics on fixture manifests: what the ecosystem set is, what the Dispatch table
looks like, and that a drifted CI loop or a missing charter is reported.
"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_workspace as sw  # noqa: E402

FIXTURE = {
    "cascade": ["core", "ui"],
    "units": [
        {"path": "core", "release": "cascade", "domain": "Core"},
        {"path": "extra", "release": "standalone", "domain": "Extra"},
        {"path": "ui", "release": "cascade", "domain": "UI"},
        {"path": "notes", "release": "none", "domain": "Notes"},
    ],
}


class TestRealManifest(unittest.TestCase):
    def test_the_manifest_validates(self):
        self.assertEqual(sw.validate(sw.load()), [])

    def test_the_ci_sibling_loops_list_the_registry_set(self):
        self.assertEqual(sw.workflow_drift(), [])

    def test_every_declared_unit_on_disk_carries_its_charter(self):
        self.assertEqual(sw.missing_charters(), [])

    def test_the_root_dispatch_table_is_current(self):
        if not sw.ROOT_AGENTS.is_file():
            self.skipTest("no workspace root checkout (a CI runner clones repos only)")
        self.assertIsNone(sw.dispatch_drift())

    def test_the_instruction_tree_is_in_line_with_its_packs(self):
        """Every unit's AGENTS.md + stub, its declared packs vendored and
        current against m3trik/agents/packs, its hook, its section citations."""
        self.assertEqual(sw.instruction_problems(), [])

    def test_every_committed_operation_catalog_is_current(self):
        self.assertEqual(sw.catalog_problems(), [])

    def test_the_unity_editors_operations_agree_with_their_twins_in_the_other_hosts(self):
        """``unity.scene.view`` takes the arguments ``maya.scene.view`` and
        ``blender.scene.view`` take: twins across hosts never differ. The Unity
        editor's operations are C#, catalogued in unitytk's
        ``editor_operations.json`` beside its ``operations.py``; unitytk names
        no other host, so the workspace holds the three together."""
        workspace = sw.WORKSPACE
        provider = sw._operation_provider([workspace / name for name in ("unitytk", "mayatk", "blendertk")])
        catalog = workspace / "unitytk" / "unitytk" / "editor_operations.json"
        if not catalog.is_file():
            self.skipTest("no unitytk checkout in this workspace")
        modules = [catalog.as_posix()]
        for twin in ("mayatk.operations", "blendertk.operations"):
            try:
                __import__(twin)
            except ImportError:
                continue
            modules.append(twin)
        self.assertEqual(provider.check(modules=modules), [])


class TestCatalogs(unittest.TestCase):
    def test_a_missing_or_stale_catalog_is_reported_and_writing_brings_it_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            package = workspace / "swdemo" / "swdemo"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text(
                'def add(a: int) -> int:\n    """Add one."""\n    return a + 1\n', encoding="utf-8"
            )
            (package / "operations.py").write_text(
                "from pythontk import Operation\nOPERATIONS = (Operation('demo.add', 'swdemo:add'),)\n",
                encoding="utf-8",
            )
            data = {"units": [{"path": "swdemo"}, {"path": "notes"}]}
            catalog = package / "operations.json"
            try:
                self.assertIn("missing", " ".join(sw.catalog_problems(workspace, data)))
                self.assertEqual(sw.write_catalogs(workspace, data), [str(catalog)])
                self.assertEqual(sw.catalog_problems(workspace, data), [])
                self.assertEqual(sw.write_catalogs(workspace, data), [])  # idempotent
                catalog.write_text(catalog.read_text(encoding="utf-8").replace("Add one.", "Old."), encoding="utf-8")
                self.assertIn("stale (demo.add)", " ".join(sw.catalog_problems(workspace, data)))
            finally:
                sys.path.remove(str(workspace / "swdemo"))
                for name in [m for m in sys.modules if m.split(".")[0] == "swdemo"]:
                    del sys.modules[name]


class TestSemantics(unittest.TestCase):
    def test_the_registry_set_is_the_cascade_then_the_standalones(self):
        self.assertEqual(sw.ecosystem_packages(FIXTURE), ("core", "ui", "extra"))

    def test_validate_names_every_problem(self):
        broken = {
            "cascade": ["core"],
            "units": [
                {"path": "core", "release": "cascade", "domain": "Core"},
                {"path": "core", "release": "sometimes", "domain": ""},
            ],
        }
        problems = " | ".join(sw.validate(broken))
        for fragment in ("duplicate unit paths", "release must be", "no domain line"):
            self.assertIn(fragment, problems)

    def test_a_twin_is_declared_on_one_side_and_read_both_ways(self):
        paired = dict(FIXTURE, units=[
            dict(u, twin="ui") if u["path"] == "core" else u for u in FIXTURE["units"]
        ])
        self.assertEqual(sw.validate(paired), [])
        self.assertEqual(sw.twins(paired), {"core": "ui", "ui": "core"})
        for twin in ("nowhere", "core"):
            broken = dict(FIXTURE, units=[
                dict(u, twin=twin) if u["path"] == "core" else u for u in FIXTURE["units"]
            ])
            with self.subTest(twin=twin):
                self.assertTrue(any("twin" in p for p in sw.validate(broken)))

    def test_the_cascade_must_name_exactly_the_cascade_units(self):
        drifted = dict(FIXTURE, cascade=["core"])
        self.assertTrue(any("cascade" in p for p in sw.validate(drifted)))

    def test_a_manifest_without_a_cascade_is_malformed(self):
        # push.ps1 reads the cascade raw: an empty or missing one would release
        # nothing in order and validate nothing strictly, so the gate refuses it.
        units = [dict(u, release="none") for u in FIXTURE["units"]]
        for manifest in ({"units": units}, {"cascade": [], "units": units}, {}):
            with self.subTest(manifest=manifest):
                self.assertIn("no cascade declared", sw.validate(manifest))

    def test_the_dispatch_table_links_each_charter_in_manifest_order(self):
        table = sw.render_dispatch(FIXTURE).splitlines()
        self.assertEqual(table[:2], ["| Unit | Domain |", "|:---|:---|"])
        self.assertEqual(table[2], "| [`core/`](core/AGENTS.md) | Core |")
        self.assertEqual(len(table), 2 + len(FIXTURE["units"]))

    def test_splice_replaces_only_the_table_under_the_heading(self):
        text = "# Title\n\n## Dispatch\n\n| a |\n| b |\n\n## Next\n| keep |\n"
        spliced = sw.splice_dispatch(text, "| new |")
        self.assertEqual(
            spliced, "# Title\n\n## Dispatch\n\n| new |\n\n## Next\n| keep |\n"
        )

    def test_splice_refuses_a_file_without_the_heading_or_its_table(self):
        with self.assertRaises(ValueError):
            sw.splice_dispatch("# Title\n| a |\n", "| new |")
        with self.assertRaises(ValueError):
            sw.splice_dispatch("## Dispatch\n\n## Next\n| a |\n", "| new |")

    def test_a_drifted_ci_loop_is_reported_and_an_unrelated_loop_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            wanted = " ".join(sw.ecosystem_packages())
            (Path(tmp) / "ok.yml").write_text(f"for repo in {wanted}; do\n")
            (Path(tmp) / "other.yml").write_text("for repo in alpha beta; do\n")
            (Path(tmp) / "bad.yml").write_text("for repo in pythontk uitk; do\n")
            drift = sw.workflow_drift(Path(tmp))
        self.assertEqual(len(drift), 1)
        self.assertTrue(drift[0].startswith("bad.yml:1:"))



CHAIN_FIXTURE = {
    "cascade": ["core", "ui", "app"],
    "units": [
        {"path": "core", "release": "cascade", "domain": "Core"},
        {"path": "ui", "release": "cascade", "domain": "UI"},
        {"path": "app", "release": "cascade", "role": "product", "domain": "App"},
        {"path": "kit", "release": "standalone", "role": "product", "domain": "Kit"},
    ],
}


class TestChainStatements(unittest.TestCase):
    """Prose restates the dependency chain; the pyprojects' dependencies are
    the data. Each stated edge holds in them, and each dependency in them is
    stated, directly or through another (``A → B → C`` states C needs A)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)
        self._deps({
            "core": [],
            "ui": ["core>=1.0"],
            # ``kit`` is a product: a dependency on it pins an install (the
            # app opens it by name), never an import, so it is no chain edge.
            "app": ["core>=1.0", "ui>=1.0", "numpy"],
            "kit": ["ui>=1.0"],
        })
        (self.root / "app" / "pyproject.toml").write_text(
            '[project]\nname = "apptk"\ndependencies = ["core>=1.0", "ui>=1.0", "numpy"]\n'
            '[project.optional-dependencies]\napps = ["kit>=0.1,<0.2"]\n',
            encoding="utf-8",
        )

    def _deps(self, table: dict) -> None:
        for name, deps in table.items():
            (self.root / name).mkdir(exist_ok=True)
            listed = ", ".join(f'"{d}"' for d in deps)
            (self.root / name / "pyproject.toml").write_text(
                f'[project]\nname = "{name}"\ndependencies = [{listed}]\n', encoding="utf-8"
            )

    def _drift(self, line: str, anchor: str = "The chain is ") -> list:
        doc = self.root / "DOC.md"
        doc.write_text(f"# Doc\n\n{line}\n\nMore.\n", encoding="utf-8")
        return sw.chain_drift(doc, anchor, self.root, CHAIN_FIXTURE)

    def test_a_chain_that_states_every_dependency_agrees(self):
        self.assertEqual(self._drift("The chain is `core → ui → app`; also `ui → kit`."), [])

    def test_a_set_stage_states_an_edge_to_each_member(self):
        self.assertEqual(
            self._drift("The chain is `core → ui → {app, kit}`, nothing else."), []
        )

    def test_a_stated_edge_the_pyprojects_lack_is_named(self):
        self.assertEqual(
            self._drift("The chain is `core → ui → app`; also `ui → kit`, `app → kit`."),
            ["DOC.md: states kit depends on app; its pyproject does not (directly or through another)"],
        )

    def test_a_dependency_the_chain_leaves_out_is_named(self):
        self.assertEqual(
            self._drift("The chain is `core → ui → app`."),
            [
                "DOC.md: kit depends on core (its pyproject); the chain does not state it",
                "DOC.md: kit depends on ui (its pyproject); the chain does not state it",
            ],
        )

    def test_a_heading_anchors_the_line_under_it(self):
        doc = self.root / "AGENTS.md"
        doc.write_text(
            "# Root\n\n## Ecosystem chain\n`core → ui → app`; also `ui → kit`.\n",
            encoding="utf-8",
        )
        self.assertEqual(sw.chain_drift(doc, "## Ecosystem chain", self.root, CHAIN_FIXTURE), [])

    def test_an_unknown_name_or_a_missing_statement_is_named(self):
        self.assertEqual(
            self._drift("The chain is `core → ui → app`; also `ui → kit`, `ui → nowhere`."),
            ["DOC.md: the chain names nowhere, no ecosystem package"],
        )
        self.assertEqual(
            self._drift("No chain here."),
            ["DOC.md: no chain statement at 'The chain is '"],
        )

    def test_the_real_statements_match_the_real_pyprojects(self):
        absent = [p for p in sw.ecosystem_packages() if not (sw.WORKSPACE / p / "pyproject.toml").is_file()]
        if absent:
            self.skipTest(f"no checkout of {absent} here")
        checked = 0
        for path, anchor in sw.CHAIN_STATEMENTS:
            if not path.is_file():
                continue  # a CI runner clones repos, never the workspace root
            with self.subTest(path=path.name):
                self.assertEqual(sw.chain_drift(path, anchor), [])
                checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
