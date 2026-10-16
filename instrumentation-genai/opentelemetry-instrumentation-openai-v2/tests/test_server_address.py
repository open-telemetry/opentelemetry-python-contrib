# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for endpoint extraction in `get_server_address_and_port`.

The extraction must not depend on which HTTP client library the OpenAI SDK happens to use internally.
openai 3.x builds on httpx2, so `client._client.base_url` is an `httpx2.URL`; an isinstance check against
`httpx.URL` silently stops matching and `server.address` disappears from every span.
"""

import subprocess
import sys
import textwrap
from importlib.metadata import version

import pytest

from opentelemetry.instrumentation.openai_v2.utils import (
    get_server_address_and_port,
)


class _Client:
    """Stands in for the resource object the instrumentation receives (e.g. `client.chat.completions`),
    whose `_client` is the SDK client holding `base_url`."""

    def __init__(self, base_url):
        self._client = type("Inner", (), {"base_url": base_url})()


def test_httpx_url():
    httpx = pytest.importorskip("httpx")
    address, port = get_server_address_and_port(_Client(httpx.URL("http://localhost:8080/v1")))
    assert address == "localhost"
    assert port == 8080


def test_httpx2_url():
    httpx2 = pytest.importorskip("httpx2")
    address, port = get_server_address_and_port(_Client(httpx2.URL("http://localhost:8080/v1")))
    assert address == "localhost"
    assert port == 8080


def test_string_base_url():
    address, port = get_server_address_and_port(_Client("http://localhost:8080/v1"))
    assert address == "localhost"
    assert port == 8080


def test_default_https_port_is_omitted():
    address, port = get_server_address_and_port(_Client("https://api.openai.com:443/v1"))
    assert address == "api.openai.com"
    assert port is None


def test_missing_base_url():
    assert get_server_address_and_port(_Client(None)) == (None, None)
    assert get_server_address_and_port(object()) == (None, None)


def test_importable_without_httpx():
    """The module must import when httpx is not installed.

    This package declares no dependency on httpx, and openai 3.x depends on httpx2 instead, so httpx can
    legitimately be absent. A module-scope `from httpx import URL` then makes the instrumentation
    unimportable rather than merely degraded.

    Skipped on openai 2.x, which imports httpx itself, so the situation cannot arise there.
    """
    if int(version("openai").split(".")[0]) < 3:
        pytest.skip("openai 2.x depends on httpx itself, so httpx is never absent")
    script = textwrap.dedent(
        """
        import sys

        class Blocker:
            def find_spec(self, name, path=None, target=None):
                if name == "httpx" or name.startswith("httpx."):
                    raise ModuleNotFoundError("No module named 'httpx'")
                return None

        sys.meta_path.insert(0, Blocker())
        for module in [m for m in sys.modules if m == "httpx" or m.startswith("httpx.")]:
            del sys.modules[module]

        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor  # noqa: F401
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
