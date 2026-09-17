#!/usr/bin/python
# coding=utf-8
"""Tests that every gate script in ``scripts/`` is actually WIRED to run.

``scripts/CLAUDE.md`` already states the rule -- "New gate => wire it into the
workflow or weekly task that owns it" -- and nothing enforced it.  Measured
2026-09-16, nine of seventeen scripts were invoked by no workflow, no
``push.ps1`` step and no scheduled task: they ran only when a human remembered.
A gate nobody runs is worse than no gate, because its existence reads as
coverage.

**Being named in a test is NOT wiring.**  ``sync_rpc_core`` and
``sync_shadow_shaders`` are each pinned by a pythontk test that pythontk's CI
really does collect -- and that ``skipTest``s on every run, because the sibling
DCC repos are never checked out there.  Only a workflow step or a ``push.ps1``
call counts here.

Adding a script to :data:`WIRING_EXEMPT` is the deliberate escape hatch, and it
costs a written reason.  The ledger is checked in BOTH directions: an entry for
a script that has since been wired, or that no longer exists, fails too, so the
exemption list cannot quietly become the place scripts go to avoid the rule.
"""

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, "scripts")
WORKSPACE = os.path.dirname(REPO)

# Repos whose .github/workflows may invoke an m3trik script.  m3trik itself is
# included: tests.yml runs the drift and workspace gates from its own repo.
SIBLINGS = (
    "pythontk",
    "uitk",
    "mayatk",
    "blendertk",
    "tentacle",
    "unitytk",
    "extapps",
    "m3trik",
)

# Scripts that legitimately run on demand rather than on a gate.  Each entry is
# a REASON, not a name: "it isn't wired yet" is not one.
WIRING_EXEMPT = {
    "build_stingray_ao_presets": (
        "Needs a Maya install even to --check: main() calls build(args.maya) "
        "BEFORE the --check branch, and stock_presets_dir() sys.exits with 'no "
        "Maya install with ShaderFX presets found' when none is present. It "
        "cannot run on a Linux runner, so it stays a local/release-time check. "
        "Wire it only behind a self-hosted runner that has Maya, or after the "
        "--check path stops reading the stock presets."
    ),
    "generate_dcc_coverage": (
        "Generator, not a gate: writes a coverage table for humans to read. It "
        "has no --check mode, so there is nothing for CI to fail on. Wire it "
        "only if the table ever becomes a reviewed artifact."
    ),
}


def _script_stems():
    """Return the stem of every ``scripts/*.py``, excluding dunder files."""
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(SCRIPTS)
        if f.endswith(".py") and not f.startswith("__")
    )


def _invocation_corpus():
    """Return the text of everything that can INVOKE a script.

    Workflow YAML across every sibling repo, ``push.ps1``, and the PowerShell
    wrappers in ``scripts/``.  The wrappers count because they are a real
    invocation chain, not prose: ``verify_runtime_surface.py`` is reached only
    through ``Check-RuntimeSurface.ps1``, which ``Invoke-ContextBudgetCheck.ps1``
    calls in turn.  Deliberately excludes test files: see the module docstring.

    Returns:
        A ``{source label: text}`` mapping.
    """
    corpus = {}
    for name in sorted(os.listdir(SCRIPTS)):
        if name.endswith(".ps1"):
            with open(
                os.path.join(SCRIPTS, name), encoding="utf-8", errors="replace"
            ) as fh:
                corpus["scripts/%s" % name] = fh.read()
    for repo in SIBLINGS:
        wf_dir = os.path.join(WORKSPACE, repo, ".github", "workflows")
        if not os.path.isdir(wf_dir):
            continue
        for name in sorted(os.listdir(wf_dir)):
            if not name.endswith((".yml", ".yaml")):
                continue
            path = os.path.join(wf_dir, name)
            with open(path, encoding="utf-8", errors="replace") as fh:
                corpus["%s/%s" % (repo, name)] = fh.read()
    push = os.path.join(REPO, "push.ps1")
    if os.path.isfile(push):
        with open(push, encoding="utf-8", errors="replace") as fh:
            corpus["push.ps1"] = fh.read()
    return corpus


def _callers(stem, corpus):
    """Return the sources that invoke ``<stem>.py``.

    Two narrowings, because a gate that prose can satisfy reads as coverage:

    * the FILENAME, not the bare stem -- ``check_docs`` is not a substring of
      ``check_doc_line_refs`` today, but matching ``.py`` keeps that true if a
      future script name does nest;
    * COMMENT lines do not count. Several workflow steps explain why a
      neighbouring script is or is not wired, and those sentences name the
      file.
    """
    needle = re.compile(re.escape(stem + ".py"))
    hits = []
    for src, text in corpus.items():
        for line in text.splitlines():
            if not needle.search(line):
                continue
            # A COMMENT naming a script is prose, not a caller. Several steps
            # here explain why a neighbouring script is or is not wired, and
            # counting those would let a gate be satisfied by its own
            # documentation.
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith("<#"):
                continue
            hits.append(src)
            break
    return sorted(hits)


class GateWiringTest(unittest.TestCase):
    """Every script is wired, or carries a written reason why not."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = _invocation_corpus()
        # The corpus spans sibling repos. In a standalone m3trik checkout only
        # m3trik's own workflows are present, which would make every other
        # repo's wiring read as absent and fail the suite for the wrong reason.
        found = {src.split("/")[0] for src in cls.corpus} & set(SIBLINGS)
        if len(found) < 2:
            raise unittest.SkipTest(
                "sibling repos not checked out (standalone m3trik checkout); "
                "wiring spans %s" % ", ".join(SIBLINGS)
            )

    def test_every_script_is_wired_or_exempt(self):
        unwired = []
        for stem in _script_stems():
            if stem in WIRING_EXEMPT:
                continue
            if not _callers(stem, self.corpus):
                unwired.append(stem)
        self.assertEqual(
            [],
            unwired,
            "scripts/%s.py is invoked by no workflow and no push.ps1 step. "
            "Wire it into the workflow that owns it, or add it to "
            "WIRING_EXEMPT with a reason." % ".py, scripts/".join(unwired),
        )

    def test_exemptions_are_live(self):
        """An exemption for a wired or deleted script is stale and must go."""
        stems = set(_script_stems())
        for stem, reason in sorted(WIRING_EXEMPT.items()):
            with self.subTest(script=stem):
                self.assertIn(
                    stem,
                    stems,
                    "WIRING_EXEMPT names scripts/%s.py, which does not exist. "
                    "Remove the entry." % stem,
                )
                callers = _callers(stem, self.corpus)
                self.assertEqual(
                    [],
                    callers,
                    "scripts/%s.py is exempt from the wiring rule but IS "
                    "invoked by %s. Remove the exemption." % (stem, ", ".join(callers)),
                )

    def test_exemptions_carry_a_reason(self):
        for stem, reason in sorted(WIRING_EXEMPT.items()):
            with self.subTest(script=stem):
                self.assertTrue(
                    reason and len(reason.split()) >= 8,
                    "WIRING_EXEMPT[%r] needs a real reason, not a placeholder." % stem,
                )


if __name__ == "__main__":
    unittest.main()
