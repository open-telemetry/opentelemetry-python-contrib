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

"""Streaming response wrappers for Agno instrumentation."""

from __future__ import annotations

import logging
import time
from typing import Any

from wrapt import ObjectProxy  # type: ignore[import-untyped]

from opentelemetry.metrics import Histogram
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.agno.utils import should_capture_content

logger = logging.getLogger(__name__)

# Custom semantic attributes for Agno (following gen_ai.* namespace)
GENAI_OPERATION_NAME = "gen_ai.operation.name"
AGNO_ENTITY_OUTPUT = "gen_ai.agno.entity.output"
AGNO_RUN_ID = "gen_ai.agno.run.id"


class AgnoAsyncStream(ObjectProxy):
    """Wrapper for Agno async streaming responses that handles instrumentation."""

    def __init__(
        self,
        span: Any,
        response: Any,
        instance: Any,
        start_time: float,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the async stream wrapper.

        Args:
            span: The OpenTelemetry span.
            response: The original async stream response.
            instance: The Agno Agent instance.
            start_time: The start time of the request.
            duration_histogram: Optional histogram for recording duration.
            token_histogram: Optional histogram for recording token usage.
        """
        super().__init__(response)

        self._self_span = span
        self._self_instance = instance
        self._self_start_time = start_time
        self._self_duration_histogram = duration_histogram
        self._self_token_histogram = token_histogram
        self._self_events: list[Any] = []
        self._self_final_result: Any = None
        self._self_instrumentation_completed = False

    def __aiter__(self) -> "AgnoAsyncStream":
        return self

    async def __anext__(self) -> Any:
        try:
            event = await self.__wrapped__.__anext__()
        except StopAsyncIteration:
            if not self._self_instrumentation_completed:
                self._complete_instrumentation()
            raise
        except Exception as e:
            if not self._self_instrumentation_completed:
                if self._self_span and self._self_span.is_recording():
                    self._self_span.set_status(Status(StatusCode.ERROR, str(e)))
                    self._self_span.record_exception(e)
                    self._self_span.end()
                self._self_instrumentation_completed = True
            raise

        self._self_events.append(event)

        if hasattr(event, "event") and event.event == "run_response":
            self._self_final_result = event

        return event

    def _complete_instrumentation(self) -> None:
        """Complete the instrumentation when stream is fully consumed."""
        if self._self_instrumentation_completed:
            return

        try:
            duration = time.time() - self._self_start_time

            if self._self_final_result:
                result = self._self_final_result
                if hasattr(result, "content") and should_capture_content():
                    self._self_span.set_attribute(
                        AGNO_ENTITY_OUTPUT, str(result.content)
                    )

                if hasattr(result, "run_id"):
                    self._self_span.set_attribute(AGNO_RUN_ID, result.run_id)

                if hasattr(result, "metrics"):
                    metrics = result.metrics
                    if hasattr(metrics, "input_tokens"):
                        self._self_span.set_attribute(
                            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                            metrics.input_tokens,
                        )
                    if hasattr(metrics, "output_tokens"):
                        self._self_span.set_attribute(
                            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                            metrics.output_tokens,
                        )

            self._self_span.set_status(Status(StatusCode.OK))

            if self._self_duration_histogram:
                self._self_duration_histogram.record(
                    duration,
                    attributes={
                        GenAIAttributes.GEN_AI_SYSTEM: "agno",
                        GENAI_OPERATION_NAME: "agent",
                    },
                )

        except Exception as e:
            logger.warning("Failed to complete instrumentation: %s", str(e))
        finally:
            if self._self_span.is_recording():
                self._self_span.end()
            self._self_instrumentation_completed = True


class AgnoStream(ObjectProxy):
    """Wrapper for Agno sync streaming responses that handles instrumentation."""

    def __init__(
        self,
        span: Any,
        response: Any,
        instance: Any,
        start_time: float,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the sync stream wrapper.

        Args:
            span: The OpenTelemetry span.
            response: The original sync stream response.
            instance: The Agno Agent instance.
            start_time: The start time of the request.
            duration_histogram: Optional histogram for recording duration.
            token_histogram: Optional histogram for recording token usage.
        """
        super().__init__(response)

        self._self_span = span
        self._self_instance = instance
        self._self_start_time = start_time
        self._self_duration_histogram = duration_histogram
        self._self_token_histogram = token_histogram
        self._self_events: list[Any] = []
        self._self_final_result: Any = None
        self._self_instrumentation_completed = False

    def __iter__(self) -> "AgnoStream":
        return self

    def __next__(self) -> Any:
        try:
            event = self.__wrapped__.__next__()
        except StopIteration:
            if not self._self_instrumentation_completed:
                self._complete_instrumentation()
            raise
        except Exception as e:
            if not self._self_instrumentation_completed:
                if self._self_span and self._self_span.is_recording():
                    self._self_span.set_status(Status(StatusCode.ERROR, str(e)))
                    self._self_span.record_exception(e)
                    self._self_span.end()
                self._self_instrumentation_completed = True
            raise

        self._self_events.append(event)

        if hasattr(event, "event") and event.event == "run_response":
            self._self_final_result = event

        return event

    def _complete_instrumentation(self) -> None:
        """Complete the instrumentation when stream is fully consumed."""
        if self._self_instrumentation_completed:
            return

        try:
            duration = time.time() - self._self_start_time

            if self._self_final_result:
                result = self._self_final_result
                if hasattr(result, "content") and should_capture_content():
                    self._self_span.set_attribute(
                        AGNO_ENTITY_OUTPUT, str(result.content)
                    )

                if hasattr(result, "run_id"):
                    self._self_span.set_attribute(AGNO_RUN_ID, result.run_id)

                if hasattr(result, "metrics"):
                    metrics = result.metrics
                    if hasattr(metrics, "input_tokens"):
                        self._self_span.set_attribute(
                            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                            metrics.input_tokens,
                        )
                    if hasattr(metrics, "output_tokens"):
                        self._self_span.set_attribute(
                            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                            metrics.output_tokens,
                        )

            self._self_span.set_status(Status(StatusCode.OK))

            if self._self_duration_histogram:
                self._self_duration_histogram.record(
                    duration,
                    attributes={
                        GenAIAttributes.GEN_AI_SYSTEM: "agno",
                        GENAI_OPERATION_NAME: "agent",
                    },
                )

        except Exception as e:
            logger.warning("Failed to complete instrumentation: %s", str(e))
        finally:
            if self._self_span.is_recording():
                self._self_span.end()
            self._self_instrumentation_completed = True
