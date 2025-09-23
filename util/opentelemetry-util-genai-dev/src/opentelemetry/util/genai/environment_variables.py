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

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)

OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK = (
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK
"""

OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH = (
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH

An :func:`fsspec.open` compatible URI/path for uploading prompts and responses. Can be a local
path like ``/path/to/prompts`` or a cloud storage URI such as ``gs://my_bucket``. For more
information, see

* `Instantiate a file-system
  <https://filesystem-spec.readthedocs.io/en/latest/usage.html#instantiate-a-file-system>`_ for supported values and how to
  install support for additional backend implementations.
* `Configuration
  <https://filesystem-spec.readthedocs.io/en/latest/features.html#configuration>`_ for
  configuring a backend with environment variables.
*  `URL Chaining
   <https://filesystem-spec.readthedocs.io/en/latest/features.html#url-chaining>`_ for advanced
   use cases.
"""

# ---- Evaluation configuration ----
OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE

Enable or disable GenAI evaluations. Accepted values (case-insensitive):

* ``true`` / ``1`` / ``yes``: Enable evaluations
* ``false`` / ``0`` / ``no`` (default): Disable evaluations

If disabled, calls to ``TelemetryHandler.evaluate_llm`` will return an empty list without invoking evaluators.
"""

OTEL_INSTRUMENTATION_GENAI_EVALUATORS = "OTEL_INSTRUMENTATION_GENAI_EVALUATORS"
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATORS

Comma-separated list of evaluator names to run (e.g. ``deepeval,sentiment``). If not provided
and explicit names are not passed to ``evaluate_llm``, no evaluators are run.
"""

OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE

Controls creation of evaluation spans. Accepted values:

* ``off`` (default): No evaluation spans are created.
* ``aggregated``: A single span summarizing all evaluator results (implemented).
* ``per_metric``: One span per evaluation metric (implemented).
"""

OTEL_INSTRUMENTATION_GENAI_GENERATOR = "OTEL_INSTRUMENTATION_GENAI_GENERATOR"
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_GENERATOR

Select telemetry generator strategy. Accepted values (case-insensitive):

* ``span`` (default) - spans only (SpanGenerator)
* ``span_metric`` - spans + metrics (SpanMetricGenerator)
* ``span_metric_event`` - spans + metrics + events (SpanMetricEventGenerator)

Invalid or unset values fallback to ``span``.
"""

__all__ = [
    # existing
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK",
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH",
    # evaluation
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE",
    "OTEL_INSTRUMENTATION_GENAI_EVALUATORS",
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE",
    # generator selection
    "OTEL_INSTRUMENTATION_GENAI_GENERATOR",
]
