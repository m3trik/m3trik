"""
Shared setup utilities for m3trik packages.

This module provides helper functions used by setup.py files. It's designed to work
in isolated build environments where packages may not be installed.

Key features:
- Reads version from __init__.py without importing the package
- Extracts description from README markers
- Reads requirements.txt and filters optional dependencies
- Returns data_files for non-Python assets
"""

import os
import re
from pathlib import Path
from typing import Optional


def get_version(init_path: Path) -> str:
    """Extract __version__ from __init__.py without importing.

    Parameters:
        init_path: Path to the __init__.py file

    Returns:
        Version string (e.g., '0.7.34')
    """
    content = init_path.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError(f"Could not find __version__ in {init_path}")
    return match.group(1)


def get_description(readme_path: Path, fallback: str = "") -> str:
    """Extract short description from README using HTML comment markers.

    Looks for:
        <!-- short_description_start -->..<!-- short_description_end -->

    Parameters:
        readme_path: Path to README.md
        fallback: Default if markers not found

    Returns:
        Description string
    """
    if not readme_path.exists():
        return fallback

    content = readme_path.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- short_description_start -->(.+?)<!-- short_description_end -->",
        content,
        re.DOTALL,
    )
    return match.group(1).strip() if match else fallback


def get_long_description(readme_path: Path) -> str:
    """Read full README content.

    Parameters:
        readme_path: Path to README.md

    Returns:
        Full README content or empty string
    """
    if not readme_path.exists():
        return ""
    return readme_path.read_text(encoding="utf-8")


def get_requirements(req_path: Path, exclude: Optional[list[str]] = None) -> list[str]:
    """Parse requirements.txt and filter out optional dependencies.

    Parameters:
        req_path: Path to requirements.txt
        exclude: Package names to exclude (optional/system dependencies)

    Returns:
        List of requirement strings like ['package==1.0.0']
    """
    if not req_path.exists():
        return []

    exclude = set(exclude or [])
    requirements = []

    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Extract package name (before ==, >=, etc.)
        match = re.match(r"([a-zA-Z0-9_-]+)", line)
        if match:
            pkg_name = match.group(1)
            if pkg_name not in exclude:
                requirements.append(line)

    return requirements


def get_data_files(
    package_dir: Path, package_name: str, exclude_extensions: Optional[list[str]] = None
) -> list[tuple[str, list[str]]]:
    """Find non-Python data files to include in the package.

    Parameters:
        package_dir: Path to the package directory
        package_name: Name of the package (for install paths)
        exclude_extensions: File extensions to exclude (e.g., ['*.py', '*.pyc'])

    Returns:
        List of (install_dir, [files]) tuples for data_files parameter
    """
    exclude_extensions = exclude_extensions or ["*.py", "*.pyc", "*.json", "*.bak"]
    exclude_patterns = set(ext.lstrip("*.") for ext in exclude_extensions)

    data_files = []
    pkg_path = package_dir / package_name

    if not pkg_path.exists():
        return []

    for root, dirs, files in os.walk(pkg_path):
        # Skip __pycache__ and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]

        # Filter files
        valid_files = []
        for f in files:
            ext = f.split(".")[-1] if "." in f else ""
            if ext not in exclude_patterns and not f.startswith("."):
                valid_files.append(os.path.join(root, f))

        if valid_files:
            # Calculate relative install path
            rel_root = os.path.relpath(root, package_dir)
            data_files.append((rel_root, valid_files))

    return data_files
