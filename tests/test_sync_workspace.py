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
from unittest import mock

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

    def test_the_dispatch_table_is_current_where_it_is_written_and_where_it_is_rendered(self):
        self.assertIsNone(sw.dispatch_drift())  # the source: in every checkout
        if sw.ROOT_AGENTS.is_file():  # its render: a workspace only
            self.assertIsNone(sw.dispatch_drift(sw.ROOT_AGENTS))

    def test_the_workspace_roots_instruction_files_are_what_their_sources_build(self):
        """Built in a temporary folder, so a checkout with no root checks them
        too; where a root exists, its ``AGENTS.md`` is that build."""
        self.assertEqual(sw.root_problems(), [])

    def test_the_m3trik_distribution_installs_the_cascade_and_the_products(self):
        absent = [p for p in sw.ecosystem_packages() if not (sw.WORKSPACE / p / "pyproject.toml").is_file()]
        if absent:
            self.skipTest(f"no checkout of {absent} here")
        self.assertEqual(sw.meta_drift(), [])

    def test_every_link_the_workspaces_rules_hold_resolves_where_they_are_written(self):
        """The source's links are valid in place (a reader on GitHub, the docs
        sweep); a target in another repo or at the unversioned root is checked
        only where that exists."""
        folder = sw.ROOT_SOURCE.parent
        text = sw.ROOT_SOURCE.read_text(encoding="utf-8")
        targets = [match[1].partition("#")[0] for match in sw.LINK_TARGET.findall(text)]
        self.assertGreater(len(targets), 10)
        workspace = sw.WORKSPACE.resolve()
        for target in targets:
            path = (folder / target).resolve()
            # In this repo, always; elsewhere, wherever the folder that would
            # hold it is checked out (a sibling repo, the root's ``.claude``).
            top = workspace / path.relative_to(workspace).parts[0]
            with self.subTest(target=target):
                self.assertTrue(path.exists() or not top.exists(), f"{target} names nothing")
        rendered = [match[1] for match in sw.LINK_TARGET.findall(sw.render_root())]
        self.assertEqual([target for target in rendered if target.startswith("..")], [])

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

    def test_the_dispatch_rows_link_from_the_folder_they_are_written_in(self):
        nested = dict(FIXTURE, units=FIXTURE["units"] + [
            {"path": "tools", "release": "none", "domain": "Tools"},
            {"path": "tools/scripts", "release": "none", "domain": "Scripts"},
        ])
        rows = sw.render_dispatch(nested, start="tools/agents").splitlines()[2:]
        self.assertEqual(rows[0], "| [`core/`](../../core/AGENTS.md) | Core |")
        self.assertEqual(rows[-2], "| [`tools/`](../AGENTS.md) | Tools |")
        self.assertEqual(rows[-1], "| [`tools/scripts/`](../scripts/AGENTS.md) | Scripts |")
        # Rendered to the root, each row is the root's own.
        self.assertEqual(
            sw.rebase_links(sw.render_dispatch(nested, start="tools/agents"), "tools/agents"),
            sw.render_dispatch(nested),
        )

    def test_links_are_rebased_from_the_folder_they_were_written_in_to_the_root(self):
        text = (
            "See [std](../docs/STD.md#rules), [packs](packs/), [`core/`](../../core/AGENTS.md)\n"
            "and [self](workspace.md). Kept: [web](https://example.com/a/../b), [top](#top),\n"
            "[mail](mailto:a@b.c), `[code](../kept.md)`.\n"
            "```\n[fenced](../kept.md)\n```\n"
        )
        self.assertEqual(
            sw.rebase_links(text, "tools/agents"),
            "See [std](tools/docs/STD.md#rules), [packs](tools/agents/packs/), [`core/`](core/AGENTS.md)\n"
            "and [self](tools/agents/workspace.md). Kept: [web](https://example.com/a/../b), [top](#top),\n"
            "[mail](mailto:a@b.c), `[code](../kept.md)`.\n"
            "```\n[fenced](../kept.md)\n```\n",
        )
        self.assertEqual(sw.rebase_links(text, ""), text)  # written at the root already

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

    def test_a_hidden_folder_is_no_unit_whatever_it_holds(self):
        """``.claude`` keeps the ledgers' history in a repo of its own: tooling
        state, never a member the manifest must declare."""
        with tempfile.TemporaryDirectory() as tmp:
            for name in (".claude", "stray"):
                (Path(tmp) / name / ".git").mkdir(parents=True)
            self.assertEqual(sw.unclassified(Path(tmp)), [])  # beside a lone clone: not ours
            (Path(tmp) / sw.load()["cascade"][0] / ".git").mkdir(parents=True)
            self.assertEqual(sw.unclassified(Path(tmp)), ["stray"])


