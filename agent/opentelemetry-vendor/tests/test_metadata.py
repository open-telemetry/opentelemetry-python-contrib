# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from opentelemetry.vendor.download import unpack_wheels
from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import (
    VendoredPackage,
    copy_license_files,
    read_package,
    remove_dist_info,
)

from .helpers import make_wheel


def _read(tmp_path: Path, wheel: Path) -> VendoredPackage:
    destination = tmp_path / "_vendor"
    ((wheel, dist_info),) = unpack_wheels([wheel], destination).items()
    return read_package(wheel, dist_info)


def test_read_package(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        "Charset_Normalizer",
        "3.5.2",
        [
            "charset_normalizer/__init__.py",
            "charset_normalizer/cli/__init__.py",
            "six.py",
            "README.md",
            "wrapt-stubs/__init__.pyi",
            "__pycache__/six.cpython-312.pyc",
            "charset_normalizer-3.5.2.data/scripts/normalizer",
        ],
        metadata="License-Expression: MIT\nLicense-File: LICENSE\n",
    )

    package = _read(tmp_path, wheel)

    dist_info = tmp_path / "_vendor/Charset_Normalizer-3.5.2.dist-info"
    assert package == VendoredPackage(
        name="charset-normalizer",
        version="3.5.2",
        sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        license_expression="MIT",
        top_level_names=("charset_normalizer", "six"),
        license_files={"charset-normalizer.LICENSE": dist_info / "licenses/LICENSE"},
        dist_info=dist_info,
    )


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ("License-Expression: Apache-2.0\nLicense: MIT\n", "Apache-2.0"),
        ("License: MPL-2.0\n", "MPL-2.0"),
        (
            "License: line one\n line two\nClassifier: License :: OSI Approved :: MIT License\n",
            "MIT License",
        ),
        (
            "Classifier: License :: OSI Approved :: MIT License\n"
            "Classifier: Programming Language :: Python\n"
            "Classifier: License :: OSI Approved :: BSD License\n",
            "MIT License OR BSD License",
        ),
        ("", None),
    ],
)
def test_read_package_license_expression(tmp_path: Path, metadata: str, expected: str | None) -> None:
    wheel = make_wheel(tmp_path, "pkg", "1.0", ["pkg.py"], metadata=metadata)

    assert _read(tmp_path, wheel).license_expression == expected


def test_read_package_legacy_license_files(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        "pkg",
        "1.0",
        ["pkg.py"],
        licenses={
            "LICENSE.txt": "",
            "NOTICE": "",
            "licenses/vendor/COPYING": "",
            "entry_points.txt": "",
        },
    )

    package = _read(tmp_path, wheel)

    assert sorted(package.license_files) == [
        "pkg.LICENSE.txt",
        "pkg.NOTICE",
        "pkg.vendor.COPYING",
    ]


def test_read_package_license_file_in_dist_info_root(tmp_path: Path) -> None:
    wheel = make_wheel(
        tmp_path,
        "pkg",
        "1.0",
        ["pkg.py"],
        metadata="License-File: LICENSE.md\n",
        licenses={"LICENSE.md": ""},
    )

    assert sorted(_read(tmp_path, wheel).license_files) == ["pkg.LICENSE.md"]


def test_read_package_missing_declared_license_file(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "pkg", "1.0", ["pkg.py"], metadata="License-File: LICENSE\n", licenses={})

    with pytest.raises(VendorError, match="declares missing license file LICENSE"):
        _read(tmp_path, wheel)


def test_read_package_without_license_file(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path, "pkg", "1.0", ["pkg.py"], licenses={})

    with pytest.raises(VendorError, match="does not contain a license file"):
        _read(tmp_path, wheel)


def test_copy_license_files_and_remove_dist_info(tmp_path: Path) -> None:
    destination = tmp_path / "_vendor"
    wheel = make_wheel(tmp_path, "pkg", "1.0", ["pkg.py"], licenses={"licenses/LICENSE": "text"})
    package = _read(tmp_path, wheel)

    copy_license_files([package], destination)
    remove_dist_info([package])

    assert (destination / "pkg.LICENSE").read_text() == "text"
    assert sorted(p.name for p in destination.iterdir()) == ["pkg.LICENSE", "pkg.py"]


def test_copy_license_files_collision(tmp_path: Path) -> None:
    destination = tmp_path / "_vendor"
    package = _read(tmp_path, make_wheel(tmp_path, "pkg", "1.0", ["pkg.py"]))
    (destination / "pkg.LICENSE").write_text("existing")

    with pytest.raises(VendorError, match="already exists"):
        copy_license_files([package], destination)
