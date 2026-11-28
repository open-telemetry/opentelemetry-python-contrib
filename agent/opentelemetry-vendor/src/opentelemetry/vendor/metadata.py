# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Collect metadata from unpacked ``*.dist-info`` directories."""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from importlib.metadata import PathDistribution
from pathlib import Path

from opentelemetry.vendor.errors import VendorError

_LICENSE_FILE_PATTERN = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)
_LICENSE_CLASSIFIER_PREFIX = "License :: "


@dataclass(frozen=True)
class VendoredPackage:
    name: str
    """Canonical (PEP 503) distribution name."""
    version: str
    sha256: str
    """SHA-256 of the downloaded wheel."""
    license_expression: str | None
    top_level_names: Collection[str]
    """Top-level importable module and package names."""
    license_files: Mapping[str, Path]
    """Vendored license file name -> source file inside ``dist_info``."""
    dist_info: Path


def read_package(wheel: Path, dist_info: Path, license_file: Path | None = None) -> VendoredPackage:
    """Read the metadata needed for vendoring from an unpacked dist-info.

    ``license_file`` stands in for a wheel that ships no license file of its own.
    """
    distribution = PathDistribution(dist_info)
    metadata = distribution.metadata
    name = canonicalize_name(metadata["Name"])
    return VendoredPackage(
        name=name,
        version=metadata["Version"],
        sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        license_expression=_license_expression(
            metadata.get("License-Expression"),
            metadata.get("License"),
            metadata.get_all("Classifier") or [],
        ),
        top_level_names=_top_level_names(distribution, dist_info),
        license_files=_license_files(name, dist_info, metadata.get_all("License-File") or [], license_file),
        dist_info=dist_info,
    )


def copy_license_files(packages: Collection[VendoredPackage], destination: Path) -> None:
    """Copy every package's license files into ``destination``."""
    for package in packages:
        for target_name, source in package.license_files.items():
            target = destination / target_name
            if target.exists():
                raise VendorError(f"license file {target} for {package.name} already exists")
            shutil.copyfile(source, target)


def remove_dist_info(packages: Collection[VendoredPackage]) -> None:
    for package in packages:
        shutil.rmtree(package.dist_info)


def canonicalize_name(name: str) -> str:
    """Normalize a distribution name as specified by PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _license_expression(expression: str | None, license_field: str | None, classifiers: Collection[str]) -> str | None:
    if expression:
        return expression.strip()
    # The legacy License field sometimes holds the full license text.
    if license_field and "\n" not in license_field.strip():
        return license_field.strip()
    names = [
        classifier.rsplit(" :: ", 1)[-1]
        for classifier in classifiers
        if classifier.startswith(_LICENSE_CLASSIFIER_PREFIX)
    ]
    return " OR ".join(names) if names else None


def _top_level_names(distribution: PathDistribution, dist_info: Path) -> tuple[str, ...]:
    files = distribution.files
    if files is None:
        raise VendorError(f"{dist_info.name} has no RECORD file")
    names: set[str] = set()
    for file in files:
        top = file.parts[0]
        if top == ".." or top.endswith((".dist-info", ".data")):
            continue
        if top == "__pycache__":
            continue
        if len(file.parts) == 1:
            if not top.endswith(".py"):
                continue
            top = top.removesuffix(".py")
        if top.isidentifier():
            names.add(top)
    return tuple(sorted(names))


def _license_files(name: str, dist_info: Path, declared: Collection[str], license_file: Path | None) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    if declared:
        # PEP 639 puts License-File paths under .dist-info/licenses/; older
        # tools put them directly in .dist-info/.
        for relative in declared:
            for base in (dist_info / "licenses", dist_info):
                if (base / relative).is_file():
                    sources[relative] = base / relative
                    break
            else:
                raise VendorError(f"{dist_info.name} declares missing license file {relative}")
    else:
        for path in sorted(dist_info.rglob("*")):
            if path.is_file() and _LICENSE_FILE_PATTERN.match(path.name):
                base = dist_info / "licenses"
                if not path.is_relative_to(base):
                    base = dist_info
                sources[path.relative_to(base).as_posix()] = path
    if sources and license_file is not None:
        raise VendorError(f"{dist_info.name} contains a license file; remove its license-files entry")
    if not sources and license_file is not None:
        if not license_file.is_file():
            raise VendorError(f"license file {license_file} for {name} does not exist")
        sources[license_file.name] = license_file
    if not sources:
        raise VendorError(
            f"{dist_info.name} does not contain a license file; add one under [tool.opentelemetry-vendor.license-files]"
        )
    return {f"{name}.{relative.replace('/', '.')}": path for relative, path in sources.items()}
