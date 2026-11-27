"""Copy uitk's icons into unitytk's editor kernel -- and fail when the copy drifts.

The manifests draw one icon set: uitk's SVGs (``uitk/uitk/icons``), which the
Shot Manifest's Qt panel draws through uitk's ``IconManager``. unitytk's Unity
Manifest draws the same files, copied next to its editor kernel's assembly
(``Kernel/Editor/Icons``; ``VectorIcons``), since a Unity package can reach no
Python package's folder. Unity's built-in SVG importer (Unity 6.3+) makes each a
UI Toolkit vector image, drawn tinted by ``Image.tintColor``, which multiplies:
so the copy is the file verbatim but for the icon colour uitk recolours
(:data:`TINT`), written white, which the tint then gives exactly. A copy is the
one sanctioned duplicate when a check holds it to its source: this is that
check, run by CI's gate job. Each copy's ``.meta`` GUID, and the folder's, is
derived from its name, so a re-copy never mints a new one; the rest of a
``.meta`` (the import settings) is Unity's to write. A file uitk no longer has
goes, ``.meta`` too. A check writes nothing.

Usage::

    python sync_unity_icons.py           # copy the icons
    python sync_unity_icons.py --check   # exit 1 when the copy drifts
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import sync_scene_records as records  # noqa: E402  (its sync and the package's files)

REPO_ROOT = records.REPO_ROOT
SOURCE = REPO_ROOT / "uitk" / "uitk" / "icons"
#: The editor kernel's assembly: the icons sit in its folder's ``Icons``.
ASSEMBLY = "M3trik.Unitytk.Kernel.asmdef"
#: The namespace each copied file's ``.meta`` GUID is derived in.
GUID_NAMESPACE = "https://github.com/m3trik/unitytk/icons/"
SCRIPT = "sync_unity_icons.py"
#: The colour uitk's icons mean by "the icon's colour" (``IconManager`` recolours
#: it); written white in the copy, for a multiplying tint to give exactly.
TINT = "#888888"
WHITE = "#ffffff"


def copied(svg: Path) -> str:
    """*svg* as unitytk carries it: LF text, its icon colour white."""
    text = svg.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return text.replace(TINT, WHITE).replace(TINT.upper(), WHITE)


def icons_dir() -> Path:
    """Where the copies go: ``Icons`` beside the editor kernel's asmdef."""
    return records.unity_file(ASSEMBLY).parent / "Icons"


def guid(name: str) -> str:
    """The GUID of copy *name* (or the folder's), derived from its name."""
    return uuid.uuid5(uuid.NAMESPACE_URL, GUID_NAMESPACE + name).hex


def meta(name: str, folder: bool = False) -> str:
    """The ``.meta`` a new copy (or the folder) starts with: its GUID, and for
    the folder Unity's folder form. Unity writes a file's import settings."""
    if folder:
        return (
            f"fileFormatVersion: 2\nguid: {guid(name)}\nfolderAsset: yes\n"
            "DefaultImporter:\n  externalObjects: {}\n  userData: \n"
            "  assetBundleName: \n  assetBundleVariant: \n"
        )
    return f"fileFormatVersion: 2\nguid: {guid(name)}\n"


def targets() -> list:
    """``[(path, text)]``: every copied icon."""
    folder = icons_dir()
    return [(folder / svg.name, copied(svg)) for svg in sorted(SOURCE.glob("*.svg"))]


def metas() -> list:
    """``[(path, text)]``: the folder's ``.meta`` and each copy's, as a new one
    starts (:func:`meta`); its GUID line is what is held (:func:`sync_meta`)."""
    folder = icons_dir()
    out = [(folder.parent / "Icons.meta", meta("Icons", folder=True))]
    out += [(folder / f"{svg.name}.meta", meta(svg.name)) for svg in sorted(SOURCE.glob("*.svg"))]
    return out


def guid_line(text: str) -> str:
    """The ``guid: ...`` line of ``.meta`` *text*."""
    return next(line for line in text.splitlines() if line.startswith("guid:"))


def stale(wanted) -> list:
    """The copies (and their ``.meta``) uitk no longer has."""
    folder = icons_dir()
    keep = {path for path, _text in wanted} | {path for path, _text in metas()}
    return sorted(p for p in folder.glob("*") if p.is_file() and p not in keep) if folder.is_dir() else []


def sync_meta(path: Path, new: str, check: bool) -> bool:
    """Hold *path*'s GUID to the one *new* (the ``.meta`` a new one starts
    with) carries, the rest Unity's. Returns whether it drifted; writes *new*
    (or the GUID line) unless *check*."""
    text = path.read_text(encoding="utf-8") if path.is_file() else None
    line = guid_line(new)
    if text is not None and line in text.splitlines():
        return False
    if check:
        print(f"DRIFT: {path.relative_to(REPO_ROOT)} lacks {line}; run {SCRIPT}")
        return True
    if text is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8", newline="\n")
    else:
        kept = [l if not l.startswith("guid:") else line for l in text.splitlines()]
        path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="exit 1 on drift")
    args = parser.parse_args(argv)
    wanted = targets()
    failed = False
    for path, text in wanted:
        failed |= records.sync_text(path, text, args.check, "icon copy", SCRIPT)
    for path, new in metas():
        failed |= sync_meta(path, new, args.check)
    for path in stale(wanted):
        failed = True
        if args.check:
            print(f"DRIFT: {path.relative_to(REPO_ROOT)} is no uitk icon; run {SCRIPT}")
        else:
            path.unlink()
            print(f"removed {path.relative_to(REPO_ROOT)}")
    if not failed:
        print(f"in sync: {len(wanted)} icons")
    return 1 if failed and args.check else 0


if __name__ == "__main__":
    sys.exit(main())
