#!/usr/bin/env python
"""Runtime-vs-static API drift gate.

Two independent introspection producers must agree on a package's public *class
surface*:

  * the STATIC registry - ``generate_api_registry.py`` walks source with ``ast``
    and owns the committed ``API_REGISTRY.json``. It cannot see members that only
    exist at runtime (metaclass/mixin injection) nor detect a public method a
    decorator shadows.
  * the DYNAMIC surface - ``pythontk.HelpMixin`` introspects the *live* classes
    (``_collect_records``), so it sees exactly those.

This gate compares the two by member NAME per class (with kind as a secondary
signal, see below) - deliberately NOT by signature string, which the
``ast.unparse`` and ``inspect.signature`` renderers format differently.
Comparison is scoped to own-body members on both sides (``inherited=False``), so
inherited-mixin members are excluded symmetrically and never show as false drift;
genuine metaclass injection (into the class ``__dict__``) is caught.

Drift is classified by member NAME so a kind change is not mistaken for a
missing method:

    * ``missing`` - the registry promises a public member the live class does
      NOT have (a real contract break / stale registry) -> FAIL.
    * ``added`` - live-only members the static walker cannot see (metaclass /
      mixin injection, nested classes, dynamically-composed methods) ->
      advisory, exit 0 unless ``--strict``.
    * ``kind_changed`` - present on both sides but a different kind, e.g. a
      wrapping decorator over ``@staticmethod`` yields a plain function at
      runtime -> advisory; the member still exists.

Two execution modes, because the DCC packages cannot be imported on a cloud CI
box (no Maya/Qt/Blender):

    # importable, DCC-free package - import + diff in one process:
    python verify_runtime_surface.py verify pythontk

    # DCC package - dump the live surface from INSIDE a headless session
    # (mayapy + maya.standalone, offscreen-QPA, bpy), then diff the artifact:
    mayapy verify_runtime_surface.py dump mayatk --out mayatk/API_RUNTIME.json
    python verify_runtime_surface.py verify mayatk --runtime mayatk/API_RUNTIME.json

The ``API_RUNTIME.json`` artifact is a build product - gitignored, never
committed (it is environment-specific and would churn the context budget).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The static walker only emits def'd class members; restrict the runtime side to
# the same kinds so plain class attributes don't read as spurious drift.
METHOD_KINDS = {"method", "staticmethod", "classmethod", "property"}


# ---------- static side -------------------------------------------------------


def load_static_surface(pkg_dir: Path) -> dict[str, dict[str, str]]:
    """``{class_name: {member_name: kind}}`` from a package's committed
    ``API_REGISTRY.json``. Same-named classes across modules are merged."""
    path = pkg_dir / "API_REGISTRY.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    surface: dict[str, dict[str, str]] = {}
    for mod in data.get("modules", []):
        for cls in mod.get("classes", []):
            members = {
                m["name"]: m["kind"]
                for m in cls.get("members", [])
                if m["kind"] in METHOD_KINDS
            }
            surface.setdefault(cls["name"], {}).update(members)
    return surface


# ---------- runtime side ------------------------------------------------------


def runtime_surface_from_package(pkg_name: str) -> dict[str, list[dict]]:
    """Import ``pkg_name`` and dump ``{class_name: [record dict, ...]}`` for every
    exported ``HelpMixin`` subclass (own members only)."""
    # Make the monorepo's source packages importable without an install.
    for name in {pkg_name, "pythontk"}:
        src = REPO_ROOT / name
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))

    import importlib

    pkg = importlib.import_module(pkg_name)
    from pythontk import HelpMixin  # noqa: WPS433 (import after path setup)

    surface: dict[str, list[dict]] = {}
    seen: set[int] = set()
    # Enumerate the FULL public surface, not dir(pkg): these packages use a lazy
    # module resolver (bootstrap_package / __getattr__), so class names are
    # materialised only on attribute access - dir() would miss the unresolved
    # ones and the gate would silently see an almost-empty surface. Prefer the
    # resolver's own class registry (populated by its build-time AST scan, so it
    # knows every public class before import); fall back to __all__, then dir().
    resolver = getattr(pkg, "_RESOLVER", None)
    class_map = getattr(resolver, "class_to_module", None)
    if class_map:
        names = list(class_map.keys())
    else:
        names = list(getattr(pkg, "__all__", None) or dir(pkg))
    skipped: list[str] = []
    for attr in names:
        try:
            # A lazy resolver's __getattr__ can raise (e.g. a broken optional
            # import), which getattr(..., default) would NOT catch - so one bad
            # export must not sink the whole dump.
            obj = getattr(pkg, attr)
        except Exception:  # noqa: BLE001
            skipped.append(attr)
            continue
        if not isinstance(obj, type) or obj is HelpMixin:
            continue
        if not issubclass(obj, HelpMixin) or id(obj) in seen:
            continue
        seen.add(id(obj))
        try:
            records = obj._collect_records(inherited=False, private=False)
        except Exception:  # noqa: BLE001
            skipped.append(obj.__name__)
            continue
        surface[obj.__name__] = [
            r.as_dict() for r in records if r.kind in METHOD_KINDS
        ]
    if skipped:
        # Surface, don't hide, what couldn't be introspected.
        print(
            f"note: skipped {len(skipped)} unresolved/failed name(s): "
            f"{', '.join(sorted(set(skipped))[:10])}",
            file=sys.stderr,
        )
    return surface


def runtime_surface_from_artifact(path: Path) -> dict[str, list[dict]]:
    """Load a pre-dumped ``API_RUNTIME.json`` (produced under a headless DCC)."""
    return json.loads(path.read_text(encoding="utf-8"))


def _member_kinds(surface: dict[str, list[dict]]) -> dict[str, dict[str, str]]:
    return {
        cls: {m["name"]: m["kind"] for m in members}
        for cls, members in surface.items()
    }


# ---------- diff --------------------------------------------------------------


def compute_drift(
    static: dict[str, dict[str, str]],
    runtime: dict[str, dict[str, str]],
) -> dict[str, dict[str, list]]:
    """Per-class drift over the classes present on BOTH sides, classified by
    member NAME so a kind change is not mistaken for a missing method:

      * ``missing``      - in the registry, absent at runtime (real contract
                           break / stale registry) -> FAIL.
      * ``added``        - live-only (metaclass/mixin-injected, nested class) ->
                           advisory; the static walker cannot see these.
      * ``kind_changed`` - present both sides, different kind (e.g. a wrapping
                           decorator over ``@staticmethod`` yields a plain
                           function at runtime) -> advisory; the member exists.
    """
    report: dict[str, dict[str, list]] = {}
    for cls in sorted(set(static) & set(runtime)):
        s, r = static[cls], runtime[cls]
        missing = sorted(set(s) - set(r))
        added = sorted(set(r) - set(s))
        kind_changed = sorted(
            (name, s[name], r[name]) for name in set(s) & set(r) if s[name] != r[name]
        )
        if missing or added or kind_changed:
            report[cls] = {
                "missing": missing,
                "added": added,
                "kind_changed": kind_changed,
            }
    return report


# ---------- driver ------------------------------------------------------------


def _print_report(pkg_name: str, report: dict[str, dict[str, list]]) -> None:
    if not report:
        print(f"{pkg_name}: runtime surface matches the static registry.")
        return
    for cls, d in report.items():
        for name in d["missing"]:
            print(f"  FAIL {cls}.{name} - in registry, MISSING at runtime")
        for name in d["added"]:
            print(f"  note {cls}.{name} - live only (static walker can't see it)")
        for name, static_kind, runtime_kind in d["kind_changed"]:
            print(
                f"  note {cls}.{name} - kind {static_kind} (static) "
                f"vs {runtime_kind} (runtime)"
            )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("action", choices=["verify", "dump"])
    ap.add_argument("package")
    ap.add_argument(
        "--runtime",
        type=Path,
        help="verify against a pre-dumped API_RUNTIME.json instead of importing",
    )
    ap.add_argument("--out", type=Path, help="dump target (default <pkg>/API_RUNTIME.json)")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="also fail on runtime-only (metaclass/mixin) members",
    )
    args = ap.parse_args(argv)

    pkg_dir = REPO_ROOT / args.package
    if not pkg_dir.is_dir():
        print(f"error: package dir not found: {pkg_dir}", file=sys.stderr)
        return 2

    if args.action == "dump":
        surface = runtime_surface_from_package(args.package)
        out = args.out or (pkg_dir / "API_RUNTIME.json")
        out.write_text(json.dumps(surface, indent=2), encoding="utf-8")
        print(f"wrote {out} ({len(surface)} classes)")
        return 0

    # verify
    if args.runtime:
        try:
            surface = runtime_surface_from_artifact(args.runtime)
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"error: cannot read runtime artifact {args.runtime} ({exc}). "
                f"Did the DCC dump run and write it?",
                file=sys.stderr,
            )
            return 2
    else:
        try:
            surface = runtime_surface_from_package(args.package)
        except Exception as exc:  # noqa: BLE001
            print(
                f"error: cannot import {args.package} in-process ({exc}). "
                f"For DCC packages, 'dump' from a headless session then verify "
                f"with --runtime.",
                file=sys.stderr,
            )
            return 2

    if not surface:
        print(
            f"error: no HelpMixin classes found for {args.package} — the import "
            f"exposed an empty surface, so there is nothing to verify (an empty "
            f"surface must NOT be read as 'no drift').",
            file=sys.stderr,
        )
        return 2

    static = load_static_surface(pkg_dir)
    report = compute_drift(static, _member_kinds(surface))
    _print_report(args.package, report)

    has_missing = any(d["missing"] for d in report.values())
    fail = has_missing or (args.strict and bool(report))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
