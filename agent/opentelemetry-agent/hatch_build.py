# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Tag the wheel as platform-specific when native extensions were built into the vendor tree.

`opentelemetry-vendor build-native` (run before the wheel build) compiles stable-ABI (abi3)
extensions into ``_vendor``. Without them, the wheel is pure Python (``py3-none-any``).
"""

from __future__ import annotations

import sysconfig
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

VENDOR_DIR = Path("src/opentelemetry/agent/_vendor")
EXTENSION_SUFFIXES = (".so", ".pyd")


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        extensions = sorted(
            path.relative_to(root).as_posix()
            for path in (root / VENDOR_DIR).rglob("*")
            if path.is_file() and path.name.endswith(EXTENSION_SUFFIXES)
        )
        if not extensions:
            return
        not_abi3 = [path for path in extensions if not (".abi3." in path or path.endswith(".pyd"))]
        if not_abi3:
            raise ValueError(f"vendored extensions must use the stable ABI (abi3): {not_abi3}")
        abi3_tag = self.config.get("abi3-tag", "cp310")
        # Same platform tag as setuptools' bdist_wheel: the interpreter's deployment target (e.g.
        # macosx_11_0_arm64), not the build machine's OS version. Linux tags (linux_x86_64) are
        # meant to be repaired to manylinux/musllinux by auditwheel (cibuildwheel).
        platform = sysconfig.get_platform().replace("-", "_").replace(".", "_")
        build_data["pure_python"] = False
        build_data["tag"] = f"{abi3_tag}-abi3-{platform}"
        # Compiled extensions are gitignored, which hatch would otherwise exclude.
        build_data["artifacts"].extend(extensions)
