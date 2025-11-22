import os
import subprocess
import sys

import pytest

# The full relative path from the project root
HELPER_PATH = "instrumentation/opentelemetry-instrumentation-redis/tests/_test_semconv_helper.py"


@pytest.mark.parametrize(
    "semconv_opt_in, test_name",
    [
        (None, "default"),
        ("database", "new"),
        ("database/dup", "dup"),
    ],
)
def test_run_in_subprocess(semconv_opt_in, test_name):
    """
    Runs the semantic convention test in a clean subprocess.
    The `semconv_opt_in` value is used to set the env var.
    """
    env = os.environ.copy()

    if semconv_opt_in is None:
        if "OTEL_SEMCONV_STABILITY_OPT_IN" in env:
            del env["OTEL_SEMCONV_STABILITY_OPT_IN"]
    else:
        env["OTEL_SEMCONV_STABILITY_OPT_IN"] = semconv_opt_in

    result = subprocess.run(
        [sys.executable, "-m", "pytest", HELPER_PATH],
        capture_output=True,
        text=True,
        env=env,
        check=False,  # Explicitly set check=False to satisfy pylint
    )
    # Use a standard assert
    assert (
        result.returncode == 0
    ), f"Subprocess for '{test_name}' mode failed with stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
