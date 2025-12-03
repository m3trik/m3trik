"""
Centralized configuration for all m3trik packages.

This config is the single source of truth for:
- Package metadata (name, license, PyPI name)
- Dependency chain and ordering
- Build exclusions
- Version locations

Used by:
- publish_chain.py - for validation and publishing
- update_wheel.cmd - for single-package publishing
- GitHub Actions workflows - for CI/CD
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PackageConfig:
    """Configuration for a single package."""

    name: str
    """Package directory and import name (e.g., 'pythontk')"""

    license: str = "MIT"
    """License type for classifiers"""

    pypi_name: Optional[str] = None
    """PyPI package name if different from directory (e.g., 'tentacletk')"""

    depends_on: list[str] = field(default_factory=list)
    """List of internal package dependencies (must be published first)"""

    exclude_deps: list[str] = field(default_factory=list)
    """Dependencies to exclude from install_requires (optional/system deps)"""

    exclude_packages: list[str] = field(default_factory=list)
    """Packages to exclude from find_packages()"""

    version_files: list[str] = field(default_factory=list)
    """Files containing version strings to bump (relative to package root)"""

    @property
    def pypi(self) -> str:
        """Get the PyPI package name."""
        return self.pypi_name or self.name

    @property
    def default_version_files(self) -> list[str]:
        """Default version file locations."""
        return [
            f"{self.name}/__init__.py",
            "docs/README.md",
        ]


# =============================================================================
# Package Configurations
# =============================================================================

PACKAGES = {
    "pythontk": PackageConfig(
        name="pythontk",
        license="MIT",
        depends_on=[],  # Root package - no internal dependencies
        exclude_deps=["Pillow", "numpy"],
    ),
    "uitk": PackageConfig(
        name="uitk",
        license="LGPLv3",
        depends_on=["pythontk"],
        exclude_deps=["qtpy"],
    ),
    "mayatk": PackageConfig(
        name="mayatk",
        license="MIT",
        depends_on=["pythontk", "uitk"],
        exclude_deps=["pymel", "qtpy"],
        exclude_packages=["pymel", "pymel.*"],
    ),
    "tentacle": PackageConfig(
        name="tentacle",
        license="LGPLv3",
        pypi_name="tentacletk",
        depends_on=["pythontk", "uitk", "mayatk"],
        exclude_deps=["Pillow", "qtpy", "numpy", "shiboken6", "pymel"],
    ),
}

# Publish order (topologically sorted based on depends_on)
PUBLISH_ORDER = ["pythontk", "uitk", "mayatk", "tentacle"]

# Root directory for all packages
ROOT = Path(r"O:\Cloud\Code\_scripts")


def get_config(name: str) -> PackageConfig:
    """Get package configuration by name."""
    if name not in PACKAGES:
        raise ValueError(f"Unknown package: {name}. Available: {list(PACKAGES.keys())}")
    return PACKAGES[name]


def get_package_path(name: str) -> Path:
    """Get the filesystem path to a package."""
    return ROOT / name


def validate_chain() -> list[str]:
    """Validate that dependency chain is consistent. Returns list of errors."""
    errors = []

    for i, pkg_name in enumerate(PUBLISH_ORDER):
        config = PACKAGES[pkg_name]

        # Check all dependencies come before this package in order
        for dep in config.depends_on:
            if dep not in PUBLISH_ORDER[:i]:
                errors.append(
                    f"{pkg_name} depends on {dep} but {dep} comes later in PUBLISH_ORDER"
                )

    return errors


# Validate on import
_errors = validate_chain()
if _errors:
    raise RuntimeError(f"Package config validation failed: {_errors}")


# =============================================================================
# Classifier mappings
# =============================================================================

LICENSE_CLASSIFIERS = {
    "MIT": "License :: OSI Approved :: MIT License",
    "LGPLv3": "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
}


def get_classifiers(config: PackageConfig) -> list[str]:
    """Get Python classifiers for a package."""
    return [
        "Programming Language :: Python :: 3",
        LICENSE_CLASSIFIERS.get(config.license, f"License :: {config.license}"),
        "Operating System :: OS Independent",
    ]
