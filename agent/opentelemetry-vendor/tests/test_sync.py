# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.sync import clean_destination, drop_paths


def test_clean_destination_keeps_protected_files(tmp_path: Path) -> None:
    destination = tmp_path / "_vendor"
    destination.mkdir()
    (destination / "__init__.py").write_text("")
    (destination / "requirements.txt").write_text("requests==1.0\n")
    (destination / "six.py").write_text("")
    package = destination / "requests"
    package.mkdir()
    (package / "__init__.py").write_text("")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("")
    (destination / "link").symlink_to(outside, target_is_directory=True)

    removed = clean_destination(destination, ["__init__.py", "requirements.txt"])

    assert sorted(p.name for p in destination.iterdir()) == [
        "__init__.py",
        "requirements.txt",
    ]
    assert (destination / "requirements.txt").read_text() == "requests==1.0\n"
    assert [p.name for p in removed] == ["link", "requests", "six.py"]
    # The symlink is removed without following it.
    assert (outside / "keep.txt").exists()


def test_clean_destination_creates_missing_directory(tmp_path: Path) -> None:
    destination = tmp_path / "a" / "_vendor"

    clean_destination(destination, [])

    assert destination.is_dir()


def _make_tree(root: Path, files: list[str]) -> None:
    for file in files:
        (root / file).parent.mkdir(parents=True, exist_ok=True)
        (root / file).write_text("")


def test_drop_paths(tmp_path: Path) -> None:
    _make_tree(
        tmp_path,
        [
            "wrapt/__init__.py",
            "wrapt/py.typed",
            "wrapt-stubs/__init__.pyi",
            "wrapt-stubs/py.typed",
            "google/protobuf/py.typed",
            "wrapt-2.0.dist-info/METADATA",
        ],
    )

    removed = drop_paths(tmp_path, ["*-stubs", "**/py.typed"])

    # wrapt-stubs/py.typed matches too, but is removed with its parent.
    assert [p.relative_to(tmp_path).as_posix() for p in removed] == [
        "google/protobuf/py.typed",
        "wrapt/py.typed",
        "wrapt-stubs",
    ]
    assert (tmp_path / "wrapt/__init__.py").exists()
    assert (tmp_path / "wrapt-2.0.dist-info/METADATA").exists()


def test_drop_paths_unmatched_pattern(tmp_path: Path) -> None:
    _make_tree(tmp_path, ["wrapt/__init__.py"])

    with pytest.raises(VendorError, match="'missing' matched nothing"):
        drop_paths(tmp_path, ["missing"])


def test_drop_paths_ignores_dist_info(tmp_path: Path) -> None:
    _make_tree(tmp_path, ["wrapt-2.0.dist-info/METADATA"])

    with pytest.raises(VendorError, match="matched nothing"):
        drop_paths(tmp_path, ["**/METADATA"])

    assert (tmp_path / "wrapt-2.0.dist-info/METADATA").exists()
