#!/usr/bin/python
# coding=utf-8
"""Mirror the shared package-manager.bat into the DCC packages that ship it.

The interpreter-agnostic menu (``m3trik/package-manager.bat``) is the single
source of truth. The mayatk / blendertk thin wrappers detect their DCC, resolve
the interpreter, and hand off to it. After a bare ``pip install`` there is no
``m3trik/`` on disk to fall back to, so a copy must physically ship inside each
wheel, next to the wrapper. This script mirrors the SSoT into those
``env_utils/`` dirs; each package's wheel ``package-data`` (``*.bat``) then picks
the mirror up so the wrapper's sibling-path handoff resolves post-install.

The mirrors are committed (not generated at build time) so the wheel ships them
regardless of the build path — unlike the runtime-regenerated ``*_ui.py`` files,
nothing recreates a mirror on load. Drift is caught by ``--check`` (CI gate) and
by ``m3trik/test/test_sync_shared_bat.py``.

Usage:
    python sync_shared_bat.py            # write mirrors (idempotent)
    python sync_shared_bat.py --check    # verify mirrors match the SSoT; exit 1 on drift
"""
import argparse
import sys
from pathlib import Path

# This file: _scripts/m3trik/scripts/sync_shared_bat.py -> repo root is parents[2].
REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "m3trik" / "package-manager.bat"

# Each DCC package whose wrapper hands off to the shared menu ships a verbatim
# mirror next to its wrapper, so the copy resolves after a bare pip install.
MIRRORS = (
    REPO_ROOT / "mayatk" / "mayatk" / "env_utils" / "package-manager.bat",
    REPO_ROOT / "blendertk" / "blendertk" / "env_utils" / "package-manager.bat",
)


def _norm(data: bytes) -> bytes:
    """Normalize line endings so EOL churn is not reported as content drift."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def out_of_sync(source: Path = SOURCE, mirrors=MIRRORS):
    """Return the mirrors whose content differs from the source (missing counts as drift)."""
    src = _norm(source.read_bytes())
    return [m for m in mirrors if not m.is_file() or _norm(m.read_bytes()) != src]


def sync(source: Path = SOURCE, mirrors=MIRRORS):
    """Write the source verbatim over each out-of-sync mirror. Returns the mirrors written.

    Drives off out_of_sync() so the write decision and the --check gate share one
    comparison: a mirror that differs only in line endings is not rewritten (no churn),
    but any content difference is healed with a byte-exact copy of the source.

    A missing mirror file is self-healed, but a missing parent dir means the target
    repo/package isn't checked out — raise rather than fabricate its tree.
    """
    data = source.read_bytes()
    written = []
    for m in out_of_sync(source, mirrors):
        if not m.parent.is_dir():
            raise FileNotFoundError(
                f"mirror dir missing (repo not checked out?): {m.parent}"
            )
        m.write_bytes(data)
        written.append(m)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Mirror the shared package-manager.bat into the DCC packages that ship it."
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="verify mirrors are in sync with the SSoT; exit 1 on drift (CI gate)",
    )
    args = ap.parse_args(argv)

    if not SOURCE.is_file():
        print(f"[sync_shared_bat] source not found: {SOURCE}", file=sys.stderr)
        return 2

    if args.check:
        drift = out_of_sync()
        if drift:
            print(
                "[sync_shared_bat] OUT OF SYNC (run `python sync_shared_bat.py`):",
                file=sys.stderr,
            )
            for m in drift:
                print(f"  - {m}", file=sys.stderr)
            return 1
        print("[sync_shared_bat] all mirrors in sync")
        return 0

    try:
        written = sync()
    except FileNotFoundError as e:
        print(f"[sync_shared_bat] {e}", file=sys.stderr)
        return 2
    for m in written:
        print(f"[sync_shared_bat] wrote {m}")
    if not written:
        print("[sync_shared_bat] mirrors already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
