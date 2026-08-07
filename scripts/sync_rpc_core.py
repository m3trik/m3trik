#!/usr/bin/python
# coding=utf-8
"""Stage pythontk's in-application RPC core into each installed plugin payload.

``pythontk/net_utils/rpc/plugin_core.py`` is the single source of truth for the
server that runs *inside* a host application: the op registry, the main-thread
marshaller, and the HTTP routes :class:`pythontk.RpcClient` speaks to. Everything
host-specific is data on ``RpcPlugin`` (label / host module / env prefix / port),
so one implementation serves every host.

Why a copy exists at all
------------------------
The mayatk / blendertk plugins are *installed* into the host's own plugin folder
(``PluginInstaller`` symlinks, or copies where Developer Mode is off), and Toolbag
/ Painter have no ``pythontk`` on ``sys.path``. Their payloads must therefore be
self-contained, so the core ships inside each one as ``_rpc_core.py``.

extapps' Painter plugin is NOT staged: it loads in place from the checkout and
bootstraps ``sys.path`` back to it, so it imports the core directly. One source,
two consumption modes.

The mirrors are committed rather than generated at install time, for the same
reason ``sync_shared_bat.py``'s are: the payload has to be complete on disk before
anything copies it, and a symlink install serves the repo tree verbatim. Drift is
caught by ``--check`` (CI gate) and by ``pythontk/test/test_sync_rpc_core.py``.

**Never hand-edit a staged ``_rpc_core.py``** — edit the source and re-run this.

Usage:
    python sync_rpc_core.py            # write mirrors (idempotent)
    python sync_rpc_core.py --check    # verify mirrors match the SSoT; exit 1 on drift
"""
import argparse
import sys
from pathlib import Path

# This file: _scripts/m3trik/scripts/sync_rpc_core.py -> repo root is parents[2].
REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "pythontk" / "pythontk" / "net_utils" / "rpc" / "plugin_core.py"

#: The file name the core takes inside a payload. Leading underscore because it is
#: a staged artifact, not part of the plugin's own surface.
STAGED_NAME = "_rpc_core.py"

#: ``(package, bridge subpath, plugin package name)`` for every payload that is
#: INSTALLED into a host's plugin folder and so must carry its own copy.
_PAYLOADS = (
    ("mayatk", ("mat_utils", "marmoset_bridge"), "marmoset_rpc"),
    ("mayatk", ("mat_utils", "substance_bridge"), "substance_rpc"),
    ("blendertk", ("mat_utils", "marmoset_bridge"), "marmoset_rpc"),
    ("blendertk", ("mat_utils", "substance_bridge"), "substance_rpc"),
)


def mirrors(repo_root: Path = REPO_ROOT):
    """Absolute destination paths for the staged core, in a checked-out monorepo.

    A payload whose package isn't checked out is skipped rather than fabricated —
    the ecosystem repos are cloned independently, and a standalone pythontk
    checkout has no siblings to stage into.
    """
    out = []
    for package, subpath, plugin in _PAYLOADS:
        root = repo_root / package / package
        if not root.is_dir():
            continue
        out.append(
            root.joinpath(*subpath) / plugin / "plugin_src" / plugin / STAGED_NAME
        )
    return out


def _norm(data: bytes) -> bytes:
    """Normalize line endings so EOL churn is not reported as content drift."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def out_of_sync(source: Path = SOURCE, targets=None):
    """Return the mirrors whose content differs from the source (missing counts as drift)."""
    src = _norm(source.read_bytes())
    return [
        m
        for m in (mirrors() if targets is None else targets)
        if not m.is_file() or _norm(m.read_bytes()) != src
    ]


def sync(source: Path = SOURCE, targets=None):
    """Write the source verbatim over each out-of-sync mirror. Returns those written.

    Drives off :func:`out_of_sync` so the write decision and the ``--check`` gate
    share one comparison: a mirror differing only in line endings is not rewritten
    (no churn), but any content difference is healed with a byte-exact copy.

    A missing mirror FILE is self-healed; a missing parent dir means the payload's
    plugin tree isn't there, which is a structural problem this script must report
    rather than paper over by inventing directories.
    """
    data = source.read_bytes()
    written = []
    for m in out_of_sync(source, targets):
        if not m.parent.is_dir():
            raise FileNotFoundError(f"plugin payload dir missing: {m.parent}")
        m.write_bytes(data)
        written.append(m)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage pythontk's RPC plugin core into each installed plugin payload."
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="verify mirrors are in sync with the SSoT; exit 1 on drift (CI gate)",
    )
    args = ap.parse_args(argv)

    if not SOURCE.is_file():
        print(f"[sync_rpc_core] source not found: {SOURCE}", file=sys.stderr)
        return 2

    targets = mirrors()
    if not targets:
        print("[sync_rpc_core] no consumer packages checked out; nothing to stage")
        return 0

    if args.check:
        drift = out_of_sync()
        if drift:
            print(
                "[sync_rpc_core] OUT OF SYNC (run `python sync_rpc_core.py`):",
                file=sys.stderr,
            )
            for m in drift:
                print(f"  - {m}", file=sys.stderr)
            return 1
        print(f"[sync_rpc_core] all {len(targets)} payload(s) in sync")
        return 0

    try:
        written = sync()
    except FileNotFoundError as e:
        print(f"[sync_rpc_core] {e}", file=sys.stderr)
        return 2
    for m in written:
        print(f"[sync_rpc_core] wrote {m}")
    if not written:
        print(f"[sync_rpc_core] all {len(targets)} payload(s) already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
