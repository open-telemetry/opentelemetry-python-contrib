# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The ``sync`` command: (re)populate a project's vendor directory."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Collection
from pathlib import Path

from opentelemetry.vendor import output
from opentelemetry.vendor.config import VendorConfig
from opentelemetry.vendor.download import download_wheels, unpack_wheels
from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import (
    VendoredPackage,
    copy_license_files,
    read_package,
    remove_dist_info,
)
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
    destination = config.destination
    clean(config)

    with tempfile.TemporaryDirectory() as tmp:
        count = _count_requirements(config.requirements)
        with output.status(f"Downloading {output.plural(count, 'requirement')}…"):
            wheels = download_wheels(config.requirements, config.python_version, Path(tmp))
        output.step(f"Downloaded {output.plural(len(wheels), 'wheel')}")

        dist_infos = unpack_wheels(wheels, destination)
        packages = [read_package(wheel, dist_info) for wheel, dist_info in dist_infos.items()]
        output.step(f"Unpacked {output.plural(len(packages), 'wheel')}")

    if config.drop:
        dropped = drop_paths(destination, config.drop)
        output.step(f"Dropped {output.plural(len(dropped), 'path')}")

    copy_license_files(packages, destination)
    license_count = sum(len(package.license_files) for package in packages)
    output.step(f"Copied {output.plural(license_count, 'license file')}")

    if config.sbom_file is not None:
        write_sbom(packages, config.sbom_file)
        output.step(f"Wrote SBOM {_display(config.sbom_file, config)}")

    remove_dist_info(packages)
    output.package_table(packages)
    return packages


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


def _count_requirements(requirements: Path) -> int:
    try:
        text = requirements.read_text()
    except FileNotFoundError as exc:
        raise VendorError(f"requirements file {requirements} does not exist") from exc
    lines = (line.strip() for line in text.splitlines())
    return sum(1 for line in lines if line and not line.startswith(("#", "-")))
