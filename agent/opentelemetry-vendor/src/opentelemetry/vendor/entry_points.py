# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Keep a trimmed, namespaced copy of the vendored distributions' metadata.

Vendored code that discovers plugins through ``importlib.metadata`` entry points needs the
metadata of the vendored distributions, but not that of the application's (which point at
un-vendored modules). The copy lives in a directory that isn't on ``sys.path``, so only code
that passes it explicitly (``importlib.metadata.distributions(path=[...])``) sees it.
"""

from __future__ import annotations

import configparser
import re
import shutil
from collections.abc import Collection
from pathlib import Path

from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import VendoredPackage
from opentelemetry.vendor.rewrite import is_vendored

_METADATA = "METADATA"
_ENTRY_POINTS = "entry_points.txt"
_DROPPED_GROUPS = frozenset({"console_scripts", "gui_scripts"})
"""Script wrappers are generated at install time from the vendoring project's own metadata."""
# Same grammar as importlib.metadata.EntryPoint: ``module[:attr] [extras]``.
_ENTRY_POINT_VALUE = re.compile(r"(?P<module>[\w.]+)(?P<rest>\s*(?::\s*[\w.]+\s*)?(?:\[.*\]\s*)?)$")


def write_metadata(
    packages: Collection[VendoredPackage],
    destination: Path,
    metadata_dir: Path,
    namespace: str,
    names: Collection[str],
) -> int:
    """Write each package's ``METADATA`` and namespaced ``entry_points.txt`` to ``metadata_dir``.

    Raises ``VendorError`` for an entry point whose module isn't in the vendored tree (dropped,
    excluded or never vendored). Returns the number of entry points written.
    """
    metadata_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for package in sorted(packages, key=lambda package: package.name):
        target = metadata_dir / package.dist_info.name
        target.mkdir()
        shutil.copyfile(package.dist_info / _METADATA, target / _METADATA)
        source = package.dist_info / _ENTRY_POINTS
        if not source.is_file():
            continue
        groups = rewrite_entry_points(source.read_text(), namespace, names)
        for group, entries in groups.items():
            for name, value in entries.items():
                module = value.split(":", 1)[0].strip()
                if not _module_exists(destination, module.removeprefix(f"{namespace}.")):
                    raise VendorError(
                        f"entry point {group}:{name} of {package.name} references {module}, "
                        "which isn't in the vendored tree"
                    )
                count += 1
        if groups:
            (target / _ENTRY_POINTS).write_text(_format(groups))
    return count


def rewrite_entry_points(text: str, namespace: str, names: Collection[str]) -> dict[str, dict[str, str]]:
    """Parse ``entry_points.txt`` ``text`` and move vendored modules under ``namespace``.

    Script groups are dropped. Values of non-vendored modules are kept, so ``write_metadata``
    reports them.
    """
    parser = _CaseSensitiveParser(delimiters=("=",), interpolation=None, strict=False)
    parser.read_string(text)
    groups: dict[str, dict[str, str]] = {}
    for group in parser.sections():
        if group in _DROPPED_GROUPS:
            continue
        entries = {}
        for name, value in parser.items(group):
            match = _ENTRY_POINT_VALUE.match(value.strip())
            if match is None:
                raise VendorError(f"invalid entry point {group}:{name} = {value!r}")
            module = match.group("module")
            if is_vendored(module, names, namespace):
                module = f"{namespace}.{module}"
            entries[name] = f"{module}{match.group('rest')}".strip()
        if entries:
            groups[group] = entries
    return groups


class _CaseSensitiveParser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        # Entry point names are case-sensitive; ConfigParser lowercases keys by default.
        return optionstr


def _module_exists(destination: Path, module: str) -> bool:
    path = destination.joinpath(*module.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file() or path.is_dir()


def _format(groups: dict[str, dict[str, str]]) -> str:
    sections = [
        f"[{group}]\n" + "".join(f"{name} = {value}\n" for name, value in entries.items())
        for group, entries in groups.items()
    ]
    return "\n".join(sections)
