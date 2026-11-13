# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from opentelemetry.vendor import native as native_module
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
    assert lines[:6] == [
        "✔ Cleaned src/pkg/_vendor (1 entry removed)",
        "✔ Downloaded 1 wheel",
        "✔ Unpacked 1 wheel",
        "✔ Rewrote 0 imports in 0 files",
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


def test_sync_patches(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project_dir / "patches").mkdir()
    (project_dir / "patches/six.patch").write_text(
        "diff --git a/six/__init__.py b/six/__init__.py\n"
        "--- a/six/__init__.py\n"
        "+++ b/six/__init__.py\n"
        "@@ -0,0 +1 @@\n"
        "+patched = True\n"
    )
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'patches = ["patches/six.patch"]\n')
    _fake_download(monkeypatch, ["six/__init__.py"])

    result = runner.invoke(app, ["sync", str(project_dir), "--verbose"])

    assert result.exit_code == 0, result.output
    destination = project_dir / "src/pkg/_vendor"
    assert (destination / "six/__init__.py").read_text() == "patched = True\n"
    assert "applied patches/six.patch" in result.output
    assert "✔ Applied 1 patch" in result.output
    bom = json.loads((destination / "bom.cdx.json").read_text())
    assert bom["components"][0]["pedigree"]["patches"][0]["type"] == "unofficial"


def test_sync_patch_does_not_apply(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project_dir / "patches").mkdir()
    (project_dir / "patches/six.patch").write_text(
        "diff --git a/six.py b/six.py\n--- a/six.py\n+++ b/six.py\n@@ -1 +1 @@\n-old\n+new\n"
    )
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'patches = ["patches/six.patch"]\n')
    _fake_download(monkeypatch)

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 1
    assert "six.patch does not apply:" in result.output


def test_sync_patch_adding_vendored_import(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project_dir / "patches").mkdir()
    (project_dir / "patches/six.patch").write_text(
        "diff --git a/six/__init__.py b/six/__init__.py\n"
        "--- a/six/__init__.py\n"
        "+++ b/six/__init__.py\n"
        "@@ -0,0 +1 @@\n"
        "+import six.moves\n"
    )
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'patches = ["patches/six.patch"]\n')
    _fake_download(monkeypatch, ["six/__init__.py"])

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 1
    assert "imports of vendored packages must be rewritten" in result.output
    assert "six/__init__.py:1: import six.moves" in result.output


def test_sync_requirement_without_hash_keeps_tree(project_dir: Path) -> None:
    destination = project_dir / "src/pkg/_vendor"
    (destination / "requirements.txt").write_text("six==1.0\n")
    (destination / "six.py").write_text("vendored = True\n")

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 1
    assert "requirement 'six'" in result.output
    assert "has no --hash" in result.output
    assert (destination / "six.py").read_text() == "vendored = True\n"


def _fake_stable_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Build the wheel once: like a real index, every download returns identical bytes.
    cache = tmp_path / "wheel-cache"
    cache.mkdir()
    wheel = make_wheel(cache, "six", "1.0", ["six/__init__.py"], metadata="License-Expression: MIT\n")

    def fake_download_wheels(requirements: Path, python_version: str, dest: Path) -> list[Path]:
        return [Path(shutil.copy(wheel, dest))]

    monkeypatch.setattr(sync_module, "download_wheels", fake_download_wheels)


