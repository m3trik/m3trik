#!/usr/bin/python
# coding=utf-8
"""Tests for check_saved_names.py -- the names saved data reads, frozen by name.

The real workspace must hold against the frozen baseline; fixture trees prove a
move passes and a lost name fails: a .ui moving between packages keeps its stem
and widget names, a renamed widget or a dropped record key does not.
"""

import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_saved_names as gate  # noqa: E402

UI = """\
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>{stem}</class>
 <widget class="QMainWindow" name="{stem}">
  <widget class="QWidget" name="central">
   <widget class="QPushButton" name="b000"/>
   {extra}
  </widget>
 </widget>
</ui>
"""
RECORDS = textwrap.dedent(
    """\
    class SceneRecords:
        MATERIALS = RecordSpec("materials", Scope.DELIVERABLE, 1, owner="Export")
        SHOTS = RecordSpec(
            "shots",
            Scope.PRIVATE,
            2,
        )
    """
)


def _tree(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class TestSavedNames(unittest.TestCase):
    BEFORE = {
        "mayatk/mayatk/edit_utils/duplicate_radial.ui": UI.format(
            stem="duplicate_radial", extra='<widget class="QSpinBox" name="s000"/>'
        ),
        "blendertk/blendertk/edit_utils/duplicate_radial.ui": UI.format(
            stem="duplicate_radial", extra='<widget class="QSpinBox" name="s001"/>'
        ),
        gate.RECORDS_FILE: RECORDS,
    }
    #: After a move the libraries are still checked out, without the panel.
    LIBRARIES = {"mayatk/mayatk/__init__.py": "", "blendertk/blendertk/__init__.py": ""}

    def scan(self, files: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            return gate.scan(
                _tree(Path(tmp), files),
                packages=("mayatk", "blendertk", "tentacle", "pythontk"),
            )

    def test_names_are_keyed_by_stem_across_packages(self):
        found = self.scan(self.BEFORE)
        self.assertEqual(
            found["ui"]["duplicate_radial"],
            ["b000", "central", "duplicate_radial", "s000", "s001"],
        )
        self.assertEqual(found["records"], ["materials", "shots"])

    def test_a_panel_moved_with_its_names_loses_nothing(self):
        merged = UI.format(
            stem="duplicate_radial",
            extra='<widget class="QSpinBox" name="s000"/><widget class="QSpinBox" name="s001"/>',
        )
        after = {
            **self.LIBRARIES,
            "tentacle/tentacle/ui/panels/duplicate_radial/duplicate_radial.ui": merged,
            gate.RECORDS_FILE: RECORDS,
        }
        self.assertEqual(gate.lost(self.scan(self.BEFORE), self.scan(after)), [])

    def test_a_renamed_widget_or_a_dropped_record_is_lost(self):
        after = {
            **self.LIBRARIES,
            "tentacle/tentacle/ui/panels/duplicate_radial/duplicate_radial.ui": UI.format(
                stem="duplicate_radial", extra='<widget class="QSpinBox" name="s000"/>'
            ),
            gate.RECORDS_FILE: RECORDS.replace('"shots"', '"shot_list"'),
        }
        self.assertEqual(
            gate.lost(self.scan(self.BEFORE), self.scan(after)),
            ["duplicate_radial.ui: s001", "SceneRecords: shots"],
        )

    def test_a_record_renamed_with_its_old_name_kept_loses_nothing(self):
        """Old scenes store a record under its ``renamed_from`` names: a rename
        that keeps the old name there passes, and dropping that name later is
        a loss like any other."""
        old_name = '        renamed_from=("shots",),\n'
        renamed = RECORDS.replace('"shots",', '"shot_list",').replace(
            "        2,\n", "        2,\n" + old_name
        )
        frozen = self.scan(self.BEFORE)
        after = self.scan({**self.BEFORE, gate.RECORDS_FILE: renamed})
        self.assertEqual(after["records"], ["materials", "shot_list", "shots"])
        self.assertEqual(gate.lost(frozen, after), [])
        dropped = {**self.BEFORE, gate.RECORDS_FILE: renamed.replace(old_name, "")}
        self.assertEqual(gate.lost(after, self.scan(dropped)), ["SceneRecords: shots"])

    def test_a_wrapped_spec_and_a_retired_key_are_frozen(self):
        """A deprecated record still wraps its spec, and a retired key is one
        an older scene may hold: both are names a reader still meets."""
        records = RECORDS + (
            "    OLD = Deprecation.class_attribute(RecordSpec(\"old_key\", Scope.PRIVATE, 1))\n"
            "    RETIRED = (\"gone_key\",)\n"
            "    RETIRED_BLOCKS: Tuple[str, ...] = (\"stale_block\",)\n"
        )
        found = self.scan({**self.BEFORE, gate.RECORDS_FILE: records})["records"]
        self.assertEqual(
            found, ["gone_key", "materials", "old_key", "shots", "stale_block"]
        )

    def test_a_run_judges_only_the_names_its_packages_carry(self):
        """Another package's uncommitted .ui edit never stops this release;
        the record keys are judged when pythontk is in the run."""
        after = {
            **self.BEFORE,
            "mayatk/mayatk/edit_utils/duplicate_radial.ui": UI.format(
                stem="duplicate_radial", extra=""
            ),
            gate.RECORDS_FILE: RECORDS.replace('"shots"', '"shot_list"'),
        }
        frozen, now = self.scan(self.BEFORE), self.scan(after)
        self.assertEqual(gate.lost(frozen, now, ["tentacle"]), [])
        self.assertEqual(gate.lost(frozen, now, ["mayatk"]), ["duplicate_radial.ui: s000"])
        self.assertEqual(gate.lost(frozen, now, ["pythontk"]), ["SceneRecords: shots"])

    def test_a_panel_gone_loses_every_name(self):
        after = {**self.LIBRARIES, gate.RECORDS_FILE: RECORDS}
        self.assertIn(
            "duplicate_radial.ui: (the whole panel)",
            gate.lost(self.scan(self.BEFORE), self.scan(after)),
        )

    def test_a_partial_checkout_judges_only_what_it_can_see(self):
        frozen = self.scan(self.BEFORE)
        self.assertEqual(
            gate.lost(
                frozen,
                self.scan(
                    {
                        "tentacle/tentacle/__init__.py": "",
                        "pythontk/pythontk/__init__.py": "",
                    }
                ),
            ),
            [],
        )


class TestRenamedPanels(unittest.TestCase):
    """A panel renamed or merged into a tool passes when tentacle's
    ``RENAMED_FROM`` lists it under the tool and the tool's ``.ui`` carries each
    of its names (under its new name where the table renames it). A name two
    former panels both keep passes only when ``RENAMED_HOSTS`` puts them in
    separate hosts: otherwise their values would meet in one store."""

    BEFORE = {
        "tentacle/tentacle/ui/tools/old_map.ui": UI.format(
            stem="old_map", extra='<widget class="QLineEdit" name="txt000"/>'
        ),
        "tentacle/tentacle/ui/tools/old_editor.ui": UI.format(
            stem="old_editor", extra='<widget class="QLineEdit" name="txt000"/>'
        ),
    }
    TABLE = textwrap.dedent(
        """\
        RENAMED_FROM = {
            "merged": {"old_map": {}, "old_editor": {"txt000": "txt002"}},
        }
        RENAMED_HOSTS = {"old_map": ("maya",), "old_editor": ("blender",)}
        """
    )

    def scan(self, files: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            return gate.scan(_tree(Path(tmp), files), packages=("tentacle",))

    def _after(self, extra: str, table: str = None) -> dict:
        return {
            "tentacle/tentacle/ui/tools/merged.ui": UI.format(stem="merged", extra=extra),
            gate.RENAMES_FILE: self.TABLE if table is None else table,
        }

    def test_the_table_is_read_as_a_literal(self):
        found = self.scan(self._after(""))
        self.assertEqual(
            found["renamed"],
            {"old_map": ["merged", {}], "old_editor": ["merged", {"txt000": "txt002"}]},
        )

    def test_a_merge_that_keeps_every_name_loses_nothing(self):
        """Each former root (named after its panel) stores nothing and is not
        looked for; ``txt000`` stays the map's, the editor's moved to txt002."""
        extra = '<widget class="QLineEdit" name="txt000"/><widget class="QLineEdit" name="txt002"/>'
        self.assertEqual(gate.lost(self.scan(self.BEFORE), self.scan(self._after(extra))), [])

    def test_a_name_the_tool_does_not_carry_is_lost(self):
        extra = '<widget class="QLineEdit" name="txt000"/>'
        self.assertEqual(
            gate.lost(self.scan(self.BEFORE), self.scan(self._after(extra))),
            ["old_editor.ui: txt000 (renamed into merged.ui as txt002)"],
        )

    def test_a_panel_the_table_does_not_list_is_lost_whole(self):
        extra = '<widget class="QLineEdit" name="txt000"/><widget class="QLineEdit" name="txt002"/>'
        table = 'RENAMED_FROM = {"merged": {"old_map": {}}}'
        self.assertEqual(
            gate.lost(self.scan(self.BEFORE), self.scan(self._after(extra, table))),
            ["old_editor.ui: (the whole panel)"],
        )

    def test_a_name_two_formers_keep_needs_separate_hosts(self):
        """Both formers keep ``b000`` and ``central``: with no hosts row (or one
        host for both) their values would land on one key, which fails."""
        extra = '<widget class="QLineEdit" name="txt000"/><widget class="QLineEdit" name="txt002"/>'
        frozen = self.scan(self.BEFORE)
        lost = [
            "merged.ui: b000 (kept by old_editor and old_map, which RENAMED_HOSTS "
            "puts in no separate hosts: declare their hosts or rename one)",
            "merged.ui: central (kept by old_editor and old_map, which RENAMED_HOSTS "
            "puts in no separate hosts: declare their hosts or rename one)",
        ]
        no_row = self.TABLE.split("RENAMED_HOSTS")[0]
        self.assertEqual(gate.lost(frozen, self.scan(self._after(extra, no_row))), lost)
        one_host = self.TABLE.replace('("blender",)', '("maya",)')
        self.assertEqual(gate.lost(frozen, self.scan(self._after(extra, one_host))), lost)

    def test_the_table_never_enters_the_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), self._after(""))
            gate.main(["--update", "--workspace", str(root)])
            frozen = gate.load_baseline(gate.baseline_file(root))
        self.assertNotIn("renamed", frozen)
        self.assertNotIn("renamed_hosts", frozen)


class TestWorkspaceBaseline(unittest.TestCase):
    """A baseline describes the workspace it was frozen from, so ``--workspace``
    judges that workspace against its own copy: a fixture with a bare tentacle
    is not this workspace's tentacle with every panel gone."""

    def setUp(self):
        real = self.real = gate.BASELINE.read_bytes()
        # A regression would rewrite the real baseline before failing: put it back.
        self.addCleanup(
            lambda: gate.BASELINE.read_bytes() == real
            or gate.BASELINE.write_bytes(real)
        )

    def test_a_workspace_with_no_saved_names_needs_no_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), {"tentacle/tentacle/__init__.py": ""})
            self.assertEqual(gate.main(["--workspace", str(root), "tentacle"]), 0)

    def test_saved_names_without_a_baseline_fail(self):
        """A deleted baseline must not pass as nothing frozen."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), TestSavedNames.BEFORE)
            self.assertEqual(gate.main(["--workspace", str(root), "mayatk"]), 1)

    def test_an_update_keeps_what_a_partial_checkout_cannot_see(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), TestSavedNames.BEFORE)
            gate.main(["--update", "--workspace", str(root)])
            shutil.rmtree(root / "blendertk")
            shutil.rmtree(root / "pythontk")
            gate.main(["--update", "--workspace", str(root)])
            frozen = gate.load_baseline(gate.baseline_file(root))
        self.assertIn("s001", frozen["ui"]["duplicate_radial"])
        self.assertEqual(frozen["homes"]["duplicate_radial"], ["blendertk", "mayatk"])
        self.assertEqual(frozen["records"], ["materials", "shots"])
        self.assertEqual(gate.BASELINE.read_bytes(), self.real)

    def test_a_workspace_is_judged_against_its_own_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), TestSavedNames.BEFORE)
            self.assertEqual(gate.main(["--update", "--workspace", str(root)]), 0)
            self.assertTrue(gate.baseline_file(root).is_file())
            self.assertEqual(gate.main(["--workspace", str(root), "mayatk"]), 0)
            (root / "mayatk/mayatk/edit_utils/duplicate_radial.ui").unlink()
            self.assertEqual(gate.main(["--workspace", str(root), "mayatk"]), 1)
        self.assertEqual(gate.BASELINE.read_bytes(), self.real)


class TestRealWorkspace(unittest.TestCase):
    def test_no_frozen_name_is_lost(self):
        self.assertEqual(gate.lost(gate.load_baseline(), gate.scan()), [])


if __name__ == "__main__":
    unittest.main()
