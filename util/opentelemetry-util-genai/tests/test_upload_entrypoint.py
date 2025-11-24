# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable=import-outside-toplevel,no-name-in-module
import importlib
import logging
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from opentelemetry.util.genai._upload.completion_hook import (
    UploadCompletionHook,
)
from opentelemetry.util.genai.completion_hook import (
    _NoOpCompletionHook,
)
from opentelemetry.util.genai.completion_hook import (
    load_completion_hook as real_load_completion_hook,
)

# Use MemoryFileSystem for testing
# https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.implementations.memory.MemoryFileSystem
BASE_PATH = "memory://"


@pytest.fixture(name="load_completion_hook")
def fixture_load_completion_hook():
    with ExitStack() as stack:

        def load_completion_hook():
            hook = real_load_completion_hook()
            if isinstance(hook, UploadCompletionHook):
                stack.callback(hook.shutdown)
            return hook

        yield load_completion_hook


@pytest.fixture(name="upload_environ", autouse=True)
def fixture_upload_environ():
    with patch.dict(
        "os.environ",
        {
            "OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK": "upload",
            "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH": BASE_PATH,
        },
        clear=True,
    ):
        yield


def test_upload_entry_point(load_completion_hook):
    assert isinstance(load_completion_hook(), UploadCompletionHook)


def test_upload_entry_point_no_fsspec(load_completion_hook):
    """Tests that the a no-op uploader is used when fsspec is not installed"""

    from opentelemetry.util.genai import _upload  # noqa: PLC0415

    # Simulate fsspec imports failing
    with patch.dict(
        sys.modules,
        {"opentelemetry.util.genai._upload.completion_hook": None},
    ):
        importlib.reload(_upload)
        assert isinstance(load_completion_hook(), _NoOpCompletionHook)


def test_upload_no_base_path(load_completion_hook, caplog):
    with patch.dict(
        "os.environ", {"OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH": ""}
    ):
        assert isinstance(load_completion_hook(), _NoOpCompletionHook)

    assert caplog.records[0].levelno == logging.WARNING
    assert (
        caplog.records[0].message
        == "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH is required but not set, using no-op instead"
    )


@pytest.mark.parametrize(
    "envvar_value,expect_format,expect_warn",
    (
        (None, "json", False),
        ("", "json", False),
        ("json", "json", False),
        ("invalid", "json", True),
        ("jsonl", "jsonl", False),
        ("jSoNl", "jsonl", False),
    ),
)
def test_parse_upload_format_envvar(
    envvar_value, expect_format, expect_warn, load_completion_hook, caplog
):
    with patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT": envvar_value}
        if envvar_value is not None
        else {},
    ):
        assert isinstance(hook := load_completion_hook(), UploadCompletionHook)
        assert hook._format == expect_format, (
            f"expected upload format {expect_format=} with {envvar_value=} got {hook._format}"
        )

        if expect_warn:
            assert caplog.records[0].levelno == logging.WARNING
            assert (
                "is not a valid option for OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT, should be be one of ('json', 'jsonl'). Defaulting to json."
                in caplog.records[0].message
            )


@pytest.mark.parametrize(
    "envvar_value,expect_size,expect_warn",
    (
        ("", 20, False),
        ("foobar", 20, True),
        ("1", 1, False),
        ("100", 100, False),
    ),
)
def test_parse_max_queue_size_envvar(
    envvar_value, expect_size, expect_warn, load_completion_hook, caplog
):
    with patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE": envvar_value}
        if envvar_value is not None
        else {},
    ):
        assert isinstance(hook := load_completion_hook(), UploadCompletionHook)
        assert hook._max_queue_size == expect_size, (
            f"expected max_queue_size {expect_size=} with {envvar_value=} got {hook._format}"
        )

        if expect_warn:
            assert caplog.records
            assert caplog.records[0].levelno == logging.WARNING
            assert (
                "is not a valid integer for OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE. Defaulting to 20."
                in caplog.records[0].message
            )
