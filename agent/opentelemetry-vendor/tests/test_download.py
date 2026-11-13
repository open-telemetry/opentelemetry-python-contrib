# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from opentelemetry.vendor.download import (
    DownloadError,
    download_wheels,
    unpack_wheels,
)

from .helpers import make_wheel, make_zip


def _fake_run(
    returncode: int, wheel_names: Sequence[str], stderr: str = ""
) -> tuple[list[list[str]], Callable[..., subprocess.CompletedProcess[str]]]:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        dest = Path(args[args.index("--dest") + 1])
        for name in wheel_names:
            make_zip(dest / name, [])
        return subprocess.CompletedProcess(args, returncode, "", stderr)

    return calls, run


def test_download_wheels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requirements = tmp_path / "requirements.txt"
    calls, run = _fake_run(0, ["requests-2.0-py3-none-any.whl", "six-1.0-py2.py3-none-any.whl"])
    monkeypatch.setattr(subprocess, "run", run)

    wheels = download_wheels(requirements, "3.10", tmp_path)

    assert [w.name for w in wheels] == [
        "requests-2.0-py3-none-any.whl",
        "six-1.0-py2.py3-none-any.whl",
    ]
    assert calls == [
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
            "3.10",
            "--disable-pip-version-check",
            "--dest",
            str(tmp_path),
            "-r",
            str(requirements),
        ]
    ]


def test_download_wheels_pip_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, run = _fake_run(1, [], stderr="No matching distribution found for foo")
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DownloadError, match="No matching distribution found"):
        download_wheels(tmp_path / "requirements.txt", "3.10", tmp_path)


def test_download_wheels_rejects_platform_wheel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, run = _fake_run(0, ["wrapt-2.0-cp312-cp312-linux_x86_64.whl"])
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DownloadError, match="not a pure-Python wheel"):
        download_wheels(tmp_path / "requirements.txt", "3.10", tmp_path)


def test_unpack_wheels_shared_namespace(tmp_path: Path) -> None:
    destination = tmp_path / "_vendor"
    protobuf = make_wheel(tmp_path, "protobuf", "7.0", ["google/protobuf/__init__.py"])
    common_protos = make_wheel(tmp_path, "googleapis-common-protos", "1.0", ["google/api/__init__.py"])

    dist_infos = unpack_wheels([protobuf, common_protos], destination)

    assert dist_infos == {
        protobuf: destination / "protobuf-7.0.dist-info",
        common_protos: destination / "googleapis_common_protos-1.0.dist-info",
    }
    assert (destination / "google/protobuf/__init__.py").is_file()
    assert (destination / "google/api/__init__.py").is_file()
    assert (destination / "protobuf-7.0.dist-info/METADATA").is_file()


def test_unpack_wheels_refuses_to_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "_vendor"
    destination.mkdir()
    (destination / "requirements.txt").write_text("keep")
    wheel = make_wheel(tmp_path, "bad", "1.0", ["requirements.txt"])

    with pytest.raises(DownloadError, match="would overwrite"):
        unpack_wheels([wheel], destination)

    assert (destination / "requirements.txt").read_text() == "keep"


@pytest.mark.parametrize(
    "members",
    [
        ["bad/__init__.py"],
        ["a-1.0.dist-info/METADATA", "b-1.0.dist-info/METADATA"],
    ],
)
def test_unpack_wheels_requires_one_dist_info(tmp_path: Path, members: list[str]) -> None:
    wheel = make_zip(tmp_path / "bad-1.0-py3-none-any.whl", members)

    with pytest.raises(DownloadError, match="exactly one .dist-info"):
        unpack_wheels([wheel], tmp_path / "_vendor")
