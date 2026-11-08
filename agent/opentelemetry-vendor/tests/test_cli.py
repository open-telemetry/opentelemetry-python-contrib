# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from opentelemetry.vendor import sync as sync_module
from opentelemetry.vendor.cli import app
from opentelemetry.vendor.download import DownloadError

from .helpers import make_wheel

# A fixed width keeps rich from wrapping lines in the captured output.
runner = CliRunner(env={"COLUMNS": "200"})


def _fake_download(monkeypatch: pytest.MonkeyPatch, members: list[str] | None = None) -> None:
    def fake_download_wheels(requirements: Path, python_version: str, dest: Path) -> list[Path]:
        assert requirements.name == "requirements.txt"
        assert python_version == "3.10"
        return [
            make_wheel(
                dest,
                "six",
                "1.0",
                members or ["six.py"],
                metadata="License-Expression: MIT\n",
            )
        ]

    monkeypatch.setattr(sync_module, "download_wheels", fake_download_wheels)


def test_sync(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = project_dir / "src/pkg/_vendor"
    (destination / "stale.py").write_text("")
    _fake_download(monkeypatch)

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in destination.iterdir()) == [
        "bom.cdx.json",
        "requirements.txt",
        "six.LICENSE",
        "six.py",
    ]
    bom = json.loads((destination / "bom.cdx.json").read_text())
    assert [c["purl"] for c in bom["components"]] == ["pkg:pypi/six@1.0"]
    lines = result.output.splitlines()
    assert lines[:5] == [
        "✔ Cleaned src/pkg/_vendor (1 entry removed)",
        "✔ Downloaded 1 wheel",
        "✔ Unpacked 1 wheel",
        "✔ Copied 1 license file",
        "✔ Wrote SBOM src/pkg/_vendor/bom.cdx.json",
    ]
    assert lines[-1].split() == ["six", "1.0", "MIT", "six"]


def test_sync_drop(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'drop = ["*-stubs", "**/py.typed"]\n')
    _fake_download(monkeypatch, ["six/__init__.py", "six/py.typed", "six-stubs/__init__.pyi"])

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 0, result.output
    destination = project_dir / "src/pkg/_vendor"
    assert not (destination / "six-stubs").exists()
    assert not (destination / "six/py.typed").exists()
    assert (destination / "six/__init__.py").exists()
    assert "✔ Dropped 2 paths" in result.output


def test_sync_verbose(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project_dir / "src/pkg/_vendor/stale.py").write_text("")
    _fake_download(monkeypatch)

    result = runner.invoke(app, ["sync", str(project_dir), "--verbose"])

    assert result.exit_code == 0, result.output
    assert "removed " in result.output
    assert "stale.py" in result.output


def test_sync_quiet(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_download(monkeypatch)

    result = runner.invoke(app, ["sync", str(project_dir), "-q"])

    assert result.exit_code == 0, result.output
    assert result.output == ""


def test_sync_quiet_and_verbose(project_dir: Path) -> None:
    result = runner.invoke(app, ["sync", str(project_dir), "-q", "-v"])

    assert result.exit_code == 2
    assert "cannot be used together" in result.output


def test_sync_download_error(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download_wheels(requirements: Path, python_version: str, dest: Path) -> list[Path]:
        raise DownloadError("no wheel for foo")

    monkeypatch.setattr(sync_module, "download_wheels", fake_download_wheels)

    result = runner.invoke(app, ["sync", str(project_dir), "--quiet"])

    assert result.exit_code == 1
    # Errors are printed even with --quiet.
    assert result.output == "error: no wheel for foo\n"


def test_sync_missing_requirements(project_dir: Path) -> None:
    (project_dir / "src/pkg/_vendor/requirements.txt").unlink()

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 1
    assert "requirements.txt does not exist" in result.output


def test_sync_invalid_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")

    result = runner.invoke(app, ["sync", str(tmp_path)])

    assert result.exit_code == 1
    assert "no [tool.opentelemetry-vendor] table" in result.output


def test_sync_missing_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sync", str(tmp_path / "missing")])

    assert result.exit_code != 0


def test_clean(project_dir: Path) -> None:
    destination = project_dir / "src/pkg/_vendor"
    (destination / "requests").mkdir()
    (destination / "requests/__init__.py").write_text("")
    (destination / "requests.LICENSE").write_text("")
    (destination / "__init__.py").write_text("")
    (destination / "requirements.txt").write_text("requests==2.0\n")

    result = runner.invoke(app, ["clean", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in destination.iterdir()) == [
        "__init__.py",
        "requirements.txt",
    ]
    assert (destination / "requirements.txt").read_text() == "requests==2.0\n"
    assert result.output == "✔ Cleaned src/pkg/_vendor (2 entries removed)\n"


def test_clean_invalid_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")

    result = runner.invoke(app, ["clean", str(tmp_path)])

    assert result.exit_code == 1
    assert "error: " in result.output
    assert "no [tool.opentelemetry-vendor] table" in result.output