class TestRootBuild(unittest.TestCase):
    """The workspace root is not a repo, so it holds only renders: its
    ``AGENTS.md`` is built from ``agents/workspace.md``, its stub and packs by
    ``AgentInstructions.sync``. The build is made in a temporary folder (the
    check) and copied over the root's own files (the write): no other folder
    of the workspace is walked or written, and no other project's file is
    ever replaced."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name) / "workspace"
        # The cascade's first package beside the clone is what makes a workspace.
        (self.root / sw.load()["cascade"][0] / ".git").mkdir(parents=True)

    def _layout_problems(self) -> list:
        result = sw._instructions().check(
            str(self.root), source=str(sw.PACKS), standard=str(sw.STANDARD), mode="import"
        )
        return result["problems"]

    def _tree(self) -> dict:
        """Every file under the root, by path, as bytes."""
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def test_a_root_is_built_from_nothing_and_writing_again_changes_nothing(self):
        written = {Path(p).relative_to(self.root).as_posix() for p in sw.write_root(self.root)}
        packs = {f".agents/packs/{name}.md" for name in sw.load()["packs"]}
        self.assertEqual(written, {"AGENTS.md", "CLAUDE.md"} | packs)
        self.assertEqual(set(self._tree()), written)  # those files, and no other
        self.assertEqual(self._layout_problems(), [])
        self.assertEqual(sw.root_problems(self.root), [])
        self.assertEqual(sw.write_root(self.root), [])
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(sw.render_dispatch(), text)  # the rows, linked from the root
        self.assertIn(f"]({sw.UNIT}/agents/workspace.md)", text)  # where to edit it

    def test_a_root_that_is_not_its_sources_render_is_reported_and_rewritten(self):
        sw.write_root(self.root)
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\n- A rule edited into the render.\n", encoding="utf-8")
        (problem,) = sw.root_problems(self.root)
        self.assertIn("edit that source", problem)
        self.assertEqual(sw.write_root(self.root), [str(agents)])
        self.assertEqual(sw.root_problems(self.root), [])

    def test_a_roots_own_newlines_and_its_stubs_other_imports_are_kept(self):
        sw.write_root(self.root)
        agents, stub = self.root / "AGENTS.md", self.root / "CLAUDE.md"
        agents.write_bytes(agents.read_bytes().replace(b"\n", b"\r\n") + b"Stale.\r\n")
        stub.write_text(stub.read_text(encoding="utf-8") + "@notes.md\n", encoding="utf-8")
        self.assertEqual(sw.write_root(self.root), [str(agents)])
        raw = agents.read_bytes()
        self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"))
        self.assertIn("@notes.md", stub.read_text(encoding="utf-8"))
        self.assertEqual(sw.root_problems(self.root), [])
        self.assertEqual(self._layout_problems(), [])

    def test_no_other_folder_of_the_workspace_is_read_or_written(self):
        """Bug: the root was brought in line by the engine's own sync, which
        walks every folder under it: an unrelated project's ``CLAUDE.md`` was
        moved into a new ``AGENTS.md`` and a stub written beside every
        ``AGENTS.md`` it met, in a folder that is no repository. Fixed:
        2026-11-11"""
        (self.root / "other" / "CLAUDE.md").parent.mkdir()
        (self.root / "other" / "CLAUDE.md").write_text("Use tabs.\n", encoding="utf-8")
        (self.root / "notes" / "sub").mkdir(parents=True)
        (self.root / "notes" / "sub" / "AGENTS.md").write_text("# Notes\n", encoding="utf-8")
        before = self._tree()
        written = {Path(p).relative_to(self.root).as_posix() for p in sw.write_root(self.root)}
        after = self._tree()
        self.assertEqual({name: after[name] for name in before}, before)
        self.assertEqual(set(after) - set(before), written)
        self.assertFalse(any(name.startswith(("other/", "notes/")) for name in written))

    def test_another_projects_agents_file_is_never_overwritten(self):
        """Bug: any ``AGENTS.md`` in the folder holding the clone made it "the
        workspace", and the write replaced it with the render. Fixed: 2026-11-11"""
        theirs = self.root / "AGENTS.md"
        theirs.write_text("# My own multi-repo rules\n\n- Mine.\n", encoding="utf-8")
        (problem,) = sw.root_problems(self.root)
        self.assertIn("not this workspace's", problem)
        with self.assertRaises(ValueError):
            sw.write_root(self.root)
        self.assertEqual(theirs.read_text(encoding="utf-8"), "# My own multi-repo rules\n\n- Mine.\n")
        self.assertEqual(sorted(self._tree()), ["AGENTS.md"])  # nothing else was made either

    def test_a_stub_holding_rules_stops_the_write_before_anything_is_written(self):
        (self.root / "CLAUDE.md").write_text("@AGENTS.md\n\nA rule kept in the stub.\n", encoding="utf-8")
        with self.assertRaises(ValueError) as raised:
            sw.write_root(self.root)
        self.assertIn(str(self.root / "CLAUDE.md"), str(raised.exception))
        self.assertEqual(sorted(self._tree()), ["CLAUDE.md"])

    def test_a_pack_the_root_no_longer_takes_is_removed(self):
        sw.write_root(self.root)
        stale = self.root / ".agents" / "packs" / "retired.md"
        stale.write_text("# Retired\n", encoding="utf-8")
        self.assertEqual(sw.write_root(self.root), [str(stale)])
        self.assertFalse(stale.exists())
        self.assertEqual(self._layout_problems(), [])

    def test_a_folder_that_only_holds_a_clone_is_no_workspace(self):
        """Not the folder's contents but this workspace's own make it one: the
        cascade's first package beside the clone, or a root already rendered
        from here. A generic sibling (``www``) or someone's ``AGENTS.md`` does not."""
        with tempfile.TemporaryDirectory() as other:
            lone = Path(other)
            self.assertFalse(sw.is_workspace(lone))
            (lone / "www" / ".git").mkdir(parents=True)
            (lone / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
            self.assertFalse(sw.is_workspace(lone))
            # Their ``www`` is not the declared unit: never checked, never synced.
            self.assertEqual([folder for folder, _packs, _mode in sw.instruction_roots(lone)], [])
            self.assertEqual(sw.missing_charters(lone), [])
            self.assertEqual(sw.root_problems(lone), [])  # theirs: not ours to judge
            with self.assertRaises(ValueError):
                sw.write_root(lone)
            self.assertEqual((lone / "AGENTS.md").read_text(encoding="utf-8"), "# Root\n")
            (lone / "AGENTS.md").write_text(sw.render_root(), encoding="utf-8")
            self.assertTrue(sw.is_workspace(lone))  # a root rendered from here
        self.assertTrue(sw.is_workspace(self.root))

    def test_links_name_this_repo_by_its_declared_path_whatever_a_clone_is_called(self):
        """Bug: the links were written from the clone's own folder name, so a
        worktree named anything but ``m3trik`` reported a drifted Dispatch
        table and rendered links to a folder that does not exist. Fixed:
        2026-11-11"""
        self.assertIn(sw.UNIT, [unit["path"] for unit in sw.load()["units"]])
        clone = Path(self._td.name) / "a-worktree"
        (clone / "agents").mkdir(parents=True)
        source = clone / "agents" / "workspace.md"
        source.write_bytes(sw.ROOT_SOURCE.read_bytes())
        rendered = sw.render_root()
        with mock.patch.object(sw, "M3TRIK", clone):
            self.assertEqual(sw._folder(source), f"{sw.UNIT}/agents")
            self.assertEqual(sw._folder(clone / "AGENTS.md"), sw.UNIT)
            self.assertIsNone(sw.dispatch_drift(source))
            self.assertEqual(sw.render_root(source), rendered)
        self.assertEqual(sw._folder(self.root / "AGENTS.md"), "")  # the root's render


META_FIXTURE = {
    "cascade": ["core", "ui", "host", "app"],
    "units": [
        {"path": "core", "release": "cascade", "domain": "Core"},
        {"path": "ui", "release": "cascade", "domain": "UI"},
        {"path": "host", "release": "cascade", "domain": "Host"},
        {"path": "app", "release": "cascade", "role": "product", "domain": "App"},
        {"path": "kit", "release": "standalone", "role": "product", "domain": "Kit"},
        {"path": "side", "release": "standalone", "domain": "Side"},
    ],
}


class TestMetaDistribution(unittest.TestCase):
    """``m3trik/pyproject.toml`` is one install of the cascade and the
    products: dependencies only, followed through the packages' own
    pyprojects (the product's extras carry the host library and the apps)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)
        self._package("core", "core", [])
        self._package("ui", "ui", ["core>=1.0", "qtpy"])
        self._package("host", "host", ["core>=1.0", "ui>=1.0"])
        self._package("kit", "kit", ["ui>=1.0"])
        self._package("side", "side", ["core>=1.0"])
        self._package(
            "app", "apptk", ["core>=1.0", "ui>=1.0"],
            '[project.optional-dependencies]\nhost = ["host>=1.0"]\napps = ["kit>=0.1,<0.2"]\n',
        )

    def _package(self, unit: str, name: str, deps: list, more: str = "") -> None:
        (self.root / unit).mkdir(exist_ok=True)
        listed = ", ".join(f'"{d}"' for d in deps)
        (self.root / unit / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\ndependencies = [{listed}]\n{more}', encoding="utf-8"
        )

    def _drift(self, deps: list, tool: str = "packages = []\npy-modules = []\n") -> list:
        self._package("meta", "meta", deps, f"[tool.setuptools]\n{tool}")
        return sw.meta_drift(self.root / "meta" / "pyproject.toml", self.root, META_FIXTURE)

    def test_the_products_extras_carry_the_whole_set(self):
        self.assertEqual(self._drift(["apptk[host,apps]"]), [])
        self.assertEqual(self._drift(["apptk[host, apps]>=1.0"]), [])
        self.assertEqual(self._drift(["AppTK[host,apps]", "core"]), [])  # names compare normalized

    def test_a_package_left_out_or_added_is_named(self):
        self.assertEqual(
            self._drift(["apptk[host]"]),
            ["pyproject.toml: does not install kit (the cascade and the products)"],
        )
        self.assertEqual(
            self._drift(["apptk[host,apps]", "side"]),
            ["pyproject.toml: installs side, neither a cascade package nor a product"],
        )

    def test_a_requirement_of_its_own_or_an_undeclared_extra_is_named(self):
        (foreign,) = self._drift(["apptk[host,apps]", "PySide6>=6.5"])
        self.assertIn("requires 'PySide6>=6.5', no ecosystem package", foreign)
        drift = self._drift(["apptk[host,apps,gone]"])
        self.assertEqual(drift, ["pyproject.toml: asks app for the extra 'gone', which it does not declare"])

    def test_an_extra_of_its_own_names_ecosystem_packages_only(self):
        """Its own extra (the MCP SDK, through the core's extra) is held like its
        dependencies: an ecosystem package, asked for an extra it declares."""
        self._package("core", "core", [], '[project.optional-dependencies]\nserver = ["server-sdk>=2"]\n')
        tool = "packages = []\npy-modules = []\n[project.optional-dependencies]\n"
        self.assertEqual(self._drift(["apptk[host,apps]"], tool + 'agent = ["core[server]"]\n'), [])
        (foreign,) = self._drift(["apptk[host,apps]"], tool + 'agent = ["core", "server-sdk>=2"]\n')
        self.assertIn("its extra 'agent' requires 'server-sdk>=2', no ecosystem package", foreign)
        self.assertEqual(
            self._drift(["apptk[host,apps]"], tool + 'agent = ["core[renamed]"]\n'),
            ["pyproject.toml: asks core for the extra 'renamed', which it does not declare"],
        )

    def test_it_holds_no_code(self):
        (problem,) = self._drift(["apptk[host,apps]"], tool="")
        self.assertIn("holds dependencies only", problem)



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
