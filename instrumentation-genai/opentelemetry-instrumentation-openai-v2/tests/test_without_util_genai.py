# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import sys
import textwrap

from opentelemetry.instrumentation._semconv import OTEL_SEMCONV_STABILITY_OPT_IN

# Runs in a fresh process so modules imported by other tests (and conftest) don't leak in.
_SCRIPT = textwrap.dedent(
    """
    import sys
    from importlib.metadata import entry_points

    sys.modules["opentelemetry.util.genai"] = None

    entry_point = next(
        ep
        for ep in entry_points(group="opentelemetry_instrumentor")
        if ep.value.startswith("opentelemetry.instrumentation.openai_v2")
    )
    instrumentor = entry_point.load()()
    instrumentor.instrument()
    instrumentor.uninstrument()
    """
)


def test_loads_and_instruments_without_util_genai():
    env = {k: v for k, v in os.environ.items() if k != OTEL_SEMCONV_STABILITY_OPT_IN}
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
