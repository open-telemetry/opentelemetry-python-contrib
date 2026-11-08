# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from opentelemetry.vendor import output
from opentelemetry.vendor import sync as _sync
from opentelemetry.vendor.config import load_config
from opentelemetry.vendor.errors import VendorError

app = typer.Typer(no_args_is_help=True)

ProjectDir = Annotated[
    Path,
    typer.Argument(
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="Directory containing the pyproject.toml to vendor for.",
    ),
]
Check = Annotated[
    bool,
    typer.Option(
        "--check",
        help="Only check that the vendored files match what sync would produce; change nothing.",
    ),
]
Quiet = Annotated[bool, typer.Option("--quiet", "-q", help="Only print errors.")]
Verbose = Annotated[
    bool,
    typer.Option("--verbose", "-v", help="Show pip output and every file removed."),
]


@app.callback()
def _callback() -> None:
    """Vendor third-party packages into an OpenTelemetry Python package."""


@app.command()
def sync(project_dir: ProjectDir, check: Check = False, quiet: Quiet = False, verbose: Verbose = False) -> None:
    """Sync the vendored packages of PROJECT_DIR."""
    _configure_output(quiet, verbose)
    try:
        config = load_config(project_dir)
        if check:
            _sync.check(config)
        else:
            _sync.sync(config)
    except VendorError as exc:
        _fail(exc)


@app.command()
def clean(project_dir: ProjectDir, quiet: Quiet = False, verbose: Verbose = False) -> None:
    """Remove vendored packages from PROJECT_DIR, keeping protected files."""
    _configure_output(quiet, verbose)
    try:
        _sync.clean(load_config(project_dir))
    except VendorError as exc:
        _fail(exc)


def _configure_output(quiet: bool, verbose: bool) -> None:
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together")
    output.configure(quiet=quiet, verbose=verbose)


def _fail(exc: VendorError) -> NoReturn:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(code=1) from exc


def main() -> None:
    app()