def test_sync_check_up_to_date(project_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_stable_download(monkeypatch, tmp_path)
    assert runner.invoke(app, ["sync", str(project_dir)]).exit_code == 0

    result = runner.invoke(app, ["sync", "--check", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "✔ Vendored files are up to date"


def test_sync_check_out_of_date(project_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_stable_download(monkeypatch, tmp_path)
    assert runner.invoke(app, ["sync", str(project_dir)]).exit_code == 0
    destination = project_dir / "src/pkg/_vendor"
    (destination / "six/__init__.py").write_text("edited = True\n")
    (destination / "six.LICENSE").unlink()
    (destination / "extra.py").write_text("")
    (destination / "six/__pycache__").mkdir()
    (destination / "six/__pycache__/x.pyc").write_text("")

    result = runner.invoke(app, ["sync", "--check", str(project_dir)])

    assert result.exit_code == 1
    assert result.output.endswith(
        "error: vendored files are out of date (run opentelemetry-vendor sync):\n"
        "  - extra.py\n"
        "  + six.LICENSE\n"
        "  ~ six/__init__.py\n"
    )
    # --check never changes the project.
    assert (destination / "six/__init__.py").read_text() == "edited = True\n"
    assert (destination / "extra.py").exists()
    assert not (destination / "six.LICENSE").exists()


def test_sync_unused_license_files_entry(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + '[tool.opentelemetry-vendor.license-files]\nother = "LICENSE"\n')
    _fake_download(monkeypatch)

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 1
    assert "license-files entries ['other'] match no vendored distribution" in result.output


def test_sync_metadata_dir(project_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'metadata-dir = "_metadata"\n')
    cache = tmp_path / "wheel-cache"
    cache.mkdir()
    wheel = make_wheel(
        cache,
        "six",
        "1.0",
        ["six/__init__.py", "six/plugin.py"],
        metadata="License-Expression: MIT\n",
        entry_points="[console_scripts]\nsix = six:main\n\n[six_plugins]\nplugin = six.plugin:Plugin\n",
    )

    def fake_download_wheels(requirements: Path, python_version: str, dest: Path) -> list[Path]:
        return [Path(shutil.copy(wheel, dest))]

    monkeypatch.setattr(sync_module, "download_wheels", fake_download_wheels)

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "✔ Wrote metadata to src/pkg/_vendor/_metadata (1 entry point)" in result.output.splitlines()
    dist_info = project_dir / "src/pkg/_vendor/_metadata/six-1.0.dist-info"
    assert (dist_info / "entry_points.txt").read_text() == "[six_plugins]\nplugin = pkg._vendor.six.plugin:Plugin\n"
    assert not (project_dir / "src/pkg/_vendor/six-1.0.dist-info").exists()

    assert runner.invoke(app, ["sync", "--check", str(project_dir)]).exit_code == 0
    (dist_info / "entry_points.txt").write_text("")
    result = runner.invoke(app, ["sync", "--check", str(project_dir)])
    assert result.exit_code == 1
    assert result.output.endswith("  ~ _metadata/six-1.0.dist-info/entry_points.txt\n")


def test_sync_check_sbom_outside_destination(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("src/pkg/_vendor/bom.cdx.json", "bom.cdx.json"))
    _fake_stable_download(monkeypatch, tmp_path)
    assert runner.invoke(app, ["sync", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["sync", "--check", str(project_dir)]).exit_code == 0
    (project_dir / "bom.cdx.json").write_text("{}")

    result = runner.invoke(app, ["sync", "--check", str(project_dir)])

    assert result.exit_code == 1
    assert "  ~ bom.cdx.json\n" in result.output


def test_sync_failure_cleans_destination(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project_dir / "patches").mkdir()
    (project_dir / "patches/six.patch").write_text(
        "diff --git a/six.py b/six.py\n--- a/six.py\n+++ b/six.py\n@@ -1 +1 @@\n-old\n+new\n"
    )
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + 'patches = ["patches/six.patch"]\n')
    _fake_download(monkeypatch)

    result = runner.invoke(app, ["sync", str(project_dir)])

    assert result.exit_code == 1
    assert "does not apply" in result.output
    # Neither the unpacked package nor its *.dist-info is left behind.
    assert sorted(p.name for p in (project_dir / "src/pkg/_vendor").iterdir()) == ["requirements.txt"]


def test_build_native_cli(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(native_module, "build_native", lambda config: calls.append(("build", config.project_dir)))
    monkeypatch.setattr(native_module, "clean_native", lambda config: calls.append(("clean", config.project_dir)))

    assert runner.invoke(app, ["build-native", str(project_dir)]).exit_code == 0
    assert runner.invoke(app, ["build-native", "--clean", str(project_dir)]).exit_code == 0

    assert calls == [("build", project_dir.resolve()), ("clean", project_dir.resolve())]


def test_build_native_cli_error(project_dir: Path) -> None:
    result = runner.invoke(app, ["build-native", str(project_dir)])

    assert result.exit_code == 1
    assert result.output.startswith("error: ")
