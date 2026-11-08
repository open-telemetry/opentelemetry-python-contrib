# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The ``sync`` command: (re)populate a project's vendor directory."""

from __future__ import annotations

import dataclasses
import re
import shutil
import tempfile
from collections.abc import Collection
from pathlib import Path

from opentelemetry.vendor import output
from opentelemetry.vendor.checks import check_vendored_tree
from opentelemetry.vendor.config import VendorConfig
from opentelemetry.vendor.download import download_wheels, unpack_wheels
from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import (
    VendoredPackage,
    copy_license_files,
    read_package,
    remove_dist_info,
)
from opentelemetry.vendor.patches import apply_patches, patches_by_package, read_patches
from opentelemetry.vendor.rewrite import RewriteResult, rewrite_imports
from opentelemetry.vendor.sbom import write_sbom


def clean_destination(destination: Path, protected_files: Collection[str]) -> list[Path]:
    """Remove everything in ``destination`` except top-level ``protected_files``.

    Returns the removed entries.
    """
    destination.mkdir(parents=True, exist_ok=True)
    removed = []
    for entry in sorted(destination.iterdir()):
        if entry.name in protected_files:
            continue
        _remove(entry, destination)
        removed.append(entry)
    return removed


def drop_paths(destination: Path, patterns: Collection[str]) -> list[Path]:
    """Remove files and directories in ``destination`` matching glob ``patterns``.

    Matches inside top-level ``*.dist-info`` directories are ignored, and a
    pattern that matches nothing is an error so stale config is noticed.
    Returns the removed paths.
    """
    matches: set[Path] = set()
    for pattern in patterns:
        matched = {
            path
            for path in destination.glob(pattern)
            if not path.relative_to(destination).parts[0].endswith(".dist-info")
        }
        if not matched:
            raise VendorError(f"drop pattern {pattern!r} matched nothing")
        matches |= matched

    removed = []
    for path in sorted(matches):
        # Already gone when an ancestor directory was dropped.
        if any(parent in matches for parent in path.parents):
            continue
        _remove(path, destination)
        removed.append(path)
    return removed


def clean(config: VendorConfig) -> None:
    """Empty ``config.destination``, keeping protected files."""
    removed = clean_destination(config.destination, config.protected_files)
    entries = output.plural(len(removed), "entry", "entries")
    output.step(f"Cleaned {_display(config.destination, config)} ({entries} removed)")


def sync(config: VendorConfig) -> list[VendoredPackage]:
    """Re-vendor ``config``'s requirements and return the vendored packages."""
    # Validate requirements before cleaning, so a bad file leaves the vendored tree intact.
    requirements = read_requirements(config.requirements)
    clean(config)
    try:
        return _populate(config, requirements)
    except BaseException:
        # Never leave a half-built tree (unpatched code, *.dist-info, ...) behind: back to the protected files only.
        clean_destination(config.destination, config.protected_files)
        raise


def _populate(config: VendorConfig, requirements: Collection[str]) -> list[VendoredPackage]:
    destination = config.destination
    with tempfile.TemporaryDirectory() as tmp:
        with output.status(f"Downloading {output.plural(len(requirements), 'requirement')}…"):
            wheels = download_wheels(config.requirements, config.python_version, Path(tmp))
        output.step(f"Downloaded {output.plural(len(wheels), 'wheel')}")

        dist_infos = unpack_wheels(wheels, destination)
        packages = [read_package(wheel, dist_info) for wheel, dist_info in dist_infos.items()]
        output.step(f"Unpacked {output.plural(len(packages), 'wheel')}")

    if config.drop:
        dropped = drop_paths(destination, config.drop)
        output.step(f"Dropped {output.plural(len(dropped), 'path')}")

    names = {name for package in packages for name in package.top_level_names}
    rewritten = rewrite_imports(destination, config.namespace, names)
    output.step(f"Rewrote {_rewrite_summary(rewritten)} in {output.plural(rewritten.files, 'file')}")
    patches = read_patches(config.patches)
    if patches:
        apply_patches(destination, patches)
        for patch in patches:
            output.detail(f"applied {_display(patch.path, config)}")
        output.step(f"Applied {output.plural(len(patches), 'patch', 'patches')}")

    for finding in check_vendored_tree(destination, names, config.allow):
        output.detail(f"allowed {finding.kind} {finding}")

    copy_license_files(packages, destination)
    license_count = sum(len(package.license_files) for package in packages)
    output.step(f"Copied {output.plural(license_count, 'license file')}")

    if config.sbom_file is not None:
        write_sbom(packages, config.sbom_file, patches_by_package(patches, packages))
        output.step(f"Wrote SBOM {_display(config.sbom_file, config)}")

    remove_dist_info(packages)
    output.package_table(packages)
    return packages


_REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _rewrite_summary(rewritten: RewriteResult) -> str:
    parts = [output.plural(rewritten.imports, "import")]
    if rewritten.loggers:
        parts.append(output.plural(rewritten.loggers, "logger name"))
    if rewritten.modules:
        parts.append(output.plural(rewritten.modules, "module name"))
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def check(config: VendorConfig) -> None:
    """Raise ``VendorError`` if the vendored files differ from what ``sync`` would produce.

    Syncs into a temporary directory and compares it, file by file, with ``config.destination``
    (and ``config.sbom_file`` when it lives outside the destination). Nothing in the project is changed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        expected = root / "destination"
        expected.mkdir()
        for name in config.protected_files:
            source = config.destination / name
            if source.is_dir():
                shutil.copytree(source, expected / name)
            elif source.exists():
                shutil.copy2(source, expected / name)
        sbom_file = None
        sbom_outside = config.sbom_file is not None and not config.sbom_file.is_relative_to(config.destination)
        if config.sbom_file is not None:
            sbom_file = (
                root / "sbom" / config.sbom_file.name
                if sbom_outside
                else expected / config.sbom_file.relative_to(config.destination)
            )
        sync(dataclasses.replace(config, destination=expected, sbom_file=sbom_file))

        differences = _diff_trees(config.destination, expected, config.protected_files)
        if sbom_outside and config.sbom_file is not None and sbom_file is not None:
            display = _display(config.sbom_file, config)
            if not config.sbom_file.exists():
                differences.append(f"+ {display}")
            elif config.sbom_file.read_bytes() != sbom_file.read_bytes():
                differences.append(f"~ {display}")

    if differences:
        lines = "\n".join(f"  {difference}" for difference in differences)
        raise VendorError(f"vendored files are out of date (run opentelemetry-vendor sync):\n{lines}")
    output.step("Vendored files are up to date")


def _diff_trees(actual: Path, expected: Path, protected_files: Collection[str]) -> list[str]:
    """Describe how ``actual`` must change to match ``expected``: ``+`` added, ``-`` removed, ``~`` changed."""
    actual_files = _tree_files(actual, protected_files)
    expected_files = _tree_files(expected, protected_files)
    differences = []
    for path in sorted(actual_files | expected_files):
        if path not in actual_files:
            differences.append(f"+ {path}")
        elif path not in expected_files:
            differences.append(f"- {path}")
        elif (actual / path).read_bytes() != (expected / path).read_bytes():
            differences.append(f"~ {path}")
    return differences


def _tree_files(root: Path, protected_files: Collection[str]) -> set[str]:
    if not root.is_dir():
        return set()
    files = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] in protected_files or "__pycache__" in relative.parts or path.is_dir():
            continue
        files.add(relative.as_posix())
    return files


def _remove(path: Path, destination: Path) -> None:
    display = path.relative_to(destination).as_posix()
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        display += "/"
    else:
        path.unlink()
    output.detail(f"removed {display}")


def _display(path: Path, config: VendorConfig) -> str:
    if path.is_relative_to(config.project_dir):
        return path.relative_to(config.project_dir).as_posix()
    return str(path)


def read_requirements(requirements: Path) -> list[str]:
    """Return the logical requirement lines of ``requirements``, each of which must be pinned by hash.

    Continuation lines (ending in ``\\``) are joined; comments and option lines are skipped.
    """
    try:
        text = requirements.read_text()
    except FileNotFoundError as exc:
        raise VendorError(f"requirements file {requirements} does not exist") from exc
    logical_lines: list[str] = []
    pending = ""
    for physical in text.splitlines():
        stripped = physical.split(" #", 1)[0].strip()
        # Like pip, a comment line ends a continuation.
        if stripped.endswith("\\") and not stripped.startswith("#"):
            pending += stripped[:-1] + " "
            continue
        logical_lines.append(pending + ("" if stripped.startswith("#") else stripped))
        pending = ""
    logical_lines.append(pending)
    lines = [" ".join(line.split()) for line in logical_lines if line.strip() and not line.strip().startswith("-")]
    for line in lines:
        if "--hash=" not in line:
            name = _REQUIREMENT_NAME.match(line)
            label = name.group() if name else line
            raise VendorError(
                f"requirement {label!r} in {requirements} has no --hash; compile it with --generate-hashes"
            )
    return lines
