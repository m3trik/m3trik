#!/usr/bin/python
# coding=utf-8
"""Tests for pm_doctor.py — the shadow doctor the package manager runs post-install.

A non-elevated ``pip install`` into a DCC's interpreter lands in the shared USER
site, which precedes the interpreter's own site-packages on ``sys.path``. A stray
copy of a dist the host BUNDLES then overrides it — the failure that killed every
Qt import on m3trik-desktop (2026-08-24: user-site shiboken6 6.9.1 over Maya's
bundled 6.5.3 → ``DLL load failed while importing QtWidgets``). pip cannot warn
about that; these guard the scan that does.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

M3TRIK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(M3TRIK))

import pm_doctor  # noqa: E402


class _Dist:
    """Stand-in for an importlib.metadata Distribution."""

    def __init__(self, name, version, location):
        self.metadata = {"Name": name}
        self.version = version
        self._location = location

    def locate_file(self, _):
        return self._location


class PmDoctorTest(unittest.TestCase):
    USER = r"C:\Users\x\AppData\Roaming\Python\Python311\site-packages"
    MAYA = r"C:\Program Files\Autodesk\Maya2025\Python\Lib\site-packages"

    def _run(self, dists):
        with mock.patch.object(
            pm_doctor.site, "getusersitepackages", return_value=self.USER
        ):
            with mock.patch.object(
                pm_doctor.metadata, "distributions", return_value=dists
            ):
                return pm_doctor.find_shadows()

    def test_reports_version_mismatch_shadow(self):
        """The real incident: user-site shiboken6 overriding Maya's bundled copy."""
        found = self._run(
            [
                _Dist("shiboken6", "6.9.1", self.USER),
                _Dist("shiboken6", "6.5.3", self.MAYA),
            ]
        )
        self.assertEqual(found, [("shiboken6", "6.9.1", "6.5.3")])

    def test_same_version_is_not_a_shadow(self):
        """A duplicate at the SAME version overrides nothing that matters."""
        found = self._run(
            [
                _Dist("numpy", "1.24.4", self.USER),
                _Dist("numpy", "1.24.4", self.MAYA),
            ]
        )
        self.assertEqual(found, [])

    def test_user_site_only_dist_is_not_a_shadow(self):
        """Nothing bundled to override — a normal user install."""
        self.assertEqual(self._run([_Dist("requests", "2.32.0", self.USER)]), [])

    def test_bundled_only_dist_is_not_a_shadow(self):
        self.assertEqual(self._run([_Dist("maya", "2025", self.MAYA)]), [])

    def test_packaging_tooling_is_skipped(self):
        """pip/setuptools/wheel are EXPECTED newer in the user site (`pip install
        --upgrade pip` lands there without elevation). Flagging them would train
        the user to ignore the warning."""
        found = self._run(
            [
                _Dist("pip", "25.3", self.USER),
                _Dist("pip", "23.2.1", self.MAYA),
                _Dist("setuptools", "80.9.0", self.USER),
                _Dist("setuptools", "65.5.0", self.MAYA),
            ]
        )
        self.assertEqual(found, [])

    def test_unreadable_dist_is_skipped_not_fatal(self):
        """A dist whose metadata raises must not take the whole scan down."""

        class Broken:
            metadata = {}

            @property
            def version(self):
                raise RuntimeError("boom")

            def locate_file(self, _):
                return ""

        found = self._run(
            [
                Broken(),
                _Dist("shiboken6", "6.9.1", self.USER),
                _Dist("shiboken6", "6.5.3", self.MAYA),
            ]
        )
        self.assertEqual(found, [("shiboken6", "6.9.1", "6.5.3")])

    def test_main_is_advisory_and_never_blocks(self):
        """It advises; it must never fail an install."""
        with mock.patch.object(
            pm_doctor, "find_shadows", return_value=[("x", "2", "1")]
        ):
            self.assertEqual(pm_doctor.main(), 0)
        with mock.patch.object(pm_doctor, "find_shadows", return_value=[]):
            self.assertEqual(pm_doctor.main(), 0)


if __name__ == "__main__":
    unittest.main(exit=False)
