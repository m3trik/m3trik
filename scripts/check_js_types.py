#!/usr/bin/python
# coding=utf-8
"""Type-check the workspace's JavaScript with ``tsc --checkJs``.

CODE_STANDARD section 0, Proof: a rule without a check is a wish. The WebXR
preview's runtime (pythontk ``net_utils/preview``: the page's kernel and its
features) is plain ES modules, served exactly as written -- no build step --
and typed with JSDoc, including the record typedefs ``sync_scene_records.py``
generates. The TypeScript compiler holds the modules to each other: an export
renamed, a kernel function called with the wrong arguments, a manifest field a
typedef does not declare. Each project is a ``jsconfig.json`` (:data:`PROJECTS`).

The compiler is found, in order:

1. ``$TSC`` -- a whole command line (CI: ``npx --yes -p typescript@5 tsc``);
2. ``tsc`` on PATH, then ``npx`` on PATH (``npx --yes -p typescript@<PIN> tsc``);
3. on a machine with neither: a Node runtime and TypeScript's compiler API
   that are installed anyway -- Playwright's bundled ``node`` (the browser
   suites' driver) and the ``typescript`` package VS Code ships -- driven
   through the same project file (:data:`API_DRIVER`).

Finding none is a ``[SKIP]`` and exit 2 -- never a pass.

Usage:
    python check_js_types.py        # exit 1 on a diagnostic, 2 when no compiler
"""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

SCRIPTS = Path(__file__).resolve().parent
WORKSPACE = SCRIPTS.parents[1]

#: Every JavaScript project checked, by its ``jsconfig.json``.
PROJECTS = [WORKSPACE / "pythontk" / "jsconfig.json"]

#: The TypeScript release ``npx`` fetches when nothing names one.
PIN = "5"

#: TypeScript's compiler API run as ``tsc -p`` would run it: the project parsed,
#: every diagnostic printed, exit 1 when there is one. Read from the
#: environment rather than argv, which ``node -e`` passes on its own terms.
API_DRIVER = r"""
const ts = require(process.env.CHECK_JS_TYPESCRIPT);
const host = {
  getCanonicalFileName: (f) => f,
  getCurrentDirectory: ts.sys.getCurrentDirectory,
  getNewLine: () => '\n',
};
const parsed = ts.getParsedCommandLineOfConfigFile(process.env.CHECK_JS_PROJECT, {}, {
  ...ts.sys,
  onUnRecoverableConfigFileDiagnostic: (d) => {
    console.log(ts.formatDiagnostics([d], host));
    process.exit(2);
  },
});
const program = ts.createProgram({ rootNames: parsed.fileNames, options: parsed.options });
const diagnostics = [...parsed.errors, ...ts.getPreEmitDiagnostics(program)];
if (diagnostics.length) {
  console.log(ts.formatDiagnostics(diagnostics, host));
  process.exit(1);
}
console.log(`${parsed.fileNames.length} files, TypeScript ${ts.version}`);
"""


def _local_api() -> Optional[Tuple[str, str]]:
    """``(node, typescript.js)`` found on this machine without either being
    installed for this purpose, or ``None``."""
    node = shutil.which("node")
    if node is None:
        try:
            import playwright  # the browser suites' driver ships a node binary

            exe = "node.exe" if os.name == "nt" else "node"
            candidate = Path(playwright.__file__).parent / "driver" / exe
            node = str(candidate) if candidate.is_file() else None
        except ImportError:
            node = None
    if node is None:
        return None
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft VS Code",
        Path("/usr/share/code"),
        Path("/Applications/Visual Studio Code.app/Contents/Resources/app"),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        found = sorted(
            root.glob("**/extensions/node_modules/typescript/lib/typescript.js"),
            key=lambda p: p.stat().st_mtime,
        )
        if found:
            return node, str(found[-1])
    return None


def compiler() -> Optional[Tuple[str, List[str]]]:
    """``(description, argv prefix)`` of the compiler to run, or ``None``. The
    API driver's prefix is ``["node", "-e", API_DRIVER, typescript.js]``."""
    if os.environ.get("TSC"):
        return "$TSC", shlex.split(os.environ["TSC"])
    tsc = shutil.which("tsc")
    if tsc:
        return tsc, [tsc]
    npx = shutil.which("npx")
    if npx:
        return f"npx typescript@{PIN}", [npx, "--yes", "-p", f"typescript@{PIN}", "tsc"]
    local = _local_api()
    if local:
        node, typescript = local
        return f"{node} + {typescript}", [node, "-e", API_DRIVER, typescript]
    return None


def check(project: Path, found: Tuple[str, List[str]]) -> Tuple[int, str]:
    """Run the compiler over *project*: ``(returncode, output)``."""
    _, argv = found
    env = dict(os.environ)
    if "-e" in argv[1:2]:
        node, _, driver, typescript = argv
        env.update(CHECK_JS_TYPESCRIPT=typescript, CHECK_JS_PROJECT=str(project))
        command = [node, "-e", driver]
    else:
        command = [*argv, "-p", str(project), "--pretty", "false"]
    done = subprocess.run(
        command,
        cwd=project.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return done.returncode, (done.stdout + done.stderr).strip()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    found = compiler()
    if found is None:
        print(
            "[SKIP] no TypeScript compiler: set $TSC, or put tsc / npx (Node) on "
            "PATH -- a check that did not run is not a pass"
        )
        return 2
    print(f"compiler: {found[0]}")
    failed = False
    for project in PROJECTS:
        name = project.relative_to(WORKSPACE).as_posix()
        if not project.is_file():
            print(f"[FAIL] {name}: no such project")
            failed = True
            continue
        code, output = check(project, found)
        if code == 0:
            print(f"[OK] {name}" + (f": {output.splitlines()[-1]}" if output else ""))
        else:
            failed = True
            print(f"[FAIL] {name}\n{output}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
