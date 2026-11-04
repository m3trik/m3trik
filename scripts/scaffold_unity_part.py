#!/usr/bin/python
# coding=utf-8
"""Start a part of unitytk's Unity package from its scaffold.

The base architecture's rails: every part starts from a scaffold, which writes a
failing test (unitytk/docs/parts/<kind>.md say what each part holds). Each kind
writes its folders, its assembly definitions, every file's and folder's ``.meta``
(a fresh GUID, in the format Unity writes, so the editor rewrites nothing), its
main type with a ``Prior art:`` record to fill in, and for a feature a failing
Edit Mode test:

    python m3trik/scripts/scaffold_unity_part.py feature Lighting
    python m3trik/scripts/scaffold_unity_part.py contract IRigPose [--editor]
    python m3trik/scripts/scaffold_unity_part.py door Lighting URP com.unity.render-pipelines.universal 17.3.0
    python m3trik/scripts/scaffold_unity_part.py tool Lighting

It refuses to write over anything that exists. ``--root`` names the package
folder (default: unitytk's ``[tool.m3trik.layers.csharp] root``).
"""

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
UNITYTK = WORKSPACE / "unitytk"
TAIL = "  userData: \n  assetBundleName: \n  assetBundleVariant: \n"
IMPORTERS = {
    "": "folderAsset: yes\nDefaultImporter:\n  externalObjects: {}\n",
    ".cs": (
        "MonoImporter:\n  externalObjects: {}\n  serializedVersion: 2\n"
        "  defaultReferences: []\n  executionOrder: 0\n  icon: {instanceID: 0}\n"
    ),
    ".asmdef": "AssemblyDefinitionImporter:\n  externalObjects: {}\n",
    ".md": "TextScriptImporter:\n  externalObjects: {}\n",
}
NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
TEST_REFS = ["UnityEngine.TestRunner", "UnityEditor.TestRunner"]


