# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Make the conformance test self-contained under plain ``pytest``.

The conformance run shells out to the Weaver binary and checks against a pinned
semantic-conventions registry. Neither is a Python package, so this conftest
provisions both on demand the first time the conformance test is collected:

- Weaver: the pinned release is downloaded and cached, and its directory is put
  on ``PATH`` for this process. If it is already on ``PATH`` at the pinned
  version, nothing is downloaded.
- Registry: the pinned semantic-conventions checkout is fetched into the
  tooling's own cache (the same cache the run uses), so a network failure turns
  into a clean skip here rather than an error in the middle of the run.

If either genuinely cannot be obtained (for example offline), the conformance
test is SKIPPED with a clear reason instead of erroring. A developer runs plain
``pytest`` and it just works; nothing has to be pre-provisioned by hand.

This conftest is deliberately generic: it provisions the tooling for any
``conformance.yaml`` collected beneath it, so the next instrumentation reuses it
unchanged.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import pytest

# The Weaver release the pinned conformance tooling expects. Keep in sync with
# WEAVER_VERSION in the semantic-conventions-conformance repo the tooling is
# pinned to (see this package's test-requirements-3.txt).
_WEAVER_VERSION = "v0.25.1"

# Where the downloaded Weaver binary is cached between runs.
_WEAVER_CACHE = (
    Path.home() / ".cache" / "otel-conformance" / "weaver" / _WEAVER_VERSION
)

# Set by _provision() to a human-readable reason when the conformance test
# cannot run in this environment; None means it can.
_skip_reason: str | None = None


def _weaver_asset() -> str | None:
    """The Weaver release asset for this OS/arch, or None if unsupported."""
    system = platform.system()
    machine = platform.machine().lower()
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }.get(machine)
    if arch is None:
        return None
    if system == "Linux":
        return f"weaver-{arch}-unknown-linux-gnu.tar.xz"
    if system == "Darwin":
        return f"weaver-{arch}-apple-darwin.tar.xz"
    return None


def _weaver_on_path_version() -> str | None:
    """The bare version of a ``weaver`` already on PATH, or None."""
    weaver = shutil.which("weaver")
    if weaver is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603
            [weaver, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    words = completed.stdout.split()
    return words[-1].lstrip("v") if words else None


def _ensure_weaver() -> str | None:
    """Put the pinned Weaver on PATH, downloading it if needed.

    Returns None on success, or a reason string explaining why it could not be
    provisioned (used to skip the test).
    """
    if _weaver_on_path_version() is not None:
        # Something usable is already on PATH; let the tooling's own version
        # check warn if it is not the exact pin.
        return None

    cached = _WEAVER_CACHE / "weaver"
    if cached.is_file():
        os.environ["PATH"] = f"{_WEAVER_CACHE}{os.pathsep}{os.environ['PATH']}"
        return None

    asset = _weaver_asset()
    if asset is None:
        return (
            f"no Weaver {_WEAVER_VERSION} release asset for this platform "
            f"({platform.system()} {platform.machine()})"
        )

    url = (
        "https://github.com/open-telemetry/weaver/releases/download/"
        f"{_WEAVER_VERSION}/{asset}"
    )
    _WEAVER_CACHE.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / asset
            with (
                urllib.request.urlopen(url, timeout=60) as response,  # noqa: S310
                archive.open("wb") as out,
            ):
                shutil.copyfileobj(response, out)
            with tarfile.open(archive, "r:xz") as tar:
                member = next(
                    (m for m in tar.getmembers() if m.name.endswith("/weaver")),
                    None,
                )
                if member is None:
                    return f"Weaver archive at {url} did not contain a weaver binary"
                member.name = "weaver"
                tar.extract(member, _WEAVER_CACHE, filter="data")
        cached.chmod(cached.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    except (OSError, tarfile.TarError) as error:
        return f"could not download Weaver {_WEAVER_VERSION} from {url}: {error}"

    os.environ["PATH"] = f"{_WEAVER_CACHE}{os.pathsep}{os.environ['PATH']}"
    return None


def _ensure_registry() -> str | None:
    """Fetch the pinned semantic-conventions registry into the tooling cache.

    Returns None on success, or a reason string on failure. The HTTP domain
    package knows which repo and ref to pin, so this reuses its own values and
    the tooling's own provisioner and cache.
    """
    try:
        from http_conformance import DOMAIN  # noqa: PLC0415
        from opentelemetry.conformance import provision  # noqa: PLC0415
    except ImportError as error:
        return f"conformance tooling is not installed: {error}"

    # The same label the domain itself uses, so the fetch here lands in the very
    # cache entry the run consumes (rather than fetching the registry twice).
    label = DOMAIN.repo.rpartition("/")[2]
    try:
        provision(DOMAIN.repo, DOMAIN.ref, label=label)
    except (RuntimeError, OSError) as error:
        return f"could not fetch the semantic-conventions registry: {error}"
    return None


def _provision() -> None:
    """Provision Weaver and the registry once, recording any skip reason."""
    global _skip_reason
    reason = _ensure_weaver()
    if reason is not None:
        _skip_reason = reason
        return
    _skip_reason = _ensure_registry()


def pytest_configure(config: pytest.Config) -> None:
    # Runs once per session, before the conformance items execute. Provisioning
    # here (rather than in a fixture) is what lets the plugin-generated
    # conformance items — which take no fixtures — still find Weaver on PATH.
    _provision()


def pytest_runtest_setup(item: pytest.Item) -> None:
    # Skip only the conformance items (the ones the conformance plugin makes
    # from a conformance.yaml), and only when provisioning failed. Ordinary
    # tests collected nearby are untouched.
    if _skip_reason is None:
        return
    if type(item).__name__ == "ConformanceItem":
        pytest.skip(_skip_reason)
