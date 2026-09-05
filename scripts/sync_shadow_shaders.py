#!/usr/bin/python
# coding=utf-8
"""Splice pythontk's shared horizon shader body into every generated mirror.

``pythontk/geo_utils/shadow_horizon.glsl`` is the single source of truth for
the coverage-aware horizon evaluation, and ``HorizonMap.alpha`` beside it is
the numeric oracle that body is written against. One text, every consumer.

Why copies exist at all
-----------------------
A consumer that IS a Python process when it needs the shader assembles it
through ``ShadowHorizon.shader_source(language)`` and carries nothing: that is
Maya's ``.ogsfx`` / ``.fx`` and Blender's ``gpu`` overlay. A consumer that is
not gets a mirror:

* the WebXR viewer's ``shadow_rig.js`` runs in a browser — the preview server
  copies bytes and must not learn what a shadow is to serve them;
* Unity's ``ShadowPlaneHorizon.hlsl`` is deployed into a Unity project, which
  has no ``pythontk`` and no Python at all.

That is CODE_STANDARD section 6's sanctioned duplicate, invoked once for each
consumer that genuinely cannot import the source, and no more.

Each mirror carries the body between two markers, with its own host prologue
(uniforms, and the ``SH_Fetch`` texel hook the body calls) outside them. Only
the marked region is written, so a host's own code is never touched.

**Never hand-edit between the markers** — edit the ``.glsl`` and re-run this.
Drift is caught by ``--check`` (CI gate) and by
``pythontk/test/test_sync_shadow_shaders.py``.

Usage:
    python sync_shadow_shaders.py            # write mirrors (idempotent)
    python sync_shadow_shaders.py --check    # verify; exit 1 on drift
"""

import argparse
import sys
from pathlib import Path

# This file: _scripts/m3trik/scripts/sync_shadow_shaders.py -> root is parents[2].
REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "pythontk" / "pythontk" / "geo_utils" / "shadow_horizon.glsl"

BEGIN = "// >>> BEGIN GENERATED shadow_horizon body"
END = "// <<< END GENERATED shadow_horizon body"

#: ``(package, relative path, language)`` per mirror. A package that is not
#: checked out is skipped rather than fabricated — the ecosystem repos are
#: cloned independently.
_MIRRORS = (
    ("pythontk", "pythontk/net_utils/preview/scripts/shadow_rig.js", "glsl"),
    ("unitytk", "unitytk/templates/ShadowPlaneHorizon.hlsl", "hlsl"),
)


def _shader_source(language: str) -> str:
    """The body for *language*, from the checked-out pythontk.

    Imported here rather than at module scope so ``--help`` and a missing
    pythontk both fail with something readable.
    """
    root = str(REPO_ROOT / "pythontk")
    if root not in sys.path:
        sys.path.insert(0, root)
    from pythontk.geo_utils.shadow_horizon import ShadowHorizon

    return ShadowHorizon.shader_source(language)


def mirrors(repo_root: Path = REPO_ROOT):
    """``(path, language)`` for every mirror whose package is checked out."""
    out = []
    for package, relative, language in _MIRRORS:
        root = repo_root / package
        if not root.is_dir():
            continue
        out.append((root / relative, language))
    return out


def _norm(text: str) -> str:
    """Normalize line endings so EOL churn is not reported as content drift."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


#: Characters a mirror's own syntax would choke on, by suffix. The viewer's
#: body lands inside a JS template literal, where a backtick ends the string
#: and ``${`` opens an interpolation — either produces a *syntax* error in a
#: file the browser then refuses whole, with the shader nowhere in the
#: message. Cheap to check here, expensive to diagnose there.
_FORBIDDEN = {".js": ("`", "${")}


def render(path: Path, language: str) -> str:
    """The mirror's full text with the marked region rewritten from the SSoT.

    Raises:
        ValueError: the file carries no marker pair — a mirror must declare
            where the generated region starts and ends, and guessing would
            overwrite a host's own shader — or the body holds a sequence that
            mirror's own syntax cannot carry.
    """
    text = _norm(path.read_text(encoding="utf-8"))
    start = text.find(BEGIN)
    stop = text.find(END)
    if start < 0 or stop < 0 or stop < start:
        raise ValueError(f"markers not found in {path}")
    body = _norm(_shader_source(language))
    for token in _FORBIDDEN.get(path.suffix.lower(), ()):
        if token in body:
            raise ValueError(
                f"the shared body holds {token!r}, which {path.name} cannot "
                f"carry; remove it from {SOURCE.name}"
            )
    head = text[: start + len(BEGIN)]
    tail = text[stop:]
    return f"{head}\n{body}{tail}"


def out_of_sync(targets=None):
    """The mirrors whose marked region differs from the SSoT (missing counts)."""
    drift = []
    for path, language in mirrors() if targets is None else targets:
        if not path.is_file():
            drift.append(path)
            continue
        if _norm(path.read_text(encoding="utf-8")) != render(path, language):
            drift.append(path)
    return drift


def sync(targets=None):
    """Rewrite each out-of-sync mirror's marked region. Returns those written.

    Drives off the same comparison ``--check`` uses, so a mirror differing
    only in line endings is not rewritten (no churn) while any content
    difference is healed.
    """
    written = []
    for path, language in mirrors() if targets is None else targets:
        if not path.is_file():
            raise FileNotFoundError(f"mirror missing: {path}")
        rendered = render(path, language)
        if _norm(path.read_text(encoding="utf-8")) == rendered:
            continue
        path.write_text(rendered, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Splice pythontk's shared horizon shader body into its mirrors."
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="verify mirrors are in sync with the SSoT; exit 1 on drift (CI gate)",
    )
    args = ap.parse_args(argv)

    if not SOURCE.is_file():
        print(f"[sync_shadow_shaders] source not found: {SOURCE}", file=sys.stderr)
        return 2

    targets = mirrors()
    if not targets:
        print("[sync_shadow_shaders] no consumer packages checked out; nothing to do")
        return 0

    try:
        if args.check:
            drift = out_of_sync()
            if drift:
                print(
                    "[sync_shadow_shaders] OUT OF SYNC "
                    "(run `python sync_shadow_shaders.py`):",
                    file=sys.stderr,
                )
                for path in drift:
                    print(f"  - {path}", file=sys.stderr)
                return 1
            print(f"[sync_shadow_shaders] all {len(targets)} mirror(s) in sync")
            return 0
        written = sync()
    except (FileNotFoundError, ValueError) as error:
        print(f"[sync_shadow_shaders] {error}", file=sys.stderr)
        return 2
    for path in written:
        print(f"[sync_shadow_shaders] wrote {path}")
    if not written:
        print(f"[sync_shadow_shaders] all {len(targets)} mirror(s) already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
