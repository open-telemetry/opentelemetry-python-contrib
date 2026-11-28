# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from opentelemetry.vendor import native
from opentelemetry.vendor.config import load_config
from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import VendoredPackage
from opentelemetry.vendor.sbom import write_sbom

CURRENT_PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"
NATIVE_PATCH = """\
Rename the module.

diff --git a/setup.py b/setup.py
--- a/setup.py
+++ b/setup.py
@@ -1 +1 @@
-NAME = 'six._ext'
+NAME = 'pkg._vendor.six._ext'
"""
EXTENSION = "pkg/_vendor/six/_ext.abi3.so"


def _sdist(directory: Path, files: Mapping[str, str] | None = None) -> Path:
    path = directory / "six-1.0.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, content in (files or {"six-1.0/setup.py": "NAME = 'six._ext'\n"}).items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def _wheel(directory: Path, members: Mapping[str, bytes]) -> Path:
    path = directory / "six-1.0-cp310-abi3-plat.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


@pytest.fixture(name="native_project")
def fixture_native_project(project_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace('python-version = "3.10"', f'python-version = "{CURRENT_PYTHON}"')
        + '\n[tool.opentelemetry-vendor.native.six]\npatches = ["patches/native/six.patch"]\n'
        'build-requirements = "native-build-requirements.txt"\n'
    )
    (project_dir / "patches/native").mkdir(parents=True)
    (project_dir / "patches/native/six.patch").write_text(NATIVE_PATCH)
    (project_dir / "native-build-requirements.txt").write_text("setuptools==1.0 --hash=sha256:00\n")
    destination = project_dir / "src/pkg/_vendor"
    (destination / "six").mkdir()
    (destination / "six/__init__.py").write_text("")
    (destination / "six/moves.py").write_text("")
    package = VendoredPackage(
        name="six",
        version="1.0",
        sha256=hashlib.sha256(b"six").hexdigest(),
        license_expression="MIT",
        top_level_names=("six",),
        license_files={},
        dist_info=Path("six-1.0.dist-info"),
    )
    write_sbom([package], destination / "bom.cdx.json")

    sdists = tmp_path / "sdists"
    sdists.mkdir()
    monkeypatch.setattr(native, "download_sdist", lambda requirement, dest: _sdist(sdists))
    set_built_wheel(monkeypatch, tmp_path, {EXTENSION: b"\x00pkg._vendor.six._ext\x00google.protobuf.Any\x00"})
    return project_dir


def set_built_wheel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, members: Mapping[str, bytes]) -> None:
    wheels = tmp_path / "wheels"
    wheels.mkdir(exist_ok=True)

    def fake_build_wheel(source: Path, build_requirements: Path, work: Path) -> Path:
        # The native patch was applied to the extracted sdist before building.
        assert (source / "setup.py").read_text() == "NAME = 'pkg._vendor.six._ext'\n"
        assert build_requirements.name == "native-build-requirements.txt"
        return _wheel(wheels, members)

    monkeypatch.setattr(native, "_build_wheel", fake_build_wheel)


def test_build_native_and_clean(native_project: Path) -> None:
    config = load_config(native_project)
    sbom = config.destination / "bom.cdx.json"
    committed_sbom = sbom.read_bytes()

    written = native.build_native(config)

    extension = config.destination / "six/_ext.abi3.so"
    assert written == [extension]
    assert extension.read_bytes().startswith(b"\x00pkg._vendor.six._ext")
    [component] = json.loads(sbom.read_text())["components"]
    assert [patch["diff"]["text"]["content"] for patch in component["pedigree"]["patches"]] == [NATIVE_PATCH]
    assert component["properties"] == [
        {
            "name": "opentelemetry-vendor:native-sdist-sha256",
            "value": hashlib.sha256((native_project / "sdists/six-1.0.tar.gz").read_bytes()).hexdigest(),
        },
        {"name": "opentelemetry-vendor:native-extension", "value": "six/_ext.abi3.so"},
    ]
    assert json.loads(sbom.read_text())["serialNumber"] != json.loads(committed_sbom)["serialNumber"]

    native.clean_native(config)

    assert not extension.exists()
    assert sbom.read_bytes() == committed_sbom
    assert not (native_project / "build/opentelemetry-vendor").exists()


