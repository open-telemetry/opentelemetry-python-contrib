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

from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.openai_v2.response_wrappers import (
    ResponseStreamManagerWrapper,
)


class _FakeManager:
    def __init__(self, stream, suppressed=False, exit_error=None):
        self._stream = stream
        self._suppressed = suppressed
        self._exit_error = exit_error
        self.exit_args = None

    def __enter__(self):
        return self._stream

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit_args = (exc_type, exc_val, exc_tb)
        if self._exit_error is not None:
            raise self._exit_error
        return self._suppressed


def _make_wrapper(manager):
    handler = SimpleNamespace()
    invocation = SimpleNamespace(request_model=None)
    return ResponseStreamManagerWrapper(
        manager=manager,
        handler=handler,
        invocation=invocation,
        capture_content=False,
    )


class _FakeStreamWrapper:
    def __init__(self):
        self.exit_args = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit_args = (exc_type, exc_val, exc_tb)
        return False


def test_manager_exit_forwards_exception_to_stream_wrapper():
    manager = _FakeManager(stream=SimpleNamespace(), suppressed=False)
    wrapper = _make_wrapper(manager)
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("boom")
    result = wrapper.__exit__(ValueError, error, None)

    assert result is False
    assert manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)
    assert wrapper._stream_wrapper is None


def test_manager_exit_uses_none_exception_when_manager_suppresses():
    manager = _FakeManager(stream=SimpleNamespace(), suppressed=True)
    wrapper = _make_wrapper(manager)
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = RuntimeError("ignored")
    result = wrapper.__exit__(RuntimeError, error, None)

    assert result is True
    assert manager.exit_args == (RuntimeError, error, None)
    assert stream_wrapper.exit_args == (None, None, None)
    assert wrapper._stream_wrapper is None


def test_manager_exit_still_finalizes_stream_wrapper_when_manager_raises():
    manager_error = RuntimeError("manager failure")
    manager = _FakeManager(
        stream=SimpleNamespace(), suppressed=False, exit_error=manager_error
    )
    wrapper = _make_wrapper(manager)
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("outer")
    with pytest.raises(RuntimeError, match="manager failure"):
        wrapper.__exit__(ValueError, error, None)

    assert manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)
    assert wrapper._stream_wrapper is None
    
