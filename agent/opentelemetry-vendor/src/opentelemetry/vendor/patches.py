# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Apply patch files to the vendored packages with ``git apply``."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import VendoredPackage

_GIT_DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)
_NEW_FILE_HEADER = re.compile(r"^\+\+\+ b/(\S+)$", re.MULTILINE)


@dataclass(frozen=True)
class VendorPatch:
    path: Path
    text: str
    files: tuple[str, ...]
    """POSIX paths, relative to the vendor destination, that the patch touches."""


def read_patches(paths: Collection[Path]) -> list[VendorPatch]:
    """Read patch files, in order, and the destination-relative files each one touches."""
    patches = []
    for path in paths:
        try:
            text = path.read_text()
        except FileNotFoundError as exc:
            raise VendorError(f"patch {path} does not exist") from exc
        files: set[str] = set()
        for old, new in _GIT_DIFF_HEADER.findall(text):
            files |= {old, new}
        if not files:
            files = set(_NEW_FILE_HEADER.findall(text))
        if not files:
            raise VendorError(f"patch {path} contains no changes")
        patches.append(VendorPatch(path=path, text=text, files=tuple(sorted(files))))
    return patches


def apply_patches(destination: Path, patches: Collection[VendorPatch]) -> None:
    """Apply ``patches`` in order to ``destination``; nothing is applied if any patch fails."""
    git = shutil.which("git")
    if git is None:
        raise VendorError("applying patches requires git on PATH")
    # Feed all patches to git as one input: `git apply` then applies them as a series (later patches see earlier
    # changes) and atomically. Given several patch files instead, git writes each file's changes before reading
    # the next one, and `--check` checks every file against the unpatched tree.
    patches = list(patches)
    error = _git_apply(git, destination, patches)
    if error is None:
        return
    # Find the first patch that breaks the series, to name it in the error.
    for index, patch in enumerate(patches):
        prefix_error = _git_apply(git, destination, patches[: index + 1], "--check")
        if prefix_error is not None:
            raise VendorError(f"patch {patch.path} does not apply:\n{prefix_error}")
    raise VendorError(f"patches do not apply:\n{error}")


def _git_apply(git: str, destination: Path, patches: Collection[VendorPatch], *args: str) -> str | None:
    """Run ``git apply`` on the concatenated ``patches``; return git's error output on failure."""
    series = "".join(patch.text if patch.text.endswith("\n") else f"{patch.text}\n" for patch in patches)
    # Inside a work tree, git reads patch paths relative to the repository root and silently skips files
    # outside the current directory. Stop repository discovery at the destination so paths are always
    # relative to it.
    env = os.environ | {"GIT_CEILING_DIRECTORIES": str(destination.resolve().parent)}
    result = subprocess.run(
        [git, "apply", *args],
        input=series,
        cwd=destination,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stderr.strip() if result.returncode != 0 else None


def patches_by_package(
    patches: Collection[VendorPatch], packages: Collection[VendoredPackage]
) -> dict[str, list[VendorPatch]]:
    """Map each package name to the patches that touch its files."""
    owners = {top_level: package.name for package in packages for top_level in package.top_level_names}
    result: dict[str, list[VendorPatch]] = {}
    for patch in patches:
        names: set[str] = set()
        for file in patch.files:
            top = PurePosixPath(file).parts[0].removesuffix(".py")
            if top not in owners:
                raise VendorError(f"patch {patch.path} touches {file}, which belongs to no vendored package")
            names.add(owners[top])
        for name in sorted(names):
            result.setdefault(name, []).append(patch)
    return result
