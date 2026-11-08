# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Loading of the ``[tool.opentelemetry-vendor]`` configuration table."""

from __future__ import annotations

import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from opentelemetry.vendor.checks import ALLOW_TABLE, ALLOWABLE_KINDS, DYNAMIC_IMPORTS
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
    allow: Mapping[str, Collection[str]]
    """Check kind -> files (relative to ``destination``) whose findings of that kind have been reviewed."""
    patches: Collection[Path]
    """Patch files, applied in order after imports are rewritten."""
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

    sbom_file = _optional_str(table, "sbom-file")
    return VendorConfig(
        project_dir=project_dir,
        destination=destination,
        requirements=project_dir / _require_str(table, "requirements"),
        namespace=_require_str(table, "namespace"),
        python_version=_optional_str(table, "python-version") or f"{sys.version_info.major}.{sys.version_info.minor}",
        protected_files=_str_list(table, "protected-files"),
        drop=_relative_paths(table, "drop"),
        allow=_allow(table),
        patches=tuple(project_dir / patch for patch in _str_list(table, "patches")),
        sbom_file=project_dir / sbom_file if sbom_file else None,
    )


def _allow(table: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    if "allow-dynamic-imports" in table:
        raise ConfigError(f"'allow-dynamic-imports' moved to {ALLOW_TABLE} {DYNAMIC_IMPORTS}")
    allow = table.get("allow", {})
    if not isinstance(allow, dict):
        raise ConfigError(f"'allow' must be a table ({ALLOW_TABLE})")
    unknown = sorted(set(allow) - set(ALLOWABLE_KINDS))
    if unknown:
        raise ConfigError(f"unknown {ALLOW_TABLE} keys {unknown}; expected some of {list(ALLOWABLE_KINDS)}")
    return {kind: _relative_paths(allow, kind) for kind in allow}


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


def _relative_paths(table: Mapping[str, Any], key: str) -> tuple[str, ...]:
    paths = _str_list(table, key)
    for entry in paths:
        path = PurePosixPath(entry)
        if not entry or path.is_absolute() or ".." in path.parts:
            raise ConfigError(f"'{key}' entry {entry!r} must be relative to destination")
    return paths


def _str_list(table: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"'{key}' must be a list of strings")
    return tuple(value)
