# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Loading of the ``[tool.opentelemetry-vendor]`` configuration table."""

from __future__ import annotations

import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from opentelemetry.vendor.errors import VendorError

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_PYPROJECT = "pyproject.toml"
_TOOL_NAME = "opentelemetry-vendor"


class ConfigError(VendorError):
    """Raised when the vendoring configuration is missing or invalid."""


@dataclass(frozen=True)
class VendorConfig:
    project_dir: Path
    destination: Path
    requirements: Path
    namespace: str
    python_version: str
    protected_files: Collection[str]
    drop: Collection[str]
    patches_dir: Path | None
    sbom_file: Path | None


def load_config(project_dir: Path) -> VendorConfig:
    """Read and validate ``[tool.opentelemetry-vendor]`` from ``project_dir``."""
    project_dir = project_dir.resolve()
    pyproject = project_dir / _PYPROJECT
    try:
        with pyproject.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError as exc:
        raise ConfigError(f"{pyproject} does not exist") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{pyproject} is not valid TOML: {exc}") from exc

    table = data.get("tool", {}).get(_TOOL_NAME)
    if not isinstance(table, dict):
        raise ConfigError(f"{pyproject} has no [tool.{_TOOL_NAME}] table")

    destination = (project_dir / _require_str(table, "destination")).resolve()
    if destination == project_dir or not destination.is_relative_to(project_dir):
        raise ConfigError(f"'destination' must be a directory inside {project_dir}, got {destination}")

    patches_dir = _optional_str(table, "patches-dir")
    sbom_file = _optional_str(table, "sbom-file")
    return VendorConfig(
        project_dir=project_dir,
        destination=destination,
        requirements=project_dir / _require_str(table, "requirements"),
        namespace=_require_str(table, "namespace"),
        python_version=_optional_str(table, "python-version") or f"{sys.version_info.major}.{sys.version_info.minor}",
        protected_files=_str_list(table, "protected-files"),
        drop=_drop_patterns(table),
        patches_dir=project_dir / patches_dir if patches_dir else None,
        sbom_file=project_dir / sbom_file if sbom_file else None,
    )


def _require_str(table: Mapping[str, Any], key: str) -> str:
    value = _optional_str(table, key)
    if value is None:
        raise ConfigError(f"missing required key '{key}'")
    return value


def _optional_str(table: Mapping[str, Any], key: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"'{key}' must be a non-empty string")
    return value


def _drop_patterns(table: Mapping[str, Any]) -> tuple[str, ...]:
    patterns = _str_list(table, "drop")
    for pattern in patterns:
        path = PurePosixPath(pattern)
        if not pattern or path.is_absolute() or ".." in path.parts:
            raise ConfigError(f"'drop' pattern {pattern!r} must be relative to destination")
    return patterns


def _str_list(table: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"'{key}' must be a list of strings")
    return tuple(value)
