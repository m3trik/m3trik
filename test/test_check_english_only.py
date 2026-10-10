#!/usr/bin/python
# coding=utf-8
"""Tests for scripts/check_english_only.py -- the English-only text gate.

Every letter this file feeds the gate as a FAILING case is built with ``chr()``,
and every escape from a joined backslash: the gate scans m3trik too, so a
literal non-Latin letter (or a literal escape spelling one) here would fail it.
Letters that pass (accented Latin, fullwidth Latin, a lone Greek letter) are
written as they are.
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import check_english_only as gate  # noqa: E402


def _text(*code_points):
    return "".join(chr(cp) for cp in code_points)


BS = chr(92)
CYRILLIC = _text(0x0416, 0x0443, 0x043A)  # a three-letter word
CJK = _text(0x65E5, 0x672C)
KATAKANA = _text(0x30C6, 0x30B9, 0x30C8)
HANGUL = _text(0xD55C, 0xAE00)
ARABIC = _text(0x0639, 0x0631, 0x0628)
HEBREW = _text(0x05E9, 0x05DC, 0x05D5, 0x05DD)
THAI = _text(0x0E44, 0x0E17, 0x0E22)
DEVANAGARI = _text(0x0939, 0x093F, 0x0928)
GREEK_WORD = _text(0x03B1, 0x03B2, 0x03B3, 0x03B4)
#: The same word with its accent DECOMPOSED: the mark must not split the run.
GREEK_DECOMPOSED = _text(0x03BB, 0x03BF, 0x0301, 0x03B3, 0x03BF, 0x03C2)


class TestLetters(unittest.TestCase):
    """What the gate fails on, one string at a time."""

    def test_english_text_and_notation_pass(self):
        for text in (
            "plain ASCII",
            "café, naïve, résumé, Ångström, Zoë, über-shader, tête-à-tête",
            "Ünïcode and a decomposed e" + chr(0x0301),
            "ＷＩＤＥ fullwidth Latin",
            "10⁻ᵈᵉᶜⁱᵐᵃˡˢ and M3ᵀ (modifier letters)",
            "ℹ info, ℓ, Ω, ℵ₀, ʼ, ː (letterlike and modifier notation)",
            "★ ✓ → — symbols and 🚀 emoji",
            "1/π, ref_std/σ, sin²(πs), (0,0,0,α), Δt, covφ, [φ-ρ, φ+ρ], 2ρ, θ1",
            "~63 µs per node-frame, 0.4-22 µm",
        ):
            with self.subTest(text=text):
                self.assertEqual(gate.offending_runs(text), [])

    def test_a_letter_of_any_other_script_fails(self):
        for word in (CYRILLIC, CJK, KATAKANA, HANGUL, ARABIC, HEBREW, THAI, DEVANAGARI):
            with self.subTest(word=ascii(word)):
                self.assertEqual(
                    gate.offending_runs(f"name = 'Zo{chr(0xEB)} {word}!'"), [word]
                )

    def test_a_greek_word_fails_and_a_lone_greek_letter_is_notation(self):
        self.assertEqual(gate.offending_runs(f"s = '{GREEK_WORD}'"), [GREEK_WORD])
        self.assertEqual(gate.offending_runs(GREEK_DECOMPOSED), [GREEK_DECOMPOSED])
        self.assertEqual(gate.offending_runs("windowΔ=3, Δ, π"), [])

    def test_each_run_is_reported_once(self):
        line = f"{CYRILLIC} and {CJK}{KATAKANA}"
        self.assertEqual(gate.offending_runs(line), [CYRILLIC, CJK + KATAKANA])

    def test_an_escape_spells_the_same_text_at_run_time(self):
        cyrillic = "".join(BS + "u%04x" % ord(ch) for ch in CYRILLIC)
        self.assertEqual(gate.offending_runs(f'title = "{cyrillic}"'), [CYRILLIC])
        long_form = BS + "U%08x" % ord(CJK[0])
        self.assertEqual(gate.offending_runs(long_form), [CJK[0]])
        named = BS + "N{CYRILLIC CAPITAL LETTER ZHE}"
        self.assertEqual(gate.offending_runs(named), [CYRILLIC[0]])

    def test_an_escape_of_an_english_character_passes(self):
        for text in (
            "Zo" + BS + "u00eb " + BS + "u2605",  # Zoë ★
            BS + "U0001f680",  # an emoji
            BS + "udce9",  # a lone surrogate: what mayapy made of an é
            BS + "N{LATIN SMALL LETTER E WITH ACUTE}",
            BS + "N{NOT A REAL NAME}",
            BS + "u12",  # too short to be an escape
        ):
            with self.subTest(text=text):
                self.assertEqual(gate.offending_runs(text), [])


class _RepoCase(unittest.TestCase):
    """One throwaway git repo inside a throwaway workspace."""

    REPO = "somerepo"

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="english_gate_test_")
        self.addCleanup(temp.cleanup)
        self.root = temp.name
        self.repo = os.path.join(self.root, self.REPO)
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def write(self, rel, content, track=True):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(
                content if isinstance(content, bytes) else content.encode("utf-8")
            )
        if track:
            subprocess.run(["git", "-C", self.repo, "add", "--", rel], check=True)

    def scan(self):
        return gate.scan_repo(self.repo, self.REPO)

    def run_main(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main(["--workspace", self.root, *argv])
        return code, out.getvalue()


class TestScan(_RepoCase):
    def test_a_tracked_file_is_reported_at_its_line(self):
        self.write("test/test_a.py", f"ok = 'café'\nname = '{CYRILLIC}'\n")
        self.assertEqual(
            self.scan(), [gate.Finding(self.REPO, "test/test_a.py", 2, CYRILLIC)]
        )

    def test_a_crlf_file_reports_the_same_lines(self):
        self.write("a.txt", f"one\r\ntwo\r\n{CJK}\r\n")
        self.assertEqual([f.line for f in self.scan()], [3])

    def test_an_untracked_file_would_be_published_so_it_is_scanned(self):
        self.write("draft.md", f"{CJK}\n", track=False)
        self.assertEqual([f.path for f in self.scan()], ["draft.md"])

    def test_an_ignored_file_is_not_scanned(self):
        self.write(".gitignore", "local.txt\n")
        self.write("local.txt", f"{CJK}\n", track=False)
        self.assertEqual(self.scan(), [])

    def test_a_binary_file_is_skipped(self):
        self.write("asset.bin", b"\x00\x01" + CJK.encode("utf-8"))
        self.assertEqual(self.scan(), [])

    def test_a_path_is_text_too(self):
        self.write(f"docs/{CJK}.md", "clean\n")
        self.assertEqual(
            self.scan(), [gate.Finding(self.REPO, f"docs/{CJK}.md", None, CJK)]
        )

    def test_a_generated_registry_is_exempt(self):
        for name in ("API_REGISTRY.md", "API_REGISTRY.json", "docs/PARITY_SURFACE.md"):
            self.write(name, f"{CYRILLIC}\n")
        self.assertEqual(self.scan(), [])

    def test_a_vendored_tree_is_exempt(self):
        self.write("lib/vendor.min.js", f"var a = '{CJK}';\n")
        self.write("src/ours.js", f"var a = '{CJK}';\n")
        with mock.patch.dict(gate.VENDORED, {self.REPO: ("lib/",)}):
            self.assertEqual([f.path for f in self.scan()], ["src/ours.js"])

    def test_text_in_another_encoding_is_not_misread_as_a_letter(self):
        self.write("legacy.txt", "caf\xe9 — cp1252 bytes\n".encode("cp1252"))
        self.assertEqual(self.scan(), [])

    def test_a_utf16_file_is_text_not_a_binary(self):
        """What Windows PowerShell 5.1's ``>`` writes: a byte order mark, then
        a NUL in every ASCII character -- read as text, never skipped."""
        for codec in ("utf-16-le", "utf-16-be"):
            with self.subTest(codec=codec):
                bom = "﻿".encode(codec)
                self.write("ps.log", bom + f"x\n{CJK}\n".encode(codec))
                self.assertEqual(
                    self.scan(), [gate.Finding(self.REPO, "ps.log", 2, CJK)]
                )


class TestMain(_RepoCase):
    def test_a_finding_fails_and_prints_where(self):
        self.write("notes.md", f"x\n{GREEK_WORD}\n")
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn(f"{self.REPO}/notes.md:2", out)

    def test_a_clean_workspace_passes(self):
        self.write("notes.md", "café, π, ★\n")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn(self.REPO, out)

    def test_every_child_repo_is_scanned_and_a_named_one_alone(self):
        other = os.path.join(self.root, "other")
        subprocess.run(["git", "init", "-q", other], check=True)
        with open(os.path.join(other, "x.txt"), "w", encoding="utf-8") as handle:
            handle.write(f"{CJK}\n")
        os.makedirs(os.path.join(self.root, "not_a_repo"))
        self.assertEqual(self.run_main()[0], 1)
        self.assertEqual(self.run_main(self.REPO)[0], 0)
        self.assertEqual(self.run_main("other")[0], 1)

    def test_a_missing_repo_is_an_error_not_a_pass(self):
        self.assertEqual(self.run_main("absent")[0], 2)

    def test_a_workspace_with_no_repo_is_an_error_not_a_pass(self):
        """Nothing checked is not clean: a wrong --workspace must not read green."""
        empty = os.path.join(self.root, "empty")
        os.makedirs(os.path.join(empty, "not_a_repo"))
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main(["--workspace", empty])
        self.assertEqual(code, 2, out.getvalue())

    def test_help_prints_on_a_console_that_cannot_hold_its_examples(self):
        """The docstring's ★ example must not crash ``-h`` on a cp1252 console."""
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "check_english_only.py"), "-h"],
            capture_output=True,
            env=env,
        )
        self.assertEqual(
            result.returncode, 0, result.stderr.decode("cp1252", "replace")
        )

    def test_a_git_failure_is_an_error_not_a_pass(self):
        error = subprocess.CalledProcessError(128, "git", stderr=b"fatal: broken")
        with mock.patch.object(gate, "_publishable_files", side_effect=error):
            code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("broken", out)


if __name__ == "__main__":
    unittest.main()
