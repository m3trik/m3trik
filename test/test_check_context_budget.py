"""Tests for check_context_budget.py — the context-budget guard.

A guard that cannot fail is worse than no guard. These verify it actually
CATCHES the regressions it exists to prevent (an over-cap / inconsistent
MEMORY.md) and passes a clean memory dir, plus that the live root dispatch table
still covers every ECOSYSTEM_PACKAGES member.
"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(r"O:\Cloud\Code\_scripts\m3trik\scripts")
sys.path.insert(0, str(SCRIPTS))

import check_context_budget as guard  # noqa: E402


def _write(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text, encoding="utf-8")


class TestMemoryGuard(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _run(self) -> guard.Report:
        rep = guard.Report()
        guard.check_memory(self.dir, rep)
        return rep

    def test_clean_dir_passes(self):
        _write(self.dir, "reference_a.md", "a")
        _write(self.dir, "feedback_b.md", "b")
        _write(
            self.dir,
            "MEMORY.md",
            "# Memory Index\n\n- [A](reference_a.md) — hook a\n- [B](feedback_b.md) — hook b\n",
        )
        self.assertEqual(self._run().fails, [])

    def test_over_cap_fails(self):
        _write(self.dir, "reference_a.md", "a")
        pad = "x" * (guard.MEMORY_BYTE_CAP + 100)
        _write(
            self.dir,
            "MEMORY.md",
            f"# Memory Index\n\n- [A](reference_a.md) — hook\n<!-- {pad} -->\n",
        )
        self.assertTrue(
            any("cap" in f and "TRUNCATED" in f for f in self._run().fails),
            "an over-cap MEMORY.md must FAIL — that is the exact regression this guard exists for",
        )

    def test_over_long_entry_fails(self):
        _write(self.dir, "reference_a.md", "a")
        long_hook = "y" * (guard.MEMORY_ENTRY_CHAR_CAP + 50)
        _write(self.dir, "MEMORY.md", f"# Memory Index\n\n- [A](reference_a.md) — {long_hook}\n")
        self.assertTrue(any("chars >" in f for f in self._run().fails))

    def test_broken_link_fails(self):
        _write(self.dir, "reference_a.md", "a")
        _write(
            self.dir,
            "MEMORY.md",
            "# Memory Index\n\n- [A](reference_a.md) — ok\n- [X](does_not_exist.md) — broken\n",
        )
        self.assertTrue(any("missing files" in f for f in self._run().fails))

    def test_orphan_topic_fails(self):
        _write(self.dir, "reference_a.md", "a")
        _write(self.dir, "reference_orphan.md", "no index entry points here")
        _write(self.dir, "MEMORY.md", "# Memory Index\n\n- [A](reference_a.md) — ok\n")
        self.assertTrue(any("NO index entry" in f for f in self._run().fails))

    def test_missing_memory_dir_warns_not_fails(self):
        rep = self._run()  # empty dir, no MEMORY.md
        self.assertEqual(rep.fails, [])
        self.assertTrue(any("not found" in w for w in rep.warns))


class TestLinkChecker(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_resolving_and_broken_links(self):
        (self.dir / "good.md").write_text("ok", encoding="utf-8")
        text = (
            "[a](good.md) [b](missing.md) [c](https://x.com) [d](#anchor) "
            "[e](good.md#L3) [f](sub/none.md)"
        )
        broken = guard._broken_links(text, self.dir)
        self.assertIn("missing.md", broken)
        self.assertIn("sub/none.md", broken)
        self.assertNotIn("good.md", broken)        # resolves
        self.assertNotIn("good.md#L3", broken)     # anchor stripped, file exists
        self.assertNotIn("https://x.com", broken)  # external skipped
        self.assertNotIn("#anchor", broken)        # pure anchor skipped


class TestLiveDispatch(unittest.TestCase):
    def test_dispatch_covers_ecosystem_packages(self):
        """The live root dispatch table must reference every ECOSYSTEM_PACKAGES
        member — the regression that misrouted blendertk work."""
        rep = guard.Report()
        guard.check_dispatch(rep)
        self.assertEqual([f for f in rep.fails if "DISPATCH" in f], [])


if __name__ == "__main__":
    unittest.main()
