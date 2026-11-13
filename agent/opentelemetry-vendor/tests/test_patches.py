# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from opentelemetry.vendor import patches as patches_module
from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import VendoredPackage
from opentelemetry.vendor.patches import VendorPatch, apply_patches, patches_by_package, read_patches

FIRST = """\
Use the vendored module.

diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,2 +1,2 @@
-a = 1
+a = 2
 b = 1
"""

SECOND = """\
diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,2 +1,2 @@
 a = 2
-b = 1
+b = 2
"""

NEW_FILE = """\
diff --git a/six.py b/six.py
new file mode 100644
--- /dev/null
+++ b/six.py
@@ -0,0 +1 @@
+x = 1
"""

NOT_APPLICABLE = """\
diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,2 +1,2 @@
-a = 3
+a = 4
 b = 1
"""


def _write_patches(directory: Path, *texts: str) -> list[Path]:
    paths = []
    for index, text in enumerate(texts):
        path = directory / f"{index}.patch"
        path.write_text(text)
        paths.append(path)
    return paths


@pytest.fixture(name="destination")
def fixture_destination(tmp_path: Path) -> Path:
    destination = tmp_path / "_vendor"
    (destination / "pkg").mkdir(parents=True)
    (destination / "pkg/mod.py").write_text("a = 1\nb = 1\n")
    return destination


def test_read_patches(tmp_path: Path) -> None:
    paths = _write_patches(tmp_path, FIRST, NEW_FILE)

    patches = read_patches(paths)

    assert patches == [
        VendorPatch(path=paths[0], text=FIRST, files=("pkg/mod.py",)),
        VendorPatch(path=paths[1], text=NEW_FILE, files=("six.py",)),
    ]


def test_read_patches_plain_unified_diff(tmp_path: Path) -> None:
    paths = _write_patches(tmp_path, FIRST.split("diff --git a/pkg/mod.py b/pkg/mod.py\n", 1)[1])

    assert read_patches(paths)[0].files == ("pkg/mod.py",)


def test_read_patches_missing(tmp_path: Path) -> None:
    with pytest.raises(VendorError, match=r"patch .*missing\.patch does not exist"):
        read_patches([tmp_path / "missing.patch"])


@pytest.mark.parametrize("text", ["", "Only a description.\n"])
def test_read_patches_without_changes(tmp_path: Path, text: str) -> None:
    with pytest.raises(VendorError, match=r"patch .*0\.patch contains no changes"):
        read_patches(_write_patches(tmp_path, text))


def test_apply_patches_in_order(tmp_path: Path, destination: Path) -> None:
    patches = read_patches(_write_patches(tmp_path, FIRST, SECOND, NEW_FILE))

    apply_patches(destination, patches)

    assert (destination / "pkg/mod.py").read_text() == "a = 2\nb = 2\n"
    assert (destination / "six.py").read_text() == "x = 1\n"


def test_apply_patches_is_atomic(tmp_path: Path, destination: Path) -> None:
    patches = read_patches(_write_patches(tmp_path, NEW_FILE, NOT_APPLICABLE))

    with pytest.raises(VendorError, match=r"patch .*1\.patch does not apply:\n.*pkg/mod\.py"):
        apply_patches(destination, patches)

    assert (destination / "pkg/mod.py").read_text() == "a = 1\nb = 1\n"
    assert not (destination / "six.py").exists()


def test_apply_patches_requires_git(tmp_path: Path, destination: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patches_module.shutil, "which", lambda name: None)

    with pytest.raises(VendorError, match="applying patches requires git on PATH"):
        apply_patches(destination, read_patches(_write_patches(tmp_path, FIRST)))


def _package(name: str, *top_level_names: str) -> VendoredPackage:
    return VendoredPackage(
        name=name,
        version="1.0",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        license_expression=None,
        top_level_names=top_level_names,
        license_files={},
        dist_info=Path(f"{name}-1.0.dist-info"),
    )


def test_patches_by_package() -> None:
    package_patch = VendorPatch(path=Path("a.patch"), text="", files=("pkg/mod.py",))
    module_patch = VendorPatch(path=Path("b.patch"), text="", files=("six.py",))
    spanning_patch = VendorPatch(path=Path("c.patch"), text="", files=("pkg/other.py", "six.py"))
    packages = [_package("my-pkg", "pkg"), _package("six", "six"), _package("unpatched", "unpatched")]

    result = patches_by_package([package_patch, module_patch, spanning_patch], packages)

    assert result == {"my-pkg": [package_patch, spanning_patch], "six": [module_patch, spanning_patch]}


def test_patches_by_package_unknown_file() -> None:
    patch = VendorPatch(path=Path("a.patch"), text="", files=("other/mod.py",))

    with pytest.raises(
        VendorError, match=r"patch a\.patch touches other/mod\.py, which belongs to no vendored package"
    ):
        patches_by_package([patch], [_package("six", "six")])


def test_apply_patches_inside_git_work_tree(tmp_path: Path, destination: Path) -> None:
    # git would otherwise read patch paths relative to the repository root and silently skip them.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    patches = read_patches(_write_patches(tmp_path, FIRST))

    apply_patches(destination, patches)

    assert (destination / "pkg/mod.py").read_text() == "a = 2\nb = 1\n"
