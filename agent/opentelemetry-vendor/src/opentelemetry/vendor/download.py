# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Download pure-Python wheels and unpack them into the vendor directory."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from collections.abc import Collection
from pathlib import Path

from opentelemetry.vendor import output
from opentelemetry.vendor.errors import VendorError


class DownloadError(VendorError):
    """Raised when downloading or unpacking vendored packages fails."""


def download_wheels(requirements: Path, python_version: str, dest: Path) -> list[Path]:
    """Download a pure-Python wheel for each requirement, without dependencies.

    Only ``py3-none-any`` style wheels are accepted so compiled extensions
    (which cannot be rewritten into the vendor namespace) are never vendored.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--no-deps",
            "--only-binary=:all:",
            "--platform",
            "any",
            "--implementation",
            "py",
            "--abi",
            "none",
            "--python-version",
            python_version,
            "--disable-pip-version-check",
            "--dest",
            str(dest),
            "-r",
            str(requirements),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DownloadError(
            f"pip download failed (exit code {result.returncode}). Every "
            "requirement must have a pure-Python (py3-none-any) wheel.\n"
            f"{result.stderr.strip()}"
        )
    output.detail(result.stdout.strip())
    wheels = sorted(dest.glob("*.whl"))
    for wheel in wheels:
        _check_pure_python(wheel)
    return wheels


def _check_pure_python(wheel: Path) -> None:
    # Wheel filenames end in {python tag}-{abi tag}-{platform tag}.whl
    _, abi_tag, platform_tag = wheel.stem.rsplit("-", 3)[-3:]
    if abi_tag != "none" or platform_tag != "any":
        raise DownloadError(f"{wheel.name} is not a pure-Python wheel")


def unpack_wheels(wheels: Collection[Path], destination: Path) -> dict[Path, Path]:
    """Extract ``wheels`` into ``destination``, refusing to overwrite files.

    Returns a mapping of each wheel to its unpacked ``*.dist-info`` directory.
    """
    destination.mkdir(parents=True, exist_ok=True)
    dist_infos: dict[Path, Path] = {}
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            dist_info_names = {
                top for top in (name.split("/", 1)[0] for name in archive.namelist()) if top.endswith(".dist-info")
            }
            if len(dist_info_names) != 1:
                raise DownloadError(
                    f"{wheel.name} must contain exactly one .dist-info directory, found {sorted(dist_info_names)}"
                )
            dist_infos[wheel] = destination / dist_info_names.pop()
            for member in archive.infolist():
                target = destination / member.filename
                if not member.is_dir() and target.exists():
                    raise DownloadError(f"{wheel.name} would overwrite {target}")
                archive.extract(member, destination)
    return dist_infos
