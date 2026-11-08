# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from opentelemetry.vendor.config import ConfigError, load_config


def test_load_config(project_dir: Path) -> None:
    config = load_config(project_dir)

    root = project_dir.resolve()
    assert config.project_dir == root
    assert config.destination == root / "src/pkg/_vendor"
    assert config.requirements == root / "src/pkg/_vendor/requirements.txt"
    assert config.namespace == "pkg._vendor"
    assert config.python_version == "3.10"
    assert tuple(config.protected_files) == ("__init__.py", "requirements.txt")
    assert config.sbom_file == root / "src/pkg/_vendor/bom.cdx.json"


def test_load_config_optional_keys(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.opentelemetry-vendor]\n"
        'destination = "_vendor"\n'
        'requirements = "requirements.txt"\n'
        'namespace = "_vendor"\n'
    )

    config = load_config(tmp_path)

    assert tuple(config.protected_files) == ()
    assert tuple(config.drop) == ()
    assert config.allow == {}
    assert config.python_version == (f"{sys.version_info.major}.{sys.version_info.minor}")
    assert tuple(config.patches) == ()
    assert config.sbom_file is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("[project]\nname = 'x'\n", r"no \[tool.opentelemetry-vendor\] table"),
        (
            '[tool.opentelemetry-vendor]\nrequirements = "r.txt"\nnamespace = "v"\n',
            "missing required key 'destination'",
        ),
        (
            '[tool.opentelemetry-vendor]\ndestination = 1\nrequirements = "r.txt"\nnamespace = "v"\n',
            "'destination' must be a non-empty string",
        ),
        (
            '[tool.opentelemetry-vendor]\ndestination = "v"\n'
            'requirements = "r.txt"\nnamespace = "v"\nprotected-files = "x"\n',
            "'protected-files' must be a list of strings",
        ),
        (
            '[tool.opentelemetry-vendor]\ndestination = "v"\n'
            'requirements = "r.txt"\nnamespace = "v"\npatches = "a.patch"\n',
            "'patches' must be a list of strings",
        ),
        (
            '[tool.opentelemetry-vendor]\ndestination = "../v"\nrequirements = "r.txt"\nnamespace = "v"\n',
            "'destination' must be a directory inside",
        ),
        (
            '[tool.opentelemetry-vendor]\ndestination = "."\nrequirements = "r.txt"\nnamespace = "v"\n',
            "'destination' must be a directory inside",
        ),
        ("not toml [", "is not valid TOML"),
    ],
)
def test_load_config_invalid(tmp_path: Path, content: str, message: str) -> None:
    (tmp_path / "pyproject.toml").write_text(content)

    with pytest.raises(ConfigError, match=message):
        load_config(tmp_path)


def test_load_config_patches(project_dir: Path) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'patches = ["patches/b.patch", "patches/a.patch"]\n')

    root = project_dir.resolve()
    assert tuple(load_config(project_dir).patches) == (root / "patches/b.patch", root / "patches/a.patch")


def test_load_config_missing_pyproject(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        load_config(tmp_path)


def test_load_config_drop(project_dir: Path) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'drop = ["wrapt-stubs", "**/py.typed"]\n')

    assert tuple(load_config(project_dir).drop) == ("wrapt-stubs", "**/py.typed")


@pytest.mark.parametrize("entry", ["", "/abs", "../outside", "a/../../b"])
def test_load_config_invalid_drop(project_dir: Path, entry: str) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + f"drop = [{entry!r}]\n")

    with pytest.raises(ConfigError, match="'drop' entry .* must be relative to destination"):
        load_config(project_dir)


def test_load_config_allow(project_dir: Path) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text()
        + '[tool.opentelemetry-vendor.allow]\ndynamic-imports = ["a.py"]\nside-effects = ["b/c.py", "d.py"]\n'
        + 'module-names = ["e_pb2.py"]\n'
    )

    assert load_config(project_dir).allow == {
        "dynamic-imports": ("a.py",),
        "side-effects": ("b/c.py", "d.py"),
        "module-names": ("e_pb2.py",),
    }


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            '[tool.opentelemetry-vendor.allow]\ndynamic-imports = ["../a.py"]\n',
            "'dynamic-imports' entry '../a.py' must be relative",
        ),
        ('[tool.opentelemetry-vendor.allow]\nside-effects = "a.py"\n', "'side-effects' must be a list of strings"),
        (
            '[tool.opentelemetry-vendor.allow]\nimports = ["a.py"]\n',
            r"unknown \[tool.opentelemetry-vendor.allow\] keys \['imports'\]",
        ),
        ('allow = ["a.py"]\n', r"'allow' must be a table"),
    ],
)
def test_load_config_invalid_allow(project_dir: Path, content: str, message: str) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + content)

    with pytest.raises(ConfigError, match=message):
        load_config(project_dir)


def test_load_config_moved_allow_dynamic_imports(project_dir: Path) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'allow-dynamic-imports = ["a.py"]\n')

    with pytest.raises(
        ConfigError, match=r"'allow-dynamic-imports' moved to \[tool.opentelemetry-vendor.allow\] dynamic-imports"
    ):
        load_config(project_dir)