def test_build_native_creates_namespace_package_directories(
    native_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_built_wheel(monkeypatch, tmp_path, {"pkg/_vendor/six/_native/_ext.abi3.so": b""})
    config = load_config(native_project)

    native.build_native(config)
    assert (config.destination / "six/_native/_ext.abi3.so").exists()
    native.clean_native(config)

    assert not (config.destination / "six/_native").exists()
    assert (config.destination / "six/__init__.py").exists()


@pytest.mark.parametrize(
    ("members", "message"),
    [
        pytest.param({"pkg/_vendor/six/__init__.py": b""}, r"contains no extension under pkg/_vendor/", id="none"),
        pytest.param(
            {"pkg/_vendor/six/_ext.cpython-310-darwin.so": b""}, r"isn't a stable-ABI \(abi3\) extension", id="not-abi3"
        ),
        pytest.param(
            {EXTENSION: b"\x00six.moves\x00six.moves.urllib\x00"},
            r"native-module-names.*\n.*six/_ext\.abi3\.so:1: six\.moves",
            id="un-namespaced-module-name",
        ),
    ],
)
def test_build_native_errors_restore_tree(
    native_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, members: Mapping[str, bytes], message: str
) -> None:
    set_built_wheel(monkeypatch, tmp_path, members)
    config = load_config(native_project)
    committed_sbom = (config.destination / "bom.cdx.json").read_bytes()

    with pytest.raises(VendorError, match=message):
        native.build_native(config)

    assert not list(config.destination.rglob("*.so"))
    assert (config.destination / "bom.cdx.json").read_bytes() == committed_sbom
    assert not (native_project / "build/opentelemetry-vendor").exists()


def test_build_native_allowed_native_finding(
    native_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_built_wheel(monkeypatch, tmp_path, {EXTENSION: b"\x00six.moves\x00"})
    pyproject = native_project / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text() + '\n[tool.opentelemetry-vendor.allow]\nnative-module-names = ["six/_ext.abi3.so"]\n'
    )

    assert native.build_native(load_config(native_project))


def test_build_native_patch_does_not_apply(native_project: Path) -> None:
    (native_project / "patches/native/six.patch").write_text(NATIVE_PATCH.replace("-NAME = 'six._ext'", "-NAME = 'x'"))

    with pytest.raises(VendorError, match=r"six\.patch does not apply"):
        native.build_native(load_config(native_project))


def test_build_native_requirement_not_pinned(native_project: Path) -> None:
    pyproject = native_project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("native.six]", "native.Other_Pkg]"))

    with pytest.raises(VendorError, match=r"native build 'other-pkg' is not pinned in"):
        native.build_native(load_config(native_project))


def test_build_native_requires_synced_tree(native_project: Path) -> None:
    config = load_config(native_project)
    for path in sorted(config.destination.rglob("*"), reverse=True):
        if path.name not in ("requirements.txt", "bom.cdx.json"):
            path.unlink() if path.is_file() else path.rmdir()

    with pytest.raises(VendorError, match="has no vendored packages; run opentelemetry-vendor sync first"):
        native.build_native(config)


def test_build_native_unsafe_sdist(native_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    monkeypatch.setattr(
        native, "download_sdist", lambda requirement, dest: _sdist(unsafe, {"six-1.0/../../evil.py": "x"})
    )

    with pytest.raises(VendorError, match=r"contains an unsafe path: six-1\.0/\.\./\.\./evil\.py"):
        native.build_native(load_config(native_project))


def test_check_interpreter_version() -> None:
    with pytest.raises(VendorError, match=r"must run on CPython 2\.7 \(running CPython"):
        native._check_interpreter("2.7")


def test_check_interpreter_free_threaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native.sysconfig, "get_config_var", lambda name: 1 if name == "Py_GIL_DISABLED" else None)

    with pytest.raises(VendorError, match="can't run on a free-threaded interpreter"):
        native._check_interpreter(CURRENT_PYTHON)


def test_clean_native_without_build(native_project: Path) -> None:
    native.clean_native(load_config(native_project))
