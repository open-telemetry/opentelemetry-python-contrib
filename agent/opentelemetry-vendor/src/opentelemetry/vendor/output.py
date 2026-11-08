# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Progress output for the ``opentelemetry-vendor`` commands."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from rich.console import Console
from rich.markup import escape
from rich.status import Status
from rich.table import Table

from opentelemetry.vendor.metadata import VendoredPackage

# Progress goes to stderr so stdout stays clean for future machine-readable output.
_console = Console(stderr=True, highlight=False)


@dataclass
class _Settings:
    verbose: bool = False


_settings = _Settings()


def configure(*, quiet: bool, verbose: bool) -> None:
    _console.quiet = quiet
    _settings.verbose = verbose


def step(message: str) -> None:
    """Report a completed step."""
    _console.print(f"[green]✔[/] {escape(message)}")


def detail(message: str) -> None:
    """Report a detail, only shown with ``--verbose``."""
    if _settings.verbose:
        for line in message.splitlines():
            _console.print(f"  [dim]{escape(line)}[/]", soft_wrap=True)


def status(message: str) -> Status:
    """A spinner shown while a long-running step is in progress."""
    return _console.status(escape(message))


def package_table(packages: Collection[VendoredPackage]) -> None:
    table = Table("Package", "Version", "License", "Modules", box=None)
    for package in sorted(packages, key=lambda package: package.name):
        table.add_row(
            package.name,
            package.version,
            package.license_expression or "-",
            ", ".join(package.top_level_names),
        )
    _console.print()
    _console.print(table)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural_form or singular + 's'}"
