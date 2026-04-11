"""Generate a workspace-wide repository inventory for the monorepo.

The report is written into ``m3trik/docs`` as both Markdown and JSON so it can
serve as a human-readable index and a machine-readable source of truth.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import tomllib


CODE_SUFFIXES = {
    ".bash",
    ".bat",
    ".cmd",
    ".cfg",
    ".css",
    ".conf",
    ".html",
    ".htm",
    ".ini",
    ".js",
    ".json",
    ".jsonc",
    ".jsx",
    ".less",
    ".ps1",
    ".psd1",
    ".psm1",
    ".py",
    ".qml",
    ".qss",
    ".sass",
    ".scss",
    ".sh",
    ".sql",
    ".svelte",
    ".toml",
    ".ts",
    ".tsx",
    ".ui",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
ENTRYPOINT_SUFFIXES = {".bat", ".cmd", ".ps1", ".py", ".sh"}
SKIP_DIR_NAMES = {
    ".egg-info",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "output",
    "temp",
    "tmp",
    "venv",
}
NON_REPO_IGNORE = {"bin", "$null"}
MANIFEST_NAMES = ["pyproject.toml", "package.json", "requirements.txt", "setup.py"]


@dataclass(slots=True)
class PackageRootInventory:
    name: str
    path: str
    immediate_subpackages: list[str] = field(default_factory=list)
    immediate_modules: list[str] = field(default_factory=list)
    recursive_module_count: int = 0


@dataclass(slots=True)
class CodeRootInventory:
    name: str
    path: str
    code_file_count: int
    dominant_suffixes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RepoInventory:
    name: str
    path: str
    domain: str
    summary: str
    repo_kind: str
    manifests: list[str] = field(default_factory=list)
    root_scripts: list[str] = field(default_factory=list)
    package_roots: list[PackageRootInventory] = field(default_factory=list)
    code_roots: list[CodeRootInventory] = field(default_factory=list)
    has_docs: bool = False
    has_tests: bool = False
    has_examples: bool = False
    tracked_code_files: int = 0
    tracked_total_lines: int = 0
    tracked_nonempty_lines: int = 0


@dataclass(slots=True)
class NonRepoInventory:
    name: str
    path: str
    manifests: list[str] = field(default_factory=list)
    package_roots: list[str] = field(default_factory=list)
    root_scripts: list[str] = field(default_factory=list)
    code_file_count: int = 0


def _should_skip_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIP_DIR_NAMES


def _iter_code_files(root: Path) -> Iterable[Path]:
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = [name for name in dir_names if not _should_skip_dir(name)]
        current_path = Path(current_root)
        for file_name in file_names:
            if file_name.startswith("."):
                continue
            file_path = current_path / file_name
            if file_path.suffix.lower() in CODE_SUFFIXES:
                yield file_path


def _count_lines(file_path: Path) -> tuple[int, int]:
    total_lines = 0
    nonempty_lines = 0
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            total_lines += 1
            if line.strip():
                nonempty_lines += 1
    return total_lines, nonempty_lines


def _read_pyproject_metadata(repo_root: Path) -> tuple[str, str]:
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        return "", ""

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project_data = data.get("project", {})
    poetry_data = data.get("tool", {}).get("poetry", {})
    name = project_data.get("name") or poetry_data.get("name") or ""
    description = (
        project_data.get("description") or poetry_data.get("description") or ""
    )
    return name.strip(), description.strip()


def _read_readme_summary(repo_root: Path) -> str:
    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        return ""

    lines = readme_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!["):
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped
    return ""


def _parse_domain_map(workspace_root: Path) -> dict[str, str]:
    instructions_path = workspace_root / ".github" / "copilot-instructions.md"
    if not instructions_path.exists():
        return {}

    domain_map: dict[str, str] = {}
    for raw_line in instructions_path.read_text(
        encoding="utf-8", errors="ignore"
    ).splitlines():
        line = raw_line.lstrip("> ").strip()
        if not line.startswith("|"):
            continue
        match = re.match(r"^\|\s*`([^`]+?)/`\s*\|.*?\|\s*([^|]+?)\s*\|$", line)
        if match is None:
            continue
        repo_name, domain_cell = match.groups()
        domain_map[repo_name] = domain_cell.strip()
    return domain_map


def _tracked_relative_files(repo_root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
            check=True,
        )
        return [
            Path(relative_path)
            for relative_path in result.stdout.decode("utf-8", errors="ignore").split(
                "\0"
            )
            if relative_path
        ]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [
            file_path.relative_to(repo_root)
            for file_path in _iter_code_files(repo_root)
        ]


def _scan_package_root(
    package_root: Path,
    repo_root: Path,
    tracked_relative_file_set: set[str],
) -> PackageRootInventory:
    immediate_subpackages: list[str] = []
    immediate_modules: list[str] = []
    recursive_module_count = 0

    for current_root, dir_names, file_names in os.walk(package_root):
        dir_names[:] = [name for name in dir_names if not _should_skip_dir(name)]
        current_path = Path(current_root)
        current_rel_path = current_path.relative_to(repo_root)
        if current_path == package_root:
            for dir_name in sorted(dir_names):
                init_rel_path = (current_rel_path / dir_name / "__init__.py").as_posix()
                if init_rel_path in tracked_relative_file_set:
                    immediate_subpackages.append(dir_name)
            for file_name in sorted(file_names):
                rel_path = (current_rel_path / file_name).as_posix()
                if (
                    file_name.endswith(".py")
                    and file_name != "__init__.py"
                    and rel_path in tracked_relative_file_set
                ):
                    immediate_modules.append(Path(file_name).stem)
        for file_name in file_names:
            rel_path = (current_rel_path / file_name).as_posix()
            if (
                file_name.endswith(".py")
                and file_name != "__init__.py"
                and rel_path in tracked_relative_file_set
            ):
                recursive_module_count += 1

    return PackageRootInventory(
        name=package_root.name,
        path=package_root.relative_to(repo_root).as_posix(),
        immediate_subpackages=immediate_subpackages,
        immediate_modules=immediate_modules,
        recursive_module_count=recursive_module_count,
    )


def _scan_code_root(
    code_root: Path,
    repo_root: Path,
    tracked_relative_files: list[Path],
) -> CodeRootInventory | None:
    suffix_counter: Counter[str] = Counter()
    code_file_count = 0

    for relative_path in tracked_relative_files:
        if not relative_path.parts:
            continue
        if relative_path.parts[0] != code_root.name:
            continue
        if any(_should_skip_dir(part) for part in relative_path.parts[:-1]):
            continue
        suffix = relative_path.suffix.lower()
        if suffix not in CODE_SUFFIXES:
            continue
        suffix_counter[suffix] += 1
        code_file_count += 1

    if not code_file_count:
        return None

    dominant_suffixes = [
        f"{suffix} ({count})" for suffix, count in suffix_counter.most_common(5)
    ]
    return CodeRootInventory(
        name=code_root.name,
        path=code_root.relative_to(repo_root).as_posix(),
        code_file_count=code_file_count,
        dominant_suffixes=dominant_suffixes,
    )


def _root_scripts(repo_root: Path) -> list[str]:
    scripts = []
    for child in sorted(repo_root.iterdir(), key=lambda path: path.name.lower()):
        if child.is_file() and child.suffix.lower() in ENTRYPOINT_SUFFIXES:
            scripts.append(child.name)
    return scripts


def _tracked_code_stats(repo_root: Path) -> tuple[int, int, int]:
    tracked_files = [
        repo_root / relative_path
        for relative_path in _tracked_relative_files(repo_root)
    ]

    code_file_count = 0
    total_lines = 0
    nonempty_lines = 0

    for file_path in tracked_files:
        if not file_path.is_file():
            continue
        if any(
            _should_skip_dir(part)
            for part in file_path.relative_to(repo_root).parts[:-1]
        ):
            continue
        if file_path.suffix.lower() not in CODE_SUFFIXES:
            continue
        code_file_count += 1
        file_total_lines, file_nonempty_lines = _count_lines(file_path)
        total_lines += file_total_lines
        nonempty_lines += file_nonempty_lines

    return code_file_count, total_lines, nonempty_lines


def _repo_kind(
    manifests: list[str],
    package_roots: list[PackageRootInventory],
    code_roots: list[CodeRootInventory],
    root_scripts: list[str],
) -> str:
    if package_roots:
        return "Python package"
    if root_scripts and any(script.endswith(".ps1") for script in root_scripts):
        return "Operations / scripts"
    if code_roots:
        return "Application / mixed codebase"
    return "Repository"


def _repo_summary(repo_root: Path, domain: str) -> str:
    _, pyproject_description = _read_pyproject_metadata(repo_root)
    if pyproject_description:
        return pyproject_description

    readme_summary = _read_readme_summary(repo_root)
    if readme_summary and readme_summary.lower() != repo_root.name.lower():
        return readme_summary

    if domain:
        return f"Workspace repo aligned with the {domain} domain."

    return "Workspace repository."


def _collect_repo_inventory(
    workspace_root: Path, repo_root: Path, domain_map: dict[str, str]
) -> RepoInventory:
    manifests = [name for name in MANIFEST_NAMES if (repo_root / name).exists()]
    tracked_relative_files = _tracked_relative_files(repo_root)
    tracked_relative_file_set = {
        relative_path.as_posix() for relative_path in tracked_relative_files
    }
    package_roots = [
        _scan_package_root(child, repo_root, tracked_relative_file_set)
        for child in sorted(repo_root.iterdir(), key=lambda path: path.name.lower())
        if child.is_dir()
        and not _should_skip_dir(child.name)
        and (child / "__init__.py").exists()
    ]
    package_names = {package.name for package in package_roots}

    code_roots: list[CodeRootInventory] = []
    for child in sorted(repo_root.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir():
            continue
        if _should_skip_dir(child.name) or child.name in package_names:
            continue
        code_root = _scan_code_root(child, repo_root, tracked_relative_files)
        if code_root is not None:
            code_roots.append(code_root)

    root_scripts = _root_scripts(repo_root)
    tracked_code_files, tracked_total_lines, tracked_nonempty_lines = (
        _tracked_code_stats(repo_root)
    )
    domain = domain_map.get(repo_root.name, "")

    return RepoInventory(
        name=repo_root.name,
        path=repo_root.relative_to(workspace_root).as_posix(),
        domain=domain,
        summary=_repo_summary(repo_root, domain),
        repo_kind=_repo_kind(manifests, package_roots, code_roots, root_scripts),
        manifests=manifests,
        root_scripts=root_scripts,
        package_roots=package_roots,
        code_roots=code_roots,
        has_docs=(repo_root / "docs").exists(),
        has_tests=(repo_root / "test").exists(),
        has_examples=(repo_root / "examples").exists(),
        tracked_code_files=tracked_code_files,
        tracked_total_lines=tracked_total_lines,
        tracked_nonempty_lines=tracked_nonempty_lines,
    )


def _collect_non_repo_inventory(
    workspace_root: Path, repo_names: set[str]
) -> list[NonRepoInventory]:
    non_repo_entries: list[NonRepoInventory] = []
    for child in sorted(workspace_root.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir():
            continue
        if (
            child.name in repo_names
            or child.name in NON_REPO_IGNORE
            or child.name.startswith(".")
            or child.name.startswith("_")
        ):
            continue
        manifests = [name for name in MANIFEST_NAMES if (child / name).exists()]
        package_roots = [
            grandchild.name
            for grandchild in sorted(
                child.iterdir(), key=lambda path: path.name.lower()
            )
            if grandchild.is_dir()
            and not _should_skip_dir(grandchild.name)
            and (grandchild / "__init__.py").exists()
        ]
        root_scripts = _root_scripts(child)
        code_file_count = sum(1 for _ in _iter_code_files(child))
        if not (manifests or package_roots or root_scripts or code_file_count):
            continue
        non_repo_entries.append(
            NonRepoInventory(
                name=child.name,
                path=child.relative_to(workspace_root).as_posix(),
                manifests=manifests,
                package_roots=package_roots,
                root_scripts=root_scripts,
                code_file_count=code_file_count,
            )
        )
    return non_repo_entries


def _join_items(items: list[str]) -> str:
    return ", ".join(items) if items else "-"


def _table_cell(items: list[str]) -> str:
    return "<br>".join(items) if items else "-"


def _render_markdown(
    workspace_root: Path,
    repos: list[RepoInventory],
    non_repo_entries: list[NonRepoInventory],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_lines = sum(repo.tracked_total_lines for repo in repos)
    total_nonempty_lines = sum(repo.tracked_nonempty_lines for repo in repos)
    total_code_files = sum(repo.tracked_code_files for repo in repos)

    lines = [
        "# Workspace Repository Inventory",
        "",
        f"Generated from `{workspace_root.as_posix()}` on {generated_at}.",
        "",
        "Scope: direct child git repositories under the workspace root. Line counts cover tracked code/config files and exclude common generated folders such as `.venv`, `build`, `dist`, `output`, `node_modules`, and `__pycache__`.",
        "",
        "## Summary",
        "",
        f"- Repositories: {len(repos)}",
        f"- Tracked code/config files: {total_code_files}",
        f"- Total lines: {total_lines}",
        f"- Non-empty lines: {total_nonempty_lines}",
        "",
        "## Repository Index",
        "",
        "| Repo | Domain | Kind | Package roots | Code roots | Docs | Tests | Files | Total lines | Non-empty |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]

    for repo in repos:
        package_root_names = [package.name for package in repo.package_roots]
        code_root_names = [code_root.name for code_root in repo.code_roots]
        lines.append(
            "| {name} | {domain} | {kind} | {packages} | {code_roots} | {docs} | {tests} | {files} | {total_lines} | {nonempty} |".format(
                name=repo.name,
                domain=repo.domain or "-",
                kind=repo.repo_kind,
                packages=_table_cell(package_root_names),
                code_roots=_table_cell(code_root_names),
                docs="Yes" if repo.has_docs else "No",
                tests="Yes" if repo.has_tests else "No",
                files=repo.tracked_code_files,
                total_lines=repo.tracked_total_lines,
                nonempty=repo.tracked_nonempty_lines,
            )
        )

    lines.extend(
        [
            "",
            "## Repository Details",
            "",
        ]
    )

    for repo in repos:
        lines.extend(
            [
                f"### {repo.name}",
                "",
                f"- Path: `{repo.path}`",
                f"- Domain: {repo.domain or 'Unclassified'}",
                f"- Kind: {repo.repo_kind}",
                f"- Summary: {repo.summary}",
                f"- Manifests: {_join_items(repo.manifests)}",
                f"- Root entry scripts: {_join_items(repo.root_scripts)}",
                f"- Support folders: docs={'Yes' if repo.has_docs else 'No'}, tests={'Yes' if repo.has_tests else 'No'}, examples={'Yes' if repo.has_examples else 'No'}",
                f"- Tracked code surface: {repo.tracked_code_files} files, {repo.tracked_total_lines} total lines, {repo.tracked_nonempty_lines} non-empty lines",
                "",
            ]
        )

        if repo.package_roots:
            lines.extend(
                [
                    "#### Package Roots",
                    "",
                    "| Package | Path | Immediate subpackages | Immediate modules | Recursive module count |",
                    "| --- | --- | --- | --- | ---: |",
                ]
            )
            for package in repo.package_roots:
                lines.append(
                    "| {name} | `{path}` | {subpackages} | {modules} | {count} |".format(
                        name=package.name,
                        path=package.path,
                        subpackages=_table_cell(package.immediate_subpackages),
                        modules=_table_cell(package.immediate_modules),
                        count=package.recursive_module_count,
                    )
                )
            lines.append("")
        else:
            lines.extend(
                [
                    "#### Package Roots",
                    "",
                    "No top-level Python package roots detected.",
                    "",
                ]
            )

        if repo.code_roots:
            lines.extend(
                [
                    "#### Non-package Code Roots",
                    "",
                    "| Root | Path | Code files | Dominant suffixes |",
                    "| --- | --- | ---: | --- |",
                ]
            )
            for code_root in repo.code_roots:
                lines.append(
                    "| {name} | `{path}` | {count} | {suffixes} |".format(
                        name=code_root.name,
                        path=code_root.path,
                        count=code_root.code_file_count,
                        suffixes=_table_cell(code_root.dominant_suffixes),
                    )
                )
            lines.append("")
        else:
            lines.extend(
                [
                    "#### Non-package Code Roots",
                    "",
                    "No additional top-level code roots detected.",
                    "",
                ]
            )

    if non_repo_entries:
        lines.extend(
            [
                "## Non-repository Code Folders",
                "",
                "These top-level folders contain code or manifests but are not standalone git repositories.",
                "",
                "| Folder | Path | Manifests | Package roots | Root scripts | Code files |",
                "| --- | --- | --- | --- | --- | ---: |",
            ]
        )
        for entry in non_repo_entries:
            lines.append(
                "| {name} | `{path}` | {manifests} | {packages} | {scripts} | {count} |".format(
                    name=entry.name,
                    path=entry.path,
                    manifests=_table_cell(entry.manifests),
                    packages=_table_cell(entry.package_roots),
                    scripts=_table_cell(entry.root_scripts),
                    count=entry.code_file_count,
                )
            )
        lines.append("")

    return "\n".join(lines)


def generate_inventory(workspace_root: Path, output_dir: Path) -> tuple[Path, Path]:
    workspace_root = workspace_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    domain_map = _parse_domain_map(workspace_root)
    repo_roots = sorted(
        [
            child
            for child in workspace_root.iterdir()
            if child.is_dir() and (child / ".git").exists()
        ],
        key=lambda path: path.name.lower(),
    )
    repos = [
        _collect_repo_inventory(workspace_root, repo_root, domain_map)
        for repo_root in repo_roots
    ]
    non_repo_entries = _collect_non_repo_inventory(
        workspace_root, {repo.name for repo in repos}
    )

    markdown_path = output_dir / "workspace_repo_inventory.md"
    json_path = output_dir / "workspace_repo_inventory.json"

    markdown_path.write_text(
        _render_markdown(workspace_root, repos, non_repo_entries), encoding="utf-8"
    )
    json_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": workspace_root.as_posix(),
        "repo_count": len(repos),
        "repos": [asdict(repo) for repo in repos],
        "non_repo_code_folders": [asdict(entry) for entry in non_repo_entries],
    }
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")
    return markdown_path, json_path


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_workspace_root = script_path.parents[2]
    default_output_dir = script_path.parents[1] / "docs"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=default_workspace_root,
        help="Workspace root to inventory. Defaults to the monorepo root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where the generated Markdown and JSON files are written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    markdown_path, json_path = generate_inventory(args.workspace_root, args.output_dir)
    print(f"Wrote {markdown_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
