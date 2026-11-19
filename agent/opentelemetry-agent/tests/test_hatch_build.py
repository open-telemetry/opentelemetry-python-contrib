# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("hatchling")

_SPEC = importlib.util.spec_from_file_location("hatch_build", Path(__file__).parents[1] / "hatch_build.py")
assert _SPEC is not None and _SPEC.loader is not None
hatch_build = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hatch_build)


def _initialize(root: Path, target_name: str = "wheel") -> dict[str, Any]:
    hook = hatch_build.CustomBuildHook(str(root), {"abi3-tag": "cp310"}, None, None, str(root), target_name)
    build_data: dict[str, Any] = {"artifacts": [], "pure_python": True}
    hook.initialize("1.0", build_data)
    return build_data


def _vendor_file(root: Path, relative: str) -> None:
    path = root / "src/opentelemetry/agent/_vendor" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_pure_without_extensions(tmp_path: Path) -> None:
    _vendor_file(tmp_path, "google/protobuf/message.py")

    assert _initialize(tmp_path) == {"artifacts": [], "pure_python": True}


def test_abi3_extension_makes_platform_wheel(tmp_path: Path) -> None:
    _vendor_file(tmp_path, "google/_upb/_message.abi3.so")

    build_data = _initialize(tmp_path)

    platform = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    assert build_data == {
        "artifacts": ["src/opentelemetry/agent/_vendor/google/_upb/_message.abi3.so"],
        "pure_python": False,
        "tag": f"cp310-abi3-{platform}",
    }


def test_non_abi3_extension_is_rejected(tmp_path: Path) -> None:
    _vendor_file(tmp_path, "google/_upb/_message.cpython-312-darwin.so")

    with pytest.raises(ValueError, match="must use the stable ABI"):
        _initialize(tmp_path)


def test_sdist_target_is_untouched(tmp_path: Path) -> None:
    _vendor_file(tmp_path, "google/_upb/_message.abi3.so")

    assert _initialize(tmp_path, "sdist") == {"artifacts": [], "pure_python": True}
