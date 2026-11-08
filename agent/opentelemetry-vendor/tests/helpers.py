# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import zipfile
from collections.abc import Collection, Mapping
from pathlib import Path

DEFAULT_LICENSES: Mapping[str, str] = {"licenses/LICENSE": "license text"}


def make_zip(path: Path, members: Collection[str]) -> Path:
    """Create a zip archive at ``path`` containing empty ``members``."""
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, "")
    return path


def make_wheel(
    directory: Path,
    name: str,
    version: str,
    members: Collection[str] = (),
    *,
    metadata: str = "",
    licenses: Mapping[str, str] = DEFAULT_LICENSES,
    tag: str = "py3-none-any",
) -> Path:
    """Create a minimal but valid wheel with METADATA, RECORD and licenses.

    ``metadata`` is appended to the METADATA headers; ``licenses`` maps paths
    relative to the dist-info directory to their contents.
    """
    dist_info = f"{name.replace('-', '_')}-{version}.dist-info"
    files = {member: "" for member in members}
    files[f"{dist_info}/METADATA"] = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{metadata}"
    for relative, content in licenses.items():
        files[f"{dist_info}/{relative}"] = content
    record = f"{dist_info}/RECORD"
    files[record] = "".join(f"{path},,\n" for path in [*files, record])

    wheel = directory / f"{name.replace('-', '_')}-{version}-{tag}.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return wheel
