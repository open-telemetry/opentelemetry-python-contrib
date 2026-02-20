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
import unittest
from unittest.mock import patch

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT,
)
from opentelemetry.util.genai.utils import (
    should_capture_content,
    should_emit_event,
)


def patch_env_vars(stability_mode, content_capturing, emit_event):
    def decorator(test_case):
        @patch.dict(
            os.environ,
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: stability_mode,
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: content_capturing,
                OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT: emit_event,
            },
        )
        def wrapper(*args, **kwargs):
            # Reset state.
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            return test_case(*args, **kwargs)

        return wrapper

    return decorator


class TestShouldEmitEvent(unittest.TestCase):
    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="true",
    )
    def test_should_emit_event_returns_true_when_set_to_true(
        self,
    ):  # pylint: disable=no-self-use
        assert should_emit_event() is True

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="True",
    )
    def test_should_emit_event_case_insensitive_true(
        self,
    ):  # pylint: disable=no-self-use
        assert should_emit_event() is True

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="false",
    )
    def test_should_emit_event_returns_false_when_set_to_false(
        self,
    ):  # pylint: disable=no-self-use
        assert should_emit_event() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="False",
    )
    def test_should_emit_event_case_insensitive_false(
        self,
    ):  # pylint: disable=no-self-use
        assert should_emit_event() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="",
    )
    def test_should_emit_event_defaults_to_true_for_event_only(
        self,
    ):  # pylint: disable=no-self-use
        # When EVENT_ONLY is set, should_emit_event should default to True
        assert should_emit_event() is True

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_AND_EVENT",
        emit_event="",
    )
    def test_should_emit_event_defaults_to_true_for_span_and_event(
        self,
    ):  # pylint: disable=no-self-use
        # When SPAN_AND_EVENT is set, should_emit_event should default to True
        assert should_emit_event() is True

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="NO_CONTENT",
        emit_event="",
    )
    def test_should_emit_event_defaults_to_false_for_no_content(
        self,
    ):  # pylint: disable=no-self-use
        # When NO_CONTENT is set, should_emit_event should default to False
        assert should_emit_event() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
        emit_event="",
    )
    def test_should_emit_event_defaults_to_false_for_span_only(
        self,
    ):  # pylint: disable=no-self-use
        # When SPAN_ONLY is set, should_emit_event should default to False
        assert should_emit_event() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="",
        emit_event="",
    )
    def test_should_emit_event_defaults_to_false_when_no_content_capturing_set(
        self,
    ):  # pylint: disable=no-self-use
        # When content_capturing is not set (defaults to NO_CONTENT),
        # should_emit_event should default to False
        assert should_emit_event() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="INVALID_VALUE",
    )
    def test_should_emit_event_with_invalid_value_falls_back_to_default(
        self,
    ):  # pylint: disable=no-self-use
        # When invalid value is set, should fall back to default based on content_capturing_mode
        # EVENT_ONLY should default to True
        with self.assertLogs(level="WARNING") as cm:
            result = should_emit_event()
            assert result is True, (
                f"Expected True but got {result} (EVENT_ONLY should default to True)"
            )
        self.assertEqual(len(cm.output), 1)
        self.assertIn("INVALID_VALUE is not a valid option for", cm.output[0])
        self.assertIn(
            "Must be one of true or false (case-insensitive)", cm.output[0]
        )

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
        emit_event="INVALID_VALUE",
    )
    def test_should_emit_event_with_invalid_value_falls_back_to_false_for_span_only(
        self,
    ):  # pylint: disable=no-self-use
        # When invalid value is set with SPAN_ONLY, should default to False
        with self.assertLogs(level="WARNING") as cm:
            result = should_emit_event()
            assert result is False, (
                f"Expected False but got {result} (SPAN_ONLY should default to False)"
            )
        self.assertEqual(len(cm.output), 1)
        self.assertIn("INVALID_VALUE is not a valid option for", cm.output[0])

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="false",
    )
    def test_should_emit_event_user_setting_overrides_default(
        self,
    ):  # pylint: disable=no-self-use
        # User explicitly setting emit_event="false" should override the default (True for EVENT_ONLY)
        assert should_emit_event() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="NO_CONTENT",
        emit_event="true",
    )
    def test_should_emit_event_user_setting_overrides_default_for_no_content(
        self,
    ):  # pylint: disable=no-self-use
        # User explicitly setting emit_event="true" should override the default (False for NO_CONTENT)
        assert should_emit_event() is True


class TestShouldCaptureContent(unittest.TestCase):
    @patch_env_vars(
        stability_mode="default",
        content_capturing="SPAN_AND_EVENT",
        emit_event="true",
    )
    def test_should_capture_content_false_when_not_experimental(
        self,
    ):  # pylint: disable=no-self-use
        assert should_capture_content() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="NO_CONTENT",
        emit_event="true",
    )
    def test_should_capture_content_false_when_no_content(
        self,
    ):  # pylint: disable=no-self-use
        assert should_capture_content() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="false",
    )
    def test_should_capture_content_false_when_event_only_but_event_disabled(
        self,
    ):  # pylint: disable=no-self-use
        assert should_capture_content() is False

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
        emit_event="",
    )
    def test_should_capture_content_true_for_span_only(
        self,
    ):  # pylint: disable=no-self-use
        assert should_capture_content() is True
