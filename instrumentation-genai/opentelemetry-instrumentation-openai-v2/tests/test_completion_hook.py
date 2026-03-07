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

import os
from unittest.mock import MagicMock, patch

import pytest

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)

from .test_utils import DEFAULT_MODEL, USER_ONLY_PROMPT


# Run hook tests in experimental mode only — hooks are only active on the new path
@pytest.fixture(params=[(True, "span_only")])
def content_mode(request):
    return request.param


@pytest.fixture
def completion_hook():  # pylint: disable=redefined-outer-name
    return MagicMock()


def test_custom_hook_is_called(
    span_exporter,
    log_exporter,
    instrument_no_content,
    completion_hook,
    openai_client,
    vcr,
):
    """A hook passed to instrument() is called after each chat completion."""
    with vcr.use_cassette("test_chat_completion_with_content.yaml"):
        openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
            stream=False,
        )

    completion_hook.on_completion.assert_called_once()
    kwargs = completion_hook.on_completion.call_args.kwargs
    assert kwargs["inputs"]
    assert kwargs["outputs"]
    assert kwargs["span"] is not None

    # Content goes to the hook only — not to span attributes or log records
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span_attrs = spans[0].attributes or {}
    assert "gen_ai.input.messages" not in span_attrs
    assert "gen_ai.output.messages" not in span_attrs

    assert log_exporter.get_finished_logs() == ()


@patch.dict(
    os.environ,
    {
        OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "span_only",
    },
)
def test_default_hook_loaded_from_env(
    span_exporter,
    tracer_provider,
    logger_provider,
    meter_provider,
    openai_client,
    vcr,
):
    """When no hook kwarg is given, load_completion_hook() provides the default."""
    default_hook = MagicMock()
    instrumentor = OpenAIInstrumentor()
    with patch(
        "opentelemetry.instrumentation.openai_v2.load_completion_hook",
        return_value=default_hook,
    ):
        instrumentor.instrument(
            tracer_provider=tracer_provider,
            logger_provider=logger_provider,
            meter_provider=meter_provider,
            # no completion_hook kwarg — should fall back to load_completion_hook()
        )

    try:
        with vcr.use_cassette("test_chat_completion_with_content.yaml"):
            openai_client.chat.completions.create(
                messages=USER_ONLY_PROMPT,
                model=DEFAULT_MODEL,
                stream=False,
            )
    finally:
        instrumentor.uninstrument()

    default_hook.on_completion.assert_called_once()
    kwargs = default_hook.on_completion.call_args.kwargs
    assert kwargs["inputs"]
    assert kwargs["outputs"]
    assert kwargs["span"] is not None

    # Content goes to the hook only — not to span attributes or log records
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span_attrs = spans[0].attributes or {}
    assert "gen_ai.input.messages" in span_attrs
    assert "gen_ai.output.messages" in span_attrs