class UnityScaffold:
    """Writes one part's files under a package root, each with its ``.meta``."""

    def __init__(self, root: Path):
        self.root = root
        self.written = []

    @staticmethod
    def package_root() -> Path:
        """unitytk's declared C# root (``[tool.m3trik.layers.csharp] root``)."""
        text = (UNITYTK / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r"\[tool\.m3trik\.layers\.csharp\][^\[]*?^root\s*=\s*\"([^\"]+)\"", text, re.S | re.M)
        if not match:
            raise SystemExit("unitytk/pyproject.toml declares no [tool.m3trik.layers.csharp] root: name --root")
        return UNITYTK / match.group(1)

    def _meta(self, path: Path) -> None:
        meta = Path(str(path) + ".meta")
        if meta.exists():
            return
        suffix = "" if path.is_dir() else path.suffix
        body = IMPORTERS.get(suffix, IMPORTERS[".md"])
        meta.write_text(f"fileFormatVersion: 2\nguid: {uuid.uuid4().hex}\n{body}{TAIL}", encoding="utf-8", newline="\n")

    def folder(self, rel: str) -> Path:
        """*rel* under the root, each new folder with its ``.meta``."""
        path = self.root
        for part in rel.split("/"):
            path = path / part
            if not path.exists():
                path.mkdir()
                self._meta(path)
        return path

    def file(self, rel: str, text: str) -> None:
        """Write *rel*, refusing to replace anything."""
        path = self.root / rel
        if path.exists():
            raise SystemExit(f"{path} exists: a scaffold never writes over a file")
        self.folder(rel.rsplit("/", 1)[0])
        path.write_text(text, encoding="utf-8", newline="\n")
        self._meta(path)
        self.written.append(rel)

    def asmdef(self, rel_folder: str, name: str, references, editor=False, auto=True, tests=False, defines=None, version_defines=None, no_engine=False) -> None:
        data = {
            "name": name, "rootNamespace": "", "references": list(references),
            "includePlatforms": ["Editor"] if editor or tests else [], "excludePlatforms": [],
            "allowUnsafeCode": False, "overrideReferences": tests,
            "precompiledReferences": ["nunit.framework.dll"] if tests else [],
            "autoReferenced": auto and not tests,
            "defineConstraints": list(defines or []), "versionDefines": list(version_defines or []),
            "noEngineReferences": no_engine,
        }
        self.file(f"{rel_folder}/{name}.asmdef", json.dumps(data, indent=4) + "\n")

    # -- the kinds ---------------------------------------------------------------

    def feature(self, feature: str) -> None:
        base = f"Features/{feature}"
        if (self.root / base).exists():
            raise SystemExit(f"{self.root / base} exists: split today's code into it by hand (docs/parts/feature.md)")
        core = ["M3trik.Unitytk.Core", "M3trik.Unitytk.Contracts"]
        self.asmdef(f"{base}/Runtime", f"M3trik.Unitytk.{feature}", core)
        self.asmdef(f"{base}/Editor", f"M3trik.Unitytk.{feature}.Editor",
                    core + ["M3trik.Unitytk.Kernel", "M3trik.Unitytk.Contracts.Editor", f"M3trik.Unitytk.{feature}"], editor=True)
        self.file(f"{base}/Editor/{feature}s.cs", f'''using M3trik.Unitytk.Kernel;

/// <summary>
/// The {feature} feature's actions: what a person's menu item and an agent's code
/// do to a project. Each takes an optional <see cref="OpContext"/>: a dry run
/// plans, a menu's run is one undo step, and none just runs.
/// </summary>
/// <remarks>
/// Prior art: TODO -- what was weighed (our API via api.search, Unity's built-ins
/// and packages, an open standard, a maintained library), and why each was or
/// was not adopted.
/// </remarks>
public static class {feature}s
{{
}}
''')
        self.asmdef(f"{base}/Tests", f"M3trik.Unitytk.{feature}.Tests",
                    ["M3trik.Unitytk.Core", "M3trik.Unitytk.Kernel", f"M3trik.Unitytk.{feature}", f"M3trik.Unitytk.{feature}.Editor"] + TEST_REFS,
                    tests=True, defines=["UNITY_INCLUDE_TESTS", "UNITYTK_TEST_FRAMEWORK"],
                    version_defines=[{"name": "com.unity.test-framework", "expression": "1.6.0", "define": "UNITYTK_TEST_FRAMEWORK"}])
        self.file(f"{base}/Tests/{feature}sTests.cs", f'''using M3trik.Unitytk.Kernel;
using NUnit.Framework;

/// <summary>
/// The {feature} actions, each held to the kernel's three checks: one Ctrl+Z after
/// a run restores the scene, the dry run's plan names every change the run makes,
/// and a second run plans nothing.
/// </summary>
public class {feature}sTests
{{
    [Test]
    public void The_first_action_is_planned_undone_and_converges()
    {{
        Assert.Fail("write the first action's test, then the action ({feature}s.cs)");
    }}
}}
''')

    def contract(self, name: str, editor: bool) -> None:
        stand_in = "Pure" + name[1:] if name.startswith("I") else "Pure" + name
        rel = f"Contracts/Editor/{name}.cs" if editor else f"Contracts/{name}.cs"
        provides = f"    [Provides(typeof({name}), StandIn = true)]\n" if editor else ""
        usings = "using M3trik.Unitytk.Kernel;\n\n" if editor else ""
        self.file(rel, f'''{usings}namespace M3trik.Unitytk.Contracts
{{
    /// <summary>TODO: what two features meet through here.</summary>
    /// <remarks>Prior art: TODO.</remarks>
    public interface {name}
    {{
    }}

    /// <summary>The stand-in: TODO what it answers when nothing real provides it.</summary>
{provides}    public sealed class {stand_in} : {name}
    {{
    }}
}}
''')

    def door(self, feature: str, door: str, package: str, version: str) -> None:
        define = "UNITYTK_" + re.sub(r"[^A-Z0-9]+", "_", package.upper().split(".")[-1]).strip("_")
        self.asmdef(f"Features/{feature}/{door}", f"M3trik.Unitytk.{feature}.{door}",
                    ["M3trik.Unitytk.Core", f"M3trik.Unitytk.{feature}"], auto=False, defines=[define],
                    version_defines=[{"name": package, "expression": version, "define": define}])

    def tool(self, feature: str) -> None:
        self.asmdef(f"Tools/{feature}", f"M3trik.Unitytk.Tools.{feature}",
                    ["M3trik.Unitytk.Kernel", f"M3trik.Unitytk.{feature}.Editor"], editor=True, auto=False)
        self.file(f"Tools/{feature}/{feature}Menu.cs", f'''using M3trik.Unitytk.Kernel;
using UnityEditor;

/// <summary>Tools ▸ unitytk ▸ {feature}: a line per menu item over the feature's actions ({feature}s).</summary>
/// <remarks>Prior art: Unity's MenuItem; Unity Search already finds each item.</remarks>
static class {feature}Menu
{{
}}
''')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kind", choices=("feature", "contract", "door", "tool"))
    parser.add_argument("names", nargs="+")
    parser.add_argument("--editor", action="store_true", help="contract: an editor contract (Contracts/Editor)")
    parser.add_argument("--root", type=Path, help="the package folder (default: unitytk's declared root)")
    args = parser.parse_args(argv)
    for name in args.names[:2]:
        if not NAME.match(name):
            parser.error(f"{name!r} is no PascalCase name")
    scaffold = UnityScaffold(args.root or UnityScaffold.package_root())
    if args.kind == "feature":
        scaffold.feature(args.names[0])
    elif args.kind == "contract":
        scaffold.contract(args.names[0], args.editor)
    elif args.kind == "door":
        if len(args.names) != 4:
            parser.error("door takes <Feature> <Door> <package> <version>")
        scaffold.door(*args.names)
    else:
        scaffold.tool(args.names[0])
    for rel in scaffold.written:
        print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
